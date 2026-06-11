
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

---

## Round 17 — Shared ack store, un-ack/expiry, on-call ack view, burn audit history

### Track AT — KV-backed (shared) ack/silence store
| # | Sprint | Status |
|---|--------|--------|
| AT1 | SharedBurnAckStore: single-doc JSON in KV (Memory/Redis), async | ⚪ |
| AT2 | ack/silence/is_silenced/ack_for parity with in-proc store | ⚪ |
| AT3 | ack TTL/expiry; silence expiry; prune on read | ⚪ |
| AT4 | Context uses shared store (KV); burn eval awaits async lookups | ⚪ |
| AT5 | Tests: two stores sharing one KV see each other's ack/silence | ⚪ |

### Track AU — un-ack / un-silence + ack expiry
| # | Sprint | Status |
|---|--------|--------|
| AU1 | DELETE ack + DELETE silence endpoints (responder+, audited) | ⚪ |
| AU2 | ack auto-expiry window (config); expired acks drop on read | ⚪ |
| AU3 | Frontend: un-ack/un-silence controls on banner | ⚪ |
| AU4 | Tests: un-ack clears, expiry drops, RBAC | ⚪ |

### Track AV — on-call page ack/silence state + counts
| # | Sprint | Status |
|---|--------|--------|
| AV1 | /oncall includes active acks/silences summary | ⚪ |
| AV2 | On-call page shows current acks/silences | ⚪ |
| AV3 | Tests + tsc/build | ⚪ |

### Track AW — burn-alert audit/history view
| # | Sprint | Status |
|---|--------|--------|
| AW1 | GET /slo/burn-events: burn.ack/.silence audit history (filter/paginate) | ⚪ |
| AW2 | Frontend: burn history on On-call (or Security) page | ⚪ |
| AW3 | Tests: history returns ack/silence events; scoped to admin/responder | ⚪ |

### Close-out
| # | Sprint | Status |
|---|--------|--------|
| AX1 | Full backend suite + frontend tsc/build + node unit green | ⚪ |
| AX2 | Docs + package | ⚪ |
