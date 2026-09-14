#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Backend and model are chosen in JSON. The harness loads the ignored root .env.
config="${1:-configs/griddle/llm_comparison.json}"
output="${2:-results/griddle/llm_comparison.json}"
unset VIRTUAL_ENV
uv run python -m game_agent.griddle.benchmark --config "$config" --output "$output"
