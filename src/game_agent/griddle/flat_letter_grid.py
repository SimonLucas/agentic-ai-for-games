"""Validated square grid; immutable snapshots make simulation copies safe."""

from typing import Annotated

from pydantic import ConfigDict, Field, StrictInt, StringConstraints
from pydantic.dataclasses import dataclass

Letter = Annotated[str, StringConstraints(min_length=1, max_length=1, pattern=r"^[A-Z]$")]
Cell = Annotated[str, StringConstraints(min_length=1, max_length=1, pattern=r"^[A-Z ]$")]
GridSize = Annotated[StrictInt, Field(ge=2, le=6)]


@dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class FlatLetterGrid:
    width: GridSize = 5
    letters: tuple[Cell, ...] | None = None

    def __post_init__(self) -> None:
        if self.letters is None:
            object.__setattr__(self, "letters", (" ",) * self.width**2)
        elif len(self.letters) != self.width**2:
            raise ValueError("letters must contain exactly width squared cells")

    def size(self) -> int:
        return self.width

    def index(self, row: int, col: int) -> int:
        if any(type(n) is not int or not 0 <= n < self.width for n in (row, col)):
            raise ValueError("row and column must be integers inside the grid")
        return row * self.width + col

    def get_letter(self, row: int, col: int) -> str:
        return self.letters[self.index(row, col)]

    def n_free(self) -> int:
        return self.letters.count(" ")

    def get_free_indices(self) -> list[int]:
        return [i for i, letter in enumerate(self.letters) if letter == " "]

    def place(self, index: int, letter: str) -> "FlatLetterGrid":
        """Return a new grid with one empty cell filled; do not mutate this grid."""
        if type(index) is not int or not 0 <= index < len(self.letters):
            raise ValueError("cell index is outside the grid")
        if self.letters[index] != " ":
            raise ValueError("cell is already occupied")
        if not isinstance(letter, str) or len(letter) != 1 or not "A" <= letter <= "Z":
            raise ValueError("letter must be a single uppercase ASCII letter")
        cells = list(self.letters)
        cells[index] = letter
        return FlatLetterGrid(self.width, tuple(cells))
