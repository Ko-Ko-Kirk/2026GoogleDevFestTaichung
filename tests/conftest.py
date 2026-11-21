import pytest


@pytest.fixture(autouse=True)
def isolate_execution_review(monkeypatch):
    # Developer machine may have a real live review. Tests must never use it.
    monkeypatch.setenv('LAB_EXECUTION_POLICY', '{}')
    monkeypatch.delenv('LAB_CLOUD_PROJECT', raising=False)
