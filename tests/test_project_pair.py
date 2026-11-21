import json
from datetime import UTC, datetime, timedelta

import pytest

from devfest_security import free_model, projects
from devfest_security.cloud import validate_operator
from devfest_security.common import Blocked

CONFIG = {'project': 'example-infra-project', 'model_project': 'example-free-model',
          'account': 'operator@example.com', 'region': 'us-central1', 'venue': 'taichung'}


def responses(config, args, **kwargs):
    if args[:2] == ['projects', 'describe']:
        return {'projectId': config['project'], 'lifecycleState': 'ACTIVE'}
    assert args[:3] == ['billing', 'projects', 'describe']
    billed = config['project'] == CONFIG['project']
    return {'billingEnabled': billed, 'billingAccountName': 'billingAccounts/example' if billed else ''}


def test_plan_is_local_and_fixes_both_explicit_projects(monkeypatch):
    monkeypatch.setattr(projects, 'command', lambda *a, **kw: pytest.fail('Plan must not contact cloud'))
    plan = projects.plan(CONFIG)
    assert plan['model']['project'] == CONFIG['model_project']
    assert plan['infrastructure']['project'] == CONFIG['project']
    assert '--account operator@example.com' in plan['commands'][0]
    assert 'gcloud config' not in json.dumps(plan)
    with pytest.raises(Blocked, match='separate'):
        validate_operator({**CONFIG, 'model_project': CONFIG['project']})


def test_check_reads_only_the_pair_under_explicit_account(monkeypatch):
    calls = []
    def command(config, args, **kwargs):
        calls.append((config, args))
        assert config['account'] == CONFIG['account']
        return responses(config, args)
    monkeypatch.setattr(projects, 'command', command)
    projects.check(CONFIG)
    assert len(calls) == 4
    assert {c[0]['project'] for c in calls} == {CONFIG['project'], CONFIG['model_project']}


@pytest.mark.parametrize('model_billing', [
    {'billingEnabled': True, 'billingAccountName': 'billingAccounts/example'},
    {'billingEnabled': False, 'billingAccountName': 'billingAccounts/example'},
])
def test_model_project_linked_to_billing_stops(model_billing, monkeypatch):
    def command(config, args, **kwargs):
        if config['project'] == CONFIG['model_project'] and args[:3] == ['billing', 'projects', 'describe']:
            return model_billing
        return responses(config, args)
    monkeypatch.setattr(projects, 'command', command)
    with pytest.raises(Blocked, match='linked to billing'):
        projects.check(CONFIG)


def tracked_key(tmp_path, monkeypatch, **state_changes):
    monkeypatch.chdir(tmp_path)
    free_model.STATE.parent.mkdir(exist_ok=True)
    key = 'synthetic-key-not-a-real-credential'
    free_model.KEY.write_text(key)
    state = {'operator': {'project': CONFIG['model_project'], 'account': CONFIG['account']},
             'key_sha256': free_model.key_fingerprint(key), 'cleaned': False, **state_changes}
    free_model.STATE.write_text(json.dumps(state))
    return key


def test_review_binds_key_without_writing_secret_and_keeps_original_expiry(tmp_path, monkeypatch):
    key = tracked_key(tmp_path, monkeypatch)
    checked = datetime.now(UTC) - timedelta(minutes=5)
    evidence = {'project': CONFIG['project'], 'account': CONFIG['account'],
                'billing_account': 'billingAccounts/example', 'checked_at': checked.isoformat(),
                'evidence': {'account_level_remaining_allowances_reviewed': True}}
    source = tmp_path / 'allowance.json'
    source.write_text(json.dumps(evidence))
    monkeypatch.setattr(projects, 'command', responses)
    result = projects.prepare_review(CONFIG, source)
    policy = json.loads(projects.POLICY.read_text())
    assert policy['expires_at'] == (checked + timedelta(minutes=60)).isoformat()
    assert policy['model_key_sha256'] == free_model.key_fingerprint(key)
    assert policy['model_project'] != policy['cloud_project']
    assert key not in projects.POLICY.read_text()
    assert result['key_bound'] is True


@pytest.mark.parametrize('changes', [
    {'checked_at': '2000-01-01T00:00:00+00:00'},
    {'checked_at': '2000-01-01T00:00:00'},
    {'account': 'another@example.com'},
    {'project': 'another-infra-project'},
    {'evidence': None},
])
def test_bad_allowance_review_stops_before_cloud(tmp_path, monkeypatch, changes):
    monkeypatch.chdir(tmp_path)
    evidence = {'project': CONFIG['project'], 'account': CONFIG['account'],
                'checked_at': datetime.now(UTC).isoformat(), 'evidence': {'checked': True}, **changes}
    path = tmp_path / 'allowance.json'
    path.write_text(json.dumps(evidence))
    monkeypatch.setattr(projects, 'command', lambda *a, **kw: pytest.fail('No cloud request'))
    with pytest.raises(Blocked, match='Fresh'):
        projects.prepare_review(CONFIG, path)
    assert not projects.POLICY.exists()


@pytest.mark.parametrize('state_changes', [{'cleaned': True}, {'operator': {'project': 'another-model', 'account': CONFIG['account']}}, {'key_sha256': 'wrong'}])
def test_key_must_belong_to_the_tracked_model_project(tmp_path, monkeypatch, state_changes):
    tracked_key(tmp_path, monkeypatch, **state_changes)
    with pytest.raises(Blocked):
        free_model.local_model_key(CONFIG['model_project'], CONFIG['account'])
