from types import SimpleNamespace

import pytest

from devfest_security.armor_probe import MAX_LOCAL_CODEPOINTS, reserve, sample_budget
from devfest_security.cloud import Cloud
from devfest_security.common import Blocked


def test_probe_payload_and_aggregate_bound():
    assert sample_budget() < 1024
    with pytest.raises(Blocked):
        sample_budget([('oversized', 'x' * 1025)] * 3)


def test_failed_calls_keep_reservation_and_separate_months(tmp_path):
    path = tmp_path / 'ledger.json'
    assert reserve(path, MAX_LOCAL_CODEPOINTS, '2026-10') == MAX_LOCAL_CODEPOINTS
    with pytest.raises(Blocked):
        reserve(path, 1, '2026-10')
    assert reserve(path, 1, '2026-11') == 1


def test_corrupt_negative_usage_cannot_unlock_budget(tmp_path):
    path = tmp_path / 'ledger.json'
    path.write_text('{"months":{"2026-10":-10000}}')
    with pytest.raises(Blocked):
        reserve(path, 100, '2026-10')


def test_template_cli_uses_regional_endpoint_without_global_config(tmp_path, monkeypatch):
    config = {'project': 'example-lab-123', 'account': 'operator@example.com',
              'region': 'us-central1', 'venue': 'taichung'}
    cloud = Cloud(config, tmp_path / 'state.json')
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout='{}', stderr='')

    monkeypatch.setattr('devfest_security.cloud.subprocess.run', run)
    cloud.gcloud(['model-armor', 'templates', 'describe', 'example'])
    command, kwargs = calls[0]
    assert command[0] == 'gcloud'
    assert '--project=example-lab-123' in command
    assert '--account=operator@example.com' in command
    assert kwargs['env']['CLOUDSDK_API_ENDPOINT_OVERRIDES_MODELARMOR'] == (
        'https://modelarmor.us-central1.rep.googleapis.com/')
