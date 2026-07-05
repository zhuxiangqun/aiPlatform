#!/usr/bin/env bash
# rollback.sh — rollback K8s deployment to previous version
# Usage: bash scripts/rollback.sh [deployment_name]
set -euo pipefail

DEPLOY="${1:-aiplat-core}"
NAMESPACE="${AIPLAT_NAMESPACE:-aiplat}"

echo "Rolling back $DEPLOY in namespace $NAMESPACE..."

if command -v kubectl &>/dev/null; then
    kubectl rollout undo deployment/"$DEPLOY" -n "$NAMESPACE"
    echo "Waiting for rollback..."
    kubectl rollout status deployment/"$DEPLOY" -n "$NAMESPACE" --timeout=120s
elif [ -f ./deploy/helm/aiplat/values.yaml ]; then
    # Fallback: Helm rollback if kubectl unavailable
    RELEASE="${DEPLOY}"
    if helm history "$RELEASE" --max 2 2>/dev/null | tail -1 | grep -q .; then
        PREV_REV=$(helm history "$RELEASE" --max 2 2>/dev/null | tail -2 | head -1 | awk '{print $1}')
        helm rollback "$RELEASE" "$PREV_REV"
        echo "✅ Rolled back Helm release $RELEASE to revision $PREV_REV"
    else
        echo "No previous Helm revision found for $RELEASE"
        exit 1
    fi
else
    echo "Neither kubectl nor Helm chart found. Cannot rollback."
    exit 1
fi

echo "✅ Rollback of $DEPLOY complete"
