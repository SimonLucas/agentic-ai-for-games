"""Count every contiguous word occurrence, reading rightwards and downwards."""

from typing import Annotated, Literal

from pydantic import Field, StrictInt, StringConstraints
from pydantic.dataclasses import dataclass

from .flat_letter_grid import FlatLetterGrid
from .trie_dict import TrieDict

WORD_SCORES = {2: 1, 3: 3, 4: 7, 5: 10, 6: 15}


@dataclass(frozen=True)
class WordMatch:
    word: Annotated[str, StringConstraints(min_length=2, max_length=6, pattern=r"^[A-Z]+$")]
    row: Annotated[StrictInt, Field(ge=0)]
    col: Annotated[StrictInt, Field(ge=0)]
    direction: Literal["right", "down"]

    @property
    def score(self) -> int:
        return WORD_SCORES[len(self.word)]


class GridWordSearch:
    def __init__(self, trie_dict: TrieDict, grid: FlatLetterGrid):
        self.trie_dict = trie_dict
        self.grid = grid

    def find_matches(self) -> list[WordMatch]:
        matches = []
        size = self.grid.size()
        for direction, dr, dc in (("right", 0, 1), ("down", 1, 0)):
            for row in range(size):
                for col in range(size):
                    node = self.trie_dict.root
                    word = ""
                    r, c = row, col
                    while r < size and c < size:
                        letter = self.grid.get_letter(r, c)
                        node = node.nodes.get(letter)
                        if node is None:
                            break
                        word += letter
                        if node.is_word and len(word) >= 2:
                            matches.append(WordMatch(word, row, col, direction))
                        r, c = r + dr, c + dc
        return matches

    def find_words(self) -> list[str]:
        return [match.word for match in self.find_matches()]
