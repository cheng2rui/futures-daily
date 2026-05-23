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
.venv/bin/python tests/test_ask_daily.py
.venv/bin/python tests/test_tomorrow_watch.py
.venv/bin/python tests/test_push_digest.py
.venv/bin/python tests/test_history_factors.py
.venv/bin/python tests/test_history_backfill.py
npm run build --prefix frontend
