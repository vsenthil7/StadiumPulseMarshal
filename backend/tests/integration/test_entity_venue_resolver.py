"""Entity→venue resolution from management-zone tags, with venue_id fallback."""
from __future__ import annotations

from app.models.domain import Entity, EntityType
from app.services.entity_venue import EntityVenueResolver

ZONE_MAP = {"Arena North": "venue_arena_north", "Olympic Park": "venue_olympic_park"}


def _e(eid, tags, venue_id=None):
    return Entity(id=eid, name=eid, type=EntityType.SERVICE, tags=tags, venue_id=venue_id)


def test_resolves_from_management_zone_tag():
    r = EntityVenueResolver()
    r.load(
        [_e("SVC-1", ["mz:Arena North"]), _e("SVC-2", ["mz:Olympic Park"])],
        zone_mapping=ZONE_MAP,
    )
    assert r.venue_for("SVC-1") == "venue_arena_north"
    assert r.venue_for("SVC-2") == "venue_olympic_park"


def test_explicit_venue_id_takes_priority():
    r = EntityVenueResolver()
    # zone tag says Olympic, but explicit venue_id wins
    r.load([_e("SVC-3", ["mz:Olympic Park"], venue_id="venue_arena_north")],
           zone_mapping=ZONE_MAP)
    assert r.venue_for("SVC-3") == "venue_arena_north"


def test_custom_zone_tag_key():
    r = EntityVenueResolver()
    r.load([_e("SVC-4", ["zone:Arena North"])],
           zone_mapping=ZONE_MAP, zone_tag_key="zone")
    assert r.venue_for("SVC-4") == "venue_arena_north"


def test_unmapped_zone_is_unresolved():
    r = EntityVenueResolver()
    r.load([_e("SVC-5", ["mz:Unknown Stadium"])], zone_mapping=ZONE_MAP)
    assert r.venue_for("SVC-5") is None


def test_no_tag_no_venue_is_unresolved():
    r = EntityVenueResolver()
    r.load([_e("SVC-6", ["tier:high"])], zone_mapping=ZONE_MAP)
    assert r.venue_for("SVC-6") is None


def test_venue_for_any_first_match():
    r = EntityVenueResolver()
    r.load([_e("SVC-7", ["mz:Arena North"])], zone_mapping=ZONE_MAP)
    assert r.venue_for_any(["MISSING", "SVC-7"]) == "venue_arena_north"


def test_live_resolution_via_zone_only(monkeypatch):
    """When entities arrive with NO venue_id (live shape), zone mapping still
    resolves them."""
    r = EntityVenueResolver()
    r.load(
        [_e("SVC-LIVE", ["mz:Arena North"])],  # no venue_id, like a live tenant
        zone_mapping=ZONE_MAP,
    )
    assert r.venue_for("SVC-LIVE") == "venue_arena_north"
