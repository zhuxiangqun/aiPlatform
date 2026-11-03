# Evaluation A3 prep（Accepted 有条件 · 未授权拆分）

> ADR: [`ADR-EVALUATION-A3.md`](../../../../reports/five-products/ADR-EVALUATION-A3.md) — **Accepted（有条件）**  
> 默认仍为 Central **共宿 D1**。

| Doc | Purpose |
|-----|---------|
| [`SPLIT_CHECKLIST.md`](./SPLIT_CHECKLIST.md) | 进程拆分硬门 |
| [`PREP_STATUS.json`](./PREP_STATUS.json) | 自动检查结果 |
| [`LIVE_DRILL_EVIDENCE.md`](./LIVE_DRILL_EVIDENCE.md) | 生产 live 证据模板 |
| [`B2L_LOCAL_CLOSEOUT.md`](./B2L_LOCAL_CLOSEOUT.md) | B2-L 本地工程验收（≠ staging authorize） |
| [`B3L_LOCAL.md`](./B3L_LOCAL.md) | B3-L local_stub 沙箱雏形（无真实隔离） |
| [`LLM_LOCAL.md`](./LLM_LOCAL.md) | 可选 prompt_eval LLM + `b2l_llm_dynamic_gate.sh`（stub 必过 / live 可选） |
| [`LIVE_LLM_SMOKE.md`](./LIVE_LLM_SMOKE.md) | 10 条 stub vs live×3 smoke（`accuracy_claim=false`；证据 `local-eval-live-llm-*.json`） |
| [`P1_DIMENSIONS.md`](./P1_DIMENSIONS.md) | groundedness（有 gold 才计分）+ latency p50/p95 / cost_per_success；composite v1 |
| [`B3L_LOCAL_CLOSEOUT.md`](./B3L_LOCAL_CLOSEOUT.md) | B3-L 本地工程验收（≠ staging authorize） |
| [`S1_LOCAL.md`](./S1_LOCAL.md) | S1 SECURITY_EVAL_V1 fixture 门禁（ASR≠accuracy） |
| [`S1_LIVE.md`](./S1_LIVE.md) | S1 live_llm 攻击集（ASR/leak/false_refusal；无 skill tools；≠安全认证） |
| [`P1_LOCAL.md`](./P1_LOCAL.md) | P1–P1.2 + engineering composite（text/safety 计分；asr 报告项；≠accuracy） |
| [`B4S_PREP.md`](./B4S_PREP.md) | B4-S 主机前置（未确认 → 阻塞；≠ authorize） |
| [`MICROVM_PREP.md`](./MICROVM_PREP.md) | microVM 前置探测（无 KVM/runtime → 阻塞；≠ live tools） |
| [`CONTRACT_LOCAL.md`](./CONTRACT_LOCAL.md) | B1/B2 契约 standalone 收敛门禁（temporary_proxy=0） |
| [`P1_CANONICAL.md`](./P1_CANONICAL.md) | P1 双路径：package 计分 canonical；Central legacy report-only |
| B2 wall-clock | `AIPLAT_EVAL_JOB_TIMEOUT_SEC` → `timed_out`（见 `app/worker/timeout.py`） |
| B2 cancel | `POST .../jobs/{id}/cancel` → `cancelled`（`cancel_job`） |
| B2 cost cap | `AIPLAT_EVAL_JOB_COST_CAP` / `cost_cap` → `timed_out` |
| `scripts/local_track_closeout.sh` | 本地轨收口（P1+S1+authorize locked；≠ B4） |

```bash
bash packages/aiplat-evaluation/scripts/a3_local_rehearsal.sh  # #4 → 🟨
bash packages/aiplat-evaluation/scripts/a3_prep_check.sh
# process_split_authorized 恒 false 直至 checklist 全 ✅
bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh status
bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh authorize  # 未全 ✅ → REFUSE
```
