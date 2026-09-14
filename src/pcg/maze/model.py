"""Maze representation and shortest-path fitness."""

from __future__ import annotations

from collections import deque

from pydantic import BaseModel, ConfigDict, Field, model_validator

Cell = tuple[int, int]


class Maze(BaseModel):
    """An immutable rectangular grid in row-major order.

    ``True`` cells are walls and ``False`` cells are passages.
    """

    model_config = ConfigDict(frozen=True)

    width: int = Field(ge=2)
    height: int = Field(ge=2)
    walls: tuple[bool, ...]
    start: Cell = (0, 0)
    goal: Cell | None = None

    @model_validator(mode="after")
    def validate_grid(self) -> "Maze":
        if self.goal is None:
            object.__setattr__(self, "goal", (self.width - 1, self.height - 1))
        if len(self.walls) != self.width * self.height:
            raise ValueError("walls must contain exactly width * height cells")
        if not self.contains(self.start) or not self.contains(self.goal):
            raise ValueError("start and goal must be inside the maze")
        if self.is_wall(self.start) or self.is_wall(self.goal):
            raise ValueError("start and goal must be passages")
        return self

    @classmethod
    def open(cls, width: int, height: int) -> "Maze":
        return cls(width=width, height=height, walls=(False,) * (width * height))

    def contains(self, cell: Cell) -> bool:
        x, y = cell
        return 0 <= x < self.width and 0 <= y < self.height

    def index(self, cell: Cell) -> int:
        x, y = cell
        return x + y * self.width

    def is_wall(self, cell: Cell) -> bool:
        return self.walls[self.index(cell)]

    def neighbours(self, cell: Cell):
        x, y = cell
        for neighbour in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)):
            if self.contains(neighbour) and not self.is_wall(neighbour):
                yield neighbour


class MazeEvaluation(BaseModel):
    """The score and supporting evidence for one maze."""

    model_config = ConfigDict(frozen=True)

    fitness: int
    path: tuple[Cell, ...] = ()

    @property
    def connected(self) -> bool:
        return bool(self.path)


def shortest_path(maze: Maze) -> tuple[Cell, ...] | None:
    """Return a shortest start-to-goal path using breadth-first search."""

    queue = deque([maze.start])
    previous: dict[Cell, Cell | None] = {maze.start: None}

    while queue:
        current = queue.popleft()
        if current == maze.goal:
            break
        for neighbour in maze.neighbours(current):
            if neighbour not in previous:
                previous[neighbour] = current
                queue.append(neighbour)

    if maze.goal not in previous:
        return None

    path: list[Cell] = []
    current: Cell | None = maze.goal
    while current is not None:
        path.append(current)
        current = previous[current]
    path.reverse()
    return tuple(path)


def evaluate_maze(maze: Maze) -> MazeEvaluation:
    """Maximise the shortest-path length; disconnected mazes score -1."""

    path = shortest_path(maze)
    if path is None:
        return MazeEvaluation(fitness=-1)
    return MazeEvaluation(fitness=len(path) - 1, path=path)
