#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec uv run --frozen python -c 'import json; from devfest_security.cost import report; print(json.dumps(report(), indent=2))'
