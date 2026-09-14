#!/usr/bin/env bash
set -euo pipefail

config="${1:-configs/pcg/maze_llm_comparison.json}"
output="${2:-results/pcg/maze_llm_comparison.json}"
output_dir="$(dirname "$output")"
stem="$(basename "$output" .json)"

uv run benchmark-maze-generators \
  --config "$config" \
  --output "$output" \
  --summary-csv "$output_dir/${stem}_summary.csv" \
  --sheet "$output_dir/${stem}.png"
