import asyncio
import copy
import json
from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletion

from game_agent.llm_backend import connection, generation_options
from game_agent.griddle import CardDeck, FlatLetterGrid, ForwardModelGriddle, GriddleState, TrieDict
from game_agent.griddle.llm_agent import LLMAgent, LLMAgentParams, SYSTEM_PROMPT, parse_move, position_prompt


def response(content=None, calls=None):
    return ChatCompletion.model_validate({
        "id": "test", "object": "chat.completion", "created": 0, "model": "test/model",
        "choices": [{"index": 0, "finish_reason": "tool_calls" if calls else "stop",
                     "message": {"role": "assistant", "content": content, "tool_calls": calls}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25, "cost": 0.001},
    })


def tool(name="mcs_advice", arguments="{}", ident="call1"):
    return {"id": ident, "type": "function", "function": {"name": name, "arguments": arguments}}


class FakeClient:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        return next(self.replies)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakeSession:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return SimpleNamespace(isError=False, structuredContent={"recommended_index": 2, "total_rollouts": 40})


def params(**kwargs):
    return LLMAgentParams(backend="ollama", model="test/model", **kwargs)


def model():
    return ForwardModelGriddle.new_game(2, seed=5, trie_dict=TrieDict(["AT"]))


@pytest.mark.parametrize("backend,key,endpoint", [
    ("openai", "openai-test", "https://api.openai.com/v1"),
    ("openrouter", "router-test", "https://openrouter.ai/api/v1"),
    ("ollama", "ollama", "http://localhost:11434/v1"),
])
def test_provider_routing_and_key_isolation(monkeypatch, backend, key, endpoint):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-test")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    settings = LLMAgentParams(backend=backend, model="example")
    assert connection(settings)["api_key"] == key
    assert connection(settings)["base_url"] == endpoint
    assert "api_key" not in settings.model_dump()
    assert "openai-test" not in settings.model_dump_json()
    assert "router-test" not in settings.model_dump_json()


def test_missing_credentials_fail_before_network(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        LLMAgent(LLMAgentParams(backend="openrouter", model="example"), 1)


def test_optional_generation_parameters_and_endpoint():
    settings = params(temperature=None, reasoning_effort="low", base_url="http://localhost:9999/v1")
    options = generation_options(settings)
    assert "temperature" not in options
    assert options["reasoning_effort"] == "low"
    assert options["max_tokens"] == settings.max_output_tokens
    assert connection(settings)["base_url"] == "http://localhost:9999/v1"


@pytest.mark.parametrize("text", ['{"index":true}', '{"index":"0"}', '{"index":4}',
                                   'index 0', '{"index":0,"extra":"x"}', None])
def test_invalid_moves_are_not_coerced_or_guessed(text):
    with pytest.raises(ValueError):
        parse_move(text, [0, 1, 2, 3])


def test_no_tool_arm_never_starts_mcp_or_sends_tool_schemas(monkeypatch):
    import game_agent.griddle.llm_agent as module
    client = FakeClient([response('{"index":2}')])
    monkeypatch.setattr(module, "AsyncOpenAI", lambda **kwargs: client)
    monkeypatch.setattr(module, "stdio_client", lambda *args: pytest.fail("MCP must not start"))
    agent = LLMAgent(params(), 3)
    game = model()
    assert agent.get_action(game) == 2
    assert "tools" not in client.requests[0]
    assert client.requests[0]["messages"] == [
        {"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": position_prompt(game)}]
    assert agent.metrics["tool_calls"] == 0
    assert agent.metrics["model_calls"] == 1
    assert agent.metrics["prompt_tokens"] == 20
    assert agent.metrics["reported_cost_usd"] == 0.001


def test_optional_tool_is_not_forced_and_final_answer_remains_llm_choice():
    agent = LLMAgent(params(tools=["mcs_advice"]), 3)
    client = FakeClient([response(calls=[tool()]), response('{"index":1}')])
    session = FakeSession()
    index = asyncio.run(agent._decision_loop(model(), client, session, [{"type": "function"}]))
    assert index == 1  # Tool recommended 2; the host does not override the LLM.
    assert session.calls == [("mcs_advice", {"rollouts_per_square": 10})]
    assert client.requests[0]["tool_choice"] == "auto"
    assert any(m["role"] == "tool" for m in client.requests[1]["messages"])
    assert agent.metrics["simulated_rollouts"] == 40


def test_tool_budget_applies_to_parallel_calls_and_forces_final_answer():
    agent = LLMAgent(params(tools=["mcs_advice"], max_tool_calls_per_move=1), 3)
    client = FakeClient([response(calls=[tool(), tool(ident="call2")]), response('{"index":2}')])
    session = FakeSession()
    assert asyncio.run(agent._decision_loop(model(), client, session, [{}])) == 2
    assert len(session.calls) == 1
    assert client.requests[1]["tool_choice"] == "none"
    assert agent.metrics["tool_errors"] == 1


def test_unadvertised_tool_cannot_configure_or_mutate_server():
    agent = LLMAgent(params(tools=["rollout"]), 3)
    session = FakeSession()
    client = FakeClient([response(calls=[tool(name="configure")]), response('{"index":0}')])
    assert asyncio.run(agent._decision_loop(model(), client, session, [{}])) == 0
    assert session.calls == []
    assert agent.metrics["tool_errors"] == 1


def test_invalid_move_is_retried_and_exhaustion_has_no_silent_fallback():
    agent = LLMAgent(params(max_model_calls_per_move=2), 3)
    client = FakeClient([response('{"index":99}'), response('{"index":1}')])
    assert asyncio.run(agent._decision_loop(model(), client, None, [])) == 1
    assert agent.metrics["invalid_moves"] == 1
    failed = LLMAgent(params(max_model_calls_per_move=2), 3)
    with pytest.raises(RuntimeError, match="no fallback"):
        asyncio.run(failed._decision_loop(model(), FakeClient([response("bad"), response("bad")]), None, []))


def test_last_square_is_forced_without_llm_call(monkeypatch):
    game = model()
    for _ in range(3):
        game.act(0)
    agent = LLMAgent(params(tools=["mcs_advice"]), 3)
    monkeypatch.setattr(agent, "_choose", lambda game: pytest.fail("unnecessary model call"))
    assert agent.get_action(game) == 0
    assert agent.metrics["forced_moves"] == 1


def test_tool_enabled_agent_full_mcp_bridge(monkeypatch):
    import game_agent.griddle.llm_agent as module
    client = FakeClient([response(calls=[tool()]), response('{"index":1}')])
    monkeypatch.setattr(module, "AsyncOpenAI", lambda **kwargs: client)
    game = ForwardModelGriddle(
        GriddleState(FlatLetterGrid(2, tuple("A   ")), CardDeck(tuple("XY")), "T"), TrieDict(["AT"]))
    before = game.state
    agent = LLMAgent(params(tools=["mcs_advice"], max_rollouts_per_call=3), 3)
    assert agent.get_action(game) == 0  # Absolute cell 1 is the first empty cell.
    assert game.state == before
    assert {tool["function"]["name"] for tool in client.requests[0]["tools"]} == {"mcs_advice"}
    assert agent.metrics["simulated_rollouts"] == 9
    assert agent.metrics["tool_errors"] == 0


def test_failed_api_attempt_is_metered_and_credentials_are_redacted(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "private-test-key")
    agent = LLMAgent(LLMAgentParams(backend="openrouter", model="test"), 3)

    class FailingClient(FakeClient):
        async def create(self, **kwargs):
            raise RuntimeError("bad private-test-key")

    with pytest.raises(RuntimeError, match=r"bad \[REDACTED\]"):
        asyncio.run(agent._decision_loop(model(), FailingClient([]), None, []))
    assert agent.metrics["model_calls"] == 1
    assert agent.metrics["model_errors"] == 1
    assert agent.metrics["cost_missing_calls"] == 1
    assert "private-test-key" not in json.dumps(agent.get_metrics())


def test_persistent_game_reuses_clients_updates_positions_and_closes(monkeypatch):
    import game_agent.griddle.llm_agent as module

    class AdviceClient(FakeClient):
        closed = False

        async def create(self, **kwargs):
            self.requests.append(copy.deepcopy(kwargs))
            messages = kwargs["messages"]
            if messages[-1]["role"] == "tool":
                data = json.loads(messages[-1]["content"])
                assert "_search_seconds" not in data
                return response(json.dumps({"index": data["recommended_index"]}))
            return response(calls=[tool()])

        async def __aexit__(self, *args):
            self.closed = True

    client = AdviceClient([])
    starts = []

    def factory(**kwargs):
        starts.append(1)
        return client

    monkeypatch.setattr(module, "AsyncOpenAI", factory)
    agent = LLMAgent(params(tools=["mcs_advice"], max_rollouts_per_call=3), 3)
    game = model()

    async def play():
        async with agent.game_session():
            session = agent._session
            while not game.is_terminal():
                game.act(await agent.get_action_async(game))
                assert agent._session is session

    asyncio.run(play())
    assert len(starts) == 1
    assert client.closed
    assert agent._session is None and not agent._active
    assert agent.metrics["mcp_process_starts"] == 1
    assert agent.metrics["http_client_starts"] == 1
    assert agent.metrics["model_calls"] == 6
    assert agent.metrics["tool_calls"] == 3
    assert agent.metrics["search_seconds"] > 0
    assert agent.metrics["tool_rpc_seconds"] >= agent.metrics["search_seconds"]
    assert agent.metrics["simulated_rollouts"] == (4 + 3 + 2) * 3


def test_persistent_client_cleanup_on_error(monkeypatch):
    import game_agent.griddle.llm_agent as module
    closed = []

    class ClosingClient(FakeClient):
        async def __aexit__(self, *args):
            closed.append(True)

    client = ClosingClient([])
    monkeypatch.setattr(module, "AsyncOpenAI", lambda **kwargs: client)
    agent = LLMAgent(params(tools=["mcs_advice"]), 3)

    async def fail():
        async with agent.game_session():
            raise RuntimeError("test failure")

    with pytest.raises(RuntimeError, match="test failure"):
        asyncio.run(fail())
    assert closed == [True]
    assert agent._session is None and agent._client is None and not agent._active


def test_prompt_version_is_logged_and_identical_across_tool_conditions():
    prompts = []
    for tools in ([], ["mcs_advice"]):
        agent = LLMAgent(params(prompt_version="strategy-v2", tools=tools), 3)
        client = FakeClient([response('{"index":0}')])
        asyncio.run(agent._decision_loop(model(), client, None, []))
        actual = client.requests[0]["messages"][0]["content"]
        assert actual == agent.metrics["system_prompt"]
        assert agent.metrics["prompt_version"] == "strategy-v2"
        prompts.append(actual)
    assert prompts[0] == prompts[1]
    assert prompts[0] != SYSTEM_PROMPT
