"""Venue directory endpoints.

Exposes the venues a principal may operate within. Cross-venue (platform)
principals see the whole estate; venue-scoped principals see only their own.
This backs the console's venue switcher with real, authorization-aware data
rather than a hardcoded client list.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.auth import get_principal
from app.models.venue import Venue
from app.rbac.policy import Principal

router = APIRouter(prefix="/api/v1/venues", tags=["venues"])

# Demo venue directory (mirrors the frontend seed). In a live deployment this
# would come from a repository / config service.
_VENUES: list[Venue] = [
    Venue(id="venue_arena_north", name="Arena North", city="Manchester",
          country="GB", capacity=61000, timezone="Europe/London"),
    Venue(id="venue_olympic_park", name="Olympic Park Stadium", city="London",
          country="GB", capacity=80000, timezone="Europe/London"),
]


def all_venues() -> list[Venue]:
    return list(_VENUES)


@router.get("")
async def list_venues(
    request: Request,
    principal: Principal = Depends(get_principal),
) -> dict:
    """List venues visible to the caller (scoped by the principal)."""
    visible = [v for v in _VENUES if principal.can_access_venue(v.id)]
    return {
        "venues": [v.model_dump() for v in visible],
        "all_venues": principal.all_venues,
    }
