# StadiumPulse Marshal — User Guide

**Version 1.0.0 · Google Cloud Rapid Agent Hackathon (AT-Hack0025) · T6 Dynatrace**

StadiumPulse Marshal is an AIOps agent for 2026 World Cup matchday operations.
It watches matchday digital systems (ticket scanning, payments, app backends,
networks), uses Dynatrace Davis AI to localise the *causal* root of a problem,
correlates it with where you are in the match timeline, and proposes ranked
remediation runbooks that an SRE approves with one click.

---

## Contents
1. Concepts
2. Running the app
3. The console, screen by screen
4. Triaging an incident (step by step)
5. Approving and applying a remediation
6. Configuring guardrails
7. Mobile use
8. Live vs mock mode
9. Troubleshooting

---

## 1. Concepts

| Term | Meaning |
|---|---|
| **Problem** | A Dynatrace-detected incident (e.g. payment latency spike). |
| **Davis AI root-cause** | Dynatrace's *causal* localisation of the entity actually responsible — not just correlated symptoms. |
| **Matchday phase** | Where the match is (gates open, kickoff, half-time…). Each phase has an expected load multiplier; surges explain many incidents. |
| **Agent analysis** | The Gemini/ADK agent's summary, confidence, and reasoning, grounding the LLM in real Dynatrace facts. |
| **Remediation** | A proposed fix with a numbered runbook, risk level and estimated MTTR. |
| **Human-in-the-loop (HITL)** | You approve, reject, then apply. High-impact actions always require a person. |
| **Guardrail** | Optional auto-approval of low-risk actions within a severity ceiling. |

---

## 2. Running the app

### 2.1 Backend (API + agent)
```bash
cd backend
pip install -e .            # or: pip install -e .[agent] for the live Gemini SDK
python -m uvicorn app.main:app --port 8000
```
The backend prints its mode on start, e.g.
`StadiumPulse Marshal v1.0.0 started (data_source=mock, agent=mock)`.

### 2.2 Frontend
For development with hot reload:
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to :8000
```
For a single-origin build (the backend serves the UI):
```bash
cd frontend && npm run build
# then open http://localhost:8000  (backend serves frontend/dist)
```

> With no credentials the app runs fully on the **mock matchday scenario**, so
> you can explore every screen immediately.

---

## 3. The console, screen by screen

![Triage view](screenshots/01-console-triage.svg)

*Figure 1.* The console has three regions:

1. **Top bar** — product identity and a **mode badge** showing the data source
   (`MOCK` / `LIVE`) and agent backend (`mock` / `gemini`).
2. **Live problem feed** (left) — every problem, newest-first, with a severity
   tag, matchday phase, ID and status. The count pill shows open problems.
3. **Detail** (right) — for the selected problem: matchday-timeline correlation,
   problem context, the Davis AI root-cause tree, the agent analysis, the
   remediation recommendations, settings, and the audit log.

---

## 4. Triaging an incident (step by step)

1. **Open the console.** The first open problem is selected automatically.
2. **Read the impact line** under the title (e.g. *"Concession payments failing
   for ~12% of fans at half-time"*).
3. **Check the timeline.** The highlighted (green) bar is the current matchday
   phase. A tall bar means a big expected load multiplier — context for why a
   surge-driven incident is happening now (half-time is ×5.0).
4. **Inspect the root cause.** The tree descends from the symptom service to the
   flagged **ROOT CAUSE** entity. In the demo scenario that is
   `payments-postgres` at **91% confidence** — a connection-pool exhaustion.
5. **Read the agent analysis.** The agent states the root cause in plain
   language and explains *why* (half-time surge saturation, not a code
   regression), with a confidence score.

---

## 5. Approving and applying a remediation

![Remediation approval](screenshots/02-remediation-approval.svg)

*Figure 2.* Each recommendation shows a title, risk tag, estimated MTTR and a
numbered runbook.

1. **Review the runbook.** Steps are concrete and ordered.
2. *(Optional)* **Add a decision note**, e.g. "surge confirmed on East kiosks".
   It is stored on the audit record.
3. **Approve** or **Reject.** Rejecting records the decision and stops there.
4. After approval an **Apply runbook** button appears. Click it to mark the
   action executed (in live mode this dispatches the runbook to your automation
   backend). The card shows **Runbook applied**.
5. **Audit log.** Every decision — who, what, when, why, and whether it was
   automatic — is appended at the bottom of the detail pane.

---

## 6. Configuring guardrails

In the **Operator & guardrails** panel:

1. **Operator identity** — the name recorded on each decision. Set it to your
   handle before approving.
2. **Auto-approve low-risk actions** — when enabled, LOW-risk actions within the
   severity ceiling are applied automatically (shown as **AUTO_APPROVED**), so
   your attention is reserved for high-impact calls. The toggle is sent to the
   backend immediately. High-risk actions are *never* auto-approved.

---

## 7. Mobile use

![Mobile](screenshots/03-mobile.svg)

*Figure 3.* On a phone the layout collapses to a single column:

1. Tap the **☰ menu** in the top bar to slide out the problem feed.
2. Tap a problem; the drawer closes and the detail fills the screen.
3. All actions — approve, reject, apply, guardrails — are touch-friendly.

---

## 8. Live vs mock mode

The mode badge tells you which data path is active. To go live, set credentials
(see `ACCESS_REQUIREMENTS.md`) and `USE_MOCKS=false`. Each subsystem falls back
independently: with only Dynatrace credentials you get live observability and a
mock agent, and vice-versa.

---

## 9. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Badge stuck on `MOCK` after adding creds | Ensure `USE_MOCKS=false` and restart the backend. Check `/api/v1/config`. |
| Empty problem feed | Backend not reachable; confirm it runs on :8000 and the proxy/origin is correct. |
| `Gemini init failed … falling back to mock` | The `google-genai` SDK isn't installed or creds are invalid. Install `.[agent]` and verify the key/project. |
| Apply button missing | The action must be **approved** first (or auto-approved by a guardrail). |
| Execute returns 409 | Same — approve before applying. |
