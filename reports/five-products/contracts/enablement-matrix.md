# 本切片契约启用矩阵（WP2 草案 v0）

> 场景：`fp-internal-bundle-pi-diag-001` · 2026-10-23  
> 级别：可测最小草案，**不是**六套生产 API。

| 对象 | 本切片状态 | 生产者 | 消费者 | 版本/草案 | 不兼容/失联行为 | owner |
|------|------------|--------|--------|-----------|-----------------|--------|
| Identity / Policy | **启用** | aiPlat（`require_auth` / `_resolve_identity` / PolicyGate） | FDE API、发布面、目标服务 | 草案 `id-policy-fp-001` | 伪造身份失败；客户端不得放行服务端已拒 | 架构临时 R |
| Agent Bundle | **启用** | aiPlat export（`export_pi_bundle`） | Pi 安装加载 | 草案 `bundle-fp-001`；夹具 sample-app | 坏包/不兼容拒绝安装；`permission_claims`≠授权 | aiPlat 临时 R |
| Runtime Control | **启用** | Pi Thin | 诊断（状态引用）、运维 | 草案 `runtime-fp-001` + `pi-thin-offline.md` | 按离线表；TTL/过期停止 | Pi 临时 R |
| Evidence / Diagnosis | **启用（MVP）** | Pi 事件 + aiPlat 资产版本 | 诊断报告 → FDE | 草案 `evidence-fp-001` | 缺证据 → `unknown`/`stale`，禁 healthy | 诊断临时 R |
| Delivery（FDE） | **启用** | FDE acceptance / delivery | 业务验收人 | 草案 `delivery-fp-001` | 无 report 绑定不得「通过」（拟建） | FDE 临时 R |
| Semantic | **本切片未启用** | n/a | n/a | n/a | n/a | n/a |

## 最小字段（启用行 · 与落地方案对齐）

- **Identity**：tenant_id, actor_id\|service_id, scopes[], audience, request_id, trace_id, product_id, environment_id, authn_source, expires_at  
- **Bundle**：bundle_id, schema_version, source_asset_ids[], asset_versions[], runtime_compat_range, permission_claims[], model_requirements, build_info, integrity, rollback_hint  
- **Runtime**：instance_id, deploy_version, config_version, health, heartbeat_at, event_types[], offline_until, command_authz  
- **Evidence**：run_id, trace_id, bundle_version, runtime_version, evidence_refs[], freshness, report_id, status∈{ok,unknown,stale,fail}  
- **Delivery**：scenario_id, requirement_refs[], acceptance_decision, evidence_report_ids[], signer, decided_at  

Semantic 字段：未启用，不填。

## 负向用例（启用集 · ≥3 · 供 WP3/WP4）

1. 伪造身份调用发布或验收 API → 拒绝  
2. 坏 Bundle / 篡改 integrity → 安装前拒绝  
3. 诊断缺 Pi 或 aiPlat 证据 → 报告 unknown/stale，不得成功  
4. （加分）离线超 TTL 或 denied_ops → 停止/拒绝  
