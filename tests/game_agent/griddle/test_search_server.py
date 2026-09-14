import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import TypeAdapter
import pytest

from game_agent.griddle import CardDeck, FlatLetterGrid, GriddleState, TrieDict
from game_agent.griddle.llm_agent import result_data
from game_agent.griddle.search_server import SearchContext


def position():
    return GriddleState(FlatLetterGrid(2, tuple("A XY")), CardDeck(()), "T")


def arguments():
    return {"state": TypeAdapter(GriddleState).dump_python(position(), mode="json"),
            "words": ["AT"], "seed": 42, "max_rollouts": 10}


def test_search_advice_uses_exact_dictionary_and_does_not_mutate_position():
    context = SearchContext()
    context.configure(**arguments())
    before = context.model.state
    advice = context.mcs_advice(3)
    assert advice["recommended_index"] == 1
    assert advice["candidates"] == [{"index": 1, "mean_score": 1.0}]
    assert advice["total_rollouts"] == 3
    assert context.rollout(1, 2)["mean_score"] == 1
    assert context.model.state == before
    other = SearchContext()
    other.configure(**{**arguments(), "words": []})
    assert other.rollout(1, 2)["mean_score"] == 0


def test_server_caps_budget_and_rejects_illegal_squares_and_reconfiguration():
    context = SearchContext()
    with pytest.raises(ValueError, match="configure"):
        context.mcs_advice()
    context.configure(**arguments())
    for count in [0, -1, 11, True, 1.5]:
        with pytest.raises(ValueError):
            context.mcs_advice(count)
    for index in [0, -1, True]:
        with pytest.raises(ValueError):
            context.rollout(index)
    with pytest.raises(ValueError, match="already configured"):
        context.configure(**arguments())


def test_trie_export_round_trip():
    trie = TrieDict(["CAT", "AT", "AA"])
    assert TrieDict(trie.words()).words() == ["AA", "AT", "CAT"]


def test_real_mcp_subprocess_discovers_and_invokes_both_tools():
    async def run():
        server = StdioServerParameters(command=sys.executable, args=["-m", "game_agent.griddle.search_server"])
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert names == {"configure", "set_position", "mcs_advice", "rollout"}
                assert result_data(await session.call_tool("configure", arguments())) == {"ready": True}
                assert result_data(await session.call_tool("mcs_advice", {"rollouts_per_square": 2}))["recommended_index"] == 1
                assert result_data(await session.call_tool("rollout", {"index": 1, "rollouts": 2}))["mean_score"] == 1
                rejected = await session.call_tool("mcs_advice", {"rollouts_per_square": 11})
                assert rejected.isError
                new_state = GriddleState(FlatLetterGrid(2, tuple("AXY ")), CardDeck(()), "T")
                result_data(await session.call_tool("set_position", {
                    "state": TypeAdapter(GriddleState).dump_python(new_state, mode="json"), "seed": 42}))
                advice = result_data(await session.call_tool("mcs_advice", {"rollouts_per_square": 2}))
                assert advice["recommended_index"] == 3
                assert advice["candidates"][0]["mean_score"] == 0
    asyncio.run(run())


def test_position_updates_preserve_dictionary_budget_and_match_fresh_server():
    context = SearchContext()
    with pytest.raises(ValueError, match="configure"):
        context.set_position(arguments()["state"], 42)
    context.configure(**arguments())
    dictionary = context.trie
    new_state = GriddleState(FlatLetterGrid(2, tuple("A   ")), CardDeck(tuple("XY")), "T")
    state = TypeAdapter(GriddleState).dump_python(new_state, mode="json")
    context.set_position(state, 17)
    fresh = SearchContext()
    fresh.configure(state, ["AT"], 17, 10)
    actual, expected = context.mcs_advice(3), fresh.mcs_advice(3)
    actual.pop("_search_seconds")
    expected.pop("_search_seconds")
    assert actual == expected
    assert context.trie is dictionary
    with pytest.raises(ValueError):
        context.mcs_advice(11)
