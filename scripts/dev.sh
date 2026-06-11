#!/usr/bin/env bash
# Run backend (API) and frontend (hot-reload) together for development.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

( cd "$ROOT/backend" && python -m uvicorn app.main:app --reload --port 8000 ) &
BACK=$!
( cd "$ROOT/frontend" && npm run dev ) &
FRONT=$!
trap 'kill $BACK $FRONT 2>/dev/null || true' EXIT
wait
