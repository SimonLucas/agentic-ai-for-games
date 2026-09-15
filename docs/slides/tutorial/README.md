# Agentic AI for Games tutorial slides

Open [tutorial.pdf](tutorial.pdf): 31 widescreen Beamer slides, designed for a
concise introduction with optional live demos. Edit [tutorial.tex](tutorial.tex).

## Build

From the repository root:

```bash
./docs/slides/tutorial/build.sh
```

Requires Python 3 and `pdflatex` with Beamer, TikZ/PGF, listings, booktabs and
Latin Modern (available in common TeX distributions). No shell escape, network
access, model credentials or hosted calls are needed to build the deck.
The script refreshes the code excerpts, compiles twice, and writes `tutorial.pdf`.
Auxiliary files go into `build/`, ignored by the root `.gitignore`.

The repository README has a small animated preview made from five slide
frames. After changing those slides, run
`./docs/slides/tutorial/build_preview.sh` to refresh
[the GIF](../../media/tutorial_preview.gif). It rebuilds the local PDF first,
then uses `pdftoppm` and `ffmpeg`; no model calls are involved.

## Structure

- Slides 1–5: why tools; ordinary functions; ReAct and a concrete interaction.
- Slides 6–16: MCP, decorators, host/client/server, discovery and the execution loop.
- Slides 17–21: Griddle, Monte Carlo Search, persistent resources and evaluation.
- Slides 22–23: measured Griddle results and latency.
- Slides 24–28: maze PCG, scaling, one-shot and agentic generation.
- Slides 29–31: demo commands, references and code map.

## Diagrams and code

The five editable [TikZ diagrams](diagrams/) use component/data-flow notation
and a sequence diagram. Boxes denote responsibilities; arrows show requests or
data flow; the dashed outline encloses the host. They are vector graphics in
the PDF, so remain sharp when projected or enlarged.

[refresh_snippets.py](refresh_snippets.py) extracts exact, dedented fragments
from the repository. [snippets/manifest.json](snippets/manifest.json) records
source paths and line numbers. Snippets are teaching excerpts, not standalone
programs; edit the original Python files rather than the extracted copies.
The deck does not show or depend on `.env` contents.

## Presenter notes

- ReAct is the reasoning/action/observation pattern. Our implementation is a
  function-calling loop inspired by that pattern, not a literal reproduction of
  the paper's prompts or a display of private model reasoning.
- MCP is the tool connection protocol. The model API is a separate interface;
  the host translates schemas and executes requests. A direct function call
  can be sufficient when interoperability is unnecessary.
- The arithmetic example is intentionally small. Griddle adds selected-tool
  enforcement, search budgets, move validation and persistent resource handling.
- A rollout is a sampled completion of the game. This is flat Monte Carlo
  Search with random completions, not Monte Carlo Tree Search.
- The standard implemented deck contains 73 cards. The bundled dictionary's
  provenance has not been established as Chambers or an official Scrabble list.
- Results are a fixed snapshot of completed runs from 14 September 2026.
  The table combines separate experiments on three common deals, not a
  simultaneous benchmark. The raw GPT-4o-mini row predates HTTP persistence.
  Sol is excluded because its comparison was incomplete when this deck was made.
  See [the full experiment guide](../../griddle_llm.md) for later results and
  additional prompt variants. Rebuild alone does not refresh the result table.
- Do not interpret three deals as a robust ranking. Different search seed
  streams also prevent attributing small score differences to LLM judgement.
- Maze execution times are local measurements and hosted model latency varies.
  The agentic maze result includes evolutionary work used to initialise its
  macro-mutation library, so it is not an equal-compute algorithm ranking.

Primary references are linked on the slides: [ReAct](https://arxiv.org/abs/2210.03629),
the [MCP architecture specification](https://modelcontextprotocol.io/specification/2025-06-18/architecture)
and Jiang et al.'s [Agentic PCG](https://zehua-jiang.github.io/AgenticPCG/)
([local paper](../../papers/Agentic_PCG_Paper.pdf)).

See [the decorator guide](../../decorators.md) for the naming distinction,
server factory context, MCP primitives and Python/Pydantic decorators.
