from collections import Counter
from dataclasses import FrozenInstanceError

import pytest
from pydantic import TypeAdapter, ValidationError
from pydantic.dataclasses import is_pydantic_dataclass

from game_agent.griddle import CardDeck, FlatLetterGrid, GriddleState
from game_agent.griddle.card_deck import make_cards


def test_state_is_pydantic_and_round_trips_json():
    state = GriddleState(FlatLetterGrid(2), CardDeck(tuple("ABCDE")))
    adapter = TypeAdapter(GriddleState)
    assert adapter.validate_json(adapter.dump_json(state)) == state
    assert all(is_pydantic_dataclass(cls) for cls in (CardDeck, FlatLetterGrid, GriddleState))
    with pytest.raises(FrozenInstanceError):
        state.current_letter = "A"


def test_grid_placement_is_independent_and_does_not_alias_rows():
    grid = FlatLetterGrid(2)
    changed = grid.place(0, "A")
    assert grid.letters == (" ",) * 4
    assert changed.get_letter(0, 0) == "A"
    assert changed.get_letter(1, 0) == " "
    assert changed.n_free() == 3
    assert changed.get_free_indices() == [1, 2, 3]


@pytest.mark.parametrize("row,col", [(-1, 0), (0, -1), (0, 2), (2, 0), (True, 0), (0.5, 0)])
def test_invalid_coordinates_cannot_wrap_into_another_row(row, col):
    with pytest.raises(ValueError):
        FlatLetterGrid(2).get_letter(row, col)


@pytest.mark.parametrize("index", [-1, 4, True, 1.5])
def test_invalid_cell_indices(index):
    with pytest.raises(ValueError):
        FlatLetterGrid(2).place(index, "A")


@pytest.mark.parametrize("letter", ["", " ", "a", "AB", "é", None])
def test_invalid_placements_do_not_change_grid(letter):
    grid = FlatLetterGrid(2)
    with pytest.raises(ValueError):
        grid.place(0, letter)
    assert grid.n_free() == 4


def test_occupied_cell_is_rejected():
    with pytest.raises(ValueError, match="occupied"):
        FlatLetterGrid(2).place(0, "A").place(0, "B")


@pytest.mark.parametrize("size", [0, 1, 7, -1, True, 2.5, "5"])
def test_unsupported_grid_sizes(size):
    with pytest.raises(ValidationError):
        FlatLetterGrid(size)


def test_invalid_serialized_state_is_rejected():
    with pytest.raises(ValidationError):
        FlatLetterGrid(2, ("A",))
    with pytest.raises(ValidationError):
        CardDeck(("lowercase",))
    with pytest.raises(ValidationError, match="not enough"):
        GriddleState(FlatLetterGrid(2), CardDeck(("A",)))
    with pytest.raises(ValidationError, match="finished"):
        GriddleState(FlatLetterGrid(2, tuple("ABCD")), CardDeck(()), "A")


def test_deck_distribution_and_draw_conservation():
    deck = CardDeck()
    expected = Counter({ch: n for group, n in zip("SEAOI RLTN DUPM CYHGBKF WVZXJQ".split(), (5, 4, 3, 2, 1)) for ch in group})
    assert len(deck.cards) == 73
    assert Counter(deck.cards) == expected
    original = deck
    dealt = []
    while not deck.is_empty():
        letter, deck = deck.draw(len(deck.cards) // 2)
        dealt.append(letter)
    assert Counter(dealt) == expected
    assert len(original.cards) == 73
    with pytest.raises(ValueError):
        deck.draw(0)


@pytest.mark.parametrize("index", [-1, 2, True, 0.5])
def test_invalid_deck_draw(index):
    with pytest.raises(ValueError):
        CardDeck(tuple("AB")).draw(index)


def test_custom_deck_validates_groups_and_counts():
    assert make_cards("AB C", (2, 1)) == tuple("AABBC")
    for groups, reps in [("AB C", [1]), ("AB", [-1]), ("ab", [1]), ("AB", [True])]:
        with pytest.raises(ValueError):
            make_cards(groups, reps)
