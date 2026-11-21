import argparse
import asyncio
import json
import uuid
from pathlib import Path

from devfest_security.agent import RunConfig, run_agent
from devfest_security.common import save_json
from devfest_security.evidence import readback, verify_evidence
from devfest_security.manifest import pin
from devfest_security.mcp_client import connect, discover
from devfest_security.store import Store


def main():
    parser = argparse.ArgumentParser(description="Private DevFest synthetic security lab")
    commands = parser.add_subparsers(dest="command", required=True)
    configuration = commands.add_parser("configure", help="Operator-only scenario setup, never an MCP tool")
    configuration.add_argument("--store", default=".state/local-store")
    configuration.add_argument("--description", choices=["normal", "poisoned"], default="normal")
    configuration.add_argument("--principal", choices=["alice", "bob"], default="alice")
    configuration.add_argument("--unsafe-synthetic", action="store_true")
    capture = commands.add_parser("pin", help="Capture only a reviewed, known-good discovery result")
    capture.add_argument("--endpoint", default="http://127.0.0.1:8080/mcp")
    capture.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--endpoint", default="http://127.0.0.1:8080/mcp")
    run.add_argument("--model", choices=["fixture-read", "fixture-attack", "fixture-approve", "vertex", "gemini"], default="fixture-read")
    run.add_argument("--defense", choices=["none", "armor", "pin", "policy", "all"], default="policy")
    run.add_argument("--principal", choices=["alice", "bob"], default="alice")
    run.add_argument("--pin-path")
    run.add_argument("--armor-template")
    run.add_argument("--project")
    run.add_argument("--region", default="us-central1")
    run.add_argument("--model-location", default=RunConfig.__dataclass_fields__["model_location"].default)
    run.add_argument("--gemini-model", default=RunConfig.__dataclass_fields__["gemini_model"].default)
    run.add_argument("--prompt", default=RunConfig.__dataclass_fields__["prompt"].default)
    run.add_argument("--run-id", default=str(uuid.uuid4()))
    run.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--store", required=True)
    verify.add_argument("--evidence", type=Path, required=True)
    args = vars(parser.parse_args())
    command = args.pop("command")
    if command == "configure":
        Store(args["store"]).write("operator-config.json", {
            "description": args["description"], "principal": args["principal"],
            "enforce": not args["unsafe_synthetic"],
        })
    elif command == "pin":
        async def capture_pin():
            async with connect(args["endpoint"], "pin-review") as (session, server):
                value = await discover(session, args["endpoint"], server)
                pin(args["output"], value)
                print(json.dumps(value, ensure_ascii=False, indent=2))
        asyncio.run(capture_pin())
    elif command == "run":
        output = args.pop("output")
        evidence = asyncio.run(run_agent(RunConfig(**args)))
        save_json(output, evidence)
        print(f"Evidence saved: {output}; status={evidence['status']}")
        if evidence["status"] == "error":
            raise SystemExit(1)
    else:
        evidence = json.loads(args["evidence"].read_text())
        persisted = readback(args["store"], evidence["run_id"])
        summary = verify_evidence(evidence, persisted)
        save_json(args["evidence"].with_suffix(".readback.json"), persisted)
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
