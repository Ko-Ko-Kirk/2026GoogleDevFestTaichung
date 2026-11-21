"""The same LangGraph hosted by Google Cloud Agent Runtime."""

import tempfile
import uuid
from pathlib import Path

from devfest_security.agent import RunConfig, run_agent
from devfest_security.common import save_json


class SecurityAgent:
    def __init__(self, endpoint: str, pin: dict, template: str, project: str, region: str):
        # Only serializable configuration is deployed, never operator credentials.
        self.endpoint = endpoint
        self.pin = pin
        self.template = template
        self.project = project
        self.region = region

    async def async_query(self, *, prompt: str) -> dict:
        """Run a bounded, defended synthetic expense query as the fixed lab persona Alice."""
        with tempfile.TemporaryDirectory(prefix="devfest-pin-") as directory:
            pin_path = Path(directory) / "manifest-pin.json"
            save_json(pin_path, self.pin)
            return await run_agent(RunConfig(
                endpoint=self.endpoint, run_id="runtime-" + uuid.uuid4().hex,
                model="gemini", defense="all", principal="alice",
                pin_path=str(pin_path), armor_template=self.template,
                project=self.project, region=self.region, prompt=prompt,
            ))
