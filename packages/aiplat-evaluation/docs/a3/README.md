# Evaluation A3 prep（Accepted 有条件 · 未授权拆分）

> ADR: [`ADR-EVALUATION-A3.md`](../../../../reports/five-products/ADR-EVALUATION-A3.md) — **Accepted（有条件）**  
> 默认仍为 Central **共宿 D1**。

| Doc | Purpose |
|-----|---------|
| [`SCORE_SCOPE_V1.md`](./SCORE_SCOPE_V1.md) | **首版满分范围**（功能/架构/本地·不含 microVM；5/5 定义） |
| [`SCORECARD_V1.md`](./SCORECARD_V1.md) / [`scorecard_v1.json`](./scorecard_v1.json) | 相对 scope 的诚实记分卡（功能 4.3 / 架构 5.0 / 本地 5.0） |
| [`COMPLIANCE_PII_V0.md`](./COMPLIANCE_PII_V0.md) | 合规/PII 最小集（启发式；`certified=false`） |
| [`SANDBOX_ISOLATION_V0.md`](./SANDBOX_ISOLATION_V0.md) | Docker `network=none` 诚实钉（≠ 隔离认证） |
| [`OIDC_MINIMAL_V0.md`](./OIDC_MINIMAL_V0.md) | 本地 JWT + Keycloak profile 最小路径 |
| [`ARCH_CONSOLIDATION_V1.md`](./ARCH_CONSOLIDATION_V1.md) | 架构收口 v1：拓扑 + freeze（双挂=2、core eval router 白名单） |
| [`SPLIT_CHECKLIST.md`](./SPLIT_CHECKLIST.md) | 进程拆分硬门 |
| [`PREP_STATUS.json`](./PREP_STATUS.json) | 自动检查结果 |
| [`LIVE_DRILL_EVIDENCE.md`](./LIVE_DRILL_EVIDENCE.md) | 生产 live 证据模板 |
| [`B2L_LOCAL_CLOSEOUT.md`](./B2L_LOCAL_CLOSEOUT.md) | B2-L 本地工程验收（≠ staging authorize） |
| [`B3L_LOCAL.md`](./B3L_LOCAL.md) | B3-L local_stub 沙箱雏形（无真实隔离） |
| [`LLM_LOCAL.md`](./LLM_LOCAL.md) | 可选 prompt_eval LLM + `b2l_llm_dynamic_gate.sh`（stub 必过 / live 可选） |
| [`LIVE_LLM_SMOKE.md`](./LIVE_LLM_SMOKE.md) | 10 条 stub vs live×3 smoke（`accuracy_claim=false`；证据 `local-eval-live-llm-*.json`） |
| [`P1_DIMENSIONS.md`](./P1_DIMENSIONS.md) | groundedness（有 gold 才计分）+ latency p50/p95 / cost_per_success；composite v1 |
| [`SESSION_V0.md`](./SESSION_V0.md) | 多轮 `session_eval` v0（2–3 轮；`accuracy_claim=false`） |
| [`SESSION_V1.md`](./SESSION_V1.md) | 多轮 `session_eval` v1（5–8 轮；`accuracy_claim=false`） |
| [`PREFERENCE_V0.md`](./PREFERENCE_V0.md) | 人评/偏好 A/B v0（≠ accuracy） |
| [`B3L_LOCAL_CLOSEOUT.md`](./B3L_LOCAL_CLOSEOUT.md) | B3-L 本地工程验收（≠ staging authorize） |
| [`S1_LOCAL.md`](./S1_LOCAL.md) | S1 SECURITY_EVAL_V1 fixture 门禁（ASR≠accuracy） |
| [`S1_LIVE.md`](./S1_LIVE.md) | S1 live_llm 攻击集（ASR/leak/false_refusal；无 skill tools；≠安全认证） |
| [`P1_LOCAL.md`](./P1_LOCAL.md) | P1–P1.2 + engineering composite（text/safety 计分；asr 报告项；≠accuracy） |
| [`G2B_PREP.md`](./G2B_PREP.md) | G2b 第二标注者预备（30 条 + κ；`accuracy_claim=false`） |
| [`PROD_LIVE.md`](./PROD_LIVE.md) | 生产候选模型 live 基线（25×3；≠ 3B smoke） |
| [`B4S_PREP.md`](./B4S_PREP.md) | B4-S 主机前置（未确认 → 阻塞 staging；≠ authorize） |
| [`B4S_LOCAL_REHEARSAL.md`](./B4S_LOCAL_REHEARSAL.md) | B4-S 本机 Docker 预演（`environment=local`；≠ staging） |
| [`B4S_RUNBOOK.md`](./B4S_RUNBOOK.md) | B4-S 操作手册（local → 将来 staging 复用） |
| [`MICROVM_PREP.md`](./MICROVM_PREP.md) | microVM 前置探测（无 KVM/runtime → 阻塞；≠ live tools） |
| [`CONTRACT_LOCAL.md`](./CONTRACT_LOCAL.md) | B1/B2 契约 standalone 收敛门禁（temporary_proxy=0） |
| [`P1_CANONICAL.md`](./P1_CANONICAL.md) | P1 双路径：package 计分 canonical；Central legacy report-only |
| B2 wall-clock | `AIPLAT_EVAL_JOB_TIMEOUT_SEC` → `timed_out`（见 `app/worker/timeout.py`） |
| B2 cancel | `POST .../jobs/{id}/cancel` → `cancelled`（`cancel_job`） |
| B2 cost cap | `AIPLAT_EVAL_JOB_COST_CAP` / `cost_cap` → `timed_out` |
| `scripts/local_track_closeout.sh` | 本地轨收口 v2（+session_v1 + preference fixture；authorize locked；≠ B4 / ≠ human κ） |
| `scripts/preference_v0_gate.sh` | preference 门禁（默认 eng fixture solo；可换真人 A/B） |
| `scripts/g2b_kappa.py` | G2b inter-annotator κ（prep；≠ accuracy） |
| `scripts/prod_live_baseline.sh` | 生产候选模型 live 基线 |
| `scripts/s1_prod_model_gate.sh` | 生产候选模型 S1 红队重跑 |
| `scripts/b4s_local_rehearsal.sh` | B4-S 本机预演（PG backup/restore；≠ staging） |
| `scripts/session_v1_gate.sh` | 多轮 session v1（5–8 轮） |
| `scripts/preference_v0_report.py` | 人评偏好报告 / 双人 agreement |
| `scripts/scorecard_v1_check.sh` | 记分卡诚实门禁（有 gap 禁止静默 5/5） |
| `scripts/arch_consolidation_v1_gate.sh` | 架构 freeze（mount 数 + core `*eval*` 白名单） |
| `scripts/compliance_pii_v0_gate.sh` | 合规/PII 启发式门禁 |
| `scripts/sandbox_isolation_v0_gate.sh` | 沙箱 isolation 诚实门禁 |
| `scripts/oidc_minimal_v0_gate.sh` | OIDC 最小路径门禁 |
| `scripts/b4s_evidence_refresh_gate.sh` | B4-S 本机证据刷新（默认结构；`AIPLAT_EVAL_B4S_RUN=1` 真跑） |

```bash
bash packages/aiplat-evaluation/scripts/scorecard_v1_check.sh
bash packages/aiplat-evaluation/scripts/a3_local_rehearsal.sh  # #4 → 🟨
bash packages/aiplat-evaluation/scripts/a3_prep_check.sh
# process_split_authorized 恒 false 直至 checklist 全 ✅
bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh status
bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh authorize  # 未全 ✅ → REFUSE
```
