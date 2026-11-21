"""Manage the unbilled model key and run explicitly selected expense rehearsals."""

import argparse
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

from devfest_security.common import Blocked, save_json

STATE = Path('.state/free-model.json')
KEY = Path('.state/gemini-api-key')


class BillingRateLimited(Blocked):
    """The Cloud CLI quota refused the billing status read."""


def key_fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def verify_key_binding(key: str, policy: dict) -> None:
    project = policy.get('model_project')
    expected = policy.get('model_key_sha256', '')
    if (not project or project == policy.get('cloud_project')
            or policy.get('model_project_unbilled') is not True
            or not re.fullmatch(r'[0-9a-f]{64}', expected)
            or not hmac.compare_digest(key_fingerprint(key), expected)):
        raise Blocked('Gemini key does not match the reviewed unbilled model project')


def local_model_key(project: str, account: str) -> tuple[str, str]:
    if not STATE.exists() or not KEY.exists():
        raise Blocked('Create a tracked free-model key before preparing the review')
    state = json.loads(STATE.read_text())
    if state.get('cleaned') or state.get('operator') != {'project': project, 'account': account}:
        raise Blocked('Tracked model key belongs to another project/account or was cleaned')
    key = KEY.read_text().strip()
    fingerprint = key_fingerprint(key)
    if not key or not hmac.compare_digest(fingerprint, state.get('key_sha256', '')):
        raise Blocked('Model key file does not match its creation record; recreate the key')
    return key, fingerprint


def command(config, args, missing_ok=False):
    result = subprocess.run(['gcloud', *args, f"--project={config['project']}",
        f"--account={config['account']}", '--quiet', '--format=json'],
        capture_output=True, text=True, timeout=180)
    if result.returncode:
        if missing_ok and re.search(r'NOT_FOUND|not found|does not exist', result.stderr, re.I):
            return None
        if args[:3] == ['billing', 'projects', 'describe'] and 'RATE_LIMIT_EXCEEDED' in result.stderr:
            raise BillingRateLimited('Cloud Billing 查詢已達速率上限。')
        # API key create can include keyString in stderr. Never echo its output.
        raise Blocked(f"Model-project command failed ({' '.join(args[:3])}); inspect the selected project in Console")
    value = json.loads(result.stdout) if result.stdout.strip() else {}
    return value.get('response', value) if isinstance(value, dict) else value


def billing_status(config, *, quota_project=None):
    identity = command(config, ['projects', 'describe', config['project']])
    if identity.get('projectId') != config['project'] or identity.get('lifecycleState') != 'ACTIVE':
        raise Blocked('Model project identity is inactive or does not match')
    billing_command = ['billing', 'projects', 'describe', config['project']]
    if quota_project:
        return command(config, [*billing_command, f"--billing-project={quota_project}"])
    try:
        return command(config, billing_command)
    except BillingRateLimited:
        return command(config, [*billing_command, f"--billing-project={config['project']}"])


def require_unbilled(config):
    billing = billing_status(config)
    if billing.get('billingEnabled', True) or billing.get('billingAccountName'):
        raise Blocked('Gemini model project must not be linked to billing')


def setup(config, create=False, organization=None):
    if not re.fullmatch(r'[a-z][a-z0-9-]{4,28}[a-z0-9]', config['project']) or '@' not in config['account']:
        raise Blocked('Explicit project ID and account are required')
    if STATE.exists():
        state = json.loads(STATE.read_text())
        if state['operator'] != config:
            raise Blocked('Existing model state belongs to another target')
        if not state.get('cleaned'):
            raise Blocked('Model key already tracked; inspect or clean it before creating another')
    if create:
        args = ['projects', 'create', config['project'], '--name=DevFest free synthetic model']
        if organization:
            args.append('--organization=' + organization)
        command(config, args)
    require_unbilled(config)
    command(config, ['services', 'enable', 'generativelanguage.googleapis.com',
                     'apikeys.googleapis.com', 'cloudbilling.googleapis.com'])
    owner = uuid.uuid4().hex
    state = {'operator': config, 'owner': owner, 'key_id': 'df-model-' + owner[:12], 'cleaned': False}
    save_json(STATE, state)  # Journal before mutation, for recovery after uncertain response.
    response = command(config, ['services', 'api-keys', 'create', '--key-id=' + state['key_id'],
        '--display-name=DevFest synthetic model', '--api-target=service=generativelanguage.googleapis.com',
        '--annotations=devfest-owner=' + owner])
    key = response.pop('keyString', None)
    if not key:
        raise Blocked('Key created without a returned secret; cleanup before retrying')
    descriptor = os.open(KEY, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        output.write(key)
    KEY.chmod(0o600)
    state['key_name'] = response['name']
    state['key_sha256'] = key_fingerprint(key)
    save_json(STATE, state)
    print('Unbilled model project verified; API-restricted key saved privately. Billing was not linked.')


def smoke(config):
    from devfest_security.models import DEFAULT_GEMINI_MODEL, developer_chat

    key, _ = local_model_key(config['project'], config['account'])
    require_unbilled(config)
    chat = developer_chat(DEFAULT_GEMINI_MODEL, key)
    run_smoke(chat, vertex=False)


def vertex_smoke(config, *, billing_quota_project=None, check_authorization=False):
    from devfest_security.models import vertex_expense_chat

    if billing_status(config, quota_project=billing_quota_project).get('billingEnabled') is not True:
        raise Blocked('Vertex AI 彩排需要已啟用 Billing 的指定實驗專案。')
    chat = vertex_expense_chat(config['project'], config['account'])
    run_smoke(chat, vertex=True, check_authorization=check_authorization)


def run_smoke(chat, *, vertex, check_authorization=False):
    import asyncio

    from devfest_security.demo import local_server
    from devfest_security.expense_smoke import run_expense_lookup
    from devfest_security.models import DEFAULT_GEMINI_MODEL

    run_id = 'hydrogen-expense-' + uuid.uuid4().hex[:12]
    directory = Path('.state') / run_id
    with local_server(directory, read_only=True) as (endpoint, root):
        result = asyncio.run(run_expense_lookup(
            chat, endpoint, root, run_id, vertex=vertex, check_authorization=check_authorization,
        ))
    report = {
        'model': DEFAULT_GEMINI_MODEL, 'api': 'Vertex AI' if vertex else 'Gemini Developer API',
        'billing_enabled': vertex,
        'model_calls': len(result['model_usage']), **result, 'evidence_directory': str(directory),
    }
    save_json(directory / 'summary.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def cleanup(apply=False):
    if not STATE.exists():
        print('No tracked model key. Model project is retained.')
        return
    state = json.loads(STATE.read_text())
    print(json.dumps({'action': 'delete-model-key' if apply else 'dry-run',
        'project': state['operator']['project'], 'key_id': state['key_id']}))
    if not apply or state.get('cleaned'):
        return
    config = state['operator']
    key = command(config, ['services', 'api-keys', 'describe', state['key_id']], missing_ok=True)
    if key and not key.get('deleteTime'):
        if key.get('annotations', {}).get('devfest-owner') != state['owner']:
            raise Blocked('Model key ownership mismatch')
        command(config, ['services', 'api-keys', 'delete', state['key_id']])
    after = command(config, ['services', 'api-keys', 'describe', state['key_id']], missing_ok=True)
    if after and not after.get('deleteTime'):
        raise Blocked('Model key deletion not confirmed')
    KEY.unlink(missing_ok=True)
    state['cleaned'] = True
    save_json(STATE, state)
    print('Model key deleted; unbilled project and enabled APIs retained.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['setup', 'smoke', 'smoke-vertex', 'cleanup'])
    parser.add_argument('--project')
    parser.add_argument('--account')
    parser.add_argument('--create-project', action='store_true')
    parser.add_argument('--organization')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--check-authorization', action='store_true')
    args = parser.parse_args()
    if args.check_authorization and args.action != 'smoke-vertex':
        parser.error('--check-authorization requires smoke-vertex')
    if args.action == 'cleanup':
        cleanup(args.apply)
    else:
        configured = Path('.state/operator.json')
        pair = json.loads(configured.read_text()) if configured.exists() else {}
        vertex = args.action == 'smoke-vertex'
        expected_project = pair.get('project' if vertex else 'model_project')
        project = args.project or expected_project
        account = args.account or pair.get('account')
        if not project or not account:
            parser.error(f'{args.action} requires a configured project and account')
        if vertex and (project != expected_project or project == pair.get('model_project')
                       or account != pair.get('account')):
            parser.error('smoke-vertex requires the configured infrastructure project and account')
        if not vertex and expected_project and (project != expected_project or account != pair['account']):
            raise Blocked('Model project and account must match the configured project pair')
        config = {'project': project, 'account': account}
        if args.action in {'smoke', 'smoke-vertex'}:
            from google.genai.errors import APIError
            from httpx import TransportError
            from httpx2 import TransportError as TransportErrorV2
            from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError

            if args.create_project or args.organization or args.apply:
                parser.error(f'{args.action} accepts only project and account overrides')
            try:
                if vertex:
                    vertex_smoke(config, billing_quota_project=pair.get('model_project'),
                                 check_authorization=args.check_authorization)
                else:
                    smoke(config)
            except Blocked as error:
                print(f'Hydrogen 報帳查詢中止。{error}', file=sys.stderr)
                raise SystemExit(1) from None
            except (APIError, TransportError, TransportErrorV2, ChatGoogleGenerativeAIError) as error:
                code = getattr(error, 'code', None)
                status = f'HTTP {code}' if code else type(error).__name__
                print(f'Hydrogen 報帳查詢中止（{status}）。請開啟本機報帳排練報告。',
                      file=sys.stderr)
                raise SystemExit(1) from None
        else:
            setup(config, args.create_project, args.organization)


if __name__ == '__main__':
    main()
