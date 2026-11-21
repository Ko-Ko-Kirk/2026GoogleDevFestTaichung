import copy
from types import SimpleNamespace

import pytest
from google.cloud import modelarmor_v1

from devfest_security.armor import Armor, interpret
from devfest_security.common import Blocked
from devfest_security.evidence import verify_evidence
from devfest_security.manifest import manifest, pin, verify
from devfest_security.policy import authorize
from devfest_security.runtime import SecurityAgent
from devfest_security.server import execute
from devfest_security.store import Store


def test_pin_is_explicit_and_rejects_tampering(tmp_path):
    baseline = manifest("http://localhost:8080/mcp", {"version": "1"}, [{"name": "read", "description": "safe", "inputSchema": {}}])
    path = tmp_path / "pin.json"
    pin(path, baseline)
    verify(path, baseline)
    with pytest.raises(Blocked):
        pin(path, baseline)
    changed = copy.deepcopy(baseline)
    changed["tools"][0]["inputSchema"] = {"additionalProperties": True}
    with pytest.raises(Blocked):
        verify(path, changed)
    with pytest.raises(Blocked):
        manifest("https://example.invalid/mcp", {}, [{"name": "same"}, {"name": "same"}])


@pytest.mark.parametrize("principal,tool,args", [
    ("alice", "approve_expense", {"expense_id": "EXP-ALICE"}),
    ("bob", "approve_expense", {"expense_id": "EXP-OTHER"}),
    ("alice", "get_expense", {"expense_id": "EXP-BOB"}),
    ("admin", "get_expense", {"expense_id": "EXP-ALICE"}),
    ("bob", "send_secret", {"expense_id": "EXP-ALICE"}),
    ("bob", "approve_expense", {"expense_id": "EXP-ALICE", "role": "manager"}),
])
def test_authority_is_not_a_model_claim(principal, tool, args):
    with pytest.raises(Blocked):
        authorize(principal, tool, args)


def test_unsafe_mode_requires_explicit_server_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv("LAB_ALLOW_SYNTHETIC_UNSAFE", raising=False)
    with pytest.raises(Blocked, match="Unsafe"):
        execute(Store(str(tmp_path)), {"principal": "alice", "enforce": False}, "case", "approve_expense", {"expense_id": "EXP-ALICE"})
    assert not (tmp_path / "runs/case.json").exists()


def test_real_proto_enum_conversion_and_armor_match_handling():
    armor = Armor.__new__(Armor)
    armor.template = "projects/example-project/locations/us-central1/templates/lab"
    response = modelarmor_v1.SanitizeUserPromptResponse(sanitization_result={
        "invocation_result": "SUCCESS", "filter_match_state": "NO_MATCH_FOUND"})
    armor.client = SimpleNamespace(sanitize_user_prompt=lambda **kwargs: response)
    assert armor.scan("synthetic read", "prompt")["decision"] == "allowed"
    response.sanitization_result.filter_match_state = modelarmor_v1.FilterMatchState.MATCH_FOUND
    assert armor.scan("test injection", "prompt")["decision"] == "blocked"


@pytest.mark.parametrize("result", [
    {},
    {"invocation_result": "FAILURE", "filter_match_state": "NO_MATCH_FOUND"},
    {"invocation_result": "SUCCESS", "filter_match_state": "UNSPECIFIED"},
    {"invocation_result": "SUCCESS", "filter_match_state": "NO_MATCH_FOUND", "filter_results": {"pi": {"execution_state": "EXECUTION_FAILURE"}}},
])
def test_partial_or_unknown_armor_response_cannot_allow(result):
    with pytest.raises(Blocked):
        interpret(result)


def test_success_without_receipt_cannot_be_verified():
    with pytest.raises(Blocked, match="omitted"):
        verify_evidence({"tool_results": [{"isError": False, "content": []}]}, {"operations": {}})


def test_runtime_serialization_contains_only_deployment_configuration():
    import cloudpickle

    agent = SecurityAgent("https://example.invalid/mcp", {"sha256": "example"}, "template", "project", "us-central1")
    restored = cloudpickle.loads(cloudpickle.dumps(agent))
    assert restored.__dict__ == agent.__dict__
    assert set(restored.__dict__) == {"endpoint", "pin", "template", "project", "region"}


def test_armor_requests_multilingual_detection_for_both_surfaces():
    from unittest.mock import Mock
    armor = Armor.__new__(Armor)
    armor.template = 'projects/example-project/locations/us-central1/templates/lab'
    response = modelarmor_v1.SanitizeUserPromptResponse(sanitization_result={
        'invocation_result': 'SUCCESS', 'filter_match_state': 'NO_MATCH_FOUND'})
    armor.client = Mock()
    armor.client.sanitize_user_prompt.return_value = response
    armor.client.sanitize_model_response.return_value = response
    armor.scan('請查詢金額', 'user_prompt')
    armor.scan('金額為 500', 'final_response', response=True)
    for method in (armor.client.sanitize_user_prompt, armor.client.sanitize_model_response):
        assert method.call_args.kwargs['request']['multi_language_detection_metadata'] == {
            'enable_multi_language_detection': True}


async def test_runtime_works_inside_host_event_loop(monkeypatch):
    async def run(config):
        assert config.principal == 'alice'
        assert config.defense == 'all'
        assert config.model == 'gemini'
        assert config.prompt == 'synthetic query'
        return {'status': 'completed'}
    monkeypatch.setattr('devfest_security.runtime.run_agent', run)
    agent = SecurityAgent('https://example.invalid/mcp', {}, 'template', 'project', 'us-central1')
    assert await agent.async_query(prompt='synthetic query') == {'status': 'completed'}
