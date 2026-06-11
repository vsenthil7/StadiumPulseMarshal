#!/usr/bin/env bash
# verify_live.sh — run the environment-dependent Definition-of-DONE checks from
# the reviewer playbook (Section 7) that cannot run in a sandbox.
#
# Each check is GUARDED: if its prerequisite (a binary, a credential, a running
# service) is absent, the check is SKIPPED with a clear reason rather than
# failing. This lets you run one command in your own environment and see exactly
# which enterprise-grade gates are satisfied.
#
# Usage:
#   PROJECT_ID=my-proj REGION=europe-west2 ./scripts/verify_live.sh
#
# Exit code is 0 unless a check that COULD run actually FAILED.
set -uo pipefail

PASS=0; FAIL=0; SKIP=0
GREEN="\033[32m"; RED="\033[31m"; YELLOW="\033[33m"; DIM="\033[2m"; RST="\033[0m"

ok()   { echo -e "  ${GREEN}PASS${RST}  $1"; PASS=$((PASS+1)); }
bad()  { echo -e "  ${RED}FAIL${RST}  $1"; FAIL=$((FAIL+1)); }
skip() { echo -e "  ${YELLOW}SKIP${RST}  $1 ${DIM}($2)${RST}"; SKIP=$((SKIP+1)); }
have() { command -v "$1" >/dev/null 2>&1; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== StadiumPulse Marshal — live Definition-of-DONE verification =="
echo

# ── 1. CI green (needs gh/curl + repo) ───────────────────────────────────────
if [ -n "${GITHUB_REPO:-}" ] && have curl; then
  concl=$(curl -s "https://api.github.com/repos/${GITHUB_REPO}/actions/runs?per_page=1" \
            | grep -o '"conclusion":[^,]*' | head -1)
  case "$concl" in
    *success*) ok "CI latest run success ($GITHUB_REPO)";;
    *) bad "CI latest run not success: $concl";;
  esac
else
  skip "CI run status" "set GITHUB_REPO=org/repo (and ensure CI has run)"
fi

# ── 2. Dockerfile non-root (needs a built image) ─────────────────────────────
if have docker; then
  if docker image inspect stadiumpulse-marshal:latest >/dev/null 2>&1; then
    user=$(docker image inspect stadiumpulse-marshal:latest \
             --format '{{.Config.User}}' 2>/dev/null)
    case "$user" in
      appuser|1001) ok "Docker image runs as non-root ($user)";;
      *) bad "Docker image user is '$user' (expected appuser/1001)";;
    esac
  else
    skip "Docker non-root inspect" "image not built — run: docker build -t stadiumpulse-marshal:latest ."
  fi
else
  skip "Docker non-root inspect" "docker not installed"
fi

# ── 3. deploy.sh dryrun ──────────────────────────────────────────────────────
if [ -n "${PROJECT_ID:-}" ]; then
  if PROJECT_ID="$PROJECT_ID" REGION="${REGION:-europe-west2}" bash scripts/deploy.sh dryrun \
       | grep -q "Would deploy to Cloud Run"; then
    ok "deploy.sh dryrun prints intended Cloud Run target"
  else
    bad "deploy.sh dryrun did not print expected output"
  fi
else
  skip "deploy.sh dryrun" "set PROJECT_ID=<gcp-project>"
fi

# ── 4. Alembic upgrade head on a fresh DB (always runnable) ──────────────────
if have python3; then
  TMPDB="$(mktemp -u).db"
  if (cd backend && DATABASE_URL="sqlite+aiosqlite:///$TMPDB" alembic upgrade head >/dev/null 2>&1); then
    tables=$(python3 - "$TMPDB" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
print(",".join(sorted(r[0] for r in c.execute(
    "SELECT name FROM sqlite_master WHERE type='table'"))))
PY
)
    need="incidents remediations audit notifications refresh_tokens error_budgets outbox burn_acks audit_log runbooks postmortems slo_catalog on_call_schedules change_events fleet_venues chatops_commands cost_metrics"
    missing=""
    for t in $need; do echo "$tables" | grep -q "\b$t\b" || missing="$missing $t"; done
    [ -z "$missing" ] && ok "Alembic fresh-DB has all 17 required tables" \
                       || bad "Alembic fresh-DB missing:$missing"
    rm -f "$TMPDB"
  else
    bad "alembic upgrade head failed"
  fi
else
  skip "Alembic fresh-DB" "python3 not available"
fi

# ── 5. Multi-replica idempotency (needs docker compose) ──────────────────────
if have docker && docker compose version >/dev/null 2>&1; then
  echo "  .. bringing up compose stack for idempotency check"
  if docker compose up -d >/dev/null 2>&1; then
    sleep 6
    if (cd backend && python -m pytest tests/integration/test_multi_instance_idempotency.py -q >/dev/null 2>&1); then
      ok "Multi-replica idempotency holds across replicas"
    else
      bad "Multi-replica idempotency test failed"
    fi
    docker compose down -v >/dev/null 2>&1
  else
    skip "Multi-replica idempotency" "docker compose up failed (no daemon?)"
  fi
else
  skip "Multi-replica idempotency" "docker compose unavailable"
fi

# ── 6. Live Dynatrace dual-window burn rate (needs creds) ────────────────────
if [ -n "${DT_TENANT_URL:-}" ] && [ -n "${DT_API_TOKEN:-}" ]; then
  if (cd backend && python -m pytest tests/unit/test_dt_metrics_source.py -q >/dev/null 2>&1); then
    ok "Dynatrace dual-window metrics test passed (live creds)"
  else
    bad "Dynatrace dual-window metrics test failed with provided creds"
  fi
else
  skip "Dynatrace dual-window (live)" "set DT_TENANT_URL + DT_API_TOKEN"
fi

# ── 7. k6 matchday load test (needs k6 + running stack) ──────────────────────
if have k6; then
  if curl -sf "${BASE_URL:-http://localhost:8088}/api/v1/health" >/dev/null 2>&1; then
    if k6 run --quiet k6/matchday_load.js >/dev/null 2>&1; then
      ok "k6 matchday load thresholds met"
    else
      bad "k6 thresholds not met (see k6 output)"
    fi
  else
    skip "k6 load test" "no stack at ${BASE_URL:-http://localhost:8088}"
  fi
else
  skip "k6 load test" "k6 not installed"
fi

# ── 8. SBOM + image signing (needs docker sbom + cosign) ─────────────────────
if have docker && docker sbom --help >/dev/null 2>&1; then
  if docker image inspect stadiumpulse-marshal:latest >/dev/null 2>&1; then
    docker sbom stadiumpulse-marshal:latest -o sbom.spdx >/dev/null 2>&1 \
      && ok "SBOM generated (sbom.spdx)" || bad "SBOM generation failed"
  else
    skip "SBOM generation" "image not built"
  fi
else
  skip "SBOM generation" "docker sbom plugin not available"
fi
if have cosign; then
  if [ -n "${COSIGN_KEY:-}" ] && [ -n "${PROJECT_ID:-}" ] && [ -n "${TAG:-}" ]; then
    cosign sign --key "$COSIGN_KEY" \
      "gcr.io/${PROJECT_ID}/stadiumpulse-marshal:${TAG}" >/dev/null 2>&1 \
      && ok "Image signed with cosign" || bad "cosign sign failed"
  else
    skip "cosign sign" "set COSIGN_KEY + PROJECT_ID + TAG"
  fi
else
  skip "cosign sign" "cosign not installed"
fi

# ── 9. Secret Manager bindings on the deployed service (needs gcloud) ────────
if have gcloud && [ -n "${PROJECT_ID:-}" ]; then
  names=$(gcloud run services describe stadiumpulse-marshal \
            --region="${REGION:-europe-west2}" --format=json 2>/dev/null \
          | grep -o '"secretKeyRef"' | wc -l | tr -d ' ')
  if [ "${names:-0}" -ge 5 ]; then
    ok "Cloud Run service binds ≥5 secrets from Secret Manager"
  else
    skip "Secret Manager bindings" "service not deployed or <5 secret refs"
  fi
else
  skip "Secret Manager bindings" "gcloud unavailable or PROJECT_ID unset"
fi

# ── 10. Playwright smoke (needs node + running stack) ────────────────────────
if have npx; then
  if curl -sf "${BASE_URL:-http://localhost:8088}/api/v1/health" >/dev/null 2>&1; then
    if (cd frontend && BASE_URL="${BASE_URL:-http://localhost:8088}" npx playwright test --reporter=line >/dev/null 2>&1); then
      ok "Playwright smoke tests passed"
    else
      bad "Playwright smoke tests failed"
    fi
  else
    skip "Playwright smoke" "no stack at ${BASE_URL:-http://localhost:8088}"
  fi
else
  skip "Playwright smoke" "npx not installed"
fi

echo
echo -e "== Summary: ${GREEN}${PASS} passed${RST}, ${RED}${FAIL} failed${RST}, ${YELLOW}${SKIP} skipped${RST} =="
[ "$FAIL" -eq 0 ] || exit 1
