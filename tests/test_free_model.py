import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from devfest_security.common import Blocked
from devfest_security.cost import require_cloud_execution, require_local_endpoint
from devfest_security.free_model import key_fingerprint
from devfest_security.models import DEFAULT_GEMINI_MODEL, build_gemini


def review(monkeypatch, **changes):
    now = datetime.now(UTC)
    policy = {'mode': 'reviewed-free-tier', 'checked_at': now.isoformat(),
              'expires_at': (now + timedelta(hours=1)).isoformat(),
              'cloud_project': 'example-lab-123', 'model_project': 'example-free-model',
              'model_project_unbilled': True, 'model_key_sha256': key_fingerprint('synthetic-test-placeholder'),
              'gemini_model': 'gemini-3.1-flash-lite', 'allowance_evidence': {'checked': True},
              'operations': ['Gemini Developer inference', 'remote MCP transport', 'Vertex inference'],
              'mcp_endpoints': ['https://owned.example/mcp'], **changes}
    monkeypatch.setenv('LAB_EXECUTION_POLICY', json.dumps(policy))
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'example-lab-123')
    monkeypatch.setenv('LAB_CLOUD_PROJECT', 'example-lab-123')


def test_gemini_does_not_inherit_vertex_environment(monkeypatch):
    review(monkeypatch, gemini_model=DEFAULT_GEMINI_MODEL)
    monkeypatch.setenv('GOOGLE_GENAI_USE_VERTEXAI', 'true')
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-test-placeholder')
    constructor = Mock()
    monkeypatch.setattr('langchain_google_genai.ChatGoogleGenerativeAI', constructor)
    build_gemini(SimpleNamespace(model='gemini', gemini_model=DEFAULT_GEMINI_MODEL), {})
    options = constructor.call_args.kwargs
    assert options['model'] == 'gemini-4-hydrogen'
    assert options['vertexai'] is False
    assert options['max_retries'] == 0
    assert options['thinking_config'] == {'thinking_level': 'LOW'}
    assert 'credentials' not in options
    assert 'temperature' not in options


def test_no_paid_fallback_or_missing_key_fallback(monkeypatch):
    review(monkeypatch)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    with pytest.raises(Blocked, match='GEMINI_API_KEY'):
        build_gemini(SimpleNamespace(model='gemini', gemini_model='gemini-3.1-flash-lite'), {})
    with pytest.raises(Blocked, match='Vertex'):
        require_cloud_execution('Vertex inference')
    with pytest.raises(Blocked, match='explicitly verified'):
        build_gemini(SimpleNamespace(model='gemini', gemini_model='paid-unknown-model'), {})


def test_remote_host_is_pinned_to_review(monkeypatch):
    review(monkeypatch)
    require_local_endpoint('https://owned.example/mcp')
    with pytest.raises(Blocked, match='reviewed deployment'):
        require_local_endpoint('https://attacker.example/mcp')


def test_expired_review_or_different_project_stops_before_network(monkeypatch):
    review(monkeypatch, expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat())
    with pytest.raises(Blocked, match='expired'):
        require_cloud_execution('Gemini Developer inference')
    review(monkeypatch)
    monkeypatch.setenv('LAB_CLOUD_PROJECT', 'another-project')
    with pytest.raises(Blocked, match='another cloud project'):
        require_cloud_execution('Gemini Developer inference')


def test_runtime_reserved_host_project_is_not_the_application_target(monkeypatch):
    review(monkeypatch)
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'provider-managed-host-project')
    require_cloud_execution('Gemini Developer inference')


def test_inherited_unrelated_key_cannot_reach_model_constructor(monkeypatch):
    review(monkeypatch)
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-unrelated-billed-project-key')
    constructor = Mock()
    monkeypatch.setattr('langchain_google_genai.ChatGoogleGenerativeAI', constructor)
    with pytest.raises(Blocked, match='key does not match'):
        build_gemini(SimpleNamespace(model='gemini', gemini_model='gemini-3.1-flash-lite'), {})
    constructor.assert_not_called()


def test_cloud_load_rejects_environment_override_then_loads_tracked_key(tmp_path, monkeypatch):
    from devfest_security.cloud import Cloud
    from devfest_security.free_model import KEY, STATE
    monkeypatch.chdir(tmp_path)
    review(monkeypatch)
    STATE.parent.mkdir()
    key = 'synthetic-test-placeholder'
    KEY.write_text(key)
    STATE.write_text(json.dumps({'operator': {'project': 'example-free-model', 'account': 'operator@example.com'},
        'key_sha256': key_fingerprint(key), 'cleaned': False}))
    cloud = Cloud({'project': 'example-lab-123', 'account': 'operator@example.com', 'region': 'us-central1', 'venue': 'taichung'})
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-unrelated-billed-project-key')
    with pytest.raises(Blocked, match='key does not match'):
        cloud.load_model_key()
    monkeypatch.delenv('GEMINI_API_KEY')
    assert cloud.load_model_key() == key_fingerprint(key)
    assert os.environ['GEMINI_API_KEY'] == key


def test_runtime_rejects_secret_version_from_previous_key(tmp_path, monkeypatch):
    from devfest_security.cloud import Cloud
    cloud = Cloud({'project': 'example-lab-123', 'account': 'operator@example.com', 'region': 'us-central1', 'venue': 'taichung'}, tmp_path/'state.json')
    cloud.initialize()
    cloud.state.update(image='synthetic', smoke_passed={'image': 'synthetic'}, secret_version='1', secret_key_sha256='previous-key')
    monkeypatch.setattr('devfest_security.cloud.require_cloud_execution', lambda _: None)
    monkeypatch.setattr(cloud, 'preflight', lambda: None)
    monkeypatch.setattr(cloud, 'load_model_key', lambda: 'current-key')
    monkeypatch.setattr(cloud, 'inspect', lambda _: pytest.fail('Stop before deployment mutations'))
    with pytest.raises(Blocked, match='different key'):
        cloud.deploy_runtime(update=True)
