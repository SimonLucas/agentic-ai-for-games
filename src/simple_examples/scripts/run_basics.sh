#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."

unset VIRTUAL_ENV

uv run python src/simple_examples/direct_python.py
echo
uv run python src/simple_examples/mcp_client.py
