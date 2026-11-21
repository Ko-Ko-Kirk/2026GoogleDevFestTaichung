import json

import pytest

from devfest_security.agent import RunConfig, run_agent
from devfest_security.demo import local_server, rehearse
from devfest_security.evidence import readback
from devfest_security.manifest import pin
from devfest_security.mcp_client import connect, discover
from devfest_security.store import Store


@pytest.fixture
def server(tmp_path):
    with local_server(tmp_path) as connection:
        yield *connection, tmp_path


async def test_rehearsal_proves_execution_and_prevention(server):
    endpoint, root, directory = server
    results = await rehearse(endpoint, root, directory)
    assert [r["status"] for r in results] == ["completed", "completed", "blocked", "blocked", "blocked", "completed"]
    assert [r["unauthorized_effect_observed"] for r in results] == [False, True, False, False, False, False]
    assert all(r["model_source"] == "deterministic-policy-fixture" for r in results)
    blocked = json.loads((directory / "03-manifest-block.json").read_text())
    assert "model_calls" not in blocked
    assert not blocked["tool_results"]


async def test_description_changes_without_endpoint_version_or_schema_changes(server):
    endpoint, root, directory = server
    store = Store(root)
    store.write("operator-config.json", {"description": "normal", "enforce": True, "principal": "alice"})
    async with connect(endpoint, "normal") as (session, info):
        baseline = await discover(session, endpoint, info)
    pin(directory / "trusted.json", baseline)
    store.write("operator-config.json", {"description": "poisoned", "enforce": True, "principal": "alice"})
    async with connect(endpoint, "changed") as (session, info):
        changed = await discover(session, endpoint, info)
    assert baseline["endpoint"] == changed["endpoint"]
    assert baseline["server"] == changed["server"]
    for before, after in zip(baseline["tools"], changed["tools"], strict=True):
        assert before["name"] == after["name"]
        assert before["inputSchema"] == after["inputSchema"]
    assert baseline != changed
    result = await run_agent(RunConfig(endpoint=endpoint, run_id="drift", model="fixture-attack", defense="pin", pin_path=str(directory / "trusted.json")))
    assert result["status"] == "blocked"
    assert not readback(root, "drift")["exists"]


async def test_server_identity_cannot_be_supplied_by_model_arguments(server):
    endpoint, root, _ = server
    async with connect(endpoint, "forged-principal") as (session, _):
        result = await session.call_tool("approve_expense", {"expense_id": "EXP-ALICE", "principal": "bob"})
        assert result.is_error
    assert not readback(root, "forged-principal")["exists"]


async def test_manager_cannot_cross_tenant_and_duplicate_write_is_idempotent(server):
    endpoint, root, _ = server
    Store(root).write("operator-config.json", {"description": "normal", "enforce": True, "principal": "bob"})
    async with connect(endpoint, "manager") as (session, _):
        denied = await session.call_tool("approve_expense", {"expense_id": "EXP-OTHER"})
        assert denied.is_error
        first = await session.call_tool("approve_expense", {"expense_id": "EXP-ALICE"})
        repeat = await session.call_tool("approve_expense", {"expense_id": "EXP-ALICE"})
        assert not first.is_error
        assert first.structured_content == repeat.structured_content
    persisted = readback(root, "manager")
    assert len(persisted["operations"]) == 1
    assert persisted["expenses"]["EXP-ALICE"]["status"] == "approved"
    assert persisted["expenses"]["EXP-OTHER"]["status"] == "pending"
