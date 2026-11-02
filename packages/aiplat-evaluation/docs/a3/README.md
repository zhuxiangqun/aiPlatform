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
| [`LLM_LOCAL.md`](./LLM_LOCAL.md) | 可选 prompt_eval LLM（stub/http，无 Central） |
| [`B3L_LOCAL_CLOSEOUT.md`](./B3L_LOCAL_CLOSEOUT.md) | B3-L 本地工程验收（≠ staging authorize） |
| [`S1_LOCAL.md`](./S1_LOCAL.md) | S1 SECURITY_EVAL_V1 fixture 门禁（ASR≠accuracy） |
| [`P1_LOCAL.md`](./P1_LOCAL.md) | P1–P1.2 评分语义（B2 runners family metrics；≠accuracy） |
| [`B4S_PREP.md`](./B4S_PREP.md) | B4-S 主机前置（未确认 → 阻塞；≠ authorize） |
| `scripts/local_track_closeout.sh` | 本地轨收口（P1+S1+authorize locked；≠ B4） |

```bash
bash packages/aiplat-evaluation/scripts/a3_local_rehearsal.sh  # #4 → 🟨
bash packages/aiplat-evaluation/scripts/a3_prep_check.sh
# process_split_authorized 恒 false 直至 checklist 全 ✅
bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh status
bash packages/aiplat-evaluation/scripts/a3_split_authorize.sh authorize  # 未全 ✅ → REFUSE
```
