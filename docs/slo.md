# aiPlat Service Level Objectives

> **Status**: Draft | **Version**: 1.0 | **Owner**: aiPlat Architecture Team

## Service Tier Definitions

| Tier | Services | Criticality | Target Availability |
|:---|:---|:--:|:--:|
| **Tier 1** | aiPlat-core (API), aiPlat-management (gateway) | Critical — platform unusable without | 99.9% |
| **Tier 2** | aiPlat-infra (LLM/model management) | High — degradation but not full outage | 99.5% |
| **Tier 3** | aiPlat-platform (builder/workflow) | Medium — batch operations, not real-time | 99.0% |

## SLO Matrix

### Tier 1: Core + Management (Critical)

| SLI | Target | Measurement Window |
|:---|:--:|:--:|
| **Availability** | ≥ 99.9% | 30 days |
| **Latency (P95)** | ≤ 500ms for agent execute endpoint | 30 days |
| **Error Rate** | ≤ 0.1% of all requests | 30 days |
| **LLM Response Time** | ≤ 30s for non-streaming | 30 days |
| **Pipeline Start Latency** | ≤ 5s from request to execution | 30 days |

### Tier 2: Infra (High)

| SLI | Target | Measurement Window |
|:---|:--:|:--:|
| **Availability** | ≥ 99.5% | 30 days |
| **Model Health Check** | ≤ 10s response | 5 minutes |
| **Model Discovery Latency** | ≤ 1s to list models | 5 minutes |

### Tier 3: Platform (Medium)

| SLI | Target | Measurement Window |
|:---|:--:|:--:|
| **Availability** | ≥ 99.0% | 30 days |
| **Builder Session Commit** | ≤ 3s | 30 days |

## Error Budget

| Tier | Availability | Allowed Downtime (monthly) | Error Budget |
|:---|:--:|:--|:--:|
| Tier 1 | 99.9% | 43.2 minutes | 0.1% |
| Tier 2 | 99.5% | 3.6 hours | 0.5% |
| Tier 3 | 99.0% | 7.2 hours | 1.0% |

## Alerting Thresholds

| Alert | Condition | Severity | Action |
|:---|:---|:--|:---|
| Tier 1 availability | Error rate > 1% (5 min) | Critical | PagerDuty |
| Tier 1 latency | P95 > 2s (5 min) | Warning | Slack |
| Tier 1 error rate | 50% budget consumed | Warning | Slack + Jira ticket |
| Tier 1 error rate | 90% budget consumed | Critical | PagerDuty |
| Tier 2 availability | Error rate > 5% (5 min) | Warning | Slack |
| Pipeline timeout | > 300s (1 occurrence) | Warning | Slack |

## Measurement

All SLIs are measured via Prometheus metrics:

| SLI | Prometheus Metric |
|:---|:---|
| Availability | `http_requests_total{status_code!~"5.."}` / `http_requests_total` |
| Latency | `histogram_quantile(0.95, http_request_duration_seconds_bucket)` |
| Error Rate | `http_requests_total{status_code=~"5.."}` / `http_requests_total` |
| LLM Time | `llm_request_duration_seconds` |
| Pipeline Latency | `pipeline_start_latency_seconds` |

## Review Cadence

| Activity | Frequency | Owner |
|:---|:---|:---|
| SLO review | Monthly | Architecture Team |
| Error budget review | Monthly | Platform Engineering |
| Alert threshold tuning | Quarterly | SRE |

## Performance Baselines (Measured)

> Numbers collected from aiPlat v0.0.1 running on macOS M1 (local, no GPU). Production numbers will vary.

| Metric | Local (M1) | Target (Production) | Status |
|:---|:---:|:---|:--:|
| Agent execute P50 | ~2s | ≤ 200ms | ⚠️ local LLM bottleneck |
| Agent execute P95 | ~8s | ≤ 2s | ⚠️ local LLM bottleneck |
| Health check latency | <10ms | ≤ 50ms | ✅ |
| Model list latency | <100ms | ≤ 1s | ✅ |
| Pipeline start latency | ~3s | ≤ 5s | ✅ |
| Concurrent health checks | 50 req/s | 500 req/s | ⚠️ not stress tested |
| Wiki search latency | ~500ms | ≤ 1s | ✅ |
| Agent step latency (T1 model) | ~1s | ≤ 500ms | ⚠️ local|

**Stress test**: `bash scripts/stress-test.sh localhost 50 500`
**Continuous tracking**: Prometheus metrics → Grafana dashboard

## K8s Readiness

Production deployment requires all liveness/readiness probes to pass:

```yaml
# Core service (Tier 1)
livenessProbe:
  httpGet: {path: /api/core/health, port: 8002}
  initialDelaySeconds: 30
  periodSeconds: 15
readinessProbe:
  httpGet: {path: /api/core/health, port: 8002}
  initialDelaySeconds: 15
  periodSeconds: 10
```

**Readiness gate checklist**:
- [ ] Core health endpoint returns 200
- [ ] Infra model list endpoint returns models  
- [ ] Management health/all returns 4-layer healthy
- [ ] Database WAL mode enabled (pool.db)
- [ ] Gossip protocol peers reachable (if multi-AZ)
