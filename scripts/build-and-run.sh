#!/usr/bin/env bash
# Build the frontend and serve API + UI single-origin on :8000.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
( cd "$ROOT/frontend" && npm install && npm run build )
cd "$ROOT/backend"
pip install -e . >/dev/null
exec python -m uvicorn app.main:app --port 8000
