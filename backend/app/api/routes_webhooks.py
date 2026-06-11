"""Webhook subscription management routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.auth import require_permission
from app.core.context import AppContext
from app.core.errors import NotFoundError
from app.events.bus import EventType
from app.models.webhook import WebhookSubscription
from app.rbac.policy import Permission

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


def _ctx(request: Request) -> AppContext:
    return request.app.state.ctx


class CreateWebhookRequest(BaseModel):
    url: str
    event_types: list[EventType] = Field(default_factory=list)
    description: str = ""


class WebhookResponse(BaseModel):
    webhook: WebhookSubscription


class WebhookListResponse(BaseModel):
    webhooks: list[WebhookSubscription]


@router.get("", response_model=WebhookListResponse)
async def list_webhooks(
    request: Request,
    _p=Depends(require_permission(Permission.WEBHOOK_ADMIN)),
) -> WebhookListResponse:
    ctx = _ctx(request)
    return WebhookListResponse(webhooks=ctx.webhooks.list())


@router.post("", response_model=WebhookResponse, status_code=201)
async def create_webhook(
    request: Request,
    body: CreateWebhookRequest,
    _p=Depends(require_permission(Permission.WEBHOOK_ADMIN)),
) -> WebhookResponse:
    ctx = _ctx(request)
    sub = WebhookSubscription(
        url=body.url, event_types=body.event_types, description=body.description
    )
    ctx.webhooks.add(sub)
    return WebhookResponse(webhook=sub)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    request: Request,
    webhook_id: str,
    _p=Depends(require_permission(Permission.WEBHOOK_ADMIN)),
) -> None:
    ctx = _ctx(request)
    if not ctx.webhooks.delete(webhook_id):
        raise NotFoundError("Webhook not found")


@router.get("/dead-letter/list", response_model=WebhookListResponse)
async def list_dead_lettered(
    request: Request,
    _p=Depends(require_permission(Permission.WEBHOOK_ADMIN)),
) -> WebhookListResponse:
    ctx = _ctx(request)
    return WebhookListResponse(webhooks=ctx.webhooks.list_dead_lettered())


@router.post("/{webhook_id}/redrive", response_model=WebhookResponse)
async def redrive_webhook(
    request: Request,
    webhook_id: str,
    _p=Depends(require_permission(Permission.WEBHOOK_ADMIN)),
) -> WebhookResponse:
    ctx = _ctx(request)
    sub = await ctx.webhook_dispatcher.redrive(webhook_id)
    if sub is None:
        raise NotFoundError("Webhook not found")
    return WebhookResponse(webhook=sub)
