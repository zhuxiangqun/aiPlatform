# aiPlat Production Readiness Checklist

> 从实验级升级到准生产级的逐项检查。每项必须是生产中可验证的，不是"设计中有"。

## Deployment

| # | 检查项 | 状态 | 证据 |
|:--:|------|:--:|------|
| D1 | Helm chart 可部署到 K8s | ✅ | `deploy/helm/aiplat/` |
| D2 | 多 AZ 支持 | ✅ | `values-multi-az.yaml` |
| D3 | HPA 自动扩缩容 | ✅ | Core 2-10 副本, 70% CPU 触发 |
| D4 | CI/CD 自动构建 | ✅ | 3 GitHub Actions workflows |
| D5 | 一键回滚 | ✅ | `scripts/rollback.sh` (kubectl + Helm) |
| D6 | GitOps (ArgoCD) | ✅ | `deploy/gitops/argocd-app.yaml` |

## Reliability

| # | 检查项 | 状态 | 证据 |
|:--:|------|:--:|------|
| R1 | **RTO 验证** (Recovery Time Objective) | ⚠️ | 目标 30min, 未实战验证 |
| R2 | **RPO 验证** (Recovery Point Objective) | ⚠️ | 目标 5min, 未实战验证 |
| R3 | 崩溃自动恢复 | ✅ | _checkpoint + _snapshot + graph_snapshots |
| R4 | 数据一致性 | ✅ | SHA-256 audit hash chain |
| R5 | Circuit breaker | ✅ | MCPCircuitBreaker + WikiCircuitBreaker |

## Observability

| # | 检查项 | 状态 | 证据 |
|:--:|------|:--:|------|
| O1 | Metrics (Prometheus) | ✅ | docker-compose + custom exporter |
| O2 | Tracing (Jaeger + OTel) | ✅ | OTel SDK (260行) + FastAPI instrumentation |
| O3 | Dashboards (Grafana) | ✅ | `deploy/grafana/dashboards/aiplat-overview.json` |
| O4 | Alerting | ✅ | Prometheus Alertmanager |
| O5 | SLO defined | ✅ | `docs/slo.md` (3-tier) |

## Security

| # | 检查项 | 状态 | 证据 |
|:--:|------|:--:|------|
| S1 | SAST (静态扫描) | ✅ | ruff bandit + security_scanner |
| S2 | DAST (动态扫描) | ✅ | OWASP ZAP CI job |
| S3 | Dependabot | ✅ | Weekly pip updates |
| S4 | Secrets management | ✅ | AES-256-GCM SecretsManager |
| S5 | Audit trail | ✅ | SHA-256 hash chain |

## Production Gating

以下条件必须全部满足才能标记为 **"生产就绪"**：

| # | Gate | 状态 |
|:--:|------|:--:|
| **G1** | RTO ≤ 30min 经实战验证 | ⚠️ |
| **G2** | RPO ≤ 5min 经实战验证 | ⚠️ |
| **G3** | 压力测试: 100 并发, P95 ≤ 2s | ⚠️ |
| **G4** | 外部渗透测试通过 | ❌ |
| **G5** | 连续 7 天生产级运行 (0 critical incidents) | ❌ |

## RTO/RPO Validation Procedure

```bash
# 1. Deploy aiPlat via Helm
helm install aiplat ./deploy/helm/aiplat

# 2. Start workload
bash scripts/stress-test.sh http://localhost:8000 10 500

# 3. Kill core pod (simulate crash)
kubectl delete pod -l app.kubernetes.io/component=core -n aiplat

# 4. Measure recovery
# RTO = time from kill → healthy response
kubectl wait --for=condition=ready pod -l app.kubernetes.io/component=core -n aiplat --timeout=300s
# Expected: ≤ 30s (目标 30min 有大量余量)

# 5. Verify data integrity
curl http://localhost:8000/api/diagnostics/health/all
# Expected: all layers healthy, no data loss
```

## Stress Test Target

```bash
bash scripts/stress-test.sh http://localhost:8000 50 500
# Expected:
#   P50 < 200ms
#   P95 < 2s
#   Error rate < 0.1%
```
