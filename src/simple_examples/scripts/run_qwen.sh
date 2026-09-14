#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434/v1}"
QWEN_MODEL="${QWEN_MODEL:-qwen2.5:3b}"

if ! curl --silent --fail "${OLLAMA_BASE_URL%/v1}/api/tags" >/dev/null; then
  echo "Cannot reach Ollama at ${OLLAMA_BASE_URL%/v1}." >&2
  echo "Start it in another terminal with: ollama serve" >&2
  exit 1
fi

if ! ollama show "$QWEN_MODEL" >/dev/null 2>&1; then
  echo "The Ollama model '$QWEN_MODEL' is not installed." >&2
  echo "Install it with: ollama pull $QWEN_MODEL" >&2
  echo "Or list installed models with: ollama list" >&2
  exit 1
fi

# Use the repository environment even if another environment is active.
unset VIRTUAL_ENV

MODEL="$QWEN_MODEL" \
BASE_URL="$OLLAMA_BASE_URL" \
API_KEY="ollama" \
  uv run python src/simple_examples/model_client.py "${@:-What is 23 multiplied by 19, and how many times does e occur in Tennessee?}"
