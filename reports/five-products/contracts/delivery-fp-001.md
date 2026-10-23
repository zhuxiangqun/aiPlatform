# 契约草案 delivery-fp-001

| 项 | 内容 |
|----|------|
| 状态 | 启用 · 草案 |
| 字段 | scenario_id, requirement_refs[], acceptance_decision, evidence_report_ids[], signer, decided_at |
| 生产者 | FDE（acceptance / delivery pipeline） |
| 消费者 | 业务验收人 |
| 拟建 | signoff 强制/校验 evidence_report_ids（KG-FDE-ACCEPT-01） |
| 错误 | 无报告却「通过」→ 门禁拒绝（拟建后） |
| 现状锚点 | `POST .../acceptance/signoff` + preflight gate |
| owner | FDE 临时 R |
