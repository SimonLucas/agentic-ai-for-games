"""Small local baselines carried over from Griddle; no LLM integration."""

import random
from typing import Protocol

from .forward_model import ForwardModelGriddle


class GridPlayer(Protocol):
    def get_action(self, model: ForwardModelGriddle) -> int: ...


class RandomPlayer:
    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)

    def get_action(self, model: ForwardModelGriddle) -> int:
        if model.is_terminal():
            raise ValueError("cannot choose an action in a finished game")
        return self._rng.randrange(model.n_actions())


class OneStepLookAhead:
    def get_action(self, model: ForwardModelGriddle) -> int:
        if model.is_terminal():
            raise ValueError("cannot choose an action in a finished game")

        def immediate_score(action: int) -> int:
            child = model.copy_state()
            child.act(action)
            return child.score()

        return max(model.get_actions(), key=immediate_score)
