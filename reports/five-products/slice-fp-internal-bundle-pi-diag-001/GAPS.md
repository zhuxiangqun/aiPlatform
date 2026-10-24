# GAPS（切片收口）

| gap_id | 状态 | 严重度 | 说明 |
|--------|------|--------|------|
| KG-EDGE-01 / KG-BUNDLE-01 | **关闭** | — | `export_slice_bundle` + API；export 补齐 `*.mjs` 依赖后 live Pi 可加载 |
| KG-DIAG-01 / KG-EDGE-02 | **关闭** | — | ingest/report；live RUNLOG 已入报告 |
| KG-FDE-ACCEPT-01 | **关闭** | — | fp- signoff 须 report_id |
| KG-FAULT-01 | **关闭** | — | 四条负向均有测试/快照证据 |
| KG-OFFLINE-DOC | **关闭（执行层）** | — | `evaluate_slice_offline_policy` 对齐 `pi-thin-offline.md` |

## 后置（不挡本切片 E3）

| 项 | 说明 |
|----|------|
| Pi 模型目录告警 | MB-02：模板+本机 `~/.pi/agent/models.json` 已对齐；其它环境仍须拷贝 |
| MB-05 内嵌发射 | **已接线（opt-in）**：`slice_evidence_emit.mjs` + `ingest_slice_evidence_from_jsonl` |
| E-06 FDE→harness 直连 | platform 干净；**core/apps/fde 仍 Known Gap** — 见 `MB01_E06_REVERIFY.md`；解耦须 Gate 2 |
| 对外 E4 / Gate 2 | 未授权；本切片非客户验收 |
