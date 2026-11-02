# Engineering unfreeze — EVAL_A3 B1-L / B2-L（本地开发，非 staging 授权）

- **decided_at**: `2026-11-02`
- **status**: **Active** — local engineering only
- **plan**: [`eval-production-independent-service.md`](../../../docs/architecture/plans/eval-production-independent-service.md) v1.2+
- **P0 契约**：[`EVAL_RUNTIME_CONTRACT.md`](../../../docs/architecture/plans/EVAL_RUNTIME_CONTRACT.md) · [`B1_ROUTE_MATRIX.md`](../../../docs/architecture/plans/B1_ROUTE_MATRIX.md) · [`EVAL_MODEL_GATEWAY.md`](../../../docs/architecture/plans/EVAL_MODEL_GATEWAY.md) · [`EVAL_DATA_MIGRATION.md`](../../../docs/architecture/plans/EVAL_DATA_MIGRATION.md)
- **parent**：A-local Closed · B0 Closed
- **freeze**：[`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md)
- **production**：仍冻结（`process_split_authorized=false` / `staging_ready=false` / authorize 禁止）

## 一句话

**staging 是验收闸门，不是开工闸门。**  
本解冻允许在本机 VM/Docker 上做 B1-L / B2-L（及同轨本地的 P1 / B3-L / S1 工程），证据一律 `environment=local`；**不**签 staging、**不**翻 `process_split_authorized`。

## 闸门对照

| 动作 | 本解冻 |
|---|---|
| 写 B1-L / B2-L 代码与测试 | ✅ 允许 |
| 本机 Compose：eval-api + PG + Keycloak/JWKS + MinIO | ✅ 允许 |
| 标 `environment=staging` / staging_ready | ❌ 禁止 |
| `process_split_authorized=true` | ❌ 禁止 |
| production_signed / authorize | ❌ 禁止 |
| 激活 `ENGINEERING_UNFREEZE_EVAL_A3_B1_STAGING` | ❌ 另开；需独立主机 |

## 允许范围

| 阶段 | 内容 |
|---|---|
| **B1-L** | 独立 API + PG migrations + 本地 OIDC/JWKS；read/store 全量；动态执行 **503** + 统一错误体；`/eval` UI 降级 |
| **B2-L** | PG SKIP LOCKED job + Worker + lease/heartbeat/DLQ；runner allowlist；enqueue+execute 双点校验；Central 停机本地测 |
| **P1**（可随本解冻） | 评分语义修正（不计 accuracy） |
| **B3-L**（可随本解冻） | 沙箱原型 + 本地迁移/dual-read/回滚演练；**无生产数据** |
| **S1**（可随本解冻） | 安全套件本地门禁；生产级执行仍依赖沙箱就绪 |

## 允许的代码面

- `packages/aiplat-evaluation/`（app/worker/compose/migrations/scripts/tests）
- `aiPlat-platform/apps/eval/`（代理、503、UI 契约所需最小改动）
- management `/eval` 对 503 的降级展示（若需）
- 对应 docs / CAPABILITIES / registry

**不允许**：伪造 staging 证据；静默扩到 B4-S/B6；翻转 chart `a3_process_split_authorized`。

## 证据要求

- 所有 drill / closeout JSON：`environment=local`（或 `local-dev`）  
- **禁止** `environment=staging` 或 `production_signed=true`  
- healthz：`process_split_authorized=false`

## 退出条件

| 结果 | 动作 |
|---|---|
| B1-L + B2-L 本地验收通过 | 本地 closeout；**等独立主机**再开 B4-S 解冻 |
| 范围滑到 staging 宣称 / authorize | **停**；撤回越界提交 |
| 无 allowlist 跑 skill/tool | B2-L 失败 |

## Outcome

- **In progress** — B1-L: execute **503** stubs + Compose PG/MinIO + PG EvalStore + **`/eval` UI 降级文案**；see [`B1L_LOCAL.md`](../../../packages/aiplat-evaluation/docs/a3/B1L_LOCAL.md).
- Keycloak Compose realm：可选后续；下一步优先 **B2-L Worker allowlist**。
- `process_split_authorized=false`；证据 `environment=local`。
