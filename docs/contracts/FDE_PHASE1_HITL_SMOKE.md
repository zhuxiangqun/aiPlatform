# FDE Phase 1 HITL 冒烟清单

| 字段 | 值 |
|------|-----|
| 文档 ID | `FDE-CHK-HITL-PHASE1-2026-09` |
| 版本 | v1 |
| 关联 | `FDE_WORKBENCH_CONTRACT.md` §7 · `delivery_pipeline_session.py` |
| 日期 | 2026-09-14 |

---

## 0. 范围（诚实边界）

Phase 1 交付 session = **服务端 stage cursor**（`template_session`），**不**自动执行 agent LLM。  
真 `PipelineEngine` 多轮 HITL 另列；本清单验收工作台可启动 / 查询 / ≥2 次批准 / 刷新一致。

---

## A. 自动化（已合入）

- [x] `test_require_known_domain_*` — DomainRouter 硬闸
- [x] `test_load_delivery_template_from_workspace_seed` — 仓库种子可加载
- [x] `test_delivery_session_two_hitl_approves_and_reload` — ≥2 次 approve + reload

```bash
PYTHONPATH=aiPlat-core python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_fde_phase1b_delivery.py -q
```

---

## B. 手工冒烟（工作台）

| # | 步骤 | 期望 |
|---|------|------|
| 1 | 打开 FDE 工作台 → ⑤ 平台离线包 | 见「启动交付 Pipeline」可点（非灰） |
| 2 | 可选：① 选客户、② 选已注册域 | domain 非法时 start 返回 400 |
| 3 | 点击「启动交付 Pipeline」 | 返回 `session_id`；phase=`paused`；进度条 0% |
| 4 | 点击「批准 HITL」#1 | phase 仍 paused（下一 HITL）；`progress_pct` 上升；HITL 事件 ≥1 |
| 5 | 点击「批准 HITL」#2 | 工程师阶段被 `done_skipped_llm`；事件 ≥2 |
| 6 | 点击「刷新」 | 与服务端一致（不丢事件） |
| 7 | 如仍 paused，再批准至 done | `progress_pct=100` |

API（canonical）：

```
POST /api/platform/apps/fde/delivery-pipeline/start
GET  /api/platform/apps/fde/delivery-pipeline/{session_id}
POST /api/platform/apps/fde/delivery-pipeline/{session_id}/approve
```

---

## C. 不做（本阶段）

- 用 `PipelineEngine` 跑满 4 阶段 LLM
- 本地 React `setInterval` 假进度
- 未知 `domain_id` 静默 `GraphIndex.load`

---

## 修订

| 版本 | 日期 | 说明 |
|------|------|------|
| v1 | 2026-09-14 | Phase 1b 冒烟清单 + 自动化对照 |
