# Benchmark results

Keep the small reference reports cited in the tutorial under version control,
alongside their configurations and documented interpretation. Full JSON traces
preserve the evidence behind scores, tool use, timings and reported costs.
New files must be added and committed before a push includes them.

Put exploratory, partial or large runs in `results/local/`, which is ignored:

```bash
./scripts/compare_griddle_llm.sh configs/griddle/llm_comparison.json results/local/trial.json
```

Use distinct filenames for reference runs so historical evidence is not
overwritten. Check reports for credentials or private input before committing.
The current experiments contain game positions and model/tool responses;
credentials belong only in the ignored root `.env`.

See [the comparison tables and report links](../docs/griddle_llm.md).

The procedural maze reports and contact sheets are documented in
[the one-shot LLM maze comparison](../docs/pcg_maze_llm.md).

The GPT-4.1 experiment uses
[`llm_gpt41_comparison.json`](../configs/griddle/llm_gpt41_comparison.json).
Its agent labels deliberately retain the original `gpt4o-mini-*` names because
the harness hashes those labels into simulation seeds. The actual model is
`openai/gpt-4.1`, recorded in each agent's `params.model`; use that field when
identifying the model, rather than the legacy label. This preserves the search
randomness for the comparison without changing the harness.

The same label convention applies to
[`llm_sol_comparison.json`](../configs/griddle/llm_sol_comparison.json), which
selects `openai/gpt-5.6-sol` through OpenRouter with medium reasoning, no
temperature parameter, and an 8,192-token response limit. The larger limit
allows reasoning tokens as well as the final move. This is a different model
compute budget from the non-reasoning comparisons. Check `complete` before
treating a checkpoint as a finished experiment.

The [MCS-200 configuration](../configs/griddle/mcs200_comparison.json) similarly
retains the `mcs-10` seed label, but sets `rollouts_per_square` to **200**.
Tables identify the actual budget from parameters.
