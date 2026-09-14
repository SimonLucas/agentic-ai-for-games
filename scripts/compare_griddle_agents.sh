#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Optional arguments: config path and output path, both relative to the repo root.
config="${1:-configs/griddle/comparison.json}"
output="${2:-results/griddle/comparison.json}"

unset VIRTUAL_ENV
uv run python -m game_agent.griddle.benchmark --config "$config" --output "$output"
