"""Entity → venue resolution.

SLO budgets, trends and analytics are keyed by *entity* (a service/host/db), not
directly by venue. To partition those domains by venue we need a mapping from an
entity id to the venue that owns it. This resolver builds and caches that map
from the active observability source's entities, and is rebuilt when the
scenario changes (the map is cheap and small).
"""
from __future__ import annotations

from app.models.domain import Entity


class EntityVenueResolver:
    def __init__(self) -> None:
        self._map: dict[str, str] = {}
        self._loaded = False

    def load(
        self,
        entities: list[Entity],
        zone_mapping: dict[str, str] | None = None,
        zone_tag_key: str = "mz",
    ) -> None:
        """Build the entity→venue map.

        Venue is resolved per entity in priority order:
        1. an explicit ``venue_id`` on the entity (demo / already-tagged);
        2. a management-zone tag (e.g. ``mz:Arena North``) mapped to a venue via
           ``zone_mapping`` — the realistic Dynatrace path, where venue ownership
           lives in a management zone rather than a bespoke field.
        """
        zone_mapping = zone_mapping or {}
        prefix = f"{zone_tag_key}:"
        result: dict[str, str] = {}
        for e in entities:
            venue = e.venue_id
            if venue is None:
                for tag in e.tags:
                    if tag.startswith(prefix):
                        zone = tag[len(prefix):]
                        venue = zone_mapping.get(zone)
                        if venue:
                            break
            if venue:
                result[e.id] = venue
        self._map = result
        self._loaded = True

    def invalidate(self) -> None:
        self._loaded = False
        self._map = {}

    @property
    def loaded(self) -> bool:
        return self._loaded

    def venue_for(self, entity_id: str | None) -> str | None:
        if entity_id is None:
            return None
        return self._map.get(entity_id)

    def venue_for_any(self, entity_ids: list[str]) -> str | None:
        """First resolvable venue among the given entity ids (for SLOs/records
        that reference one or more entities)."""
        for eid in entity_ids:
            v = self._map.get(eid)
            if v:
                return v
        return None
