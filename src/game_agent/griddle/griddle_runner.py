"""Run a complete game using a local baseline player."""

from .forward_model import ForwardModelGriddle
from .griddle_agents import GridPlayer


def play_game(model: ForwardModelGriddle, player: GridPlayer) -> ForwardModelGriddle:
    """Play a copy, leaving the caller's model and future deals unchanged."""
    game = model.copy_state()
    while not game.is_terminal():
        game.act(player.get_action(game))
    return game
