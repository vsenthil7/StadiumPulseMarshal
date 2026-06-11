"""ChatOps bridge models — Slack command/event payloads."""
from __future__ import annotations

from pydantic import BaseModel


class SlackCommand(BaseModel):
    """Incoming Slack slash-command payload (URL-encoded form → JSON)."""
    command: str
    text: str = ""
    user_id: str = ""
    user_name: str = ""
    channel_id: str = ""
    response_url: str = ""
