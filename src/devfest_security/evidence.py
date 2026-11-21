"""Independent ledger read-back, not a second model assertion."""

from devfest_security.common import Blocked, digest, safe_id
from devfest_security.policy import EXPENSES
from devfest_security.store import Store


def readback(root: str, run_id: str) -> dict:
    ledger = Store(root).read(f"runs/{safe_id(run_id)}.json")
    return {
        "source": "gcs-object-readback" if root.startswith("gs://") else "local-file-readback",
        "exists": bool(ledger),
        "expenses": ledger.get("expenses", EXPENSES),
        "operations": ledger.get("operations", {}),
    }


def verify_evidence(evidence: dict, persisted: dict) -> dict:
    receipts = []
    for result in evidence.get("tool_results", []):
        value = result.get("structuredContent", {})
        if "receipt" not in value:
            if not result.get("isError", False):
                raise Blocked("Successful tool response omitted execution receipt")
            continue
        receipt = value["receipt"]
        stored = persisted["operations"].get(receipt["receipt_id"])
        if stored != value or receipt["run_id"] != evidence["run_id"]:
            raise Blocked("Tool receipt does not match independent persisted evidence")
        if digest(value["data"]) != receipt["after_sha256"]:
            raise Blocked("Receipt hash does not match tool data")
        receipts.append(receipt)
    # A successful call with no receipt must not be presented as evidence of execution.
    if any(not r.get("isError", False) for r in evidence.get("tool_results", [])) and not receipts:
        raise Blocked("Successful tool response omitted execution receipt")
    changed = {key: value for key, value in persisted["expenses"].items() if value != EXPENSES[key]}
    return {
        "run_id": evidence["run_id"],
        "model_source": evidence["model_source"],
        "status": evidence["status"],
        "readback_source": persisted["source"],
        "receipt_count": len(receipts),
        "changed_expenses": changed,
        "unauthorized_effect_observed": bool(changed) and evidence["principal"] == "alice",
    }
