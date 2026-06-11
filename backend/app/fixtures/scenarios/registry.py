"""Scenario registry: register, list and select matchday scenarios."""
from __future__ import annotations

from app.fixtures.scenarios.base import Scenario
from app.fixtures.scenarios.catalogue import (
    cdn_edge_failure,
    k8s_oom,
    network_partition,
    payment_db_saturation,
)

_BUILDERS = {
    "payment_db_saturation": payment_db_saturation,
    "cdn_edge_failure": cdn_edge_failure,
    "network_partition": network_partition,
    "k8s_oom": k8s_oom,
}

DEFAULT_SCENARIO = "payment_db_saturation"


def list_scenario_keys() -> list[str]:
    return list(_BUILDERS.keys())


def get_scenario(key: str) -> Scenario:
    builder = _BUILDERS.get(key, _BUILDERS[DEFAULT_SCENARIO])
    return builder()


def all_scenarios() -> list[Scenario]:
    return [b() for b in _BUILDERS.values()]
