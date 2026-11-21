"""Offline regression rehearsal over real MCP HTTP. No model or cloud calls."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path

from devfest_security.agent import RunConfig, run_agent
from devfest_security.common import save_json
from devfest_security.evidence import readback, verify_evidence
from devfest_security.manifest import pin
from devfest_security.mcp_client import connect, discover
from devfest_security.report import render
from devfest_security.store import Store


@contextmanager
def local_server(directory: Path, *, read_only: bool = False):
    directory.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ,
        "LAB_STORE": str(directory / "store"),
        "PORT": str(port),
        "LAB_BIND_HOST": "127.0.0.1",
        "LAB_READ_ONLY": "true" if read_only else "false",
        "LAB_ALLOW_SYNTHETIC_UNSAFE": "false" if read_only else "true",
    }
    with (directory / "server.jsonl").open("w") as log:
        process = subprocess.Popen([sys.executable, "-m", "devfest_security.server"], env=env, stdout=log, stderr=log)
        try:
            for _ in range(150):
                if process.poll() is not None:
                    raise RuntimeError(f"Server exited; inspect {directory / 'server.jsonl'}")
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("MCP health check timed out")
            yield f"http://127.0.0.1:{port}/mcp", str(directory / "store")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


async def rehearse(endpoint: str, root: str, output: Path) -> list[dict]:
    store = Store(root)
    store.write("operator-config.json", {"description": "normal", "enforce": True, "principal": "alice"})
    pin_path = output / "manifest-pin.json"
    async with connect(endpoint, "capture-baseline") as (session, server):
        pin(pin_path, await discover(session, endpoint, server))
    scenarios = [
        # name, description, server enforcement, principal, model fixture, client defense, expected change
        ("01-read", "normal", True, "alice", "fixture-read", "pin", False),
        ("02-unsafe-policy-replay", "poisoned", False, "alice", "fixture-attack", "none", True),
        ("03-manifest-block", "poisoned", False, "alice", "fixture-attack", "pin", False),
        ("04-caller-policy-block", "poisoned", False, "alice", "fixture-attack", "policy", False),
        ("05-server-policy-block", "poisoned", True, "alice", "fixture-attack", "none", False),
        ("06-manager-approved", "normal", True, "bob", "fixture-approve", "all", True),
    ]
    summaries = []
    for name, description, enforced, principal, model, defense, changed in scenarios:
        store.write("operator-config.json", {"description": description, "enforce": enforced, "principal": principal})
        config = RunConfig(endpoint=endpoint, run_id=f"{name}-{uuid.uuid4().hex[:8]}", model=model,
                           defense=defense, principal=principal, pin_path=str(pin_path))
        evidence = await run_agent(config)
        persisted = readback(root, config.run_id)
        summary = verify_evidence(evidence, persisted)
        if evidence["status"] == "error" or bool(summary["changed_expenses"]) != changed:
            save_json(output / f"{name}.json", evidence)
            raise AssertionError(f"Scenario failed: {name}; {evidence.get('reason')}")
        save_json(output / f"{name}.json", evidence)
        save_json(output / f"{name}.readback.json", persisted)
        summaries.append({"scenario": name, **summary})
    store.write("operator-config.json", {"description": "normal", "enforce": True, "principal": "alice"})
    save_json(output / "summary.json", summaries)
    return summaries


def main():
    directory = Path(".state") / f"rehearsal-{uuid.uuid4().hex[:12]}"
    with local_server(directory) as (endpoint, root):
        summaries = asyncio.run(rehearse(endpoint, root, directory))
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    print(f"Evidence: {directory.resolve()}")
    print(f"Report: {render(directory).resolve()}")


if __name__ == "__main__":
    main()
