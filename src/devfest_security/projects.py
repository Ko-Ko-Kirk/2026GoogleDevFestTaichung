"""One fixed unbilled model project plus one infrastructure project; no global switch."""

import argparse
import json
import shlex
from datetime import UTC, datetime, timedelta
from pathlib import Path

from devfest_security.cloud import OPERATOR, validate_operator
from devfest_security.common import Blocked, save_json
from devfest_security.free_model import command, local_model_key
from devfest_security.models import DEFAULT_GEMINI_MODEL

POLICY = Path('.state/execution-policy.json')
OPERATIONS = ['setup', 'deploy', 'smoke', 'live_demo', 'deploy_runtime', 'verify_runtime',
              'Gemini Developer inference', 'Model Armor scans', 'GCS IO', 'remote MCP transport']


def configuration() -> dict:
    config = validate_operator(json.loads(OPERATOR.read_text()))
    if not config.get('model_project'):
        raise Blocked('Run configure.sh with --project, --model-project and --account first')
    return config


def plan(config: dict) -> dict:
    model = config['model_project']
    account = config['account']
    return {
        'infrastructure': {'project': config['project'], 'account': account,
                           'billing': 'required; shared free allowances must be reviewed'},
        'model': {'project': model, 'account': account, 'billing': 'must remain unlinked',
                  'api': 'Gemini Developer API; vertexai=False'},
        'commands': [
            shlex.join(['./scripts/model-project.sh', 'setup', '--project', model, '--account', account]),
            './scripts/model-project.sh smoke',
            './scripts/project-pair.sh check',
            './scripts/project-pair.sh review --allowance-review .state/allowance-review.json',
            './scripts/live-check.sh',
            './scripts/model-project.sh cleanup --apply',
        ],
        'note': 'Reuse this fixed pair. A project split does not multiply billing-account free allowances.',
    }


def check(config: dict) -> dict:
    results = {}
    for role, project in [('infrastructure', config['project']), ('model', config['model_project'])]:
        target = {'project': project, 'account': config['account']}
        identity = command(target, ['projects', 'describe', project])
        if identity.get('projectId') != project or identity.get('lifecycleState') != 'ACTIVE':
            raise Blocked(f'{role} project identity is inactive or does not match')
        billing = command(target, ['billing', 'projects', 'describe', project])
        if role == 'model' and (billing.get('billingEnabled', True) or billing.get('billingAccountName')):
            raise Blocked('Model project is linked to billing; free-only execution stopped')
        if role == 'infrastructure' and not billing.get('billingEnabled'):
            raise Blocked('Infrastructure project requires active billing for its free allowances')
        results[role] = billing
    return results


def prepare_review(config: dict, path: Path, minutes: int = 60) -> dict:
    if not 1 <= minutes <= 180:
        raise Blocked('Review duration must be between 1 and 180 minutes')
    evidence = json.loads(path.read_text())
    checked = datetime.fromisoformat(evidence.get('checked_at', '2000-01-01T00:00:00+00:00'))
    now = datetime.now(UTC)
    if (checked.tzinfo is None or not checked <= now < checked + timedelta(minutes=minutes)
            or evidence.get('project') != config['project']
            or evidence.get('account') != config['account'] or not evidence.get('evidence')):
        raise Blocked('Fresh account-level allowance evidence for this project/account is required')
    _, fingerprint = local_model_key(config['model_project'], config['account'])
    billing = check(config)
    if evidence.get('billing_account') != billing['infrastructure'].get('billingAccountName'):
        raise Blocked('Allowance evidence belongs to another billing account')
    # Expiry starts at the original allowance check, never at this command's time.
    policy = {
        'mode': 'reviewed-free-tier', 'checked_at': checked.isoformat(),
        'expires_at': (checked + timedelta(minutes=minutes)).isoformat(),
        'cloud_project': config['project'], 'model_project': config['model_project'],
        'model_project_unbilled': True, 'model_key_sha256': fingerprint,
        'gemini_model': DEFAULT_GEMINI_MODEL, 'operations': OPERATIONS,
        'mcp_endpoints': [], 'allowance_evidence': evidence,
    }
    save_json(POLICY, policy)
    return {'saved': str(POLICY), 'expires_at': policy['expires_at'],
            'model_project': config['model_project'], 'key_bound': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'check', 'review'], nargs='?', default='plan')
    parser.add_argument('--allowance-review', type=Path)
    parser.add_argument('--minutes', type=int, default=60)
    args = parser.parse_args()
    config = configuration()
    if args.action == 'plan':
        result = plan(config)
    elif args.action == 'check':
        result = check(config)
    elif args.allowance_review:
        result = prepare_review(config, args.allowance_review, args.minutes)
    else:
        parser.error('--allowance-review is required for review')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
