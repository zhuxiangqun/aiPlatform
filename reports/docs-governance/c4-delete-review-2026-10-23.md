# C4 复核表 — 删除（2026-10-23）

> 批次批准：用户确认开 C4。删除最严；本批仅 **路径 A**。

## 删除清单（4）

| 已删路径 | 替代（R4） | 路径 | R5 |
|----------|------------|------|-----|
| `docs/design/ontology-design.md` | `docs/knowledge-system.md` §三（文内已声明合并） | **A** | 仓库内无单独留存义务；外部副本 **未核实·待确认**（不阻路径 A：义务由替代文承担） |
| `docs/design/knowledge-ontology-plan.md` | 同上 | **A** | 同上 |
| `docs/architecture/knowledge-base-architecture.md` | 同上（三大存储/RAG） | **A** | 同上 |
| `docs/manuals/knowledge-management.md` | 同上 + 附录 C / 知识库页 | **A** | 同上 |

## 未删

| 文件 | 理由 |
|------|------|
| `docs/manuals/ontology.md` | 仍为 manuals 阅读入口（含 UI 路径）；非纯空 stub；README 仍链入 |
| `docs/reports/*` 生成快照 | 未满足路径 B 人工「无留存价值」书面确认；§2.1 慎删 |
| archive 内历史稿 | C4 不清理 archive 正文 |

## R3 入链处置

| 引用 | 处置 |
|------|------|
| `DOCUMENT_SYSTEM.md` 设计类举例 | 已改指向 `knowledge-system.md` |
| `scripts/code_doc_map.yaml` | 已改 / 移除 design_targets 两项 |
| `knowledge_ontology.py` 头注释 | 已改 |
| whitepaper suite YAML + `scripts/generate_whitepaper_volumes.py` | 已改；分卷已重生 |
| `reports/document-disposition-register-*.csv` | **确认无需改**（时点快照登记，非运行时依赖） |

## 验收

| 项 | 结果 |
|----|------|
| 删除数 | **4** |
| 迁 archive | 0（本批直接删 stub） |
| 仓库 `docs/**/*.md` 总数 | 下降 4（另 +1 本复核表） |
| 维护区 | 同步下降 |
| 白皮书 `--check` | **PASS** |
| C0 口径复测 | total **259** · maint **187**（相对 C3：−4 删除 +1 本表） |
| 路径 B | **未使用** |
