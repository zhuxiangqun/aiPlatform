---
doc_type: Archive
---

# EVAL 董事会 — 本地范围收口（2026-11-06）

- **status**: **Local-first active** — 对外发布延后；本机评测须持续可测（[优先级](../../EVAL_LOCAL_FIRST_PRIORITY_2026-11-06.md)）
- **计划**：[EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md](../../EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md)

## 已收口

| 轨 | 状态 | 锚点 |
|---|---|---|
| P0 / A1 本地 | ✅ 本地 pass；生产 Parked（产品决定本地足够） | [本地签](./EVAL_A1_DEPLOY_SIGNOFF_local_20261105.md) · [范围决策](../../EVAL_A1_SCOPE_DECISION_LOCAL_SUFFICIENT_2026-11-06.md) |
| P1a / P1b | ✅ 人侧 + 报告轨收口 | [P1b human](./EVAL_P1B_HUMAN_TRACK_CLOSEOUT_2026-11-05.md) |
| P2-0..P2-3 | ✅ 校准 · context · memory · self-learn | [P2 本地总收口](./EVAL_P2_LOCAL_TRACK_CLOSEOUT_2026-11-06.md) |
| P2-4 | Parked（要公网/staging） | P2-4（历史链接失效） |
| 生产 A1 | Parked（非欠账） | [阻塞单](./EVAL_A1_PROD_BLOCKED_NOT_RELEASED_2026-11-05.md) |

## 诚实锁（全局）

`accuracy_claim=false` · `process_split_authorized=false` · 本地 ≠ 公网已发布 · writeback 未授权

## 延后（不阻塞本地评测做完）

1. 公网/staging → P2-4 或生产 A1（**有意不做**，直到本地确认无误）
2. process_split / 对外发布宣称

**结论**：FDE 用本机评本机是正轨。日常验收：`bash packages/aiplat-evaluation/scripts/local_track_closeout.sh`（v3）。

## 本机产品面补齐（2026-11-06 续）

- `start.sh` 默认起 eval local proxy（`:8010`+worker → `AIPLAT_EVAL_SERVICE_URL`）
- Center 增 Session / Arena / Skill / P2 Research tabs（job 平面）
- G2b UI 文案对齐 n=100 scoped；Arena 默认仍 length smoke（[决策](../../EVAL_ARENA_LOCAL_PRODUCT_DECISION_2026-11-06.md)）
- Live LLM smoke 本机已绿（Ollama `qwen2.5:3b`，见 [本地优先](../../EVAL_LOCAL_FIRST_PRIORITY_2026-11-06.md)）；Skill docker fixture 在镜像就绪后可绿
- **2026-11-06 联调**：`upstream=cohost` 根因是 `local_proxy_up` 缺 `PyJWT` 起不来 → platform 无 `AIPLAT_EVAL_SERVICE_URL`；已装 PyJWT、脚本改用工作区 `.venv`，本机已切 `mode=proxy` 且 Arena length-smoke enqueue→succeeded
