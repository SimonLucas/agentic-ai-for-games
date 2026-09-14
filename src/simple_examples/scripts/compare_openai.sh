#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

unset VIRTUAL_ENV

MODEL="${OPENAI_MODEL:-gpt-5-mini}" \
  uv run python src/simple_examples/model_client.py --compare \
  "${@:-What is 23 multiplied by 19, and how many times does e occur in Tennessee?}"
