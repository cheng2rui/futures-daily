#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${PYTHONPATH:-.}"
export FUTURES_DAILY_DB="${FUTURES_DAILY_DB:-tmp/test.db}"

python3 -m compileall app tests
for t in tests/test_*.py; do
  .venv/bin/python "$t"
done
npm run build --prefix frontend
