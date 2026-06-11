"""Remediation dispatch — execute an approved RemediationAction against a real
automation backend.

Targets, in priority order, whichever is configured:
- Google Cloud Workflows (``CLOUD_WORKFLOWS_URL``)
- Ansible AWX job template (``ANSIBLE_AWX_URL`` + ``ANSIBLE_AWX_TOKEN``)
- A generic remediation webhook (``REMEDIATION_WEBHOOK_URL``)

When none is configured the dispatcher reports ``dispatched=False, target=none``
so the approval path still succeeds in mock/demo mode. An injected
``httpx.AsyncClient`` lets tests supply a ``MockTransport``; failures are caught
and returned as structured errors rather than raised.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

from app.core.logging import get_logger
from app.models.domain import RemediationAction

log = get_logger(__name__)


class RemediationDispatcher:
    def __init__(
        self,
        cloud_workflows_url: str | None = None,
        ansible_awx_url: str | None = None,
        ansible_awx_token: str | None = None,
        webhook_url: str | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._cw_url = cloud_workflows_url
        self._awx_url = ansible_awx_url
        self._awx_token = ansible_awx_token
        self._webhook_url = webhook_url
        self._http = http or httpx.AsyncClient(timeout=15.0)
        self._owns_http = http is None

    def _payload(self, action: RemediationAction, actor: str) -> dict[str, Any]:
        return {
            "action_id": action.id,
            "problem_id": action.problem_id,
            "title": action.title,
            "description": action.description,
            "runbook": action.runbook,
            "risk": getattr(action.risk, "value", action.risk),
            "actor": actor,
        }

    async def dispatch(self, action: RemediationAction, actor: str) -> dict[str, Any]:
        payload = self._payload(action, actor)
        if self._cw_url:
            return await self._cloud_workflows(payload)
        if self._awx_url and self._awx_token:
            return await self._ansible_awx(payload)
        if self._webhook_url:
            return await self._generic_webhook(payload)
        log.info("Remediation dispatch (no backend configured): %s", action.id)
        return {"dispatched": False, "target": "none",
                "detail": "no automation backend configured"}

    async def _cloud_workflows(self, payload: dict) -> dict[str, Any]:
        try:
            resp = await self._http.post(
                self._cw_url, json={"argument": json.dumps(payload)},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            log.info("Cloud Workflows execution started: %s",
                     data.get("name", "unknown"))
            return {"dispatched": True, "target": "cloud_workflows", "response": data}
        except Exception as exc:  # noqa: BLE001
            log.error("Cloud Workflows dispatch failed: %s", exc)
            return {"dispatched": False, "target": "cloud_workflows", "error": str(exc)}

    async def _ansible_awx(self, payload: dict) -> dict[str, Any]:
        template_id = os.getenv("ANSIBLE_AWX_TEMPLATE_ID", "1")
        url = f"{self._awx_url.rstrip('/')}/api/v2/job_templates/{template_id}/launch/"
        try:
            resp = await self._http.post(
                url, json={"extra_vars": json.dumps(payload)},
                headers={"Authorization": f"Bearer {self._awx_token}",
                         "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            log.info("AWX job launched: id=%s", data.get("id"))
            return {"dispatched": True, "target": "ansible_awx", "response": data}
        except Exception as exc:  # noqa: BLE001
            log.error("Ansible AWX dispatch failed: %s", exc)
            return {"dispatched": False, "target": "ansible_awx", "error": str(exc)}

    async def _generic_webhook(self, payload: dict) -> dict[str, Any]:
        try:
            resp = await self._http.post(
                self._webhook_url, json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            log.info("Webhook dispatch accepted: status=%s", resp.status_code)
            return {"dispatched": True, "target": "webhook",
                    "response": {"status": resp.status_code}}
        except Exception as exc:  # noqa: BLE001
            log.error("Webhook dispatch failed: %s", exc)
            return {"dispatched": False, "target": "webhook", "error": str(exc)}

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()


def build_remediation_dispatcher(settings,
                                 http: httpx.AsyncClient | None = None) -> RemediationDispatcher:
    return RemediationDispatcher(
        cloud_workflows_url=getattr(settings, "cloud_workflows_url", None),
        ansible_awx_url=getattr(settings, "ansible_awx_url", None),
        ansible_awx_token=getattr(settings, "ansible_awx_token", None),
        webhook_url=getattr(settings, "remediation_webhook_url", None),
        http=http,
    )
