#!/usr/bin/env bash
# Start Deep Research (local) on http://localhost:8080
set -e
cd "$(dirname "$0")/backend"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"
