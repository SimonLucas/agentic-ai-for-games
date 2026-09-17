#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."

backend="${1:-openrouter}"
prompt="How many times does the letter r occur in the word strawberry?"

case "$backend" in
  openai|openrouter|qwen)
    exec "./src/simple_examples/scripts/compare_${backend}.sh" "$prompt"
    ;;
  *)
    echo "Usage: $0 [openai|openrouter|qwen]" >&2
    exit 2
    ;;
esac
