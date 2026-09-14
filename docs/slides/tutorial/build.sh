#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 refresh_snippets.py
mkdir -p build
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=build tutorial.tex > build/compile-pass1.log
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=build tutorial.tex > build/compile-pass2.log
cp build/tutorial.pdf tutorial.pdf
printf 'Built %s/tutorial.pdf\n' "$PWD"
