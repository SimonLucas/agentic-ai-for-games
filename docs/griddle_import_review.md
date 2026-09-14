# Griddle import review

Imported and refined from `MCGS-Play/griddle` on 14 September 2026. The source
repository was left unchanged.

## What worked well

The original split between deck, grid, trie, word search, and forward model is
small and understandable. Trie traversal naturally stops at missing prefixes,
and the flat grid is a good fit for a small board. The swap-with-last draw
preserves the intended letter frequencies without repeated full shuffles.
The migration keeps these concepts and the scoring table.

## Findings and changes

| Original issue | Refined implementation |
|---|---|
| `FlatLetterGrid` used a stdlib dataclass with no declared fields; generated equality did not describe the board. `GriddleState` contained unvalidated mutable objects. | Frozen Pydantic dataclasses with declared grid, deck, and state fields; validated JSON round trips and structural equality. |
| `LetterGrid` initialized rows with `[[' '] * size] * size`, aliasing the rows. Two grid implementations could diverge. | One flat grid representation shared by the engine and GUI. |
| Assertions checked some moves, but disappear under optimized Python; negative indices and out-of-range columns could address unintended cells. | Explicit exceptions for invalid coordinates, indices, letters, occupied cells, and finished-game actions. Rejected moves leave both state and deal RNG unchanged. |
| A cached free-cell counter could drift from the mutable board. | Derive empty cells directly from the immutable tuple. |
| `zip(groups, reps)` silently truncated mismatched deck specifications. | Validate group/count alignment, count types, and letters. |
| Search could emit one-letter dictionary entries despite declaring a minimum length of two, then scoring raised `KeyError`. Boards above six also lacked score entries. | Enforce the minimum in search and limit supported sizes to the original score table. |
| Global `random` connected dealing, actions, and simulated futures. Copy construction could automatically deal. Runner comments claimed a fixed deal but did not implement it. | A model-owned RNG, independent action RNGs, and copy without constructor side effects; seeded deals stay identical across different placements and searches. |
| `deal()` could replace an unplayed letter. Exhaustion and malformed state failed late. | Guard dealing and validate enough remaining cards to fill the board. |
| Dictionary loading used a working-directory-relative path and printed while building the trie. | Bundle the unchanged word file as package data, load through `importlib.resources`, normalize case, and avoid import/setup output. |
| Tkinter displayed the unused grid type, had no move callbacks, and blocked inside its constructor. | Clickable cells, current-letter and score display, word occurrences, occupied-cell disabling, and an explicit `run()` event loop. |
| Examples, ad hoc timing/equality experiments, and simulation runners depended on unrelated `agents` and `stats` modules. | A standalone installable package and CLI; real regression tests live outside `src`. |

Immutable deck updates still use swap-with-last ordering but copy and validate
the remaining tuple, so a draw is now O(n), rather than the old mutable O(1)
swap. At 73 cards this is a deliberate clarity/snapshot tradeoff. Profile before
building a high-throughput search agent; do not assume this import improves
simulation speed.

## Scope and compatibility

- `ForwardModelGriddle`, `GriddleState`, `FlatLetterGrid`, `CardDeck`, `TrieDict`,
  and `GridWordSearch` remain recognizable concepts in `game_agent.griddle`.
- The default 5 × 5 rules, scoring, deck distribution, and occurrence counting
  are preserved. This is not intended as a drop-in replacement for every
  MCGS-Play import: grid/deck mutation is replaced with immutable transitions.
- Random and one-step lookahead are retained as simple local baselines. The
  external Monte Carlo agent and its benchmarking framework are not imported.
- `griddle_deal_runner.py` was an unfinished duplicate whose own docstring said
  separate dealing was not implemented. It is not presented as working code.
  An explicit chance-action/dealer API remains future work.
- The HTML mockup in the source data folder describes a different interaction
  and is not used as a rule specification or copied into the playable game.
- State snapshots omit RNG state. Exact simulation branching uses
  `copy_state()`; persisted replay would need a seed plus action history or an
  explicitly serialized deal sequence.

## Verification

On this machine, the headless suite passed 58 tests, with the native GUI test
skipped by default. The opt-in GUI test passed separately, including placement,
scoring, word-list refresh, and game completion. Random and greedy 5 × 5 games
also completed. The built wheel loaded its bundled dictionary and completed a
game from a temporary directory outside the repository.

Tkinter was installed using `python-tk@3.14`. Homebrew upgraded the underlying
Python from 3.14.3 to 3.14.7 and its dependencies; `uv sync` recreated the project
environment against that interpreter. Tk 9.0 is available inside the environment.

## Source materials

The word list is copied unchanged from `MCGS-Play/data/griddle/words.txt`.
No separate dictionary provenance was present in that folder.

The source repository's README says MIT, but its actual `LICENSE` contains
GPLv3. That file is preserved as
[`SOURCE_LICENSE.txt`](../src/game_agent/griddle/SOURCE_LICENSE.txt).
The project owner should reconcile that discrepancy and identify the word-list
source when choosing this new repository's publication license. This import
does not silently assign a new license to those materials.
