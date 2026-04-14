#!/bin/zsh
set -euo pipefail

cd "/Users/dave/Documents/Coding/Quality Review Agent"

if [[ -f ".env" ]]; then
  set -a
  source ".env"
  set +a
fi

pkill -f "python3 -m quality_review_agent serve" 2>/dev/null || true
sleep 1

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "GEMINI_API_KEY is not set."
  echo "Run: ./set-gemini-key.sh"
  exit 1
fi

PYTHONPATH=src python3 -m quality_review_agent serve
