#!/usr/bin/env bash
# env-diff.sh — check environment configuration consistency
# Compares docker-compose.yml vs deploy/helm/aiplat/values.yaml
# Usage: bash scripts/env-diff.sh

set -euo pipefail

echo "=== Environment Configuration Diff ==="
echo ""

MISMATCH=0

# Compare service ports
echo "[Ports]"
DC_PORTS=$(grep -E '^\s+- "?[0-9]+:[0-9]+' docker-compose.yml 2>/dev/null | grep -oP '[0-9]+(?=:[0-9]+)' | sort -u || echo "")
HELM_PORTS=$(grep 'port:' deploy/helm/aiplat/values.yaml 2>/dev/null | awk '{print $2}' | sort -u || echo "")

for port in 8000 8001 8002 8003; do
    if echo "$DC_PORTS" | grep -q "$port" 2>/dev/null; then
        if echo "$HELM_PORTS" | grep -q "$port" 2>/dev/null; then
            echo "  ✅ Port $port: docker-compose + Helm 一致"
        else
            echo "  ⚠️  Port $port: docker-compose 有, Helm 无"
            MISMATCH=$((MISMATCH+1))
        fi
    fi
done

# Compare environment variables
echo ""
echo "[Environment Variables]"
DC_ENV=$(grep -oP 'AIPLAT_\w+' docker-compose.yml 2>/dev/null | sort -u || echo "")
HELM_ENV=$(grep -oP 'AIPLAT_\w+' deploy/helm/aiplat/values.yaml 2>/dev/null | sort -u || echo "")

COMMON=$(comm -12 <(echo "$DC_ENV" | sort) <(echo "$HELM_ENV" | sort) 2>/dev/null | wc -l || echo "0")
DC_ONLY=$(comm -23 <(echo "$DC_ENV" | sort) <(echo "$HELM_ENV" | sort) 2>/dev/null | wc -l || echo "0")
HELM_ONLY=$(comm -13 <(echo "$DC_ENV" | sort) <(echo "$HELM_ENV" | sort) 2>/dev/null | wc -l || echo "0")

echo "  Common: $COMMON, Docker-only: $DC_ONLY, Helm-only: $HELM_ONLY"

# Compare service names
echo ""
echo "[Services]"
DC_SVCS=$(grep -E '^\s{2}\w+:' docker-compose.yml 2>/dev/null | grep -v '^\s\{4\}' | sed 's/://g' | sort -u | head -10 || echo "")
HELM_SVCS=$(grep 'enabled:' deploy/helm/aiplat/values.yaml 2>/dev/null | wc -l || echo "0")

echo "  docker-compose services: $(echo "$DC_SVCS" | wc -l)"
echo "  Helm services (enabled): $HELM_SVCS"

echo ""
if [ "$MISMATCH" -eq 0 ]; then
    echo "✅ Environment consistency: OK"
else
    echo "⚠️  $MISMATCH port mismatch(es) found — review docker-compose.yml vs values.yaml"
fi
