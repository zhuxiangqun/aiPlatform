# EVAL Runtime Contract — Worker / Runner（B 轨）

> **类型**：契约（B2 实施前置）  
> **版本**：v1.0 · 2026-11-02  
> **状态**：Design baseline · **未实施**  
> **父方案**：[`eval-production-independent-service.md`](./eval-production-independent-service.md)  
> **关联**：[`B1_ROUTE_MATRIX.md`](./B1_ROUTE_MATRIX.md) · [`EVAL_MODEL_GATEWAY.md`](./EVAL_MODEL_GATEWAY.md)  
> **诚实性**：不设 `process_split_authorized=true`；B2 仅 allowlist runner；工具执行等 B3 沙箱。

---

## 1. 目标

定义 Eval Worker 如何执行评测任务，保证：

1. **不**变成「分布式单体」（禁止 `core.harness` 私有 import）。  
2. **不**在执行路径依赖 Central HTTP 存活。  
3. B2 在无沙箱前 **fail-closed**：工具/代码/终端类 runner 不得跑。

---

## 2. EvalRunner 接口

每个 `runner_id` 实现同一生命周期（同步或异步均可，状态机见 §5）：

| 方法 | 职责 | 失败 |
|---|---|---|
| `prepare(job) → ctx` | 解析 payload、校验租户/配额、解析证据 URI | 不可重试配置错 → `failed` |
| `execute(ctx) → raw` | 执行评测（只读或允许的 LLM 调用） | 超时/成本顶 → `timed_out` / `failed` |
| `collect(ctx, raw) → evidence` | 写 PG 元数据 + Object Store；返回 report refs | 写失败可重试 |
| `cancel(ctx)` | 协作取消；释放租约 | best-effort |

**幂等**：`job.idempotency_key`（租户内唯一）。同一 key 重复入队返回已有 `job_id`，不二次执行。

**错误码（与 Route Matrix 统一 shape）**：见 [`B1_ROUTE_MATRIX.md`](./B1_ROUTE_MATRIX.md) §错误体。Runner 侧拒绝使用：

- `execution_not_migrated` — 阶段未迁移  
- `sandbox_required` — 需要沙箱但未就绪  
- `runner_forbidden` — allowlist 拒绝  

---

## 3. B2 Runner allowlist（强制）

| Runner | B2 | 条件 |
|---|---|---|
| `replay_trace` | ✅ | 只读已有证据 |
| `prompt_eval` | ✅ | 纯文本 LLM；**无工具** |
| `kb_rag` | ✅ | **只读**检索；无写 KB |
| `code_review_gold` | ✅ | 静态/半静态；无沙箱工具链 |
| `skill_suite`（含工具/代码/终端） | ❌ | 等 B3 沙箱 |
| `arena` | ⚠️ | **仅**纯文本模型对战；触发工具 → 禁止 |
| `http_probe` / `cli_probe` | ❌ | B3 + 容器/微 VM |
| `security_redteam` | ❌ | S1 + 沙箱 |

不在 allowlist → **禁止静默执行**；返回统一错误体（`sandbox_required` 或 `runner_forbidden`）。

### 3.1 双点校验（fail-closed）

| 检查点 | 行为 |
|---|---|
| **API enqueue** | forbidden `runner_id` → 拒绝入队（建议 HTTP 422/403 + 统一 `error` 体） |
| **Worker execute 前** | 再校验 allowlist；旧 job / 绕过 API 的 payload 同样拒绝 → `dead_letter` 或 `failed` |

缺任一检查点 = 契约违规。实施验收必须覆盖「直接 INSERT job 表绕过 API」用例。

---

## 4. 能力归属（随 Worker 打包 vs 禁止）

| 能力 | B2 归属 | 说明 |
|---|---|---|
| LLM 调用 | Worker → infra ModelManager / LLM client | 见 [`EVAL_MODEL_GATEWAY.md`](./EVAL_MODEL_GATEWAY.md)；**不经 Central HTTP** |
| KB 只读检索 | Worker 内公开检索 API / 只读连接 | 禁止写；禁止直读业务库旁路 |
| Skill / Tool 执行 | **B2 禁止** | B3 沙箱 + 受控 runner |
| Evidence 读写 | Eval PG + Object Store | 库内 URI+hash |
| 选模 | `best_model_for_purpose` / ModelManager | 禁止 Eval 自建模型注册表 |

### 4.1 禁止清单

- `from core.harness...` 私有模块（非 facade 公开出口）  
- 执行路径 `http://central/...` 回调跑 skill/LLM  
- 直读 Central / FDE / Ontology 业务表  
- 无校验信任伪造的内部 header 充当租户  

允许：`core.api.core_facade`（或等价公开 client）、`aiPlat-infra` ModelManager、本包 `packages/aiplat-evaluation` 内公开模块。

---

## 5. Job 租约与状态机

### 5.1 字段（最低集）

| 字段 | 含义 |
|---|---|
| `job_id` | 主键 |
| `tenant_id` | 租户 |
| `runner_id` | runner |
| `idempotency_key` | 幂等键 |
| `status` | `queued\|running\|succeeded\|failed\|cancelled\|timed_out\|dead_letter` |
| `attempts` | 已尝试次数 |
| `lease_expires_at` | 租约到期；过期可被其他 Worker 抢 |
| `heartbeat_at` | 最近心跳 |
| `payload_uri` / `payload_json` | 小载荷 JSON；大输入走 Object Store |
| `error_code` / `error_detail` | 与统一错误体对齐 |

队列实现：**PG `FOR UPDATE SKIP LOCKED`**（v1 无 Redis）。

### 5.2 规则

- Worker 领取 job → `running` + 设置 `lease_expires_at`。  
- 执行中周期性 `heartbeat`；租约过期且无心跳 → 可重新入队（`attempts++`）。  
- `attempts >= max_attempts` → `dead_letter`（人工/工具处理）。  
- 成本/墙钟硬顶 → `timed_out`；**不得**标 `succeeded`。

---

## 6. 依赖矩阵（Central 停机验收）

| 依赖 | 独立地址 / 配置 | Central 停机时 | 备注 |
|---|---|---|---|
| Eval PG | `AIPLAT_EVAL_DB_URL` | **必须活** | |
| Object Store | `AIPLAT_EVAL_OBJECT_URL` | **必须活**（有大对象时） | |
| OIDC JWKS | `AIPLAT_EVAL_JWKS_URL` | API 鉴权必须活；已领取 job 可按策略降级 | |
| Model provider | `MODEL_PROVIDER_URL` / 独立 Ollama·vLLM 端点 | **必须独立可达** | 与 Central **同机同生命周期 → 验收不计通过** |
| Central HTTP | — | **允许死** | 执行路径零依赖 |

**B2「Central 停机仍可消化已入队 allowlist job」** 仅当：PG +（如需）Object + **独立** Model provider 存活，且 runner ∈ allowlist。

---

## 7. B2 验收清单（契约）

> **B2-L local**（工程证明，≠ staging）：见 `packages/aiplat-evaluation/docs/a3/B2L_LOCAL_CLOSEOUT.md` + `scripts/b2l_local_closeout.sh`。  
> Live infra LLM / staging Central-down provider 仍属后续；本地确定性 fixture 不计 accuracy。

- [x] enqueue 拒绝 `skill_suite` / `http_probe`（统一错误体）— **B2-L local**。  
- [x] Worker 对伪造 job 行二次拒绝（fail-closed）— **B2-L local**。  
- [x] `replay_trace` / `prompt_eval` / `kb_rag`(只读) 本地确定性路径跑通（Central 不依赖）；live provider 待接线。  
- [x] lease 过期可被另一 Worker 接管或 dead_letter — **B2-L local**。  
- [x] import guard：Worker 包无 `core.harness` 私有 import — **B2-L local**。  

---

## 8. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-02 | v1.0 | 初版：Runner 生命周期、allowlist、双点校验、lease、依赖矩阵 |
