# 契约草案 evidence-fp-001（诊断 MVP）

| 项 | 内容 |
|----|------|
| 状态 | 启用 · 草案 · **Known Gap 实现面**（KG-DIAG-01） |
| 字段 | run_id, trace_id, bundle_version, runtime_version, evidence_refs[], freshness, report_id, status∈{ok,unknown,stale,fail} |
| 生产者 | Pi 事件 + aiPlat 资产/bundle 版本 |
| 消费者 | 诊断报告；FDE acceptance 引用 report_id |
| 错误/失联 | 任一侧证据缺失 → unknown/stale；**禁止**默认 healthy/成功 |
| 拟建 | 薄 ingest + report API/适配器（授权 A3.2）；非新中台 |
| owner | 诊断临时 R |
