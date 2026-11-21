import copy
import json

import pytest

from devfest_security.auth import cloud_run_token, credentials
from devfest_security.cloud import Cloud, owned, validate_operator
from devfest_security.common import Blocked

CONFIG = {"account": "operator@example.com", "project": "example-lab-123", "region": "us-central1", "venue": "taipei"}


def test_billing_failure_precedes_any_state_or_mutation(tmp_path, monkeypatch):
    # Exercise the future cloud path without allowing a real cloud call.
    monkeypatch.setattr("devfest_security.cloud.require_cloud_execution", lambda _: None)
    cloud = Cloud(CONFIG, tmp_path / "state.json")
    calls = []

    def read_only(args, **kwargs):
        calls.append(args)
        if args[:2] == ["projects", "describe"]:
            return {"projectId": CONFIG["project"], "lifecycleState": "ACTIVE"}
        if args[:3] == ["billing", "projects", "describe"]:
            return {"billingEnabled": False}
        raise AssertionError("Mutation or unexpected cloud call before billing check")

    monkeypatch.setattr(cloud, "gcloud", read_only)
    with pytest.raises(Blocked, match="Billing"):
        cloud.setup()
    assert len(calls) == 2
    assert not cloud.path.exists()


def test_environment_identity_cannot_silently_switch(tmp_path):
    cloud = Cloud(CONFIG, tmp_path / "state.json")
    cloud.initialize()
    with pytest.raises(Blocked, match="different"):
        Cloud({**CONFIG, "venue": "taichung"}, cloud.path)


def test_cleaned_environment_is_archived_before_new_target(tmp_path):
    cloud = Cloud(CONFIG, tmp_path / "state.json")
    cloud.initialize()
    old_owner = cloud.state["owner"]
    cloud.state["cleaned"] = True
    cloud.save()
    next_cloud = Cloud({**CONFIG, "venue": "taichung"}, cloud.path)
    assert next_cloud.state is None
    next_cloud.initialize()
    assert next_cloud.state["owner"] != old_owner
    assert (tmp_path / f"cloud-state-{old_owner}.cleaned.json").exists()


def test_deleted_account_binding_is_detected_without_matching_unrelated_bindings(tmp_path):
    cloud = Cloud(CONFIG, tmp_path / "state.json")
    binding = {"member": "serviceAccount:lab@example.iam.gserviceaccount.com", "role": "projects/example/roles/lab"}
    tombstone = "deleted:" + binding["member"] + "?uid=123"
    policy = {"bindings": [
        {"role": binding["role"], "members": [tombstone, "user:someone@example.com"]},
        {"role": "roles/editor", "members": [binding["member"]]},
        {"role": binding["role"], "members": [binding["member"]], "condition": {"title": "unrelated"}},
    ]}
    assert cloud.binding_members(binding, policy) == [tombstone]


def test_ownership_label_is_required_even_for_correct_resource_name():
    for actual in ({}, {"labels": {"devfest-owner": "another-owner"}}):
        with pytest.raises(Blocked):
            owned(actual, "expected-owner", "bucket")
    owned({"metadata": {"labels": {"devfest-owner": "expected-owner"}}}, "expected-owner", "service")


def test_cleanup_dry_run_makes_no_remote_calls(tmp_path, monkeypatch):
    cloud = Cloud(CONFIG, tmp_path / "state.json")
    cloud.initialize()
    before = copy.deepcopy(cloud.state)
    monkeypatch.setattr(cloud, "inspect", lambda *_: pytest.fail("Dry-run must not mutate or inspect cloud resources"))
    monkeypatch.setattr(cloud, "find_runtime", lambda: pytest.fail("Dry-run must not access runtime"))
    cloud.cleanup()
    assert cloud.state == before


def test_cleanup_is_repeatable_after_partial_creation(tmp_path, monkeypatch):
    cloud = Cloud(CONFIG, tmp_path / "state.json")
    cloud.initialize()
    cloud.plan("service")
    cloud.plan("server_sa")
    present = {"service", "server_sa"}
    calls = []
    monkeypatch.setattr(cloud, "find_runtime", lambda: None)
    monkeypatch.setattr(cloud, "inspect", lambda kind: {"owned": True} if kind in present else None)

    def remove(args, **kwargs):
        calls.append(args)
        if args[:3] == ["run", "services", "delete"]:
            present.remove("service")
        elif args[:3] == ["iam", "service-accounts", "delete"]:
            present.remove("server_sa")
        else:
            raise AssertionError(args)
    monkeypatch.setattr(cloud, "gcloud", remove)
    cloud.cleanup(apply=True)
    cloud.cleanup(apply=True)
    assert len(calls) == 2
    assert json.loads(cloud.path.read_text())["cleaned"]


def test_runtime_is_gated_on_real_smoke(tmp_path, monkeypatch):
    # Exercise the future cloud path without allowing a real cloud call.
    monkeypatch.setattr("devfest_security.cloud.require_cloud_execution", lambda _: None)
    cloud = Cloud(CONFIG, tmp_path / "state.json")
    cloud.initialize()
    monkeypatch.setattr(cloud, "preflight", lambda: {})
    with pytest.raises(Blocked, match="real minimal flow"):
        cloud.deploy_runtime()


def test_cleanup_stops_on_remote_ownership_mismatch(tmp_path, monkeypatch):
    cloud = Cloud(CONFIG, tmp_path / "state.json")
    cloud.initialize()
    cloud.plan("service")
    monkeypatch.setattr(cloud, "find_runtime", lambda: None)

    def wrong_owner(kind):
        owned({"labels": {"devfest-owner": "somebody-else"}}, cloud.state["owner"], kind)

    monkeypatch.setattr(cloud, "inspect", wrong_owner)
    monkeypatch.setattr(cloud, "gcloud", lambda *_args, **_kwargs: pytest.fail("Must not delete an unowned resource"))
    with pytest.raises(Blocked, match="Ownership"):
        cloud.cleanup(apply=True)


@pytest.mark.parametrize("field,value", [("project", ""), ("account", ""), ("region", "global"), ("venue", "unknown")])
def test_no_implicit_cloud_target(field, value):
    with pytest.raises(Blocked):
        validate_operator({**CONFIG, field: value})


def test_local_credentials_require_explicit_project(monkeypatch):
    monkeypatch.setenv("LAB_GCLOUD_ACCOUNT", "operator@example.com")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    with pytest.raises(ValueError, match="explicit"):
        credentials()
    selected = credentials("example-lab-123")
    assert selected.project == "example-lab-123"


def test_identity_token_cannot_impersonate_outside_selected_project(monkeypatch):
    monkeypatch.setenv("LAB_GCLOUD_ACCOUNT", "operator@example.com")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "example-lab-123")
    monkeypatch.setenv("LAB_INVOKER_SERVICE_ACCOUNT", "someone@another-project.iam.gserviceaccount.com")
    with pytest.raises(ValueError, match="explicit project"):
        cloud_run_token("https://example.invalid")


def test_cloud_run_missing_is_distinguished_from_permission_denied(tmp_path, monkeypatch):
    from types import SimpleNamespace
    cloud = Cloud(CONFIG, tmp_path / 'state.json')
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: SimpleNamespace(
        returncode=1, stderr='ERROR: (gcloud.run.services.describe) Cannot find service [demo]', stdout=''))
    assert cloud.gcloud(['run', 'services', 'describe', 'demo'], missing_ok=True) is None
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: SimpleNamespace(
        returncode=1, stderr='PERMISSION_DENIED: access denied to service', stdout=''))
    with pytest.raises(RuntimeError, match='PERMISSION_DENIED'):
        cloud.gcloud(['run', 'services', 'describe', 'demo'], missing_ok=True)


def test_impersonated_cloud_run_token_includes_email(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setenv('LAB_GCLOUD_ACCOUNT', CONFIG['account'])
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', CONFIG['project'])
    monkeypatch.setenv('LAB_INVOKER_SERVICE_ACCOUNT', 'agent@example-lab-123.iam.gserviceaccount.com')
    def fake(command, **kwargs):
        assert '--include-email' in command
        assert '--audiences=https://owned.run.app' in command
        assert '--account=operator@example.com' in command
        assert '--project=example-lab-123' in command
        return SimpleNamespace(stdout='synthetic-token')
    monkeypatch.setattr('subprocess.run', fake)
    assert cloud_run_token('https://owned.run.app') == 'synthetic-token'


@pytest.mark.parametrize('listing', [[], [{'email': 'still-present'}], 'permission-denied'])
def test_deleted_service_account_403_requires_successful_empty_listing(tmp_path, monkeypatch, listing):
    cloud = Cloud(CONFIG, tmp_path / 'state.json')
    cloud.initialize()
    calls = []
    def lookup(args, **kwargs):
        calls.append(args)
        if args[:3] == ['iam', 'service-accounts', 'describe']:
            raise RuntimeError('PERMISSION_DENIED: resource may not exist')
        assert args == ['iam', 'service-accounts', 'list', f"--filter=email={cloud.state['agent_sa']}"]
        if listing == 'permission-denied':
            raise RuntimeError('PERMISSION_DENIED: listing unavailable')
        return listing
    monkeypatch.setattr(cloud, 'gcloud', lookup)
    if listing == []:
        assert cloud.inspect('agent_sa') is None
    else:
        with pytest.raises(RuntimeError, match='PERMISSION_DENIED'):
            cloud.inspect('agent_sa')
    assert len(calls) == 2


@pytest.mark.parametrize('statuses,expected', [([403, 200], None), ([403, 403], 'did not become ready'), ([401], 'HTTP 401')])
def test_deployment_readiness_retries_only_initialize_probe(tmp_path, monkeypatch, statuses, expected):
    from types import SimpleNamespace
    cloud = Cloud(CONFIG, tmp_path / 'state.json')
    cloud.initialize()
    cloud.state['endpoint'] = 'https://owned.run.app/mcp'
    calls = []
    remaining = iter(statuses)
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            assert kwargs['json']['method'] == 'initialize'
            calls.append(url)
            return SimpleNamespace(status_code=next(remaining), json=lambda: {'result': {'serverInfo': {'name': 'panda-expense-lab'}}})
    monkeypatch.setattr('httpx.Client', Client)
    monkeypatch.setattr('devfest_security.auth.cloud_run_token', lambda _: 'synthetic-token')
    monkeypatch.setattr('devfest_security.cloud.time.sleep', lambda _: None)
    if expected:
        with pytest.raises(Blocked, match=expected):
            cloud.wait_for_invoker(attempts=len(statuses))
    else:
        cloud.wait_for_invoker(attempts=len(statuses))
    assert calls == ['https://owned.run.app/mcp'] * len(statuses)
