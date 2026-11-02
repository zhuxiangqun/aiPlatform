# EVAL Model Access — Worker → infra（B 轨）

> **类型**：契约（B2 实施前置）  
> **版本**：v1.0 · 2026-11-02  
> **状态**：Design baseline · **未实施**  
> **父方案**：[`eval-production-independent-service.md`](./eval-production-independent-service.md)  
> **关联**：[`EVAL_RUNTIME_CONTRACT.md`](./EVAL_RUNTIME_CONTRACT.md)  
> **诚实性**：v1 **不**新建独立 Model Gateway 微服务；**不经 Central HTTP** 调模型。

---

## 1. 决定

| 项 | 锁定 |
|---|---|
| 架构 | Worker **直连** `aiPlat-infra` **ModelManager / LLM client**（与 Core `InfraLLMAdapter` 同栈） |
| 选模 | `best_model_for_purpose(purpose)`（或等价公开入口）；禁止 Eval 自建模型注册表 |
| Central | 执行路径 **零** Central HTTP 依赖 |
| 独立 Gateway 服务 | **不做**（v1）；若未来拆分另开 ADR |

---

## 2. 配置与独立可达

| 变量 / 概念 | 作用 |
|---|---|
| `MODEL_PROVIDER_URL`（或 infra 等价：provider base URL 列表） | **独立于 Central 进程** 的推理端点 |
| infra 发现的远程 API keys / Ollama 扫描 | 仍以 ModelManager 为权威 |
| 超时 / max_tokens / 成本硬顶 | Eval Worker 强制；记入 job/审计 |

### 2.1 Central 停机 vs Provider

| 依赖 | 独立地址 | Central 停机时 |
|---|---|---|
| Model provider | `MODEL_PROVIDER_URL` / 独立本机 Ollama·vLLM 端口 | **必须仍可达**；否则该 runner **禁止**跑 |
| Central HTTP | — | 允许死 |

若 Ollama/vLLM **与 Central 同机、同生命周期停启** → **不得**计入「Central 停机仍可执行」通过项（依赖矩阵见 Runtime Contract §6）。

---

## 3. 强制记录（每次 LLM 调用）

- `purpose`、`model`（含版本/标签若可得）  
- `token` 用量、估算 `cost`、`latency_ms`  
- `tenant_id`、`job_id`、`runner_id`  
- 超时 / 取消原因  

租户配额（runs/day、token/day）在 **Eval API enqueue** 与 **Worker** 两侧可强制；超限 → 明确失败，非 success。

---

## 4. 安全与合规

- 生产/staging：**禁止**默认 HS256 本地 secret 调「生产模型」旁路。  
- Prompt/输出进 Object Store 时遵守 PII/红队隔离（见数据迁移/主方案对象存储节）。  
- 不在评测日志打印 API key。

---

## 5. 验收

- [x] Worker 单元/集成：无 Central 进程时仍可完成一次 `prompt_eval`（独立 provider）— **local**：`AIPLAT_EVAL_LLM` stub/http via `packages/aiplat-evaluation/app/llm/client.py`（[`LLM_LOCAL.md`](../../../packages/aiplat-evaluation/docs/a3/LLM_LOCAL.md)）+ `scripts/b2l_llm_dynamic_gate.sh`。  
- [x] 同机捆绑 provider 的场景在验收文档中标记为 **不适用/失败** — 文档诚实声明：须独立生命周期；Central-looking URL 运行时拒绝。  
- [x] 调用审计字段齐全 — purpose/model/tokens/latency/cost_estimate/job/tenant/`central_http=false`。  
- [x] 无 `core` 内平行 `model_registry` — Eval 包 stdlib HTTP；不 import `core.harness`。  
- [ ] 真实独立 Ollama/vLLM **live** 通过 — 可选 `AIPLAT_EVAL_LLM_LIVE=1`；无主机/无 provider 时不算生产认证。  

---

## 6. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-02 | v1.0 | 初版：infra 直连、独立 provider、禁止 Central 跳板 |
