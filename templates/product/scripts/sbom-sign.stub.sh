#!/usr/bin/env bash
# P0 stub — document only; wire to CI later.
set -euo pipefail
echo "syft packages dir:. -o spdx-json > dist/sbom.spdx.json   # install syft"
echo "cosign sign-blob --yes dist/sbom.spdx.json               # install cosign + key"
echo "P0: commands printed only; not executed."
