# Agentic AI for Games

Hands-on Python tutorials exploring tool use, procedural content generation,
and game-playing agents.

Start with a small MCP example: expose arithmetic and letter-counting functions
as tools, call them from Python, then let a language model choose the tools.

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).
Run these commands from the repository root:

```bash
uv sync --extra dev
./src/simple_examples/scripts/run_basics.sh
uv run --extra dev pytest -q
```

The basics run without an API key or a language model.

For model-driven examples, copy `.env.example` to `.env` and configure your
backend, then follow the [demo runbook](docs/running_the_demo.md).
The OpenAI and OpenRouter examples make API calls using your chosen account;
the Qwen examples use local Ollama.

For OpenRouter, set `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in `.env`, then run:

```bash
./src/simple_examples/scripts/run_openrouter.sh "Add 17 and 25."
```

## Tutorial and examples

- [MCP from zero: arithmetic and strings](docs/tutorial.md)
- [Running and comparing model backends](docs/running_the_demo.md)
- [Simple examples](src/simple_examples/): plain Python, MCP, and model-driven tool use
- [Evolutionary maze PCG](docs/pcg_maze.md): seeded search with static and live visualisations
- [One-shot LLM maze generation](docs/pcg_maze_llm.md): compare quality and set diversity
- [Griddle](docs/griddle.md): a word game with terminal/Tkinter play and local baselines
- [Griddle agent benchmarks](docs/griddle_benchmarks.md): compare random and parameterized MCS agents on fixed deals
- [Griddle LLM experiments](docs/griddle_llm.md): compare an LLM with and without MCP search tools
- [Papers and reading notes](docs/papers/)

## Repository layout

```text
docs/                  Tutorial guides and reading material
src/simple_examples/   Arithmetic and string tools, clients, and run scripts
src/pcg/               Procedural content generation examples and visualisers
src/game_agent/        Griddle engine, playable interfaces, and local baselines
tests/simple_examples/ Tests for the basic operations
tests/game_agent/      Game rules, scoring, simulation, and optional GUI tests
tests/pcg/             Maze model, evolution, and rendering tests
```

Dependencies are managed by the root `pyproject.toml`; all examples share the
root `.venv`. Keep credentials in the ignored root `.env` file.
