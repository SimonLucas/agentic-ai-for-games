import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from pcg.maze.agentic_generator import _result_data
from pcg.maze.model import Maze, evaluate_maze
from pcg.maze.workshop import MazeWorkshop, minimum_wall_path


def maze(*rows: str) -> Maze:
    return Maze(
        width=len(rows[0]),
        height=len(rows),
        walls=tuple(cell == "#" for row in rows for cell in row),
    )


def configured_workshop() -> MazeWorkshop:
    workshop = MazeWorkshop()
    initial = maze(
        ".##.",
        "####",
        "####",
        ".##.",
    )
    library = [Maze.open(4, 4), maze("....", ".##.", "....", ".##.")]
    workshop.configure(
        initial.model_dump(mode="json"),
        [item.model_dump(mode="json") for item in library],
        seed=7,
        max_batch_size=8,
    )
    return workshop


def test_repair_carves_a_minimum_wall_route_and_requires_adoption() -> None:
    workshop = configured_workshop()
    before = workshop.current

    repaired = workshop.repair()

    assert workshop.current == before
    assert repaired["connected"]
    assert repaired["carved_walls"] == 4
    adopted = workshop.adopt(repaired["candidate_id"])
    assert adopted["current"]["connected"]
    assert evaluate_maze(workshop.current).fitness == 6


def test_minimum_wall_path_has_valid_orthogonal_steps() -> None:
    source = configured_workshop().current

    path = minimum_wall_path(source)

    assert path[0] == source.start
    assert path[-1] == source.goal
    assert all(
        abs(left[0] - right[0]) + abs(left[1] - right[1]) == 1
        for left, right in zip(path, path[1:])
    )


def test_local_and_macro_batches_are_seeded_proposals() -> None:
    first = configured_workshop()
    second = configured_workshop()

    local_first = first.mutate_batch(5, 2)
    local_second = second.mutate_batch(5, 2)
    macro_first = first.macro_mutation_batch(5, 2, 3)
    macro_second = second.macro_mutation_batch(5, 2, 3)

    assert local_first == local_second
    assert macro_first == macro_second
    assert len(local_first["candidates"]) == 5
    assert len(macro_first["candidates"]) == 5
    for candidate in local_first["candidates"] + macro_first["candidates"]:
        assert candidate["rows"][0][0] == "."
        assert candidate["rows"][-1][-1] == "."


def test_adoption_discards_stale_candidate_ids_and_caps_batches() -> None:
    workshop = configured_workshop()
    first = workshop.repair()
    second = workshop.repair()
    workshop.adopt(first["candidate_id"])

    with pytest.raises(ValueError, match="unknown candidate"):
        workshop.adopt(second["candidate_id"])
    with pytest.raises(ValueError, match="batch_size"):
        workshop.mutate_batch(9, 1)


def test_disconnected_candidate_must_be_repaired_before_adoption() -> None:
    workshop = configured_workshop()
    disconnected = workshop._candidate(workshop.current)

    with pytest.raises(ValueError, match="repair it first"):
        workshop.adopt(disconnected["candidate_id"])


def test_real_mcp_workshop_discovers_and_invokes_tools() -> None:
    async def run() -> None:
        server = StdioServerParameters(
            command=sys.executable, args=["-m", "pcg.maze.agentic_server"]
        )
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert names == {
                    "configure",
                    "export",
                    "status",
                    "mutate_batch",
                    "macro_mutation_batch",
                    "repair",
                    "adopt",
                }
                open_maze = Maze.open(4, 4).model_dump(mode="json")
                configured = _result_data(await session.call_tool("configure", {
                    "initial": open_maze,
                    "library": [open_maze],
                    "seed": 3,
                    "max_batch_size": 4,
                }))
                assert configured["ready"]
                batch = _result_data(await session.call_tool(
                    "mutate_batch", {"batch_size": 2, "expected_mutations": 1}
                ))
                candidate_id = batch["candidates"][0]["candidate_id"]
                adopted = _result_data(await session.call_tool(
                    "adopt", {"candidate_id": candidate_id}
                ))
                assert adopted["adopted"] == candidate_id
                exported = _result_data(await session.call_tool("export", {}))
                assert len(exported["adoptions"]) == 1

    asyncio.run(run())
