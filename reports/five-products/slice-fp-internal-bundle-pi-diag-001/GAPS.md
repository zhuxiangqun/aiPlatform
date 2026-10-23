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
| Pi 模型目录告警 | provider 对 `batiai/qwen3.5-9b` 有 “not found” 警告但 custom id 仍可跑；运维可后置整理 models.json |
| E-06 FDE→harness 直连 | Gate 2 模块化候选 |
| 对外 E4 / Gate 2 | 未授权；本切片非客户验收 |
