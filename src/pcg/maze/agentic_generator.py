"""LLM controller for the persistent MCP maze workshop."""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
import copy
from datetime import timedelta
import json
from random import Random
import sys
import time
from typing import Annotated, Literal

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from game_agent.llm_backend import LLMBackendParams, connection, generation_options

from .evolution import EvolutionConfig, run_evolution
from .llm_generator import maze_text
from .model import Maze, evaluate_maze

ToolName = Literal[
    "status",
    "mutate_batch",
    "macro_mutation_batch",
    "repair",
    "adopt",
]

SYSTEM_PROMPT = """You are controlling a procedural maze workshop through tools.
Your goal is to finish with a playable, high-fitness maze that differs from the
earlier mazes in the requested set. Fitness is the shortest four-directional
route from the top-left start to the bottom-right goal; larger is better.

Use status to inspect the incumbent. mutate_batch makes small changes.
macro_mutation_batch copies rectangular structure from evolved library mazes.
Both return scored candidate IDs but change nothing. repair creates a connected
candidate by carving a minimum-wall route. adopt is the only way to replace the
incumbent. Compare fitness and grids before adopting. Retain connectivity, try
more than one operator when budget permits, and do not adopt a lower-fitness
candidate unless repairing an invalid incumbent.

Repair only disconnected candidates; it cannot improve a connected candidate.
If a batch has a connected fitness improvement, adopt the best one. If it has
only equal-fitness connected candidates, adopt a structurally different one as
a neutral stepping stone, then generate another batch. Fitness often improves
only after several neutral changes.

Call exactly one tool per response. These operations share workshop state and
must be performed sequentially. Wait for each tool result before choosing the
next operation.

When satisfied, return only {"finish":true}. The host exports the incumbent.
Do not print a maze yourself."""


class AgenticMazeParams(LLMBackendParams):
    prompt_version: Literal["workshop-v1"] = "workshop-v1"
    tools: list[ToolName] = Field(default_factory=lambda: [
        "status", "mutate_batch", "macro_mutation_batch", "repair", "adopt"
    ])
    max_tool_calls: Annotated[StrictInt, Field(ge=1, le=20)] = 8
    max_model_calls: Annotated[StrictInt, Field(ge=2, le=24)] = 10
    max_batch_size: Annotated[StrictInt, Field(ge=1, le=64)] = 24
    library_size: Annotated[StrictInt, Field(ge=1, le=32)] = 6
    library_iterations: Annotated[StrictInt, Field(ge=0, le=20_000)] = 400
    library_expected_mutations: float = Field(default=5.0, gt=0)
    initial_source: Literal["open", "random", "library"] = "library"
    initial_wall_probability: float = Field(default=0.28, ge=0, le=1)

    @model_validator(mode="after")
    def validate_tools(self) -> "AgenticMazeParams":
        if len(set(self.tools)) != len(self.tools):
            raise ValueError("tool names must be unique")
        if "adopt" not in self.tools:
            raise ValueError("agentic maze tools must include adopt")
        return self


class Finish(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finish: Literal[True]


class AgenticMazeError(RuntimeError):
    def __init__(self, message: str, metrics: dict, rows: list[str] | None = None):
        super().__init__(message)
        self.metrics = metrics
        self.rows = rows


def _result_data(result) -> dict:
    if result.isError:
        raise ValueError(
            "; ".join(block.text for block in result.content if hasattr(block, "text"))
        )
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(
        "".join(block.text for block in result.content if hasattr(block, "text"))
    )


def _initial_maze(width: int, height: int, probability: float, random: Random) -> Maze:
    walls = [random.random() < probability for _ in range(width * height)]
    walls[0] = walls[-1] = False
    return Maze(width=width, height=height, walls=tuple(walls))


def build_library(
    width: int,
    height: int,
    random: Random,
    params: AgenticMazeParams,
) -> list[Maze]:
    return [
        run_evolution(EvolutionConfig(
            width=width,
            height=height,
            iterations=params.library_iterations,
            expected_mutations=params.library_expected_mutations,
            seed=random.getrandbits(63),
        )).final.maze
        for _ in range(params.library_size)
    ]


class AgenticMazeGenerator:
    """Reuse one model client and MCP process across a generated maze set."""

    def __init__(self, params: AgenticMazeParams):
        self.params = params
        self._connection = connection(params)
        self._active = False
        self._client = None
        self._session = None
        self._tool_definitions: list[dict] = []
        self._generation_count = 0

    @asynccontextmanager
    async def generation_session(self):
        if self._active:
            raise RuntimeError("this generator already has an active session")
        self._active = True
        stack = AsyncExitStack()
        try:
            self._client = await stack.enter_async_context(
                AsyncOpenAI(**self._connection)
            )
            read, write = await stack.enter_async_context(stdio_client(
                StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "pcg.maze.agentic_server"],
                )
            ))
            self._session = await stack.enter_async_context(ClientSession(
                read,
                write,
                read_timeout_seconds=timedelta(seconds=self.params.timeout_seconds),
            ))
            await self._session.initialize()
            available = await self._session.list_tools()
            for tool in available.tools:
                if tool.name not in self.params.tools:
                    continue
                schema = copy.deepcopy(tool.inputSchema)
                if "batch_size" in schema.get("properties", {}):
                    schema["properties"]["batch_size"].update(
                        maximum=self.params.max_batch_size,
                        default=min(12, self.params.max_batch_size),
                    )
                self._tool_definitions.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": schema,
                    },
                })
            found = {tool["function"]["name"] for tool in self._tool_definitions}
            if found != set(self.params.tools):
                raise RuntimeError("MCP server did not advertise every configured tool")
            yield self
        finally:
            await stack.aclose()
            self._client = self._session = None
            self._tool_definitions.clear()
            self._generation_count = 0
            self._active = False

    async def generate(
        self,
        *,
        width: int,
        height: int,
        seed: int,
        previous_maze_texts: list[str],
    ) -> tuple[Maze, dict]:
        if not self._active or self._client is None or self._session is None:
            raise RuntimeError("generate requires an active generation_session")
        random = Random(seed)
        setup_start = time.perf_counter()
        library = build_library(width, height, random, self.params)
        if self.params.initial_source == "library":
            initial = library[0]
        elif self.params.initial_source == "open":
            initial = Maze.open(width, height)
        else:
            initial = _initial_maze(
                width, height, self.params.initial_wall_probability, random
            )
        configured = _result_data(await self._session.call_tool("configure", {
            "initial": initial.model_dump(mode="json"),
            "library": [maze.model_dump(mode="json") for maze in library],
            "seed": random.getrandbits(63),
            "max_batch_size": self.params.max_batch_size,
        }))
        setup_seconds = time.perf_counter() - setup_start
        previous = "\n\n".join(
            f"Previous final maze {index + 1}:\n{text}"
            for index, text in enumerate(previous_maze_texts)
        ) or "There are no earlier final mazes in this set."
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Create maze {len(previous_maze_texts) + 1} for diversity seed {seed}.\n"
                f"Dimensions: {width} columns by {height} rows.\n"
                f"Initial workshop state: {json.dumps(configured, separators=(',', ':'))}\n\n"
                f"{previous}"
            )},
        ]
        metrics = {
            "prompt_version": self.params.prompt_version,
            "system_prompt": SYSTEM_PROMPT,
            "connection_lifetime": "maze set",
            "mcp_process_starts": 1 if self._generation_count == 0 else 0,
            "http_client_starts": 1 if self._generation_count == 0 else 0,
            "model_calls": 0,
            "tool_calls": 0,
            "tool_errors": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "setup_seconds": setup_seconds,
            "initial_fitness": configured["current"]["fitness"],
            "api_seconds": 0.0,
            "tool_seconds": 0.0,
            "events": [],
        }
        self._generation_count += 1
        tool_calls = 0
        for attempt in range(self.params.max_model_calls):
            final_request = (
                attempt == self.params.max_model_calls - 1
                or tool_calls >= self.params.max_tool_calls
            )
            options = generation_options(self.params)
            options.update(
                tools=self._tool_definitions,
                tool_choice="none" if final_request else "auto",
                parallel_tool_calls=False,
            )
            metrics["model_calls"] += 1
            start = time.perf_counter()
            try:
                response = await self._client.chat.completions.create(
                    messages=messages, **options
                )
            except Exception as error:
                message = str(error).replace(self._connection["api_key"], "[REDACTED]")
                raise AgenticMazeError(
                    f"{self.params.backend} request failed: {message}", metrics
                ) from None
            elapsed = time.perf_counter() - start
            metrics["api_seconds"] += elapsed
            if not response.choices:
                raise AgenticMazeError("LLM returned no choices", metrics)
            usage = response.usage
            if usage:
                metrics["prompt_tokens"] += usage.prompt_tokens or 0
                metrics["completion_tokens"] += usage.completion_tokens or 0
            message = response.choices[0].message
            assistant = message.model_dump(
                include={"role", "content", "tool_calls"}, exclude_none=True
            )
            messages.append(assistant)
            metrics["events"].append({
                "type": "model",
                "response_id": response.id,
                "model": response.model,
                "finish_reason": response.choices[0].finish_reason,
                "elapsed_seconds": elapsed,
                "message": assistant,
            })
            if message.tool_calls:
                for call_index, call in enumerate(message.tool_calls):
                    name = call.function.name
                    error = False
                    arguments = None
                    try:
                        if call_index > 0:
                            raise ValueError(
                                "stateful maze tools must be called one per response"
                            )
                        if name not in self.params.tools:
                            raise ValueError("tool is not enabled")
                        if tool_calls >= self.params.max_tool_calls:
                            raise ValueError("tool-call budget exhausted")
                        arguments = json.loads(call.function.arguments)
                        if not isinstance(arguments, dict):
                            raise ValueError("tool arguments must be an object")
                        tool_calls += 1
                        metrics["tool_calls"] += 1
                        start = time.perf_counter()
                        try:
                            data = _result_data(
                                await self._session.call_tool(name, arguments)
                            )
                        finally:
                            metrics["tool_seconds"] += time.perf_counter() - start
                    except (ValueError, TypeError) as exception:
                        error = True
                        data = {"error": str(exception)}
                        metrics["tool_errors"] += 1
                    metrics["events"].append({
                        "type": "tool",
                        "name": name,
                        "arguments": arguments,
                        "result": data,
                        "error": error,
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(data, separators=(",", ":")),
                    })
                continue
            try:
                Finish.model_validate_json(message.content or "")
                exported = _result_data(await self._session.call_tool("export", {}))
                rows = exported["current"]["rows"]
                maze = Maze(
                    width=width,
                    height=height,
                    walls=tuple(cell == "#" for row in rows for cell in row),
                )
                if not evaluate_maze(maze).connected:
                    raise AgenticMazeError(
                        "agent finished with a disconnected maze", metrics, rows
                    )
                metrics["adoptions"] = exported["adoptions"]
                metrics["final_fitness"] = exported["current"]["fitness"]
                return maze, metrics
            except AgenticMazeError:
                raise
            except ValueError:
                messages.append({
                    "role": "user",
                    "content": 'Use another tool, or finish with only {"finish":true}.',
                })
        exported = _result_data(await self._session.call_tool("export", {}))
        raise AgenticMazeError(
            "model-call budget exhausted before a valid finish response",
            metrics,
            exported.get("current", {}).get("rows"),
        )
