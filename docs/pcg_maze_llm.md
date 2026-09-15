# One-shot LLM maze generation

This experiment compares three generators on the same ordered set of generation
seeds:

- random walls;
- the `(1+1)` evolutionary baseline; and
- an LLM that generates a complete maze in one request, without tools.

The one-shot condition is a useful contrast with the iterative edit-and-evaluate
approach in Jiang et al.'s
[*Agentic PCG*](https://zehua-jiang.github.io/AgenticPCG/)
([local PDF](papers/Agentic_PCG_Paper.pdf)). Our agentic maze version is
described in [its own guide](pcg_maze_agentic.md).

Run the reference configuration from the repository root:

```bash
./scripts/compare_maze_generators.sh
```

It writes a checkpointed JSON report, a CSV summary, and a PNG contact sheet in
`results/pcg/`. The default hosted model is GPT-4o-mini through OpenRouter, so
the ignored root `.env` must contain `OPENROUTER_API_KEY`.

The LLM receives the grid dimensions, a diversity seed, and the canonical text
of every valid maze it has already made in the set. It is asked to maximise the
shortest route while choosing a visibly and structurally different topology.
Every item uses a fresh conversation and exactly one model request. There is no
repair request or fallback maze. Invalid JSON, invalid dimensions, blocked
endpoints and disconnected mazes are reported as failed generations.

The default configuration asks the provider to enforce a JSON Schema within
that request. This constrains the row count and alphabet without supplying maze
content or search. Set `structured_output` to `false` for a backend or model
that lacks JSON Schema support. Connectivity is always checked locally after
generation; schema conformance alone cannot guarantee a playable route.

The response also includes an in-grid route certificate: cells marked `P` must
form an orthogonally connected route from the start to the goal. The harness
checks this route and then converts `P` to an ordinary passage. Requiring the
model to construct this evidence in its single answer strengthens the task
specification; the certificate is not a search tool and does not contribute to
maze fitness.

The seed is a generation brief included in the prompt. It does not make a
hosted model deterministic. Repeated benchmark runs may therefore differ even
at the same temperature.

## Measures

Fitness is the shortest top-left-to-bottom-right route length. Diversity is
reported over valid mazes only:

| Measure | Interpretation |
|---|---|
| `gzip_bytes` | Size of the whole ordered text set compressed with gzip; larger suggests less repeated structure |
| `gzip_ratio` | Compressed bytes divided by uncompressed bytes |
| `unique_maze_count` | Exact duplicates detected by canonical text |
| `mean_pairwise_hamming` | Mean fraction of cells that differ between pairs |

Gzip size is a useful aggregate measure, but it is sensitive to encoding, set
size, ordering and wall density. Compare absolute byte counts only when maze
dimensions, number of valid mazes, canonical encoding and seed order match.
Hamming distance and wall fraction make the result easier to interpret. Neither
measure captures perceptual or gameplay diversity completely.

The contact sheet uses dark walls, pale passages, a blue shortest path, a green
start and a red goal. It makes repeated motifs, density differences and failure
modes visible alongside the numerical measures. If the model returned a grid
that failed validation, the sheet still shows it with a red border and label;
orange cells show its unstripped `P` route annotation.

For a stronger one-shot model through the OpenAI API, run:

```bash
./scripts/compare_maze_generators.sh \
  configs/pcg/maze_gpt5_mini_comparison.json \
  results/pcg/maze_gpt5_mini_comparison.json
```

This configuration uses `gpt-5-mini` with low reasoning, an 8,192-token ceiling, and omits
`temperature`, which older GPT-5 models do not accept.

## Initial results

The six-seed GPT-5-mini run completed on 14 September 2026:

| Generator | Valid | Mean fitness | Max | Gzip bytes | Gzip ratio | Mean Hamming | Seconds/maze |
|---|---:|---:|---:|---:|---:|---:|---:|
| Random, 25% walls | 4/6 | 18.0 | 18 | 117 | 0.280 | 0.304 | <0.01 |
| Evolution, 2,000 attempts | 6/6 | 39.7 | 44 | 186 | 0.296 | 0.463 | 0.08 |
| GPT-5-mini, one shot | 6/6 | 24.0 | 36 | 104 | 0.166 | 0.506 | 40.65 |

All six GPT-5-mini mazes were unique and playable. Four had only the minimum
Manhattan route length of 18; two scored 36. The contact sheet shows that the
model favored large, regular bands. This explains the apparently conflicting
diversity signals: many cells differ between pairs, producing high Hamming
distance, but the repeated geometric motifs compress very efficiently. The
evolutionary mazes achieved higher fitness and were less compressible.

- [Full GPT-5-mini report](../results/pcg/maze_gpt5_mini_comparison.json)
- [GPT-5-mini contact sheet](../results/pcg/maze_gpt5_mini_comparison.png)
- [CSV summary](../results/pcg/maze_gpt5_mini_comparison_summary.csv)

An earlier GPT-4o-mini experiment returned rectangular grids that looked like
mazes but failed reachability or endpoint validation. Those failed grids remain
visible in its contact sheet, rather than being replaced by blank placeholders:

- [GPT-4o-mini report](../results/pcg/maze_llm_comparison.json)
- [GPT-4o-mini contact sheet](../results/pcg/maze_llm_comparison.png)
