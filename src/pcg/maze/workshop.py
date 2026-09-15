"""Stateful maze-editing operations exposed by the agentic MCP server."""

from __future__ import annotations

from collections import deque
from random import Random

from .llm_generator import maze_text
from .model import Cell, Maze, evaluate_maze


class MazeWorkshop:
    """Own an incumbent, a maze library, and a temporary candidate pool."""

    def __init__(self):
        self.current: Maze | None = None
        self.library: tuple[Maze, ...] = ()
        self.random = Random(0)
        self.max_batch_size = 0
        self.candidates: dict[str, Maze] = {}
        self.next_candidate = 1
        self.history: list[dict] = []

    def configure(
        self,
        initial: dict,
        library: list[dict],
        seed: int,
        max_batch_size: int,
    ) -> dict:
        if type(max_batch_size) is not int or not 1 <= max_batch_size <= 64:
            raise ValueError("max_batch_size must be between 1 and 64")
        current = Maze.model_validate(initial)
        mazes = tuple(Maze.model_validate(item) for item in library)
        if not mazes:
            raise ValueError("maze library must not be empty")
        if any(
            maze.width != current.width or maze.height != current.height
            for maze in mazes
        ):
            raise ValueError("every library maze must match the current dimensions")
        self.current = current
        self.library = mazes
        self.random = Random(seed)
        self.max_batch_size = max_batch_size
        self.candidates.clear()
        self.next_candidate = 1
        self.history.clear()
        return {"ready": True, "library_size": len(mazes), **self.status()}

    def _require_current(self) -> Maze:
        if self.current is None:
            raise ValueError("configure the workshop before using maze tools")
        return self.current

    def _validate_batch(self, batch_size: int) -> None:
        self._require_current()
        if type(batch_size) is not int or not 1 <= batch_size <= self.max_batch_size:
            raise ValueError(f"batch_size must be between 1 and {self.max_batch_size}")

    def _candidate(self, maze: Maze) -> dict:
        candidate_id = f"c{self.next_candidate}"
        self.next_candidate += 1
        self.candidates[candidate_id] = maze
        return self._description(maze, candidate_id=candidate_id)

    @staticmethod
    def _description(maze: Maze, *, candidate_id: str | None = None) -> dict:
        evaluation = evaluate_maze(maze)
        description = {
            "fitness": evaluation.fitness,
            "connected": evaluation.connected,
            "wall_fraction": round(sum(maze.walls) / len(maze.walls), 4),
            "rows": maze_text(maze).splitlines(),
        }
        if candidate_id is not None:
            description["candidate_id"] = candidate_id
        return description

    def status(self) -> dict:
        return {"current": self._description(self._require_current())}

    def mutate_batch(self, batch_size: int = 12, expected_mutations: float = 5.0) -> dict:
        self._validate_batch(batch_size)
        current = self._require_current()
        mutable_cells = len(current.walls) - 2
        if not 0 < expected_mutations <= mutable_cells:
            raise ValueError(
                f"expected_mutations must be greater than 0 and at most {mutable_cells}"
            )
        probability = expected_mutations / mutable_cells
        generated = []
        for _ in range(batch_size):
            walls = list(current.walls)
            for index in range(1, len(walls) - 1):
                if self.random.random() < probability:
                    walls[index] = not walls[index]
            generated.append(self._candidate(current.model_copy(update={"walls": tuple(walls)})))
        ranked = sorted(
            generated,
            key=lambda item: (item["connected"], item["fitness"]),
            reverse=True,
        )
        return {
            "operator": "local_mutation",
            "generated": batch_size,
            "current_fitness": evaluate_maze(current).fitness,
            "candidates": ranked[: min(8, len(ranked))],
        }

    def macro_mutation_batch(
        self,
        batch_size: int = 12,
        min_block_size: int = 2,
        max_block_size: int = 5,
    ) -> dict:
        self._validate_batch(batch_size)
        current = self._require_current()
        limit = min(current.width, current.height)
        if not 1 <= min_block_size <= max_block_size <= limit:
            raise ValueError(
                f"block sizes must satisfy 1 <= min <= max <= {limit}"
            )
        generated = []
        for _ in range(batch_size):
            source = self.random.choice(self.library)
            block_width = self.random.randint(
                min_block_size, min(max_block_size, current.width)
            )
            block_height = self.random.randint(
                min_block_size, min(max_block_size, current.height)
            )
            source_x = self.random.randint(0, current.width - block_width)
            source_y = self.random.randint(0, current.height - block_height)
            target_x = self.random.randint(0, current.width - block_width)
            target_y = self.random.randint(0, current.height - block_height)
            walls = list(current.walls)
            for dy in range(block_height):
                for dx in range(block_width):
                    source_index = source.index((source_x + dx, source_y + dy))
                    target_index = current.index((target_x + dx, target_y + dy))
                    walls[target_index] = source.walls[source_index]
            walls[current.index(current.start)] = False
            walls[current.index(current.goal)] = False
            candidate = current.model_copy(update={"walls": tuple(walls)})
            description = self._candidate(candidate)
            description["block"] = {
                "size": [block_width, block_height],
                "source": [source_x, source_y],
                "target": [target_x, target_y],
            }
            generated.append(description)
        ranked = sorted(
            generated,
            key=lambda item: (item["connected"], item["fitness"]),
            reverse=True,
        )
        return {
            "operator": "library_block_copy",
            "generated": batch_size,
            "current_fitness": evaluate_maze(current).fitness,
            "candidates": ranked[: min(8, len(ranked))],
        }

    def repair(self, candidate_id: str = "current") -> dict:
        source = self._resolve(candidate_id)
        walls = list(source.walls)
        path = minimum_wall_path(source)
        carved = 0
        for cell in path:
            index = source.index(cell)
            if walls[index]:
                walls[index] = False
                carved += 1
        candidate = source.model_copy(update={"walls": tuple(walls)})
        description = self._candidate(candidate)
        description.update({"operator": "repair", "carved_walls": carved})
        return description

    def _resolve(self, candidate_id: str) -> Maze:
        if candidate_id == "current":
            return self._require_current()
        try:
            return self.candidates[candidate_id]
        except KeyError:
            raise ValueError(f"unknown candidate_id: {candidate_id}") from None

    def adopt(self, candidate_id: str) -> dict:
        candidate = self._resolve(candidate_id)
        candidate_evaluation = evaluate_maze(candidate)
        if not candidate_evaluation.connected:
            raise ValueError("cannot adopt a disconnected candidate; repair it first")
        previous = evaluate_maze(self._require_current()).fitness
        self.current = candidate
        current = candidate_evaluation.fitness
        self.history.append({
            "candidate_id": candidate_id,
            "previous_fitness": previous,
            "fitness": current,
        })
        self.candidates.clear()
        return {"adopted": candidate_id, "previous_fitness": previous, **self.status()}

    def export(self) -> dict:
        return {
            **self.status(),
            "adoptions": list(self.history),
            "library_size": len(self.library),
        }


def minimum_wall_path(maze: Maze) -> tuple[Cell, ...]:
    """Find a route that crosses the fewest walls using 0-1 BFS."""

    distances = {maze.start: 0}
    previous: dict[Cell, Cell | None] = {maze.start: None}
    queue = deque([maze.start])
    while queue:
        current = queue.popleft()
        x, y = current
        for neighbour in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)):
            if not maze.contains(neighbour):
                continue
            cost = 1 if maze.is_wall(neighbour) else 0
            distance = distances[current] + cost
            if distance >= distances.get(neighbour, maze.width * maze.height + 1):
                continue
            distances[neighbour] = distance
            previous[neighbour] = current
            if cost:
                queue.append(neighbour)
            else:
                queue.appendleft(neighbour)
    path = []
    current: Cell | None = maze.goal
    while current is not None:
        path.append(current)
        current = previous[current]
    path.reverse()
    return tuple(path)
