# 模块化 Backlog（仅 WP4/WP5 暴露边）

> 来源：切片 GAPS 后置项 + 盘点 E-06。  
> **Gate 2 已批准并落地（2026-10-24）** — 见 `GATE2_DECISION.md` / `LANDING_CLOSEOUT.md`（PR #387–#389）。Gate 3 仍未批。

| ID | 边/问题 | 严重度 | 建议手法 | 契约/facade | 后置条件 |
|----|---------|--------|----------|-------------|----------|
| MB-01 | FDE → `core.harness.knowledge|ontology` 直连（E-06） | 中 | platform 已干净；`core/apps/fde` 经 CoreFacade（agent interfaces 已迁；prompts 包导入期保留 harness 防循环；archive 除外） | CoreFacade | **Gate2 已落地** |
| MB-02 | Pi models.json 与本地 Ollama 模型 id 告警 | 低 | 运维：`~/.pi/agent/models.json`（模板含 `batiai/qwen3.5-9b:latest`） | n/a | 已对齐模板 |
| MB-03 | 诊断 MVP 持久化 | 中 | RFC 方案 B：SQLite 默认；`AIPLAT_SLICE_EVIDENCE_STORE=file` 回退 | evidence-fp-001 | **已实现（SQLite 默认）** |
| MB-04 | 正式五产品 owner 转正 | 中 | 见 `MB04_OWNER_TRANSFER.md` / `ROLES.md` | ROLES.md | **已转正（2026-10-24）** |
| MB-05 | live Pi 采集器内嵌发射 | 低 | `slice_evidence_emit.mjs` opt-in → ingest-jsonl | evidence-fp-001 | **已接线（opt-in）** |

**明确不做（本 backlog 不含）**：全仓搬目录、拆五微服务、诊断全功能、启用本体进主路径（除非另改 WP1）。
