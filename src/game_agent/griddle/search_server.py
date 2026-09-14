"""Read-only Griddle advice over MCP/stdio; host updates positions within a game."""

import random
import time
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field, StrictInt, TypeAdapter

from .forward_model import ForwardModelGriddle, GriddleState
from .griddle_agents import MCSAgent
from .trie_dict import TrieDict

Budget = Annotated[StrictInt, Field(ge=1, le=1000)]


class SearchContext:
    def __init__(self):
        self.model = None
        self.trie = None
        self.max_rollouts = 0
        self.rng = random.Random(0)

    def configure(self, state: dict, words: list[str], seed: int, max_rollouts: int) -> dict:
        if self.model is not None:
            raise ValueError("this server is already configured for a position")
        if type(max_rollouts) is not int or not 1 <= max_rollouts <= 1000:
            raise ValueError("max_rollouts must be between 1 and 1000")
        snapshot = TypeAdapter(GriddleState).validate_python(state)
        if snapshot.current_letter is None:
            raise ValueError("search requires an already revealed current letter")
        self.trie = TrieDict(words)
        self.model = ForwardModelGriddle(snapshot, self.trie, seed=seed)
        self.max_rollouts = max_rollouts
        self.rng = random.Random(seed)
        return {"ready": True}

    def set_position(self, state: dict, seed: int) -> dict:
        """Replace the host snapshot, retaining the configured dictionary and cap."""
        if self.trie is None:
            raise ValueError("configure the game before updating its position")
        snapshot = TypeAdapter(GriddleState).validate_python(state)
        if snapshot.current_letter is None:
            raise ValueError("search requires an already revealed current letter")
        self.model = ForwardModelGriddle(snapshot, self.trie, seed=seed)
        self.rng = random.Random(seed)
        return {"ready": True}

    def validate_budget(self, count: int) -> None:
        if self.model is None:
            raise ValueError("configure a position before requesting advice")
        if type(count) is not int or not 1 <= count <= self.max_rollouts:
            raise ValueError(f"rollout budget must be between 1 and {self.max_rollouts}")

    def mcs_advice(self, rollouts_per_square: int = 10) -> dict:
        self.validate_budget(rollouts_per_square)
        start = time.perf_counter()
        agent = MCSAgent(rollouts_per_square, seed=self.rng.getrandbits(64))
        values = agent.evaluate_actions(self.model)
        free = self.model.state.grid.get_free_indices()
        best = max(values, key=values.get)
        return {
            "_search_seconds": time.perf_counter() - start,
            "recommended_index": free[best],
            "rollouts_per_square": rollouts_per_square,
            "total_rollouts": len(free) * rollouts_per_square,
            "candidates": [{"index": free[action], "mean_score": round(value, 4)}
                           for action, value in values.items()],
        }

    def rollout(self, index: int, rollouts: int = 10) -> dict:
        self.validate_budget(rollouts)
        free = self.model.state.grid.get_free_indices()
        if type(index) is not int or index not in free:
            raise ValueError("index must identify an empty cell")
        action = free.index(index)
        start = time.perf_counter()
        scores = [MCSAgent._rollout(self.model, action, self.rng.getrandbits(64), self.rng.getrandbits(64))
                  for _ in range(rollouts)]
        return {"_search_seconds": time.perf_counter() - start,
                "index": index, "rollouts": rollouts, "mean_score": sum(scores) / rollouts,
                "min_score": min(scores), "max_score": max(scores), "total_rollouts": rollouts}


def create_server() -> FastMCP:
    server = FastMCP("griddle-search", log_level="WARNING")
    context = SearchContext()

    @server.tool()
    def configure(state: dict, words: list[str], seed: int, max_rollouts: Budget = 100) -> dict:
        """Host-only position setup. Never offered to the language model."""
        return context.configure(state, words, seed, max_rollouts)

    @server.tool()
    def set_position(state: dict, seed: int) -> dict:
        """Host-only position update. Never offered to the language model."""
        return context.set_position(state, seed)

    @server.tool()
    def mcs_advice(rollouts_per_square: Budget = 10) -> dict:
        """Compare every empty square with full random game completions.

        Returns a recommended absolute cell index and estimated final scores.
        Future letters are sampled, never the actual hidden deal. Does not place a letter.
        """
        return context.mcs_advice(rollouts_per_square)

    @server.tool()
    def rollout(index: StrictInt, rollouts: Budget = 10) -> dict:
        """Estimate final score after placing the current letter at one absolute cell index.

        Averages full random completions using sampled unknown future letters.
        Use this to test a candidate square. Does not change the real board.
        """
        return context.rollout(index, rollouts)

    return server


if __name__ == "__main__":
    create_server().run(transport="stdio")
