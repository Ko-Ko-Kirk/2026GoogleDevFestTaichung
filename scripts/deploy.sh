#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
./scripts/cloud.sh setup
./scripts/cloud.sh deploy
./scripts/cloud.sh smoke
