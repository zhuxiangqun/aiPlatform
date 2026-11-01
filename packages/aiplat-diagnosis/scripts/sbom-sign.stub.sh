#!/usr/bin/env bash
# D2 SBOM/sign stub — prints commands only; does not execute syft/cosign.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
exec bash "$ROOT/templates/module/scripts/sbom-sign.stub.sh"
