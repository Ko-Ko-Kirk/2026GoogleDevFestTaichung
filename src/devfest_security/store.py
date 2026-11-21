"""Atomic local files or GCS objects; no in-memory receipt presented as persistence."""

import copy
import fcntl
import json
from collections.abc import Callable
from pathlib import Path

from devfest_security.common import save_json
from devfest_security.cost import require_cloud_execution


class Store:
    def __init__(self, root: str):
        self.root = root
        self.bucket = None
        if root.startswith("gs://"):
            require_cloud_execution("GCS IO")
            import os

            from google.cloud import storage

            from devfest_security.auth import credentials
            self.bucket = storage.Client(
                project=os.environ.get("GOOGLE_CLOUD_PROJECT"), credentials=credentials()
            ).bucket(root[5:])
        else:
            Path(root).mkdir(parents=True, exist_ok=True)

    def read(self, key: str, default: dict | None = None) -> dict:
        if self.bucket is not None:
            require_cloud_execution("GCS IO")
            from google.api_core.exceptions import NotFound

            try:
                return json.loads(self.bucket.blob(key).download_as_text())
            except NotFound:
                return copy.deepcopy(default or {})
        path = Path(self.root) / key
        return json.loads(path.read_text()) if path.exists() else copy.deepcopy(default or {})

    def update(self, key: str, mutation: Callable[[dict], dict], default: dict) -> dict:
        if self.bucket is not None:
            require_cloud_execution("GCS IO")
            from google.api_core.exceptions import NotFound, PreconditionFailed

            for _ in range(5):
                blob = self.bucket.blob(key)
                try:
                    # Download and generation must describe the same object version.
                    blob.reload()
                    generation = int(blob.generation)
                    value = json.loads(blob.download_as_text(if_generation_match=generation))
                except NotFound:
                    generation, value = 0, copy.deepcopy(default)
                except PreconditionFailed:
                    continue
                result = mutation(value)
                try:
                    blob.upload_from_string(
                        json.dumps(value, ensure_ascii=False),
                        content_type="application/json",
                        if_generation_match=generation,
                    )
                    return result
                except PreconditionFailed:
                    continue
            raise RuntimeError("Concurrent ledger update did not converge; no retry of tool call")
        path = Path(self.root) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            value = self.read(key, default)
            result = mutation(value)
            save_json(path, value)
            return result

    def write(self, key: str, value: dict) -> None:
        def replace(current: dict) -> dict:
            current.clear()
            current.update(value)
            return current

        self.update(key, replace, {})
