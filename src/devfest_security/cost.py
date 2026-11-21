"""Default-off cloud execution with an expiring, operator-reviewed free-tier policy.

The policy records a cost review, not a provider-side billing cap. Vertex remains
blocked. Model inference uses an explicitly unbilled Gemini Developer project.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from devfest_security.common import Blocked


def execution_policy() -> dict:
    raw = os.environ.get('LAB_EXECUTION_POLICY')
    if not raw:
        path = Path(os.environ.get('LAB_EXECUTION_POLICY_FILE', '.state/execution-policy.json'))
        raw = path.read_text() if path.exists() else '{}'
    policy = json.loads(raw)
    if not policy:
        return {}
    expires = datetime.fromisoformat(policy['expires_at'])
    checked = datetime.fromisoformat(policy['checked_at'])
    now = datetime.now(UTC)
    if expires.tzinfo is None or checked.tzinfo is None or not checked <= now < expires:
        raise Blocked('Free-tier execution review is expired or invalid')
    if (expires - checked).total_seconds() > 10800 or policy.get('mode') != 'reviewed-free-tier':
        raise Blocked('Free-tier review must expire within three hours')
    # Agent Runtime reserves GOOGLE_CLOUD_PROJECT for its hosting context.
    # The operator explicitly supplies the application target in LAB_CLOUD_PROJECT.
    project = os.environ.get('LAB_CLOUD_PROJECT') or os.environ.get('GOOGLE_CLOUD_PROJECT')
    if project != policy.get('cloud_project'):
        raise Blocked('Free-tier review belongs to another cloud project')
    if not policy.get('allowance_evidence'):
        raise Blocked('Free-tier allowance evidence is required')
    return policy


def require_cloud_execution(operation: str) -> None:
    policy = execution_policy()
    if operation != 'Vertex inference' and operation in policy.get('operations', []):
        return
    raise Blocked(
        f"Zero-spend release blocks {operation} before cloud execution. "
        "Free-tier availability is not a verified remaining allowance. "
        "Use scripts/demo.sh for the offline HTTP rehearsal."
    )


def require_local_endpoint(endpoint: str) -> None:
    url = urlparse(endpoint)
    if url.scheme != "http" or url.hostname != "127.0.0.1":
        require_cloud_execution("remote MCP transport")
        if endpoint not in execution_policy().get('mcp_endpoints', []):
            raise Blocked('Remote MCP endpoint is not in the reviewed deployment')


def report() -> dict:
    policy = execution_policy()
    return {
        "mode": policy.get('mode', 'offline-only'),
        "cloud_execution_enabled": bool(policy),
        "review_expires_at": policy.get('expires_at'),
        "allowed": policy.get('operations', ['loopback MCP', 'local LangGraph', 'deterministic policy fixtures']),
        "always_blocked": ['Vertex inference', 'automatic paid fallback'],
        "note": 'A current operator review is required. Cleanup stays available after review expiry. Free allowance review is not a billing hard cap.',
    }
