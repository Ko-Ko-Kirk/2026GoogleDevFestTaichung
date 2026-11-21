"""Explicit Model Armor checkpoints for a LangGraph. No silent offline fallback."""

from devfest_security.common import Blocked
from devfest_security.cost import require_cloud_execution


def interpret(result: dict) -> str:
    if result.get("invocation_result") != "SUCCESS":
        raise Blocked("Model Armor did not finish successfully")
    state = result.get("filter_match_state")
    if state == "MATCH_FOUND":
        return "blocked"
    if state != "NO_MATCH_FOUND":
        raise Blocked("Model Armor returned an unspecified match state")
    # An aggregate NO_MATCH with a failed filter must never become an allow.
    def check(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "execution_state" and child != "EXECUTION_SUCCESS":
                    raise Blocked(f"Model Armor filter failed: {child}")
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(result)
    return "allowed"


class Armor:
    def __init__(self, template: str | None):
        self.template = template
        self.client = None
        if template:
            require_cloud_execution("Model Armor scans")
            from google.api_core.client_options import ClientOptions
            from google.cloud import modelarmor_v1

            from devfest_security.auth import credentials

            parts = template.split("/")
            if len(parts) != 6 or parts[0] != "projects" or parts[2] != "locations" or parts[4] != "templates":
                raise ValueError("Expected full Model Armor template resource name")
            self.client = modelarmor_v1.ModelArmorClient(
                transport="rest",
                client_options=ClientOptions(api_endpoint=f"modelarmor.{parts[3]}.rep.googleapis.com"),
                credentials=credentials(parts[1]),
            )

    def scan(self, text: str, surface: str, response: bool = False) -> dict:
        if not self.client:
            return {"surface": surface, "source": "disabled", "decision": "not_scanned"}
        from google.cloud import modelarmor_v1

        if len(text.encode()) > 24000:
            raise Blocked("Model Armor input exceeds the lab's scan budget")
        data = modelarmor_v1.DataItem(text=text)
        if response:
            result = self.client.sanitize_model_response(
                request={"name": self.template, "model_response_data": data, "multi_language_detection_metadata": {"enable_multi_language_detection": True}}, retry=None, timeout=30
            )
        else:
            result = self.client.sanitize_user_prompt(
                request={"name": self.template, "user_prompt_data": data, "multi_language_detection_metadata": {"enable_multi_language_detection": True}}, retry=None, timeout=30
            )
        raw = type(result.sanitization_result).to_dict(
            result.sanitization_result, use_integers_for_enums=False
        )
        return {"surface": surface, "source": "live-model-armor", "multi_language_detection": True, "decision": interpret(raw), "result": raw}
