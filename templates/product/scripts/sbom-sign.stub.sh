#!/usr/bin/env bash
# P2-1: engineering SBOM via platform builder; syft/cosign optional upgrade.
set -euo pipefail
ROOT="${1:-.}"
echo "Engineering (wired): python -c \"from builder.artifact_sbom_attest import build_sbom_attest_bundle; print(build_sbom_attest_bundle('$ROOT', artifact_id='local'))\""
echo "Optional upgrade: syft packages dir:$ROOT -o cyclonedx-json > dist/sbom.cdx.json"
echo "Optional upgrade: cosign sign-blob --yes dist/sbom.cdx.json"
echo "Gate: AIPLAT_P2_1_SBOM=1 or prodish profile requires sbom.digest on artifact.security.json"
