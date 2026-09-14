#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

if [[ -z "${OPENROUTER_API_KEY:-}" || "${OPENROUTER_API_KEY}" == "replace-me" ]]; then
  echo "Set OPENROUTER_API_KEY in the repository-root .env file." >&2
  exit 1
fi

unset VIRTUAL_ENV

MODEL="${OPENROUTER_MODEL:-openai/gpt-4o-mini}" \
BASE_URL="https://openrouter.ai/api/v1" \
API_KEY="$OPENROUTER_API_KEY" \
  uv run python src/simple_examples/model_client.py --compare "${@:-What is 23 multiplied by 19, and how many times does e occur in Tennessee?}"
