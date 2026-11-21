"""Pin the exact discovery result. Pin creation is an explicit trust decision."""

import copy
import json
from pathlib import Path

from devfest_security.common import Blocked, digest, save_json


def manifest(endpoint: str, server: dict, tools: list[dict]) -> dict:
    names = [t["name"] for t in tools]
    if len(names) != len(set(names)):
        raise Blocked("Duplicate MCP tool names")
    return {
        "format": 1,
        "endpoint": endpoint.rstrip("/"),
        "server": server,
        "tools": sorted(copy.deepcopy(tools), key=lambda t: t["name"]),
    }


def pin(path: Path, value: dict) -> None:
    if path.exists():
        raise Blocked("Pin already exists; review the diff before creating a different pin")
    save_json(path, {"sha256": digest(value), "manifest": value})


def verify(path: Path, value: dict) -> str:
    trusted = json.loads(path.read_text())
    expected = digest(trusted["manifest"])
    if trusted["sha256"] != expected:
        raise Blocked("The local pin was modified inconsistently")
    if digest(value) != expected:
        raise Blocked("MCP manifest drift: endpoint, metadata, descriptions or schemas changed")
    return expected
