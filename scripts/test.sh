#!/usr/bin/env bash
# Run the backend test suite with coverage.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
python -m pytest --cov=app --cov-report=term-missing
