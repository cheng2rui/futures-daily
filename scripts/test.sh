#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${PYTHONPATH:-.}"
export FUTURES_DAILY_DB="${FUTURES_DAILY_DB:-tmp/test.db}"

python3 -m compileall app tests
.venv/bin/python tests/test_gap_analysis.py
.venv/bin/python tests/test_notify.py
.venv/bin/python tests/test_akshare_source.py
npm run build --prefix frontend
