# Comparing Griddle agents

Run the supplied comparison from the repository root:

```bash
./scripts/compare_griddle_agents.sh
```

This compares **random**, **MCS with 10 rollouts per square**, and **MCS with
100 rollouts per square**, on the same five 5 × 5 games with deal seeds 0–4.
It prints progress and a summary, then writes complete results to
`results/griddle/comparison.json`. Repeating the command replaces that output.
The default comparison takes roughly 33 seconds on the development machine.

## Configuration

Edit [the supplied configuration](../configs/griddle/comparison.json), or provide
your own JSON file:

```json
{
  "size": 5,
  "seeds": [0, 1, 2, 3, 4],
  "agent_seed": 2026,
  "agents": [
    {"name": "random", "kind": "random", "params": {}},
    {"name": "mcs-10", "kind": "mcs", "params": {"rollouts_per_square": 10}},
    {"name": "mcs-100", "kind": "mcs", "params": {"rollouts_per_square": 100}}
  ]
}
```

`name` uniquely identifies an agent configuration. `kind` selects a registered
factory (`random`, `greedy`, `mcs`, or `llm`), and `params` supplies its
parameters. Duplicate names or game seeds, invalid budgets, unknown agent kinds,
and unrecognized built-in parameters are rejected before games start. MCS
defaults to 10 rollouts per square if that parameter is omitted.

The shell script accepts optional config and output paths, interpreted relative
to the repository root unless absolute:

```bash
./scripts/compare_griddle_agents.sh configs/griddle/comparison.json results/griddle/my_run.json
```

You can invoke the harness directly:

```bash
uv run python -m game_agent.griddle.benchmark \
  --config configs/griddle/comparison.json \
  --output results/griddle/my_run.json
```

An optional `words` path selects a custom dictionary. In CLI configuration files,
that path is relative to the config file's directory. The Python API interprets
it relative to the current working directory.

## Fair deals and independent searches

Every agent plays a fresh game for each configured seed. The **game seed only
controls the real deal**. Placement decisions, agent order, and simulation
budgets do not change it. The harness checks the completed deal strings agree
across all agents for each seed.

Agent randomness is derived using SHA-256 from `agent_seed`, the game seed,
and the agent configuration's name. It does not depend on Python's randomized
hash or iteration order. Reordering agents or seeds preserves their moves and
scores. Renaming an agent changes its random stream. Each agent instance is
fresh per game, so search state cannot leak between games.

The harness passes a model with the current board, current letter, and remaining
deck to the agent, but replaces the hidden deal RNG with an independent
simulation RNG. Agent mutations do not place letters in the live game. The
shared dictionary is treated as read-only. This is an interface for trusted
agent implementations, not a security sandbox.

MCS also calls `sample_future()` on every rollout, so using it outside the
harness does not expose the actual future sequence. Using `copy_state()` alone
for search would otherwise let an agent evaluate the exact benchmark deal.

## Monte Carlo search

At each turn, for every currently empty square:

1. Sample an unknown future deal independently of the real game.
2. Place the current letter in that candidate square.
3. Complete the board with uniformly random placements.
4. Score the final board, and repeat for the configured rollout budget.

Choose the square with the highest mean final score. Equal estimates choose
the first empty square in row-major order. Each candidate uses the same set of
sampled deal and placement seeds within a decision, reducing comparison noise.
These are full-game rollouts; there is no depth cutoff or learned evaluation.

The budget is **per empty square per turn**, not per game. On a 5 × 5 board,
10 rollouts per square means `10 × (25 + 24 + … + 1) = 3,250` completed
rollouts per game; 100 means 32,500. This is flat Monte Carlo search, without
a persistent search tree.

## Adding parameterized agents

`run_benchmark` accepts additional factories, so the orchestration and result
format do not need to change when an LLM agent is added. A factory receives a
fresh copy of the JSON `params` and a deterministic agent seed, and returns an
object with `get_action(model) -> int`.

For example, this small configurable baseline can be registered entirely from
Python:

```python
from game_agent.griddle.benchmark import BenchmarkConfig, run_benchmark

class EdgePlayer:
    def __init__(self, last=False):
        self.last = last

    def get_action(self, model):
        return model.n_actions() - 1 if self.last else 0

def edge_factory(params, seed):
    return EdgePlayer(**params)

config = BenchmarkConfig.model_validate({
    "seeds": [0, 1],
    "agents": [{"name": "last-cell", "kind": "edge", "params": {"last": True}}]
})
report = run_benchmark(config, factories={"edge": edge_factory})
```

The built-in `llm` factory accepts `backend`, `model`, `temperature`, and MCP
tool budgets; see [the LLM experiment guide](griddle_llm.md). Register other
factories in `AGENT_FACTORIES` to make them available to the JSON CLI, or pass
them to the Python API as above. Factories
are instantiated before play to catch parameter errors early; keep construction
free of model requests. External API determinism is separate from reproducible
deal and agent seeds.

Returned actions follow the existing `act()` convention: a rank in the current
empty-cell list, rather than an absolute board index. Invalid actions stop the
benchmark with an error instead of being silently scored as zero. Reports are
checkpointed after each game and marked `complete: false` until all games
finish. A failed run preserves completed games and failure details, but does
not resume partially completed games automatically.

## Results and replay

The JSON report records the configuration, dictionary checksum, and, for every
agent/game pair:

- Game seed and derived agent seed.
- Agent kind, label, and supplied parameters.
- Deal string and move trace (letter, empty-cell action rank, absolute index).
- Final board, score, and wall-clock play time.

Summary rows report game count, mean score, sample standard deviation, minimum,
maximum, and mean seconds per game. Timings include agent decisions and move
execution, excluding dictionary loading and agent construction. Timestamps and
timings will change on repeat runs; seeded local-agent scores and traces should
match when the code and dictionary are unchanged.

For replay, create a new game with the recorded game seed and play each recorded
action. Check the current letter, final board, and score against the report.
The tests exercise this replay, parameter forwarding, exact rollout budgets,
parent-state isolation, agent-order independence, and reproducibility.

The initial development-machine run on seeds 0–4 produced:

| Agent | Mean score | Sample standard deviation | Mean seconds/game |
|---|---:|---:|---:|
| Random | 33.0 | 10.72 | <0.01 |
| MCS-10 | 87.2 | 23.35 | 0.60 |
| MCS-100 | 105.2 | 30.22 | 5.98 |

This five-game demonstration is small: larger budgets are not guaranteed to win
each game. MCS-10 scored 74 against MCS-100's 73 on seed 0. Use more fixed seeds
and inspect paired per-seed scores for broader comparisons.
