"""Small, explicit lab primitives. All business records are synthetic."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path


class Blocked(RuntimeError):
    """A security control refused to continue."""


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", value):
        raise ValueError("Invalid lab identifier")
    return value


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def event(kind: str, **values: object) -> dict:
    item = {"severity": "INFO", "event": kind, "timestamp": timestamp(), **values}
    print(canonical(item), flush=True)
    return item
