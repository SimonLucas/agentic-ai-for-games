"""Opt-in native GUI check: GRIDDLE_TEST_GUI=1 uv run pytest -q tests/game_agent/griddle/test_gui.py."""

import os

import pytest

from game_agent.griddle import CardDeck, FlatLetterGrid, ForwardModelGriddle, GriddleState, TrieDict


@pytest.mark.skipif(os.getenv("GRIDDLE_TEST_GUI") != "1", reason="requires an explicit GUI session")
def test_buttons_play_game_and_refresh_score():
    import tkinter as tk
    from game_agent.griddle.letter_view_tkinter import GridView

    root = tk.Tk()
    try:
        model = ForwardModelGriddle(
            GriddleState(FlatLetterGrid(2, tuple("A   ")), CardDeck(tuple("XY")), "T"),
            TrieDict(["AT"]), seed=42,
        )
        view = GridView(model, root)
        root.update()
        assert str(view.buttons[0].cget("state")) == "disabled"
        for button in view.buttons[1:]:
            expected = model.state.current_letter
            button.invoke()
            root.update()
            assert button.cget("text") == expected
            assert str(button.cget("state")) == "disabled"
        assert model.is_terminal()
        assert model.score() == 1
        assert "AT: 1 points" in view.words.get("1.0", "end")
        assert view.status.get() == f"Game over — final score: {model.score()}"
    finally:
        root.destroy()
