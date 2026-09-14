"""Run with `python -m game_agent.griddle` or the `griddle` command."""

import argparse

from .forward_model import ForwardModelGriddle
from .griddle_agents import OneStepLookAhead, RandomPlayer
from .griddle_runner import play_game
from .trie_dict import trie_real_words


def show(model: ForwardModelGriddle) -> None:
    grid = model.state.grid
    print("\n   " + " ".join(str(i + 1) for i in range(grid.size())))
    for row in range(grid.size()):
        print(f"{row + 1:2} " + " ".join(grid.get_letter(row, col).replace(" ", ".")
                                     for col in range(grid.size())))
    print(f"Score: {model.score()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Play Griddle: place letters to form words across and down.")
    parser.add_argument("--size", type=int, choices=range(2, 7), default=5)
    parser.add_argument("--seed", type=int, help="Reproduce the same deal sequence")
    parser.add_argument("--words", help="Optional newline-separated dictionary file")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--gui", action="store_true", help="Play using Tkinter")
    mode.add_argument("--player", choices=("random", "greedy"), help="Run a local baseline")
    args = parser.parse_args()
    model = ForwardModelGriddle.new_game(args.size, seed=args.seed, trie_dict=trie_real_words(args.words))
    if args.gui:
        try:
            from .letter_view_tkinter import GridView
        except ImportError as error:
            parser.exit(1, f"Tkinter is unavailable: {error}. See docs/griddle.md for installation.\n")
        GridView(model).run()
        return
    if args.player:
        player = RandomPlayer(args.seed) if args.player == "random" else OneStepLookAhead()
        model = play_game(model, player)
    else:
        while not model.is_terminal():
            show(model)
            try:
                answer = input(f"Place {model.state.current_letter}: row column (or q): ")
                if answer.strip().lower() == "q":
                    return
                row, col = map(int, answer.split())
                model.place(row - 1, col - 1)
            except ValueError as error:
                print(f"Invalid move: {error}")
            except (EOFError, KeyboardInterrupt):
                print("\nGame stopped.")
                return
    show(model)
    print("Words: " + ", ".join(m.word for m in model.matches()))


if __name__ == "__main__":
    main()
