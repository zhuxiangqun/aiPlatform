#!/usr/bin/env bash
# verify-deploy.sh — production deployment validation
# Run after each deploy to verify all services are healthy.
# Usage: bash scripts/verify-deploy.sh [NAMESPACE]
set -euo pipefail

NS="${1:-aiplat}"
FAIL=0

check() {
    local label="$1"
    local cmd="$2"
    if eval "$cmd" 2>/dev/null; then
        echo "  ✅ $label"
    else
        echo "  ❌ $label"
        FAIL=$((FAIL+1))
    fi
}

echo "=== aiPlat Deployment Verification ==="
echo "Namespace: $NS"
echo ""

# ── K8s Health ──
echo "[K8s Pods]"
check "core pods running" "kubectl get pods -n $NS -l app.kubernetes.io/component=core --no-headers 2>/dev/null | grep -c Running | xargs -I{} test {} -ge 1"
check "infra pods running" "kubectl get pods -n $NS -l app.kubernetes.io/component=infra --no-headers 2>/dev/null | grep -c Running | xargs -I{} test {} -ge 1"

# ── API Health ──
echo "[API Health]"
MGMT_URL="${MGMT_URL:-http://aiplat-management.$NS:8000}"
check "management health" "curl -sf $MGMT_URL/health > /dev/null"
check "4-layer health" "curl -sf $MGMT_URL/api/diagnostics/health/all | python3 -c \"import sys,json; layers=json.load(sys.stdin); assert all(v.get('status') in ('healthy','degraded') for v in layers.values())\""

# ── Critical APIs ──
echo "[Critical APIs]"
check "agent list" "curl -sf $MGMT_URL/api/core/workspace/agents > /dev/null"
check "model list" "curl -sf http://aiplat-infra.$NS:8001/api/models > /dev/null"

# ── Data Integrity ──
echo "[Data Integrity]"
check "shared_pool accessible" "python3 -c \"
import sys; sys.path.insert(0,'.'); from core.harness.memory.shared_pool import get_shared_knowledge_pool
p=get_shared_knowledge_pool(); p._load(); print(f'facts={len(p._facts)}')
\" 2>/dev/null | grep -q 'facts=' && echo OK"

echo ""
echo "=============================="
if [ "$FAIL" -eq 0 ]; then
    echo "✅ Deployment verified (0 failures)"
else
    echo "❌ Deployment has $FAIL failure(s)"
fi
exit $FAIL
