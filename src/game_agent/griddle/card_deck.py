"""The original 73-card distribution, with explicit indexed draws."""

from collections.abc import Iterable

from pydantic import ConfigDict, Field
from pydantic.dataclasses import dataclass

from .flat_letter_grid import Letter

RAW_DECK = "SEAOI RLTN DUPM CYHGBKF WVZXJQ"
REPETITIONS = (5, 4, 3, 2, 1)


def make_cards(raw_deck: str = RAW_DECK, reps: Iterable[int] = REPETITIONS) -> tuple[str, ...]:
    groups, counts = raw_deck.split(), tuple(reps)
    if len(groups) != len(counts):
        raise ValueError("each letter group must have a repetition count")
    if any(type(n) is not int or n < 0 for n in counts):
        raise ValueError("repetition counts must be nonnegative integers")
    if any(not "A" <= ch <= "Z" for group in groups for ch in group):
        raise ValueError("deck groups must contain uppercase ASCII letters")
    return tuple(ch for group, n in zip(groups, counts) for ch in group for _ in range(n))


@dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class CardDeck:
    cards: tuple[Letter, ...] = Field(default_factory=make_cards)

    def is_empty(self) -> bool:
        return not self.cards

    def draw(self, index: int) -> tuple[str, "CardDeck"]:
        """Swap the selected card with the last card and return the remaining deck."""
        if type(index) is not int or not 0 <= index < len(self.cards):
            raise ValueError("card index is outside the remaining deck")
        cards = list(self.cards)
        letter = cards[index]
        cards[index] = cards[-1]
        cards.pop()
        return letter, CardDeck(tuple(cards))
