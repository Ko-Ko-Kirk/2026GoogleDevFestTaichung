"""Explicit operator account locally; attached service identity in cloud. No key files."""

import os
import subprocess
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import google.auth
from google.auth.credentials import Credentials


class GcloudCredentials(Credentials):
    def __init__(self, account: str, project: str):
        super().__init__()
        self.account = account
        self.project = project

    def refresh(self, request):
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token", f"--account={self.account}", f"--project={self.project}", "--quiet"],
            check=True, capture_output=True, text=True, timeout=45,
        )
        self.token = result.stdout.strip()
        self.expiry = (datetime.now(UTC) + timedelta(minutes=10)).replace(tzinfo=None)


@lru_cache(maxsize=8)
def operator_credentials(account: str, project: str):
    return GcloudCredentials(account, project)


def credentials(project: str | None = None):
    account = os.environ.get("LAB_GCLOUD_ACCOUNT")
    if account:
        project = project or os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project:
            raise ValueError("An explicit GOOGLE_CLOUD_PROJECT is required for local cloud credentials")
        return operator_credentials(account, project)
    return google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])[0]


def cloud_run_token(audience: str) -> str:
    account = os.environ.get("LAB_GCLOUD_ACCOUNT")
    if account:
        service_account = os.environ.get("LAB_INVOKER_SERVICE_ACCOUNT")
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project or not service_account or not service_account.endswith(f"@{project}.iam.gserviceaccount.com"):
            raise ValueError("Local cloud calls require an invoker service account in the explicit project")
        return subprocess.run(
            ["gcloud", "auth", "print-identity-token", f"--account={account}", f"--project={project}",
             f"--impersonate-service-account={service_account}", f"--audiences={audience}", "--include-email", "--quiet"],
            check=True, capture_output=True, text=True, timeout=45,
        ).stdout.strip()
    from google.auth.transport.requests import Request
    from google.oauth2.id_token import fetch_id_token

    return fetch_id_token(Request(), audience)
