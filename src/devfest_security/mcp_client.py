"""Bounded real HTTP transport, including private Cloud Run ID-token authentication."""

from contextlib import asynccontextmanager
from urllib.parse import urlparse

import anyio
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from devfest_security.auth import cloud_run_token
from devfest_security.common import Blocked, safe_id
from devfest_security.cost import require_local_endpoint
from devfest_security.manifest import manifest


@asynccontextmanager
async def connect(endpoint: str, run_id: str, token: str | None = None):
    require_local_endpoint(endpoint)
    url = urlparse(endpoint)
    if url.scheme != "https" and not (url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost"}):
        raise Blocked("MCP requires HTTPS except on loopback")
    if url.username or url.password or url.query or url.fragment:
        raise Blocked("Credentials, query strings and fragments are forbidden in MCP URLs")
    headers = {"x-lab-run-id": safe_id(run_id)}
    if url.scheme == "https":
        token = token or await anyio.to_thread.run_sync(cloud_run_token, f"{url.scheme}://{url.netloc}")
        headers["Authorization"] = f"Bearer {token}"
    async with httpx2.AsyncClient(headers=headers, timeout=45, follow_redirects=False) as http:
        async with streamable_http_client(endpoint, http_client=http) as transport:
            async with ClientSession(transport[0], transport[1], read_timeout_seconds=45) as session:
                initialization = await session.initialize()
                yield session, initialization.server_info.model_dump(mode="json", by_alias=True, exclude_none=True)


async def discover(session, endpoint: str, server: dict) -> dict:
    response = await session.list_tools()
    if response.next_cursor:
        raise Blocked("This two-tool lab does not accept paginated manifests")
    tools = [t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in response.tools]
    if len(tools) > 8:
        raise Blocked("Tool discovery budget exceeded")
    return manifest(endpoint, server, tools)
