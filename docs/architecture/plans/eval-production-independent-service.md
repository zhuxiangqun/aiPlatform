---
doc_type: Architecture
---

# EVAL Production Independent Service — 完整方案（B 轨）

> **文档类型**：Design / Implementation Plan（生产级独立评测服务）  
> **版本**：v1.2 · 2026-11-02  
> **状态**：P0 契约已齐 · **B1-L/B2-L 本地开发已解冻**（[`ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md`](../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md)）  
> **前置已完成**：A-local A0–A6（#529）· B0 JWKS（#531）· P0 docs（#533）  
> **P0 契约**：[`EVAL_RUNTIME_CONTRACT.md`](./EVAL_RUNTIME_CONTRACT.md) · [`B1_ROUTE_MATRIX.md`](./B1_ROUTE_MATRIX.md) · [`EVAL_MODEL_GATEWAY.md`](./EVAL_MODEL_GATEWAY.md) · [`EVAL_DATA_MIGRATION.md`](./EVAL_DATA_MIGRATION.md)  
> **关联**：[`eval-a3-independent-service.md`](./eval-a3-independent-service.md) · [`eval-v1-charter.md`](./eval-v1-charter.md) · [`ADR-EVALUATION-A3.md`](../../../reports/five-products/ADR-EVALUATION-A3.md) · [`SPLIT_CHECKLIST.md`](../../../packages/aiplat-evaluation/docs/a3/SPLIT_CHECKLIST.md)  
> **诚实性**：本稿不设 `process_split_authorized=true`；不宣称 accuracy / 安全认证。  
> **闸门**：staging = **验收/授权证**（B4-S/B6），**不是** B1-L/B2-L 开工证。本地证据 `environment=local`，不得标 staging。

---

## 0. 一句话目标

把评测从「Central 进程内顺手跑」升级为 **独立故障域的生产级评测平台**：API 入队、Worker 执行、独立 PG/OIDC、PG 队列、沙箱、可观测与门禁；并串行补齐 **评分语义（P1）** 与 **安全红队（S1）**。

```
今天（main）
  Central 共宿：动态 skill/prompt/KB/arena + runs_eval
  packages/aiplat-evaluation：:8010 store/health/JWT·JWKS
  process_split_authorized=false · accuracy_claim=false

目标（授权后）
  Eval API ──PG SKIP LOCKED──► Eval Worker(+Sandbox) ──infra ModelManager──► Provider
       │                              │
       ▼                              ▼
  Eval PG + Object Store            Evidence / Artifacts
  OIDC JWKS · 租户隔离 · OTel · 配额 · 备份/PITR · HA
```

---

## 0.1 已锁定默认（P0）

| 决策 | 锁定值 |
|---|---|
| 队列 | **PG `FOR UPDATE SKIP LOCKED`**（v1 **无 Redis**） |
| 模型 | Worker → **infra ModelManager**；**不经 Central HTTP**；provider 须 **独立地址** |
| Runtime | [`EVAL_RUNTIME_CONTRACT.md`](./EVAL_RUNTIME_CONTRACT.md)；禁 `core.harness` 私有 import |
| 路由 | [`B1_ROUTE_MATRIX.md`](./B1_ROUTE_MATRIX.md)；B1 动态执行默认 **503** + 统一错误体 |
| Allowlist | **enqueue + execute 双点 fail-closed** |
| 沙箱 | 工具/代码/文件/网络 → **必须沙箱（B3）**；B2 仅只读/纯文本 allowlist |
| 阶段序 | **本地**：B1-L → B2-L → P1 → B3-L → S1；**有主机后**：B4-S → B5-S → B6 |
| staging | 只挡 **B4-S / B6**；不挡本机写代码 |
| staging SLO | **只采基线**；不承诺 99.9% |
| 工期（单人+AI） | 整体约 **5–6 个月**；B2-L **5–7 周** |

---

## 1. 问题与动机

| 痛点 | 影响 |
|---|---|
| 动态评测共宿 Central | 长评测拖垮 Central；无法独立扩缩 |
| 无队列/Worker | 同步 HTTP；超时重试不可控 |
| 无沙箱 | 工具/代码执行即风险 |
| 评分/安全缺口 | 计分不诚实；无红队产品 |
| 准确率未认证 | G2c≠accuracy；G2b n=30 closeout 已完成、31–100 待双标；`accuracy_claim=false` |

---

## 2. 范围与非目标

### 2.1 范围内

1. Eval API / Worker / PG 队列 / Sandbox（按阶段）独立部署。  
2. 独立 PostgreSQL + 对象存储。  
3. 真实 OIDC JWKS（audience / alg allowlist / key rotation / tenant claim / service token — **B1 验收**）。  
4. canonical `/api/platform/apps/eval/**` 独立宿主；Central 仅网关。  
5. P1 评分语义；S1 安全套件（串行，不与 accuracy 混称）。  
6. 备份/PITR、限流、观测 → 授权切流。

### 2.2 非目标

| 不做 | 原因 |
|---|---|
| 无条件 `process_split_authorized=true` | ADR / checklist |
| 「所有程序」评测 | charter 首版范围 |
| 替代 FDE / Diagnosis / 自动修复 | 边界 |
| 本机 Docker 冒充 staging | 事件驱动复审 |
| B2 无沙箱跑 skill/tool | allowlist 禁止 |

### 2.3 评测对象（锁定）

**v1 = 仅 aiPlat 产物**（Agent/Skill/Prompt/KB/Workflow）。  
外部 HTTP/CLI → 后置且 **强制容器/微 VM**。

**沙箱规则（修正）**

| 任务 | 隔离 |
|---|---|
| 只读 replay / 纯文本评分 | cgroup + 超时即可（B2 allowlist） |
| 终端 / 代码 / 文件 / 网络 / 外部工具 | **必须沙箱（B3）** |
| 外部 HTTP/CLI | 容器/微 VM |

---

## 3. 现状基线

| 层 | 现状 |
|---|---|
| 动态执行 | **仍在 Central**（A-local/B0 未迁执行平面） |
| 独立宿主 | `:8010` store + JWT/JWKS |
| 授权 | `process_split_authorized=false` |

**诚实句**：A/B0 ≠ 生产级；动态执行尚未迁出 Central。

---

## 4. 目标架构

### 4.1 逻辑视图

见文首 ASCII。契约细节：

- Runner / lease / 依赖矩阵 → [`EVAL_RUNTIME_CONTRACT.md`](./EVAL_RUNTIME_CONTRACT.md)  
- 路由 / UI 503 → [`B1_ROUTE_MATRIX.md`](./B1_ROUTE_MATRIX.md)  
- 模型 → [`EVAL_MODEL_GATEWAY.md`](./EVAL_MODEL_GATEWAY.md)  
- 迁移 → [`EVAL_DATA_MIGRATION.md`](./EVAL_DATA_MIGRATION.md)

### 4.2 部署单元

| 单元 | 职责 |
|---|---|
| `eval-api` | HTTP、OIDC、入队、查询；**不跑长任务** |
| `eval-worker` | SKIP LOCKED 消费；allowlist runner；infra LLM |
| `eval-postgres` | 业务 + **job 表** |
| `eval-object` | MinIO/S3：加密、presigned 短 TTL、生命周期、红队/PII 隔离前缀 |
| `eval-sandbox` | B3+ |

### 4.3 Runner 与阶段

| Runner | B2 | B3+ |
|---|---|---|
| `replay_trace` / `prompt_eval` / `kb_rag`(只读) / `code_review_gold` | ✅ | ✅ |
| `skill_suite`（工具） / `http_probe` / `cli_probe` / 工具态 `arena` | ❌ | ✅ 沙箱后 |
| `security_redteam` | ❌ | S1 |

### 4.4 与 Central

| 允许 | 禁止 |
|---|---|
| 反向代理到 Eval API | Worker 私有 `core.harness` import |
| EvidenceRef 公开协议 | 直读业务表 |
| infra 选模 | Eval 自建 model registry；经 Central 调模型 |

双模：`AIPLAT_EVAL_MODE=cohost|standalone`；`AIPLAT_EVAL_SERVICE_URL` 代理。

---

## 5. 数据与契约

- PG `eval.*` + jobs；Object Store URI+hash。  
- `eval.protocol.v0` N-1；新增 job/heartbeat/sandbox schema。  
- 租户 `tenant_id`；跨租户 404。  
- 迁移/回滚：[`EVAL_DATA_MIGRATION.md`](./EVAL_DATA_MIGRATION.md)。

**OIDC（B1 验收必测）**：issuer JWKS、**audience**、**alg allowlist**、**key rotation**、**tenant claim**、**service token**（Worker 机机身份若需要）。

**对象存储**：at-rest 加密、presigned、生命周期、红队/PII 隔离。

---

## 6. 分阶段路线图（本地开发 vs staging 验收）

> **staging = 授权证，不是开工证。**  
> 本地解冻：[`ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md`](../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_A3_B1_B2_LOCAL_DEV.md)。

| 阶段 | 环境 | 核心 | 要 staging？ | 工期 |
|---|---|---|---|---|
| A/B0 ✅ | local | 独立进程 + JWKS | ❌ | — |
| **B1-L** | 本机 VM/Docker | API + PG + 本地 OIDC/JWKS；动态 **503**；UI 降级 | ❌ | 2–3 周 |
| **B2-L** | 本机 VM/Docker | SKIP LOCKED + Worker；allowlist；独立 provider | ❌ | **5–7 周** |
| **P1** | local | 评分语义 | ❌ | 1–2 周 |
| **B3-L** | local | 沙箱原型 + 本地迁移/回滚演练 | ❌ | 2–4 周 |
| **S1** | local | SECURITY_EVAL 套件 | ❌ | 4–8 周 |
| **B4-S** | **独立 staging** | live：备份/PITR/故障/回滚 | ✅ | 1–2 周 |
| **B5-S** | staging/生产 | HA、生产 SLO、限流 | ✅ | 2–3 周 |
| **B6** | staging | checklist ✅ + signed → `process_split_authorized=true` | ✅ | 变更窗口 |

```
本地（无需独立主机）
  A/B0 ✅ → B1-L → B2-L → P1 → B3-L → S1
有独立 staging 后（验收/授权）
  → B4-S → B5-S → B6(authorize)
```

单人+AI 合计约 **5–6 个月**；本地可完成约 **70–80%** 工程量。

### B1-L（本机）

- Compose：`eval-api` + PG + Keycloak（或 JWKS fixture）+ MinIO。  
- 全量 canonical **read/store**；动态执行 **503** + 统一错误体；`/eval` UI 降级。  
- `temporary_proxy` closeout 清零；证据 `environment=local`。  
- 详见 [`B1_ROUTE_MATRIX.md`](./B1_ROUTE_MATRIX.md)。

### B2-L（本机）

- API 只入队；Worker + lease/heartbeat/DLQ；allowlist 双点。  
- Central 停机 **本地**测；**MODEL_PROVIDER 须独立于 Central 进程**（可同物理机不同进程/容器）。  
- 详见 [`EVAL_RUNTIME_CONTRACT.md`](./EVAL_RUNTIME_CONTRACT.md) · [`EVAL_MODEL_GATEWAY.md`](./EVAL_MODEL_GATEWAY.md)。

### B3-L / P1 / S1（本机）

- 沙箱原型 + 脱敏迁移演练；评分语义；安全套件本地 gate。  
- **无生产数据**；不签 staging。

### B4-S / B5-S / B6（独立主机）

- 另开 `ENGINEERING_UNFREEZE_EVAL_A3_B1_STAGING`（或 B4 专用解冻）。  
- live 证据 → 硬化 → 授权切流。本机 local **不能**替代。

---

## 7. 产品轨（串在本地序内）

### 7.1 P1 — 评分语义（B2-L 之后）

`content_safety`/`refusal`/`text_quality` 计分或显式非计分；groundedness；latency/cost_per_success。`accuracy_claim=false` 直至 G2b。

### 7.2 S1 — SECURITY_EVAL_V1（B3-L 沙箱雏形后）

红队套件 + ASR 等；确定性检查优先；不与 G2a 混称。

---

## 8. 安全与合规

JWKS 必选（staging+）；禁默认 HS256 当生产；租户隔离；红队包加密；镜像扫描；不可变审计。

---

## 9. 可观测与 SLO

| 环境 | 要求 |
|---|---|
| **staging** | 采集可用性/延迟/错误率 **基线**；**不**承诺 99.9% |
| **生产（B5）** | 另定 SLO；入队 P95、拾取 P95、失败率、租户并发硬顶 |

配额：runs/day、token/day、arena、红队次数。

---

## 10. 工程纪律

一阶段一解冻；freeze 史；CAPABILITIES/registry；defect-gate；Runner 配置驱动。

---

## 11. 前置决策

| # | 决策 | 状态 |
|---|---|---|
| D1 | A/B0 为前置 | **是** |
| D2 | staging 主机 | **未确认 → 只阻塞 B4-S/B6**；**不**阻塞 B1-L/B2-L |
| D3 | 仅 aiPlat v1 | **锁定** |
| D4 | PG SKIP LOCKED | **锁定** |
| D5 | MinIO/S3 + 加密/隔离 | **锁定方向** |
| D6 | 本地可用 Keycloak Compose；staging 再接企业 IdP | **锁定** |
| D7 | 本地串行后 staging 验收 | **锁定** |
| D8 | HA 在 B5-S | **锁定** |

---

## 12. 成功标准

- B1-L / B2-L：本地验收绿；`environment=local`；无假 staging。  
- B2-L：allowlist 任务在 Central down + **独立 provider 进程**下可消化。  
- B6：checklist ✅ + **staging** signed live + authorize（本机不可替代）。  
- P1/S1：计分诚实；安全有独立入口（非 accuracy）。

---

## 13. 风险与止损

| 风险 | 止损 |
|---|---|
| 把 local 标成 staging | authorize / closeout **拒绝** |
| B2-L 跑 skill/tool | allowlist 拒绝 |
| provider 与 Central 同进程冒充独立 | 验收不计通过 |
| 无备份做生产回填 | 迁移硬门拒绝 |
| 无主机却开 B4-S | **停** |

---

## 14. 下一步

1. 合入本解冻 + 方案 v1.2（**本批**）。  
2. 开 **B1-L**：Compose（api+PG+Keycloak/JWKS+MinIO）→ migrations → 503 路由 → UI 降级。  
3. 续 **B2-L** Worker。  
4. 有独立主机后再开 B4-S 解冻 → B6。

---

## 15. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-02 | v1.0 | 初版 B1–B6 + P1/S1 |
| 2026-11-02 | v1.1 | P0 契约；SKIP LOCKED；allowlist；503；串行 |
| 2026-11-02 | v1.2 | **B1-L/B2-L 本地解冻**；staging 仅挡 B4-S/B6 |

---

## 16. 附录 — 三类评测落位

| 类型 | 今天 | B2 / B3 |
|---|---|---|
| 静态 | Central/API | API 或轻 Worker |
| 轨迹回放 | Central | Worker `replay_trace` |
| 动态（无工具） | Central | B2 Worker |
| 动态（有工具） | Central | **B3+ 沙箱** |
