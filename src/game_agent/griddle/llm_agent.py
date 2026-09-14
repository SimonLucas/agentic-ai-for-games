"""One LLM policy, with optional MCP advice and bounded per-move work."""

import asyncio
from collections import Counter
from contextlib import AsyncExitStack, asynccontextmanager
import copy
from datetime import timedelta
import json
from importlib.resources import files
import random
import sys
import time
from typing import Annotated, Literal

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, StrictInt, TypeAdapter, model_validator

from game_agent.llm_backend import LLMBackendParams, connection, generation_options
from .forward_model import ForwardModelGriddle, GriddleState

ToolName = Literal["mcs_advice", "rollout"]


class LLMAgentParams(LLMBackendParams):
    prompt_version: Literal["rules-v1", "strategy-v2"] = "rules-v1"
    tools: list[ToolName] = Field(default_factory=list)
    max_rollouts_per_call: Annotated[StrictInt, Field(ge=1, le=1000)] = 10
    max_tool_calls_per_move: Annotated[StrictInt, Field(ge=1, le=8)] = 2
    max_model_calls_per_move: Annotated[StrictInt, Field(ge=2, le=12)] = 4

    @model_validator(mode="after")
    def unique_tools(self):
        if len(set(self.tools)) != len(self.tools):
            raise ValueError("tool names must be unique")
        return self


class Move(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: StrictInt


def get_system_prompt(version: str) -> str:
    if version not in {"rules-v1", "strategy-v2"}:
        raise ValueError("unknown prompt version")
    return files(__package__).joinpath(f"prompts/{version}.txt").read_text(encoding="utf-8")


SYSTEM_PROMPT = get_system_prompt("rules-v1")


def position_prompt(model: ForwardModelGriddle) -> str:
    grid = model.state.grid
    return json.dumps({
        "size": grid.size(),
        "rows": ["".join(grid.letters[row * grid.size():(row + 1) * grid.size()]).replace(" ", ".")
                 for row in range(grid.size())],
        "index_rule": "index = row * size + column; row and column are zero-based; '.' means empty",
        "current_letter": model.state.current_letter,
        "legal_indices": grid.get_free_indices(),
        "remaining_letters": dict(sorted(Counter(model.state.deck.cards).items())),
        "current_score": model.score(),
        "current_words": [match.word for match in model.matches()],
    }, separators=(",", ":"))


def parse_move(text: str | None, legal: list[int]) -> int:
    text = (text or "").strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    move = Move.model_validate_json(text)
    if move.index not in legal:
        raise ValueError("index is not an empty cell")
    return move.index


def result_data(result) -> dict:
    if result.isError:
        raise ValueError("; ".join(block.text for block in result.content if hasattr(block, "text")))
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads("".join(block.text for block in result.content if hasattr(block, "text")))


class LLMAgent:
    def __init__(self, params: LLMAgentParams, seed: int):
        self.params = params
        self._prompt = get_system_prompt(params.prompt_version)
        self._connection = connection(params)  # Fail early without opening network connections.
        self._rng = random.Random(seed)
        self._words = None
        self._active = False
        self._client = None
        self._session = None
        self._tools = []
        self._position_configured = False
        self.metrics = {
            "prompt_version": params.prompt_version, "system_prompt": self._prompt,
            "connection_lifetime": "game", "resource_sessions": 0,
            "mcp_process_starts": 0, "http_client_starts": 0,
            "client_setup_seconds": 0.0, "mcp_startup_seconds": 0.0,
            "mcp_position_seconds": 0.0, "api_seconds": 0.0,
            "tool_rpc_seconds": 0.0, "search_seconds": 0.0, "resource_close_seconds": 0.0,
            "model_calls": 0, "model_errors": 0, "tool_calls": 0, "tool_errors": 0, "invalid_moves": 0,
            "forced_moves": 0, "simulated_rollouts": 0, "prompt_tokens": 0,
            "completion_tokens": 0, "usage_missing_calls": 0,
            "reported_cost_usd": 0.0, "cost_missing_calls": 0, "decisions": [],
        }

    def get_metrics(self) -> dict:
        return copy.deepcopy(self.metrics)

    def _legal_or_forced(self, model: ForwardModelGriddle) -> list[int]:
        legal = model.state.grid.get_free_indices()
        if not legal:
            raise ValueError("cannot choose an action in a finished game")
        if len(legal) == 1:
            self.metrics["forced_moves"] += 1
            self.metrics["decisions"].append({"index": legal[0], "forced": True, "events": []})
        return legal

    def get_action(self, model: ForwardModelGriddle) -> int:
        """One-shot compatibility API; benchmarks use the persistent async session."""
        if self._active:
            raise RuntimeError("use get_action_async inside an active game_session")
        legal = self._legal_or_forced(model)
        if len(legal) == 1:
            return 0

        async def single_decision():
            async with self.game_session():
                return await self._choose(model)

        return legal.index(asyncio.run(single_decision()))

    async def get_action_async(self, model: ForwardModelGriddle) -> int:
        if not self._active:
            raise RuntimeError("get_action_async requires an active game_session")
        legal = self._legal_or_forced(model)
        if len(legal) == 1:
            return 0
        return legal.index(await self._choose(model))

    @asynccontextmanager
    async def game_session(self):
        """Own the HTTP client and MCP task groups in one task for an entire game."""
        if self._active:
            raise RuntimeError("this agent already has an active game_session")
        self._active = True
        self.metrics["resource_sessions"] += 1
        stack = AsyncExitStack()
        try:
            start = time.perf_counter()
            self._client = await stack.enter_async_context(AsyncOpenAI(**self._connection))
            self.metrics["http_client_starts"] += 1
            self.metrics["client_setup_seconds"] += time.perf_counter() - start
            if self.params.tools:
                start = time.perf_counter()
                read, write = await stack.enter_async_context(stdio_client(StdioServerParameters(
                    command=sys.executable, args=["-m", "game_agent.griddle.search_server"])))
                self.metrics["mcp_process_starts"] += 1
                self._session = await stack.enter_async_context(ClientSession(
                    read, write, read_timeout_seconds=timedelta(seconds=self.params.timeout_seconds)))
                await self._session.initialize()
                available = await self._session.list_tools()
                for tool in available.tools:
                    if tool.name not in self.params.tools:
                        continue
                    schema = copy.deepcopy(tool.inputSchema)
                    budget = "rollouts_per_square" if tool.name == "mcs_advice" else "rollouts"
                    schema["properties"][budget].update(
                        maximum=self.params.max_rollouts_per_call,
                        default=min(10, self.params.max_rollouts_per_call))
                    self._tools.append({"type": "function", "function": {
                        "name": tool.name, "description": tool.description, "parameters": schema}})
                if {tool["function"]["name"] for tool in self._tools} != set(self.params.tools):
                    raise RuntimeError("MCP server did not advertise the configured tools")
                self.metrics["mcp_startup_seconds"] += time.perf_counter() - start
            yield self
        finally:
            start = time.perf_counter()
            try:
                await stack.aclose()
            finally:
                self.metrics["resource_close_seconds"] += time.perf_counter() - start
                self._client, self._session = None, None
                self._tools = []
                self._words = None
                self._position_configured = False
                self._active = False

    async def _choose(self, model: ForwardModelGriddle) -> int:
        if self._session is not None:
            if self._words is None:
                self._words = model.trie_dict.words()
            arguments = {"state": TypeAdapter(GriddleState).dump_python(model.state, mode="json"),
                         "seed": self._rng.getrandbits(64)}
            if self._position_configured:
                tool = "set_position"
            else:
                tool = "configure"
                arguments.update(words=self._words, max_rollouts=self.params.max_rollouts_per_call)
            start = time.perf_counter()
            try:
                result_data(await self._session.call_tool(tool, arguments))
                self._position_configured = True
            finally:
                self.metrics["mcp_position_seconds"] += time.perf_counter() - start
        return await self._decision_loop(model, self._client, self._session, self._tools)

    async def _decision_loop(self, model, client, session, tools) -> int:
        legal = model.state.grid.get_free_indices()
        messages = [{"role": "system", "content": self._prompt},
                    {"role": "user", "content": position_prompt(model)}]
        trace = {"events": []}
        self.metrics["decisions"].append(trace)
        calls = 0
        for attempt in range(self.params.max_model_calls_per_move):
            options = generation_options(self.params)
            if tools:
                final_request = attempt == self.params.max_model_calls_per_move - 1
                options.update(tools=tools, tool_choice=(
                    "none" if final_request or calls >= self.params.max_tool_calls_per_move else "auto"))
            self.metrics["model_calls"] += 1
            request_start = time.perf_counter()
            try:
                response = await client.chat.completions.create(messages=messages, **options)
            except Exception as exc:
                self.metrics["model_errors"] += 1
                self.metrics["usage_missing_calls"] += 1
                self.metrics["cost_missing_calls"] += 1
                message = str(exc).replace(self._connection["api_key"], "[REDACTED]")
                trace["events"].append({"type": "model_error", "error": message})
                raise RuntimeError(f"{self.params.backend} model request failed: {message}") from None
            finally:
                request_seconds = time.perf_counter() - request_start
                self.metrics["api_seconds"] += request_seconds
            usage = response.usage
            if usage is None:
                self.metrics["usage_missing_calls"] += 1
                self.metrics["cost_missing_calls"] += 1
            else:
                self.metrics["prompt_tokens"] += usage.prompt_tokens or 0
                self.metrics["completion_tokens"] += usage.completion_tokens or 0
                cost = getattr(usage, "cost", None)
                if cost is None:
                    self.metrics["cost_missing_calls"] += 1
                else:
                    self.metrics["reported_cost_usd"] += cost
            if not response.choices:
                raise RuntimeError("LLM returned no choices")
            message = response.choices[0].message
            assistant = message.model_dump(include={"role", "content", "tool_calls"}, exclude_none=True)
            messages.append(assistant)
            trace["events"].append({
                "type": "model", "id": response.id, "model": response.model,
                "elapsed_seconds": request_seconds,
                "system_fingerprint": response.system_fingerprint,
                "finish_reason": response.choices[0].finish_reason,
                "usage": usage.model_dump(mode="json") if usage else None,
                "message": assistant,
            })
            if message.tool_calls:
                for call in message.tool_calls:
                    name = call.function.name
                    error = False
                    arguments = None
                    rpc_seconds, search_seconds = 0.0, 0.0
                    try:
                        if session is None or name not in self.params.tools:
                            raise ValueError("tool is not available in this condition")
                        if calls >= self.params.max_tool_calls_per_move or options.get("tool_choice") == "none":
                            raise ValueError("tool budget exhausted; return a final legal index")
                        calls += 1
                        self.metrics["tool_calls"] += 1
                        arguments = json.loads(call.function.arguments)
                        if not isinstance(arguments, dict):
                            raise ValueError("tool arguments must be an object")
                        budget = "rollouts_per_square" if name == "mcs_advice" else "rollouts"
                        arguments.setdefault(budget, min(10, self.params.max_rollouts_per_call))
                        rpc_start = time.perf_counter()
                        try:
                            data = result_data(await session.call_tool(name, arguments))
                        finally:
                            rpc_seconds = time.perf_counter() - rpc_start
                            self.metrics["tool_rpc_seconds"] += rpc_seconds
                        # Keep timing instrumentation out of the LLM's tool output.
                        search_seconds = data.pop("_search_seconds", 0.0)
                        self.metrics["search_seconds"] += search_seconds
                        self.metrics["simulated_rollouts"] += data.get("total_rollouts", 0)
                    except (ValueError, TypeError) as exc:
                        data, error = {"error": str(exc)}, True
                        self.metrics["tool_errors"] += 1
                    trace["events"].append({"type": "tool", "name": name, "arguments": arguments,
                                             "result": data, "error": error,
                                             "rpc_seconds": rpc_seconds, "search_seconds": search_seconds})
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(data)})
                continue
            try:
                index = parse_move(message.content, legal)
                trace["index"] = index
                return index
            except ValueError:
                self.metrics["invalid_moves"] += 1
                messages.append({"role": "user", "content":
                    f'Invalid move. Return only JSON {{"index": N}} with N in {legal}.'})
        raise RuntimeError("LLM exhausted its per-move request budget without a legal move; no fallback applied")
