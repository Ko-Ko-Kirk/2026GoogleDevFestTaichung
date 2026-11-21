import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from google.genai.errors import ServerError
from langchain_core.messages import AIMessage, ToolMessage

from devfest_security import free_model
from devfest_security.common import Blocked


def test_paid_model_project_cannot_reach_key_creation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []
    def fake(config, args, **kwargs):
        calls.append(args)
        if args[:2] == ['projects', 'describe']:
            return {'projectId': config['project'], 'lifecycleState': 'ACTIVE'}
        if args[:3] == ['billing', 'projects', 'describe']:
            return {'billingEnabled': True, 'billingAccountName': 'billingAccounts/paid'}
        pytest.fail('Paid project must stop before service enablement or key creation')
    monkeypatch.setattr(free_model, 'command', fake)
    with pytest.raises(Blocked, match='must not be linked'):
        free_model.setup({'project': 'example-free-model', 'account': 'operator@example.com'})
    assert len(calls) == 2


def test_key_cleanup_refuses_different_owner(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    free_model.STATE.parent.mkdir()
    free_model.STATE.write_text(json.dumps({'operator': {'project': 'example-free-model',
        'account': 'operator@example.com'}, 'key_id': 'demo', 'owner': 'mine'}))
    def fake(config, args, **kwargs):
        assert args[:3] == ['services', 'api-keys', 'describe']
        return {'annotations': {'devfest-owner': 'not-mine'}}
    monkeypatch.setattr(free_model, 'command', fake)
    with pytest.raises(Blocked, match='ownership'):
        free_model.cleanup(apply=True)


def test_model_smoke_cannot_send_a_request_from_a_billed_project(monkeypatch):
    config = {'project': 'example-free-model', 'account': 'operator@example.com'}
    monkeypatch.setattr(free_model, 'local_model_key', lambda *_: ('synthetic-key', 'test'))
    monkeypatch.setattr(free_model, 'command', lambda _, args: (
        {'projectId': config['project'], 'lifecycleState': 'ACTIVE'}
        if args[0] == 'projects' else {'billingEnabled': True}
    ))
    monkeypatch.setattr('devfest_security.models.developer_chat',
                        lambda *_: pytest.fail('No inference on a billed project'))
    with pytest.raises(Blocked, match='must not be linked'):
        free_model.smoke(config)


def test_billing_rate_limit_can_use_only_the_same_model_projects_quota(monkeypatch):
    config = {'project': 'example-free-model', 'account': 'operator@example.com'}
    cli = Mock(side_effect=[
        {'projectId': config['project'], 'lifecycleState': 'ACTIVE'},
        free_model.BillingRateLimited('shared quota exhausted'),
        {'projectId': config['project'], 'billingEnabled': False},
    ])
    monkeypatch.setattr(free_model, 'command', cli)
    free_model.require_unbilled(config)
    assert cli.call_args.args == (config, [
        'billing', 'projects', 'describe', 'example-free-model',
        '--billing-project=example-free-model',
    ])


@pytest.mark.parametrize('retry_summary', [False, True])
def test_model_smoke_returns_the_tool_result_to_the_model(tmp_path, monkeypatch, capsys, retry_summary):
    monkeypatch.chdir(tmp_path)
    config = {'project': 'example-free-model', 'account': 'operator@example.com'}
    monkeypatch.setattr(free_model, 'local_model_key', lambda *_: ('synthetic-key', 'test'))
    monkeypatch.setattr(free_model, 'require_unbilled', Mock())
    chat = Mock()
    call = {'name': 'get_expense', 'args': {'expense_id': 'EXP-ALICE'}, 'id': 'expense-call'}
    responses = [AIMessage(content='', tool_calls=[call])]
    if retry_summary:
        responses.append(ServerError(503, {'error': {'status': 'UNAVAILABLE', 'message': 'busy'}}))
        monkeypatch.setattr('devfest_security.expense_smoke.sleep', AsyncMock())
    responses.append(AIMessage(content='EXP-ALICE 金額為 120，目前待審核。'))
    invoke = AsyncMock(side_effect=responses)
    chat.bind_tools.return_value.ainvoke = invoke
    monkeypatch.setattr('devfest_security.models.developer_chat', lambda *_: chat)

    free_model.smoke(config)

    call_messages = invoke.await_args.args[0]
    assert isinstance(call_messages[-1], ToolMessage)
    assert call_messages[-1].tool_call_id == 'expense-call'
    result = json.loads(capsys.readouterr().out)
    assert result['model'] == 'gemini-4-hydrogen'
    assert result['model_attempts'] == len(responses)
    assert result['tool_result']['amount'] == 120
    assert result['tool_result']['status'] == 'pending'
    assert result['receipt']['principal'] == 'alice'
    assert result['receipt']['side_effect'] is False
    assert result['readback'] == 'local-file-readback'
    assert result['changed_expenses'] == {}
    ledger = Path(result['evidence_directory']) / 'store' / 'runs' / f"{result['run_id']}.json"
    assert len(json.loads(ledger.read_text())['operations']) == 1
    assert all(
        [tool['name'] for tool in call.args[0]] == ['get_expense']
        for call in chat.bind_tools.call_args_list
    )


def test_key_error_never_echoes_secret_output(monkeypatch):
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: SimpleNamespace(
        returncode=1, stderr='keyString: SECRET-THAT-MUST-NOT-BE-ECHOED', stdout=''))
    with pytest.raises(Blocked) as exc:
        free_model.command({'project': 'example-free-model', 'account': 'operator@example.com'},
                           ['services', 'api-keys', 'create'])
    assert 'SECRET-THAT' not in str(exc.value)


def test_key_creation_records_project_and_fingerprint_without_secret_in_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    key = 'synthetic-model-key-never-sent-to-google'
    def fake(config, args, **kwargs):
        if args[:2] == ['projects', 'describe']:
            return {'projectId': config['project'], 'lifecycleState': 'ACTIVE'}
        if args[:3] == ['billing', 'projects', 'describe']:
            return {'billingEnabled': False, 'billingAccountName': ''}
        if args[:3] == ['services', 'api-keys', 'create']:
            return {'keyString': key, 'name': 'projects/example-free-model/locations/global/keys/synthetic'}
        assert args[:2] == ['services', 'enable']
        return {}
    monkeypatch.setattr(free_model, 'command', fake)
    target = {'project': 'example-free-model', 'account': 'operator@example.com'}
    free_model.setup(target)
    record = json.loads(free_model.STATE.read_text())
    assert record['operator'] == target
    assert record['key_sha256'] == free_model.key_fingerprint(key)
    assert key not in free_model.STATE.read_text()
    assert free_model.KEY.stat().st_mode & 0o777 == 0o600


def test_setup_cli_uses_configured_model_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    free_model.STATE.parent.mkdir()
    target = {'project': 'example-infra-project', 'model_project': 'example-free-model', 'account': 'operator@example.com'}
    (free_model.STATE.parent/'operator.json').write_text(json.dumps(target))
    calls = []
    monkeypatch.setattr('sys.argv', ['model-project', 'setup'])
    monkeypatch.setattr(free_model, 'setup', lambda config, create, organization: calls.append(config))
    free_model.main()
    assert calls == [{'project': target['model_project'], 'account': target['account']}]


def test_setup_cli_rejects_different_project_than_configured_pair(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    free_model.STATE.parent.mkdir()
    (free_model.STATE.parent/'operator.json').write_text(json.dumps({'model_project': 'example-free-model', 'account': 'operator@example.com'}))
    monkeypatch.setattr('sys.argv', ['model-project', 'setup', '--project', 'some-other-project'])
    monkeypatch.setattr(free_model, 'setup', lambda *args: pytest.fail('Wrong project must not be created'))
    with pytest.raises(Blocked, match='configured project pair'):
        free_model.main()


def test_vertex_cli_uses_only_the_configured_infrastructure_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    free_model.STATE.parent.mkdir()
    pair = {'project': 'example-infra-project', 'model_project': 'example-free-model',
            'account': 'operator@example.com'}
    (free_model.STATE.parent / 'operator.json').write_text(json.dumps(pair))
    vertex = Mock()
    monkeypatch.setattr(free_model, 'vertex_smoke', vertex)
    monkeypatch.setattr('sys.argv', ['model-project', 'smoke-vertex'])
    free_model.main()
    vertex.assert_called_once_with(
        {'project': pair['project'], 'account': pair['account']},
        billing_quota_project=pair['model_project'],
        check_authorization=False,
    )

    monkeypatch.setattr('sys.argv', ['model-project', 'smoke-vertex', '--project', pair['model_project']])
    with pytest.raises(SystemExit, match='2'):
        free_model.main()
    vertex.assert_called_once()


def test_vertex_authorization_check_stops_before_tool_execution(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    chat = Mock()
    invoke = AsyncMock(return_value=AIMessage(content='', tool_calls=[{
        'name': 'get_expense', 'args': {'expense_id': 'EXP-BOB'}, 'id': 'read-call',
    }]))
    chat.bind_tools.return_value.ainvoke = invoke

    free_model.run_smoke(chat, vertex=True, check_authorization=True)

    result = json.loads(capsys.readouterr().out)
    assert result['blocked_by'] == 'application_authorization'
    assert result['model_calls'] == 1
    assert result['tool_calls'] == result['receipt_count'] == 0
    assert result['changed_expenses'] == {}
    assert not list((Path(result['evidence_directory']) / 'store').glob('runs/*.json'))
    invoke.assert_awaited_once()


def test_vertex_lookup_checks_tool_description_before_calling_model(tmp_path, monkeypatch):
    from devfest_security import expense_smoke

    monkeypatch.chdir(tmp_path)
    chat = Mock()
    discover = expense_smoke.discover

    async def changed_description(*args):
        result = await discover(*args)
        result['tools'][0]['description'] += ' The number is shown in the local ledger.'
        return result

    monkeypatch.setattr(expense_smoke, 'discover', changed_description)
    with pytest.raises(Blocked, match='工具定義與程式預期不符'):
        free_model.run_smoke(chat, vertex=True)
    chat.bind_tools.assert_not_called()


@pytest.mark.parametrize('http_module', ['httpx', 'httpx2'])
def test_smoke_cli_stops_cleanly_on_timeout(tmp_path, monkeypatch, capsys, http_module):
    from importlib import import_module

    ReadTimeout = import_module(http_module).ReadTimeout

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('sys.argv', ['model-project', 'smoke', '--project', 'example-free-model',
                                    '--account', 'operator@example.com'])
    smoke = Mock(side_effect=ReadTimeout('request timed out'))
    monkeypatch.setattr(free_model, 'smoke', smoke)

    with pytest.raises(SystemExit) as error:
        free_model.main()

    assert error.value.code == 1
    assert 'ReadTimeout' in capsys.readouterr().err
    smoke.assert_called_once()
