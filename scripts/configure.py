"""Explicit local configuration, with a fence against changing an active environment."""
import argparse
import json
from pathlib import Path

from devfest_security.cloud import OPERATOR, STATE, validate_operator
from devfest_security.common import Blocked, save_json

parser = argparse.ArgumentParser()
parser.add_argument("--project", required=True)
parser.add_argument("--account", required=True)
parser.add_argument("--model-project", help="Separate Gemini Developer API project, kept unbilled")
parser.add_argument("--venue", choices=["taipei", "taichung"], default=json.loads(Path("venue.json").read_text())["venue"])
parser.add_argument("--region", default="us-central1")
config = validate_operator({key: value for key, value in vars(parser.parse_args()).items() if value is not None})
if STATE.exists():
    state = json.loads(STATE.read_text())
    if not state.get("cleaned") and config != state["operator"]:
        raise Blocked("Clean the existing environment before changing account/project/venue")
save_json(OPERATOR, config)
print("Saved local operator configuration. No cloud requests were sent.")
