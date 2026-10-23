# 模块化 Backlog（仅 WP4/WP5 暴露边）

> 来源：切片 GAPS 后置项 + 盘点 E-06。  
> **未批准执行** — 须 Gate 2（+ D13）后方可开工对应项。

| ID | 边/问题 | 严重度 | 建议手法 | 契约/facade | 后置条件 |
|----|---------|--------|----------|-------------|----------|
| MB-01 | FDE → `core.harness.knowledge|ontology` 直连（E-06） | 中 | 公开 API/facade + 改 caller；禁跨库直写补洞 | CoreFacade / DomainRouter | Gate 2 |
| MB-02 | Pi models.json 与本地 Ollama 模型 id 告警 | 低 | 运维配置 / 文档对齐 | n/a | 不挡 E3；可随时 |
| MB-03 | 诊断 MVP 持久化从本地文件升到正式存储选型 | 中 | 版本化 API；保持报告权威在诊断 | evidence-fp-001 | Gate 2 或独立 RFC |
| MB-04 | 正式五产品 owner 转正与临时 R 复核 | 中 | 组织动作 | ROLES.md | Gate 2 前建议完成 |
| MB-05 | live Pi 采集器从合成/手工 → 扩展内嵌发射 | 低 | Pi 扩展事件 → ingest | evidence-fp-001 | 不挡；增强可重复性 |

**明确不做（本 backlog 不含）**：全仓搬目录、拆五微服务、诊断全功能、启用本体进主路径（除非另改 WP1）。
