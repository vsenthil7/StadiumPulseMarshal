#!/usr/bin/env bash
# Verify the shared rate limiter holds across BOTH replicas.
#
# With AUTH_RATE_LIMIT_PER_MINUTE=5 and a Redis-backed shared limiter, the 6th
# bad login from one client should be 429 even though nginx round-robins the
# requests across app1 and app2 — because both increment the SAME Redis window
# counter. If the limit were per-instance (in-process), 5 per replica = 10
# would be allowed and we'd never see a 429 within 6 attempts.
set -euo pipefail
LB="${LB:-http://localhost:8088}"
EMAIL="csutest@nope.demo"

echo "Hammering ${LB}/api/v1/auth/login (limit=5, shared)…"
codes=()
upstreams=()
for i in $(seq 1 8); do
  resp="$(curl -s -o /dev/null -D - -X POST "${LB}/api/v1/auth/login" \
    -H 'content-type: application/json' \
    -d "{\"email\":\"${EMAIL}\",\"password\":\"bad\"}")"
  code="$(printf '%s' "$resp" | awk 'NR==1{print $2}')"
  up="$(printf '%s' "$resp" | awk -F': ' 'tolower($1)=="x-upstream"{print $2}' | tr -d '\r')"
  codes+=("$code"); upstreams+=("$up")
  echo "  attempt $i -> HTTP $code (upstream ${up:-?})"
done

# Assert at least one 429 within 6 attempts (shared limit), and that requests
# were actually spread across two upstreams.
got429=false
for c in "${codes[@]:0:6}"; do [ "$c" = "429" ] && got429=true; done
uniq_up="$(printf '%s\n' "${upstreams[@]}" | sort -u | grep -c .)"

echo "----"
echo "distinct upstreams hit: ${uniq_up}"
if [ "$got429" = true ]; then
  echo "PASS: shared limit enforced across replicas (429 within 6 attempts)"
else
  echo "FAIL: no 429 within 6 attempts — limit may not be shared"; exit 1
fi
[ "${uniq_up}" -ge 2 ] && echo "PASS: load balanced across >=2 replicas" || \
  echo "WARN: only one upstream observed (LB may not have round-robined)"
