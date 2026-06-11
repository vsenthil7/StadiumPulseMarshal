"""Minimal MCP (Model Context Protocol) JSON-RPC 2.0 client.

Implements the client side of an MCP session over HTTP: ``initialize``,
``tools/list`` and ``tools/call``. This is the real protocol layer used to talk
to the Dynatrace MCP server (and any MCP server). Transport is injected so it
can be exercised against a mock transport in tests without a live server.

This is intentionally framework-light: MCP is JSON-RPC, so we model requests,
responses and errors directly rather than pulling a heavy SDK.
"""
from __future__ import annotations

import itertools
from typing import Any

import httpx

from app.core.logging import get_logger

log = get_logger(__name__)

JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"


class MCPError(Exception):
    """Raised when an MCP server returns a JSON-RPC error."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"MCP error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class MCPTool:
    """Description of a tool exposed by an MCP server."""

    def __init__(self, name: str, description: str, input_schema: dict) -> None:
        self.name = name
        self.description = description
        self.input_schema = input_schema

    @classmethod
    def from_payload(cls, payload: dict) -> "MCPTool":
        return cls(
            name=payload.get("name", ""),
            description=payload.get("description", ""),
            input_schema=payload.get("inputSchema", {}),
        )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"MCPTool({self.name!r})"


class MCPSession:
    """A JSON-RPC MCP session bound to a single server endpoint."""

    def __init__(
        self,
        endpoint: str,
        http: httpx.AsyncClient,
        *,
        client_name: str = "stadiumpulse-marshal",
        client_version: str = "1.0.0",
    ) -> None:
        self._endpoint = endpoint
        self._http = http
        self._client_name = client_name
        self._client_version = client_version
        self._ids = itertools.count(1)
        self._initialized = False
        self.server_info: dict[str, Any] = {}

    async def _rpc(self, method: str, params: dict | None = None) -> Any:
        request = {
            "jsonrpc": JSONRPC_VERSION,
            "id": next(self._ids),
            "method": method,
            "params": params or {},
        }
        resp = await self._http.post(self._endpoint, json=request)
        resp.raise_for_status()
        body = resp.json()
        if "error" in body and body["error"]:
            err = body["error"]
            raise MCPError(
                code=err.get("code", -1),
                message=err.get("message", "unknown"),
                data=err.get("data"),
            )
        return body.get("result")

    async def initialize(self) -> dict[str, Any]:
        """Perform the MCP initialize handshake."""
        result = await self._rpc(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "clientInfo": {
                    "name": self._client_name,
                    "version": self._client_version,
                },
            },
        )
        self.server_info = (result or {}).get("serverInfo", {})
        self._initialized = True
        return result or {}

    async def list_tools(self) -> list[MCPTool]:
        result = await self._rpc("tools/list")
        return [MCPTool.from_payload(t) for t in (result or {}).get("tools", [])]

    async def call_tool(self, name: str, arguments: dict | None = None) -> Any:
        """Call a tool and return its structured/text content.

        MCP tool results carry a ``content`` array of typed blocks. We surface
        parsed JSON from text blocks when present, else the raw text, matching
        how downstream adapters expect to consume it.
        """
        result = await self._rpc(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )
        return self._extract_content(result or {})

    @staticmethod
    def _extract_content(result: dict) -> Any:
        import json

        content = result.get("content", [])
        texts: list[str] = []
        for block in content:
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
        joined = "\n".join(texts).strip()
        if not joined:
            return result
        try:
            return json.loads(joined)
        except (ValueError, TypeError):
            return joined

    @property
    def initialized(self) -> bool:
        return self._initialized
