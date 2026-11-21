import pytest

from devfest_security.agent import RunConfig, run_agent
from devfest_security.armor import Armor
from devfest_security.cloud import Cloud
from devfest_security.common import Blocked
from devfest_security.cost import require_local_endpoint
from devfest_security.store import Store


@pytest.mark.parametrize("action", ["setup", "deploy", "smoke", "live_demo", "deploy_runtime", "verify_runtime"])
def test_cloud_execution_stops_before_preflight_or_network(action, tmp_path, monkeypatch):
    cloud = Cloud({"project": "example-lab-123", "account": "operator@example.com",
                   "region": "us-central1", "venue": "taichung"}, tmp_path / "state.json")
    monkeypatch.setattr(cloud, "preflight", lambda: pytest.fail("No cloud requests allowed"))
    with pytest.raises(Blocked, match="Zero-spend"):
        getattr(cloud, action)()
    assert not cloud.path.exists()


@pytest.mark.parametrize("endpoint", ["https://example.run.app/mcp", "http://localhost/mcp",
                                    "http://127.0.0.1.example.com/mcp", "http://192.168.1.1/mcp"])
def test_only_literal_loopback_can_execute(endpoint):
    with pytest.raises(Blocked):
        require_local_endpoint(endpoint)
    require_local_endpoint("http://127.0.0.1:8080/mcp")


async def test_vertex_is_blocked_before_discovery_or_credentials(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "example-lab-123")
    monkeypatch.setenv("LAB_ALLOW_CLOUD", "true")
    with pytest.raises(Blocked, match="Vertex"):
        await run_agent(RunConfig(endpoint="https://example.run.app/mcp", run_id="cost-test", model="vertex"))


def test_armor_and_gcs_fail_before_client_construction():
    with pytest.raises(Blocked, match="Model Armor"):
        Armor("projects/example-lab-123/locations/us-central1/templates/test")
    with pytest.raises(Blocked, match="GCS"):
        Store("gs://example-synthetic-bucket")
