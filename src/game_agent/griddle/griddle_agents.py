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


class MCSAgent:
    """Flat Monte Carlo search: average full random completions per empty square.

    Every candidate gets the same sampled future/placement seeds, reducing
    noise when comparing actions. Those samples never use the live deal RNG.
    Equal estimates choose the first empty square in row-major order.
    """

    def __init__(self, rollouts_per_square: int = 10, seed: int | None = None):
        if type(rollouts_per_square) is not int or rollouts_per_square < 1:
            raise ValueError("rollouts_per_square must be a positive integer")
        self.rollouts_per_square = rollouts_per_square
        self._rng = random.Random(seed)

    def get_action(self, model: ForwardModelGriddle) -> int:
        values = self.evaluate_actions(model)
        return max(values, key=values.get)

    def evaluate_actions(self, model: ForwardModelGriddle) -> dict[int, float]:
        """Mean terminal score for each empty-cell action; also used by MCP."""
        if model.is_terminal():
            raise ValueError("cannot choose an action in a finished game")
        samples = [(self._rng.getrandbits(64), self._rng.getrandbits(64))
                   for _ in range(self.rollouts_per_square)]
        values = {}
        for action in model.get_actions():
            total = sum(self._rollout(model, action, deal_seed, action_seed)
                        for deal_seed, action_seed in samples)
            values[action] = total / self.rollouts_per_square
        return values

    @staticmethod
    def _rollout(model: ForwardModelGriddle, action: int, deal_seed: int, action_seed: int) -> int:
        simulation = model.sample_future(deal_seed)
        actions = random.Random(action_seed)
        simulation.act(action)
        while not simulation.is_terminal():
            simulation.act(actions.randrange(simulation.n_actions()))
        return simulation.score()
