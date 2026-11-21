#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
uv sync --frozen --extra runtime --group dev
printf '%s\n' 'Local environment ready. Run scripts/configure.sh before cloud operations.'
