#!/bin/zsh
set -euo pipefail

cd "/Users/dave/Documents/Coding/Quality Review Agent"

if [[ -f ".env" ]]; then
  set -a
  source ".env"
  set +a
fi

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "GEMINI_API_KEY is not set."
  echo "Run this first: ./set-gemini-key.sh"
  exit 1
fi

PYTHONPATH=src python3 scripts/watch_and_serve.py
