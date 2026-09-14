from pydantic import ValidationError
import pytest

from pcg.maze import Maze, evaluate_maze, shortest_path


def maze_from_rows(*rows: str) -> Maze:
    return Maze(
        width=len(rows[0]),
        height=len(rows),
        walls=tuple(cell == "#" for row in rows for cell in row),
    )


def test_breadth_first_search_finds_a_shortest_path() -> None:
    maze = maze_from_rows(
        "...#",
        "##.#",
        "....",
    )

    path = shortest_path(maze)

    assert path is not None
    assert path[0] == (0, 0)
    assert path[-1] == (3, 2)
    assert len(path) - 1 == 5
    assert all(not maze.is_wall(cell) for cell in path)


def test_disconnected_maze_has_explicit_negative_fitness() -> None:
    maze = maze_from_rows(
        ".#",
        "#.",
    )

    evaluation = evaluate_maze(maze)

    assert evaluation.fitness == -1
    assert evaluation.path == ()
    assert not evaluation.connected


def test_maze_rejects_a_blocked_endpoint() -> None:
    with pytest.raises(ValidationError, match="start and goal must be passages"):
        maze_from_rows(
            "#.",
            "..",
        )
