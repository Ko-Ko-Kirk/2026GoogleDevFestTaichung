#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
uv run --frozen --extra runtime ruff check src tests scripts
uv run --frozen --extra runtime shellcheck scripts/*.sh
uv run --frozen --extra runtime pytest -q
