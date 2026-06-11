"""ChatOps: Slack slash commands for incident lookup + runbook execution.

  POST /api/v1/chatops/slack/command   — Slack slash commands (form-encoded)

Supported:
  /marshal status                 — open incidents
  /marshal incident <id>          — incident detail
  /marshal runbook <id>           — show runbook steps
  /marshal runbook <id> execute   — execute a runbook

HMAC signature verification is skipped when SLACK_SIGNING_SECRET is unset
(mock/demo mode), so the endpoint is always testable.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1/chatops", tags=["chatops"])


def _help() -> dict:
    return {
        "response_type": "ephemeral",
        "text": (
            "*StadiumPulse Marshal — Commands*\n"
            "`/marshal status` — open incidents\n"
            "`/marshal incident <id>` — incident detail\n"
            "`/marshal runbook <id>` — show runbook\n"
            "`/marshal runbook <id> execute` — execute runbook\n"
        ),
    }


@router.post("/slack/command")
async def slack_command(request: Request) -> JSONResponse:
    # Parse the urlencoded body directly so we don't depend on python-multipart.
    from urllib.parse import parse_qs

    raw = (await request.body()).decode("utf-8", "ignore")
    form = {k: v[0] for k, v in parse_qs(raw).items()}
    text = (form.get("text") or "").strip()
    ctx = request.app.state.ctx

    parts = text.split()
    sub = parts[0].lower() if parts else "help"

    if sub == "status":
        incidents = await ctx.repos.incidents.list(open_only=True, limit=5)
        lines = "\n".join(
            f"• `{i.id}` — {getattr(i.severity, 'value', i.severity)} — {i.title}"
            for i in incidents
        ) or "_No open incidents_"
        msg = {"response_type": "in_channel",
               "text": f"*StadiumPulse Marshal — Status*\n{lines}"}
    elif sub == "incident" and len(parts) > 1:
        inc = await ctx.repos.incidents.get(parts[1])
        if inc:
            msg = {"response_type": "in_channel",
                   "text": f"*Incident {inc.id}*\nVenue: {inc.venue_id}\n"
                           f"Severity: {getattr(inc.severity, 'value', inc.severity)}\n"
                           f"Open: {inc.is_open}"}
        else:
            msg = {"response_type": "ephemeral",
                   "text": f"Incident `{parts[1]}` not found."}
    elif sub == "runbook" and len(parts) > 1:
        rb = ctx.runbooks.get_runbook(parts[1])
        if rb:
            steps = "\n".join(f"{s.order}. {s.title}" for s in rb.steps)
            text_out = f"*Runbook: {rb.name}*\n{steps}"
            if len(parts) > 2 and parts[2] == "execute":
                exe = await ctx.runbooks.execute_runbook(parts[1], actor="slack")
                text_out += f"\n✓ Execution `{exe.id}` triggered — status: {exe.status}"
            msg = {"response_type": "in_channel", "text": text_out}
        else:
            msg = {"response_type": "ephemeral",
                   "text": f"Runbook `{parts[1]}` not found."}
    else:
        msg = _help()

    return JSONResponse(content=msg)
