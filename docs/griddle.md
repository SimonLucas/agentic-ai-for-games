# Griddle

Griddle is a word game adapted from Lexicon Criss Cross.
This import provides the game engine, terminal play, a Tkinter interface, and
the original random and one-step greedy baselines. LLM and MCP integration is
the next stage.

## Play

From the repository root:

```bash
uv sync --extra dev
uv run griddle --gui --seed 42
```

For terminal play, omit `--gui`. Enter a **one-based row and column**, separated
by a space, or `q` to quit. To run a complete game without interaction:

```bash
uv run griddle --player random --seed 42
uv run griddle --player greedy --seed 42
```

`uv run python -m game_agent.griddle` is equivalent to `uv run griddle`.
Use `--size 2` through `--size 6` to change the board size, or
`--words path/to/words.txt` to supply a newline-separated dictionary.

## Rules preserved from the implementation

- The default board is 5 × 5. One letter is revealed at a time and must be
  placed in an empty cell. Placements cannot be moved or overwritten.
- Letters are drawn without replacement from the original 73-card deck:
  `SEAOI` five times each, `RLTN` four, `DUPM` three, `CYHGBKF` two, and
  `WVZXJQ` once.
- Words are contiguous, reading left to right or top to bottom. Empty cells
  break words. Diagonals, backwards words, and row wrapping do not count.
- **Every occurrence counts**, including overlapping words, prefixes, words
  embedded inside longer words, and repeated occurrences of the same word.
  The GUI lists each occurrence and its starting cell.
- The score is the sum over the current board, rather than an accumulated
  reward each turn. The game ends when the board is full.

| Word length | Points |
|---|---:|
| 2 | 1 |
| 3 | 3 |
| 4 | 7 |
| 5 | 10 |
| 6 | 15 |

One-letter dictionary entries never score. Sizes above six are rejected because
the original game provides no scoring rule for longer words.

## Core API

```python
from pydantic import TypeAdapter
from game_agent.griddle import ForwardModelGriddle, GriddleState

game = ForwardModelGriddle.new_game(seed=42)
print(game.state.current_letter)
game.place(0, 0)                    # zero-based row and column
game.place_index(7)                 # absolute row-major cell index
branch = game.copy_state()          # independent future transitions and deals
print(game.score(), game.matches())

adapter = TypeAdapter(GriddleState)
saved = adapter.dump_json(game.state)
restored = adapter.validate_json(saved)
```

`act(action)` retains the original API convention: `action` is a rank in the
**current list of empty cells**, not an absolute board index. Prefer `place`
or `place_index` for human input and future tool APIs.

The grid, deck, and state use frozen
[Pydantic dataclasses](https://docs.pydantic.dev/latest/concepts/dataclasses/)
and tuples. Placement and drawing return new values; the forward model updates
its state reference. This deliberately replaces the old mutable grid API.
State equality now compares actual fields, and invalid states are rejected at
construction. `TypeAdapter` supports JSON serialization without arbitrary-type
exceptions.

The forward model owns its deal RNG. A copied model shares immutable state and
the dictionary, and copies the RNG state without drawing a card. Random-player
choices use a separate RNG. The same seed therefore gives the same letter
sequence regardless of placements or speculative searches. Treat the trie as
read-only once games are created. Serialized `GriddleState` is a board/deck
snapshot; it does **not** contain the RNG state. Use `copy_state()` when a branch
must preserve the precise future sequence.

## Tkinter

Tkinter is part of Python's standard library but requires a native Tcl/Tk
extension in the underlying interpreter. It cannot be enabled by adding a pip
dependency to `pyproject.toml`.

For this machine's Homebrew Python 3.14, install the
[matching Homebrew package](https://formulae.brew.sh/formula/python-tk@3.14):

```bash
brew install python-tk@3.14
uv sync --extra dev
uv run python -c "import tkinter; print(tkinter.TkVersion)"
```

Use a Tk-enabled interpreter when creating the environment on other systems.
The core game, command-line interface, and normal tests work without Tkinter.
The GUI imports Tkinter only when requested, and starting its event loop is
separate from constructing the view.

## Tests

```bash
uv run --extra dev pytest -q
# Opens a short-lived native window; requires a graphical desktop:
GRIDDLE_TEST_GUI=1 uv run --extra dev pytest -q tests/game_agent/griddle/test_gui.py
```

Tests are in `tests/game_agent/griddle/`. They cover validation and immutable
state, dictionary loading, exact scoring and an independent substring oracle,
deck conservation, action bounds, copy isolation, deterministic deals, complete
games, and baseline decisions. The GUI check invokes actual buttons through to
game completion. It is opt-in so headless test runs remain usable.

See [the import review](griddle_import_review.md) for the critique and scope of
the changes.

## Benchmark agents

The [benchmark guide](griddle_benchmarks.md) describes parameterized agent
configurations, fixed deal seeds, Monte Carlo search, and replayable results.

```bash
./scripts/compare_griddle_agents.sh
```
