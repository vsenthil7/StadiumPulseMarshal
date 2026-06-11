
---

## Round 16 — Rotation pools, burn ack/silence workflow, selector preview, +depth

### Track AO — rotating schedule with real per-tier pools
| # | Sprint | Status |
|---|--------|--------|
| AO1 | default_oncall_pools(): 2+ engineers per tier; build rotating source | ⚪ |
| AO2 | Config: SHIFT_HOURS; use rotation when pools present | ⚪ |
| AO3 | /oncall exposes pool + position + who's next per tier | ⚪ |
| AO4 | On-call page: rotation roster + next-up | ⚪ |
| AO5 | Tests: rotation resolves per shift; /oncall pool shape | ⚪ |

### Track AP — burn-alert acknowledge / silence workflow
| # | Sprint | Status |
|---|--------|--------|
| AP1 | BurnAckStore: ack (who/when) + silence (until) per (slo,severity) | ⚪ |
| AP2 | Burn eval marks acked/silenced; silence suppresses notification | ⚪ |
| AP3 | POST /slo/burn-alerts/{slo}/ack + /silence (responder+; audited) | ⚪ |
| AP4 | Frontend: ack/silence buttons on banner; acked styling | ⚪ |
| AP5 | Tests: ack records, silence suppresses notify, expiry, RBAC | ⚪ |

### Track AQ — metric-selector validation/preview
| # | Sprint | Status |
|---|--------|--------|
| AQ1 | GET /slo/{id}/metric-preview: resolved selector + sample series | ⚪ |
| AQ2 | Validate selector (DT live or synthetic), return points + window rates | ⚪ |
| AQ3 | Tests: preview returns selector+series; bad SLO 404; scoped | ⚪ |

### Track AR — supporting depth
| # | Sprint | Status |
|---|--------|--------|
| AR1 | Burn alert list summary: acked/silenced counts | ⚪ |
| AR2 | Tests + tsc/build | ⚪ |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| AS1 | Full backend suite + frontend tsc/build + node unit green | ⚪ |
| AS2 | Docs + package | ⚪ |
