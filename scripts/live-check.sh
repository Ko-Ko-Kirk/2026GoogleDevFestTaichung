#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
# A fresh, operator-reviewed .state/execution-policy.json is required.
# Cleanup remains available after the execution review expires.
trap './scripts/cleanup.sh --apply' EXIT
./scripts/deploy.sh
./scripts/live-demo.sh
./scripts/cloud.sh deploy-runtime
./scripts/cloud.sh verify-runtime
./scripts/cloud.sh logs
./scripts/cleanup.sh --apply
./scripts/verify-cleanup.sh
