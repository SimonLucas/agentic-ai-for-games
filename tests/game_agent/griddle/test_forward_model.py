import random

import pytest

from game_agent.griddle import CardDeck, FlatLetterGrid, ForwardModelGriddle, GriddleState, TrieDict
from game_agent.griddle.griddle_agents import OneStepLookAhead, RandomPlayer
from game_agent.griddle.griddle_runner import play_game


def new_game(seed=12):
    return ForwardModelGriddle.new_game(3, seed=seed, trie_dict=TrieDict(["AT", "CAT"]))


def test_full_game_places_exactly_one_card_per_cell():
    model = new_game()
    assert len(model.state.deck.cards) == 72
    for free in range(9, 0, -1):
        assert model.n_actions() == free
        letter = model.state.current_letter
        model.act(0)
        assert model.state.grid.letters[9 - free] == letter
    assert model.is_terminal()
    assert model.state.current_letter is None
    assert len(model.state.deck.cards) == 73 - 9
    with pytest.raises(ValueError):
        model.act(0)


def test_copy_and_rollouts_do_not_mutate_live_state_or_deals():
    original = new_game()
    control = new_game()
    before = original.state
    child = original.copy_state()
    child.act(2)
    original.rollout()
    original.random_rollout(seed=5)
    OneStepLookAhead().get_action(original)
    assert original.state == before
    assert original.trie_dict is child.trie_dict
    while not original.is_terminal():
        assert original.state == control.state
        original.act(0)
        control.act(0)
    assert original.state == control.state


def test_deal_sequence_is_independent_of_actions_and_global_randomness():
    left, right = new_game(), new_game()
    while not left.is_terminal():
        assert left.state.current_letter == right.state.current_letter
        random.random()
        left.act(0)
        right.act(right.n_actions() - 1)


@pytest.mark.parametrize("action", [-1, 9, True, 0.5, "0"])
def test_illegal_actions_are_atomic(action):
    model = new_game()
    control = model.copy_state()
    with pytest.raises(ValueError):
        model.act(action)
    assert model.state == control.state
    model.act(0)
    control.act(0)
    assert model.state == control.state


def test_rank_actions_and_absolute_cells_are_distinct():
    model = new_game()
    model.place(0, 1)
    letter = model.state.current_letter
    model.act(1)  # The second empty cell is now absolute index 2.
    assert model.state.grid.letters[2] == letter
    with pytest.raises(ValueError, match="occupied"):
        model.place_index(1)
    with pytest.raises(ValueError):
        model.deal()  # Cannot discard the current letter.


def test_already_finished_model_does_not_draw():
    state = GriddleState(FlatLetterGrid(2, tuple("CATS")), CardDeck(()))
    model = ForwardModelGriddle(state, TrieDict(["CA", "AT"]))
    assert model.is_terminal()
    assert model.state == state
    for player in (RandomPlayer(1), OneStepLookAhead()):
        with pytest.raises(ValueError):
            player.get_action(model)


def test_greedy_player_selects_immediate_word_without_changing_parent():
    model = ForwardModelGriddle(
        GriddleState(FlatLetterGrid(2, tuple("A   ")), CardDeck(tuple("XY")), "T"),
        TrieDict(["AT"]), seed=4,
    )
    state = model.state
    assert OneStepLookAhead().get_action(model) == 0
    assert model.state == state


def test_seeded_runner_is_reproducible_and_preserves_input():
    model = new_game()
    state = model.state
    first = play_game(model, RandomPlayer(7))
    second = play_game(model, RandomPlayer(7))
    assert first.is_terminal()
    assert first.state == second.state
    assert first.score() == second.score()
    assert model.state == state
