"""Griddle rules and transitions, with a private, copyable deal RNG."""

import copy
import random

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

from .card_deck import CardDeck
from .flat_letter_grid import FlatLetterGrid, Letter
from .grid_word_search import GridWordSearch, WordMatch
from .trie_dict import TrieDict, trie_real_words


@dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class GriddleState:
    grid: FlatLetterGrid
    deck: CardDeck
    current_letter: Letter | None = None

    def __post_init__(self) -> None:
        free = self.grid.n_free()
        if not free and self.current_letter is not None:
            raise ValueError("a finished game cannot have a current letter")
        if len(self.deck.cards) + (self.current_letter is not None) < free:
            raise ValueError("not enough cards to fill the grid")


class ForwardModelGriddle:
    def __init__(self, state: GriddleState, trie_dict: TrieDict, *, seed: int | None = None):
        self.state = state
        self.trie_dict = trie_dict
        self._deal_rng = random.Random(seed)
        self.deal_if_needed()

    @classmethod
    def new_game(cls, size: int = 5, *, seed: int | None = None,
                 trie_dict: TrieDict | None = None) -> "ForwardModelGriddle":
        return cls(GriddleState(FlatLetterGrid(size), CardDeck()),
                   trie_dict if trie_dict is not None else trie_real_words(), seed=seed)

    def deal_if_needed(self) -> None:
        if not self.is_terminal() and self.state.current_letter is None:
            self.deal()

    def deal(self) -> None:
        if self.is_terminal() or self.state.current_letter is not None:
            raise ValueError("deal only when an unfinished game has no current letter")
        letter, deck = self.state.deck.draw(self._deal_rng.randrange(len(self.state.deck.cards)))
        self.state = GriddleState(self.state.grid, deck, letter)

    def n_actions(self) -> int:
        return self.state.grid.n_free()

    def get_actions(self) -> list[int]:
        return list(range(self.n_actions()))

    def is_terminal(self) -> bool:
        return self.n_actions() == 0

    def matches(self) -> list[WordMatch]:
        return GridWordSearch(self.trie_dict, self.state.grid).find_matches()

    def score(self) -> int:
        return sum(match.score for match in self.matches())

    def copy_state(self) -> "ForwardModelGriddle":
        """Share immutable state and dictionary; clone the deal RNG without drawing."""
        model = copy.copy(self)
        model._deal_rng = copy.deepcopy(self._deal_rng)
        return model

    def act(self, action: int) -> None:
        """Place into the action-th empty cell in row-major order (legacy convention)."""
        indices = self.state.grid.get_free_indices()
        if type(action) is not int or not 0 <= action < len(indices):
            raise ValueError("action must index the current list of empty cells")
        self.place_index(indices[action])

    def place_index(self, index: int) -> None:
        """Place into a stable absolute cell index, then reveal the next letter."""
        if self.state.current_letter is None:
            raise ValueError("no current letter to place")
        grid = self.state.grid.place(index, self.state.current_letter)
        self.state = GriddleState(grid, self.state.deck)
        self.deal_if_needed()

    def place(self, row: int, col: int) -> None:
        self.place_index(self.state.grid.index(row, col))

    def rollout(self) -> int:
        model = self.copy_state()
        while not model.is_terminal():
            model.act(0)
        return model.score()

    def random_rollout(self, *, seed: int | None = None) -> int:
        model, actions = self.copy_state(), random.Random(seed)
        while not model.is_terminal():
            model.act(actions.randrange(model.n_actions()))
        return model.score()
