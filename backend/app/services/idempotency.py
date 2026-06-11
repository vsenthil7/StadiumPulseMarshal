"""Idempotency support for safe POST replay.

Clients send an ``Idempotency-Key`` header on unsafe requests. The first time a
key is seen we execute the operation and store its response; subsequent requests
with the same key return the stored response without re-executing the side
effect. Keys are namespaced by route so the same key on different endpoints does
not collide. In-memory with a simple capacity bound; swappable for a shared
store behind the same interface.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any


class IdempotencyStore:
    def __init__(self, capacity: int = 10_000) -> None:
        self._items: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        self._capacity = capacity

    @staticmethod
    def _compose(namespace: str, key: str) -> str:
        return f"{namespace}:{key}"

    def get(self, namespace: str, key: str) -> dict[str, Any] | None:
        composed = self._compose(namespace, key)
        if composed in self._items:
            self._items.move_to_end(composed)
            return self._items[composed]
        return None

    def put(
        self, namespace: str, key: str, status_code: int, body: dict[str, Any]
    ) -> None:
        composed = self._compose(namespace, key)
        self._items[composed] = {"status_code": status_code, "body": body}
        self._items.move_to_end(composed)
        while len(self._items) > self._capacity:
            self._items.popitem(last=False)

    def __len__(self) -> int:
        return len(self._items)
