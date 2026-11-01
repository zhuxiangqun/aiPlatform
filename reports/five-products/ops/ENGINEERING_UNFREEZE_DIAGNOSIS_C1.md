# Engineering unfreeze — DIAGNOSIS_V1 C1（D1c MVP）

- **decided_at**: `2026-11-01`
- **status**: **Closed — C1 PASS**（[`DIAGNOSIS_V1_C1_CLOSEOUT.md`](./DIAGNOSIS_V1_C1_CLOSEOUT.md) · #513）
- **C0**: [`DIAGNOSIS_V1`](./ENGINEERING_UNFREEZE_DIAGNOSIS_V1.md) · PR #510 / `5c01721f`
- **charter**: [`diagnosis-v1-charter.md`](../../../docs/architecture/plans/diagnosis-v1-charter.md)
- **freeze**: [`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md)
- **owner**: diagnosis（D1c MVP）
- **production**: 仍冻结（`staging_ready=false` / `process_split=false` / `cutover=false` / `d3_production=false`）

## 目标

实现诊断产品 **D1c cohost MVP**：

- 两个场景：`run_failure`（S1）、`version_regression`（S2）；
- 证据驱动：aiPlat / Pi / FDE / Evaluation 只读 EvidenceRef；
- 输出 Case / Finding / Hypothesis / Report；
- **不自动修复**：无 `remediate`；`auto_execute=false`；
- 不做 A3、不碰 staging/authorize。

## 允许的代码面

- `aiPlat-platform/apps/diagnosis/api/`（canonical API）
- `aiPlat-core/core/apps/diagnosis/service/`（业务逻辑）
- `aiPlat-core/core/harness/diagnosis/`（仅通用检测）
- `packages/aiplat-diagnosis/`（contracts / fixtures / packaging）
- `aiPlat-management/frontend/src/pages/Diagnosis/`（`/diagnosis`）
- `aiPlat-platform/registry/apps.yaml`（diagnosis app）
- `capabilities.manifest`（C1 实际入册）
- `STATUS.md` / module docs / tests

## 禁止

| 禁止 | 原因 |
|---|---|
| `POST …/remediate` / 自动执行 | 本产品边界：只建议 |
| 跨产品写 / 直读源 DB | 证据只读；不拥有源事实 |
| A3 进程/DB 拆分 | 需 ADR + staging |
| staging / `production_signed` / authorize | 生产门仍冻 |
| 改 checklist 🟨→✅ | 硬门 |
| 新开 EVAL 功能 | EVAL `/eval` preview 冻结新功能，C1 期间只修缺陷 |

## 10 个真实 fixture（C1 必做）

| # | case_id | 场景 | 期望 | 证据来源 |
|---:|---|---|---|---|
| 1 | `dx.s1.tool_timeout` | S1 | `timeout` | aiPlat run/syscall 超时导出 |
| 2 | `dx.s1.tool_wrong_args` | S1 | `tool_error` | Pi fault `fi2_bad_bundle` + test 导出 |
| 3 | `dx.s1.model_route_cheap` | S1 | `wrong_model_route` | `pi-live.json` model + routing 快照 |
| 4 | `dx.s1.policy_tool_deny` | S1 | `policy_deny` | `fi4_denied_ops` + `fi1_auth` 401/403 |
| 5 | `dx.s1.context_trunc` | S1 | `context_missing` | context assemble/token budget 日志 |
| 6 | `dx.s1.no_trace` | S1 | `unknown` | `fi3_missing_evidence` / `trace_id:""` |
| 7 | `dx.s1.stale_kb` | S1 | `stale` | `fi4_offline_ttl` / wiki version 过期 |
| 8 | `dx.s2.prompt_edit` | S2 | `prompt_regression` | `local-evaluation-d2-local-*.json` + gold |
| 9 | `dx.s2.eval_gate_fail` | S2 | `eval_score_drop` | G2a/gate report + eval gate schema |
| 10 | `dx.s2.no_baseline` | S2 | `unknown` | 删除 `before_current` 的 eval closeout |

**规则**
- 前 6 个 fixture 未落盘前，不宣称 Top-1/Top-3；
- synthetic 与 real 分开报告；
- 每个 Finding/Hypothesis 必须有 evidence ref；无证据 → `unknown`。

## C1 出口

| 项 | 门槛 |
|---|---|
| Case/API/UI | `/api/platform/apps/diagnosis` + `/diagnosis` 可跑 |
| 场景 | S1 + S2 |
| 真实 fixture | **≥10**（上表） |
| Top-1 | ≥70%（real fixture 子集） |
| Top-3 | ≥85% |
| 证据完整率 | ≥90% |
| 无证据结论 | **0** |
| unknown/stale | ≥90% 正确 |
| 单案耗时 | <10 分钟 |
| 自动修复 | **无** |

## 串行规则

- **EVAL_V1**：`/eval` preview 冻结新功能；C1 期间只修缺陷。
- **DIAGNOSIS C1**：独占 4–6 周；不再并行开 EVAL 新功能。
- C1 完成后再决定 C2 / EVAL G2b。

## Manifest / 入册

- C1 实现 PR 中再把 `diagnosis` 加入 `capabilities.manifest`：
  - `current_autonomy: A0`；
  - `current_delivery: D1` + `delivery_mode: cohost`（D1c）；
  - `target: A2 / D2`；
  - `process_split_authorized: false`。
- `apps.yaml` 加 diagnosis app（enabled=true）。
- `STATUS` 加 Diagnosis 行；`check_five_products_status_sync.py` 必须通过。
- **不写 A2 当现状**；C1 出口再评估。

## 验证

```bash
python3 reports/five-products/modules/diagnosis/contracts/validate_sample.py
python3 scripts/check_five_products_status_sync.py
bash scripts/ops_engineering_freeze_check.sh
```

## 回滚

- 禁用 diagnosis app / 移除 `/diagnosis`；
- 保留 C0/C1 文档与 fixture；
- 不触碰源产品数据。

## 变更控制

- 范围变化 → 新 unfreeze，不静默扩大。
- 任何 A3/staging/authorize/auto-repair → 不在本解冻内。
- 完成/中止 → 追加 Outcome，并更新 `ENGINEERING_FREEZE.md` 解冻史。

## Outcome

- **PASS** · `20261101T131134Z` · PR #513 / merge `5ba444ac`
- Blind fixture metrics（n=10）：Top-1=1.00 · Top-3=1.00 · evidence_complete=1.00 · bare=0 · unknown/stale=1.00
- `accuracy_claim=false` · 无 `remediate` · `process_split_authorized=false`
- Closeout：[`DIAGNOSIS_V1_C1_CLOSEOUT.md`](./DIAGNOSIS_V1_C1_CLOSEOUT.md)
- 下一决策（需新 unfreeze）：DIAGNOSIS C2 **或** EVAL G2b
