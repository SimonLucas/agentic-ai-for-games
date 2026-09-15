# Griddle: LLM alone versus LLM with MCP search

Run the paired comparison from the repository root:

```bash
./scripts/compare_griddle_llm.sh
```

The default configuration uses `openai/gpt-4o-mini` through OpenRouter. Set
`OPENROUTER_API_KEY` in the ignored root `.env`. The harness loads this file;
credentials are not part of the configuration or result report.

The experiment runs three fixed 5 × 5 deals (seeds 0–2) with four agents:

- Random placement.
- Standalone MCS with 10 rollouts per square.
- GPT-4o-mini with no search tools.
- The same GPT-4o-mini with optional MCP `mcs_advice`, capped at 10 rollouts
  per square and one tool call per move.

It prints scores and timings and saves
`results/griddle/llm_comparison.json`. Hosted model calls use your provider
account. This is an initial small experiment, not a reliable ranking of models.

## Choose a model and service

Edit [the JSON configuration](../configs/griddle/llm_comparison.json), or copy
it and pass the new file to the script:

```bash
./scripts/compare_griddle_llm.sh configs/griddle/my_model.json results/griddle/my_model.json
```

Each LLM agent has `kind: "llm"`, with settings in `params`. Update the backend
and model in **both LLM arms** when making a paired comparison.

| Backend | Example model ID | Credential / endpoint |
|---|---|---|
| `openai` | `gpt-4o-mini` | `OPENAI_API_KEY`; OpenAI API |
| `openrouter` | `openai/gpt-4o-mini` | `OPENROUTER_API_KEY`; OpenRouter API |
| `ollama` | `qwen2.5:3b` | Local Ollama; no hosted API key |

For example, the tool-enabled arm for your installed local Qwen model is:

```json
{
  "name": "qwen-mcp",
  "kind": "llm",
  "params": {
    "backend": "ollama",
    "model": "qwen2.5:3b",
    "temperature": 0,
    "tools": ["mcs_advice"],
    "max_rollouts_per_call": 10,
    "max_tool_calls_per_move": 1
  }
}
```

Start `ollama serve` before running local evaluations. `base_url` can override
an endpoint; Ollama also honors `OLLAMA_BASE_URL`. Keep credentials associated
with the selected service. The OpenRouter key does not fall back to an OpenAI
key or vice versa.

The common adapter uses **Chat Completions**, as in the arithmetic tutorial.
Select models/endpoints that support that interface and, for the MCP arm,
function calling. This does not implement every provider-specific API. Models
requiring the Responses API for tools need a separate adapter.
`temperature: null` omits that parameter for models that do not accept it.
Optional `reasoning_effort` and `max_output_tokens` allow model-specific tuning.
The OpenRouter adapter requests providers that support the supplied parameters.

## What the LLM sees

Both conditions receive the same selected rules prompt and position representation: board rows,
current letter, legal absolute indices, remaining letter counts, current score,
and the words already on the board. Each decision starts a fresh conversation.
The full dictionary and future deal sequence are not in the model prompt.

The LLM must return `{"index": N}` with an empty **absolute** row-major index.
The adapter validates it and translates it to the engine's empty-cell action
rank. Both conditions use identical validation and bounded correction prompts.
The sole remaining square is played without an API call in both conditions.

## MCP tools

Set `tools` to `[]`, `["mcs_advice"]`, `["rollout"]`, or both tool names.

| Tool | Model arguments | Result |
|---|---|---|
| `mcs_advice` | `rollouts_per_square` | Recommended absolute index and estimated final scores for every empty square |
| `rollout` | `index`, `rollouts` | Estimated final score for a single proposed placement, plus sampled minimum and maximum |

Both tools perform full random completions using the same implementation as
the standalone MCS baseline. The host transfers the actual dictionary and a
validated position snapshot to the MCP subprocess, so custom dictionaries work
as well. Future letters are sampled from the remaining deck with independent
randomness. Neither tool has the live game's RNG or changes the real board.

The tool-free condition starts **no MCP process** and sends no tool schemas.
The tool-enabled condition keeps one stdio server and one HTTP client alive for
the whole game. Tool discovery runs once. The first decision supplies the
dictionary, budget cap, and position through a host-only `configure` call;
later decisions use `set_position` to transfer only the new snapshot and
simulation seed. Only the selected search tools are offered to the model.
Neither host-only operation is advertised to it; unadvertised requests are
rejected. The dictionary and budget cap remain fixed throughout the game.
Resources close when the game ends or fails, within the same async task that
opened MCP's task groups. The tool-free policy also reuses its HTTP client.

The model uses `tool_choice="auto"`: access does not force a tool call. Advice
returns to the model, which still chooses the final square. The adapter never
silently substitutes the MCS recommendation. Inspect the traces to distinguish
tool availability, actual calls, and whether the model followed the advice.

## Limits and error handling

| Parameter | Default | Meaning |
|---|---:|---|
| `max_rollouts_per_call` | 10 | Maximum rollouts per square for MCS, or total rollouts for one candidate |
| `max_tool_calls_per_move` | 2 | Accepted model-requested search attempts per decision |
| `max_model_calls_per_move` | 4 | Maximum model requests, including corrections and post-tool replies |
| `max_output_tokens` | 256 | Output cap per model request |
| `timeout_seconds` | 60 | Timeout for API requests and MCP responses |

The MCP server independently enforces the rollout cap. Parallel tool requests
count individually against the tool-call cap. Once tools are exhausted, or on
the final allowed model request, `tool_choice="none"` requests a final move.
Malformed moves get a correction containing the legal indices. The agent
raises an error if it cannot produce a legal move within the request budget;
there is no random fallback that could hide a failed LLM policy. The HTTP client
allows one retry for retryable transport/service errors.

The report is saved atomically after every completed game. It has `complete:
false` during the run, and `complete: true` only after every game finishes.
If an agent fails mid-game, completed results and the failing agent's metrics
remain available in a `failure` entry. Partial games are not assigned scores.
The harness does not automatically resume a partial run.

## Measuring the effect

Every completed LLM game includes `agent_metrics` with model requests/errors, tool
attempts/errors, invalid moves, forced moves, simulated rollouts, input/output
tokens, and per-decision model/tool events. Events include response model IDs,
fingerprints when supplied, final text, requested tools, arguments and results.
Host setup and position-update calls are not counted as model-selected search calls.

The benchmark uses `game_session()` and `get_action_async()` to retain connections.
For custom game loops, use the same lifetime explicitly:

```python
async with agent.game_session():
    while not game.is_terminal():
        game.act(await agent.get_action_async(game))
```

The synchronous `get_action()` remains a one-shot compatibility method: repeated
standalone calls do not reuse a session. Do not call it inside `game_session()`.

Timing metrics now separate `client_setup_seconds`, `mcp_startup_seconds`,
`mcp_position_seconds`, `api_seconds`, `tool_rpc_seconds`, and
`resource_close_seconds`. Server-measured `search_seconds` is a **subset** of
`tool_rpc_seconds`, not an additional cost. The difference estimates MCP transport
and serialization overhead. Timing metadata is removed before returning advice
to the LLM, keeping instrumentation out of the policy's inputs.
`mcp_process_starts` and `http_client_starts` verify that each is one per game.

`reported_cost_usd` sums costs only when the service returns them;
`cost_missing_calls` identifies incomplete cost reporting. A zero reported cost
with missing entries does not mean the run was free. Likewise,
`usage_missing_calls` records responses without token usage. Wall time includes
MCP startup, model calls, advice, and applying moves; it is a complete policy
cost, not pure model inference latency.

Compare per-seed scores and tool use alongside the means. The two LLM policies
diverge into different boards, so this is a comparison of complete games, not
the same individual positions. The standalone MCS reference helps distinguish
useful search from useful LLM control of search. The tool-enabled policy has
additional computation and dictionary-based evaluations; this is an access
comparison, not an equal-compute experiment.

Hosted replies can vary even at temperature zero. Fixed deal seeds guarantee
the paired letters, not deterministic provider output. More seeds, repeated
trials, and additional models are needed to generalize any initial result.

## Prompt versions

`params.prompt_version` selects a versioned text file:

- [`rules-v1`](../src/game_agent/griddle/prompts/rules-v1.txt) is the original
  compact prompt and remains the default for reproducing the original experiment.
- [`strategy-v2`](../src/game_agent/griddle/prompts/strategy-v2.txt) explains the
  rules more fully and gives placement heuristics: score across both axes,
  preserve plausible longer-word continuations, exploit overlapping short words,
  and weigh required letters against the remaining deck. It explicitly asks for
  the next move rather than asking the model to acknowledge the rules.

The exact system text and version are saved in each agent's metrics. Use the
same version in both tool conditions. The state representation and output contract
are unchanged. The prompt describes the implemented 73-card deck, rather than
the illustrative 80-card count. The bundled dictionary is authoritative; its
provenance has not been verified as Chambers or an official Scrabble list.

These separate configurations keep the persistence and prompt experiments distinct:

```bash
# Original tool row, original prompt, persistent connections:
./scripts/compare_griddle_llm.sh configs/griddle/llm_persistent_comparison.json results/griddle/llm_persistent_comparison.json
# Raw LLM with the revised prompt, no search tools:
./scripts/compare_griddle_llm.sh configs/griddle/llm_prompt_comparison.json results/griddle/llm_prompt_comparison.json
```

Both use the original model, game seeds, agent labels and stochastic seeds. The
raw-prompt rerun also benefits from persistent HTTP connections, so its latency
change should not be attributed to the wording alone. Model responses can still
vary between runs.

## Combined results (14 September 2026)

This table brings together the saved runs on the same three 5 × 5 deals. All
LLM rows use OpenRouter. Baseline rows are retained from the
original run; MCS-200, persistent MCP, revised-prompt and GPT-4.1 rows are
separate subsequent runs. Every row in this first table contains three completed
games. Partial Sol results are shown separately below.

| Policy | Prompt | Connection lifetime | Seed 0 | Seed 1 | Seed 2 | Mean score | Seconds/game |
|---|---|---|---:|---:|---:|---:|---:|
| Random | — | — | 24 | 20 | 38 | 27.3 | <0.01 |
| Standalone MCS-10 | — | — | 74 | 99 | 81 | 84.7 | 0.60 |
| Standalone MCS-200 | — | — | 94 | 75 | 112 | 93.7 | 11.88 |
| GPT-4o-mini, no tools | rules-v1 | Per move | 34 | 18 | 24 | 25.3 | 23.30 |
| GPT-4o-mini, MCP MCS-10 | rules-v1 | Per move | 58 | 115 | 86 | 86.3 | 57.73 |
| **GPT-4o-mini, persistent MCP MCS-10** | **rules-v1** | **Per game** | **58** | **115** | **86** | **86.3** | **44.49** |
| GPT-4o-mini, no tools, revised prompt | strategy-v2 | Per game (HTTP only) | 27 | 22 | 34 | 27.7 | 18.41 |
| GPT-4.1, no tools | rules-v1 | Per game (HTTP only) | 29 | 20 | 25 | 24.7 | 34.92 |
| GPT-4.1, persistent MCP MCS-10 | rules-v1 | Per game | 58 | 79 | 66 | 67.7 | 54.60 |

### Sol: completed games from incomplete runs

Both Sol configurations use **medium reasoning**, `rules-v1`, an 8,192-token
completion cap and persistent connections. MCP search is capped at 10 rollouts
per square. “OpenAI” denotes the API provider, not absence of tools.

| Policy | Provider | Completed games | Seed 0 | Seed 1 | Seed 2 | Mean of completed scores | Seconds/completed game | Status |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Sol, no tools | OpenRouter | 1 | 72 | — | — | 72.0 | 1684.87 | Stopped; completed games retained |
| Sol + MCP MCS-10 | OpenRouter | 1 | 58 | — | — | 58.0 | 185.42 | Stopped; completed games retained |
| Sol, no tools | OpenAI | 1 | 72 | — | — | 72.0 | 1559.39 | Completed seed 0 only |
| Sol + MCP MCS-10 | OpenAI | 0 | — | — | — | — | — | Failed before first move |

A dash means no completed game; it is not a zero score. The OpenRouter run was
stopped when switching providers. The direct OpenAI run completed its first
without-tools game, then its tool arm failed before the first move: function
tools with medium reasoning were not supported for this model through Chat
Completions. It requires the Responses API or a different reasoning
configuration. Single-game Sol scores should not be ranked against three-game
means. This table is a snapshot, not a live display.

Persistent MCP and HTTP reuse reduced observed tool-agent time by **22.9%**,
with identical moves and scores. Provider latency may vary. The revised-prompt
row also changes HTTP lifetime and is a separate exploratory trial; its nine
invalid-move corrections (versus three originally) and the small sample mean
the higher average is not convincing evidence of a better prompt.

Full JSON reports contain per-game scores, timings, move traces and LLM/tool
metrics. They are saved locally in the repository:

- [Original four-agent run](../results/griddle/llm_comparison.json)
- [Persistent MCP rerun](../results/griddle/llm_persistent_comparison.json)
- [Revised raw-prompt run](../results/griddle/llm_prompt_comparison.json)
- [Matched persistence comparison](../results/griddle/llm_persistence_summary.json)
- [MCS-200 run](../results/griddle/mcs200_comparison.json)
- [GPT-4.1 run](../results/griddle/llm_gpt41_comparison.json)
- [Sol via OpenRouter, interrupted](../results/griddle/llm_sol_comparison.json)
- [Sol via OpenAI, incomplete after tool/API incompatibility](../results/griddle/llm_sol_openai_comparison.json)

The earlier five-deal random/MCS-10/MCS-100 experiment is retained separately in
[its full report](../results/griddle/comparison.json); its five-game means use a
different sample and are not mixed into this three-deal table.

## Initial live result (14 September 2026, before persistent connections)

The default OpenRouter configuration completed all three seeded games with:

| Policy | Seed 0 | Seed 1 | Seed 2 | Mean score | Seconds/game |
|---|---:|---:|---:|---:|---:|
| Random | 24 | 20 | 38 | 27.3 | <0.01 |
| Standalone MCS-10 | 74 | 99 | 81 | 84.7 | 0.60 |
| GPT-4o-mini, no tools | 34 | 18 | 24 | 25.3 | 23.30 |
| GPT-4o-mini, MCP MCS-10 | 58 | 115 | 86 | 86.3 | 57.73 |

Search access improved the LLM score on all three deals, by 61 points on average.
The tool-enabled agent made 72 successful search calls and followed the returned
recommendation on all 72 non-forced moves. This is evidence of useful delegation
to MCS, rather than evidence that the LLM improves on MCS itself. The standalone
and tool MCS policies use different simulation seeds, so their small score
difference is not evidence of superior LLM control.

The no-tool arm made 75 model requests (including three corrected invalid
moves); the tool arm made 144. Seventeen additional tool requests were rejected
by the one-call-per-move budget; none executed extra rollouts. All allowed MCP
search calls succeeded. The final forced square required no LLM request.
This checks that the budget applies even when the model requests multiple tools
in one response.

OpenRouter reported **$0.005131** for the no-tool arm and **$0.016011** for the
tool arm, approximately **$0.02114 total**, with no missing cost/usage entries.
The full run took about four minutes on this machine. This measures one small
model and three deals; it does not establish a general ranking.

The full report and compact aggregate are saved under
`results/griddle/llm_comparison.json` and
`results/griddle/llm_comparison_summary.json` in the development checkout.

## Persistent-session rerun (14 September 2026)

Rerunning only the tool-enabled row with `rules-v1`, the same model, labels,
seeds and budgets preserved **every move and score**, while reducing elapsed time:

| Deal seed | Score | Original seconds | Persistent seconds |
|---|---:|---:|---:|
| 0 | 58 | 55.75 | 45.43 |
| 1 | 115 | 58.42 | 43.79 |
| 2 | 86 | 59.04 | 44.24 |
| Mean | 86.3 | 57.73 | 44.49 |

This is an observed **22.9% reduction** in wall time. Each game started exactly
one MCP process and one HTTP client, rather than one of each per non-forced move.
The following component times were measured in the new run (mean seconds/game):

| Component | Seconds |
|---|---:|
| LLM API requests | 42.684 |
| Search-tool RPCs, including computation | 1.080 |
| ↳ Search computation within those RPCs | 1.020 |
| MCP startup and discovery | 0.456 |
| Initial position/dictionary setup and later position updates | 0.080 |
| HTTP client construction | 0.077 |
| Resource shutdown | 0.083 |

Most remaining wall time is in the 48 model requests per game. Search budgets
remained 10 rollouts per square; the rerun made 72 successful advice calls in
total. Provider latency can vary between runs, so the measured speedup is not a
guaranteed constant. Original-run component timings were not recorded, so the
precise separate contributions of HTTP reuse and MCP reuse cannot be recovered.

Full results: `results/griddle/llm_persistent_comparison.json`.
Matched before/after aggregate: `results/griddle/llm_persistence_summary.json`.

## Revised raw-prompt trial (14 September 2026)

The separate `strategy-v2` trial used no tools and the original three deal seeds:

| Deal seed | Original `rules-v1` score | Revised `strategy-v2` score |
|---|---:|---:|
| 0 | 34 | 27 |
| 1 | 18 | 22 |
| 2 | 24 | 34 |
| Mean | 25.3 | 27.7 |

The revised wording improved two seeds and the mean slightly, but required nine
invalid-move corrections versus three in the original trial. That is not strong
evidence of a better policy. Both versions remain selectable; `rules-v1` remains
the default baseline rather than replacing it on the strength of three games.
The clearer strategy prompt has not been tested with other models yet.

The revised raw run used one HTTP client per game and no MCP process. It averaged
18.41 seconds/game, but this time comparison also includes HTTP reuse and service
variability, so it does not isolate a prompt effect on latency.

Full results: `results/griddle/llm_prompt_comparison.json`.
Score comparison: `results/griddle/llm_prompt_summary.json`.

## GPT-4.1 comparison

GPT-4.1 averaged 24.7 without tools and 67.7 with MCP search. The raw arm
needed 16 invalid-move corrections; the tool arm needed none. It made 67 search
calls across 72 non-forced decisions, with no tool errors. Reported API costs
were $0.084622 and $0.200404 respectively ($0.285026 total). These three deals
do not show an improvement over GPT-4o-mini.

[Full report](../results/griddle/llm_gpt41_comparison.json) ·
[Summary](../results/griddle/llm_gpt41_summary.json).

For a stronger non-reasoning model comparison using the same prompt and budgets:

```bash
./scripts/compare_griddle_llm.sh configs/griddle/llm_gpt41_comparison.json results/griddle/llm_gpt41_comparison.json
```

This selects `openai/gpt-4.1` through OpenRouter, with persistent HTTP and MCP
connections. The legacy agent labels are preserved to keep derived simulation
seeds identical; `params.model` identifies the actual model. GPT-4.1 supports
Chat Completions and function calling, making it a compatible next experiment
([official model documentation](https://developers.openai.com/api/docs/models/gpt-4.1)).

Reference reports are intended for version control; scratch runs belong in the
ignored `results/local/` directory. See [the results policy](../results/README.md).

## Standalone MCS-200

Increasing the budget from 10 to 200 rollouts per square produced scores 94, 75
and 112 (mean 93.7), taking 11.88 seconds per game. This improved the mean by
9 points, but seed 1 fell from 99 to 75. More rollouts do not guarantee a better
realized score on every deal. The original deal and agent seeds were preserved.
This CPU run overlapped an API-backed Sol run, so timings are approximate.

```bash
./scripts/compare_griddle_llm.sh configs/griddle/mcs200_comparison.json results/griddle/mcs200_comparison.json
```

[Full report](../results/griddle/mcs200_comparison.json) ·
[Summary](../results/griddle/mcs200_summary.json). The legacy `mcs-10` label
preserves the simulation seed; the actual rollout budget is 200 in the parameters.

## Sol routing experiment

Sol uses `rules-v1`, medium reasoning, an 8,192-token completion cap and a
180-second request timeout. Both conditions reuse connections; the tool budget
remains 10 rollouts per square and one search call per move. These reasoning
settings introduce additional compute compared with the earlier models.

The [OpenRouter run](../results/griddle/llm_sol_comparison.json) was interrupted
to switch to direct OpenAI. Its two completed seed-0 games scored 72 without
tools (1,684.87 seconds, $0.482160 reported) and 58 with tools (185.42 seconds,
$0.083206 reported). These are single-game results, not three-seed means.
The interrupted seed-1 game is not scored, and its usage is not included in
those completed-game costs.

Run the direct route with an `OPENAI_API_KEY`:

```bash
./scripts/compare_griddle_llm.sh configs/griddle/llm_sol_openai_comparison.json results/griddle/llm_sol_openai_comparison.json
```

The [direct OpenAI report](../results/griddle/llm_sol_openai_comparison.json)
is checkpointed after each game; check `complete` before interpreting it as
a finished experiment. Direct API usage does not report dollar costs through
this adapter; missing costs must not be treated as zero. Changing provider
does not guarantee lower latency. A single opening-position probe took 12.71
seconds directly versus 17.75 seconds through OpenRouter, but generated 126
versus 203 reasoning tokens, so this does not isolate serving speed.

## References

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenRouter tool calling](https://openrouter.ai/docs/guides/features/tool-calling)
- [GPT-4o-mini on OpenRouter](https://openrouter.ai/openai/gpt-4o-mini)
- [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)
- [General Griddle benchmarking](griddle_benchmarks.md)
