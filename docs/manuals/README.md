# aiPlat 操作手册目录

> 所有操作手册的统一入口。按**责任分型**查找；角色导航仍保留。  
> 分型批次：**E1**（2026-10-23）· 方案见 [`reports/docs-governance/docs-next-round-manuals-links-2026-10.md`](../../reports/docs-governance/docs-next-round-manuals-links-2026-10.md)。

---

## 责任分型（E1）

| 标签 | 含义 | 本页位置 |
|------|------|----------|
| **现行操作** | 用户/运维/开发仍按步骤执行 | §现行操作 |
| **专题合册** | 长手册/合订，仍为权威入口 | §专题合册 |
| **过程 / 降权** | 分析快照、已归档散页、签收留存指针 | §过程与降权（路径多仍保留） |

本批 **0 迁 archive、0 删除**（疑似过程项仅索引降权）。

---

## 按角色推荐

### 新用户

| 顺序 | 手册 | 说明 |
|:---:|------|------|
| 1 | [快速入门](getting-started.md) | 5 分钟体验 |
| 2 | [管理画面操作](management.md) | 角色、侧边栏、功能模块 |
| 3 | [部署指南](deployment.md) | 单机/集群/容器化 |

### 开发者

| 顺序 | 手册 | 说明 |
|:---:|------|------|
| 1 | [开发指南](development.md) | 环境、编码流程 |
| 2 | [测试指南](testing.md) | 测试金字塔、CI |
| 3 | [工程质量](engineering-quality.md) | 质量标准 |
| 4 | [PR 检查清单](PR_ARCHITECTURE_CHECKLIST.md) | 提交前自检（开发者长清单；CI 契约见 `docs/guides/`） |

### FDE 交付工程师

| 顺序 | 手册 | 说明 |
|:---:|------|------|
| 1 | [FDE 文档导航](fde/README.md) | **从这里开始** |
| 2 | [快速入门](fde/01-fde-quickstart.md) | 新人 5 分钟 |
| 3 | [交付操作](fde/02-fde-delivery.md) | 八步 SOP + 模板 |
| 4 | [运维自演进](fde/03-fde-operations.md) | 巡检 + 反馈 |
| 5 | [管理与扩展](fde/04-fde-admin.md) | Agent / CLI / API |
| 6 | [管理端创建本体+Agent 合册](../contracts/FDE_ONTOLOGY_AGENT_OPS_MANUAL.md) | 真实菜单路径 |
| 7 | [Org L5 运行手册](../contracts/ORG_L5_RUNBOOK.md) | `/org/pilot` |

> 旧版散乱 FDE 文已在 `fde/_archive/`（过程/归档）。M4 签收包见下方「过程与降权」。

### 运维 / 平台管理员

| 顺序 | 手册 | 说明 |
|:---:|------|------|
| 1 | [部署指南](deployment.md) | 完整部署步骤 |
| 2 | [部署速查](deploy-guide.md) | 短速查 |
| 3 | [管理画面操作](management.md) | 管理员日常 |
| 4 | [本体模型管理](ontology.md) | 域/类/关系（操作入口；权威叙述另见 knowledge-system） |
| 5 | [生产就绪检查](production-readiness.md) | 上线前清单 |

---

## 现行操作

| 手册 | 路径 | 受众 |
|------|------|------|
| 快速入门 | [getting-started.md](getting-started.md) | 新用户 |
| 管理画面操作 | [management.md](management.md) | 管理员 |
| 管理端 L1 页面手册 | [management-ui-operation-manual.md](management-ui-operation-manual.md) | 用户 / 数字人 |
| 本体模型管理 | [ontology.md](ontology.md) | 管理员/运维 |
| 知识管理指南 | [../knowledge-system.md](../knowledge-system.md) | 知识管理员 |
| 部署指南 | [deployment.md](deployment.md) | 运维 |
| 部署速查 | [deploy-guide.md](deploy-guide.md) | 运维 |
| 开发指南 | [development.md](development.md) | 开发者 |
| 测试指南 | [testing.md](testing.md) | 开发者 |
| 工程质量 | [engineering-quality.md](engineering-quality.md) | 开发者 |
| 生产就绪 | [production-readiness.md](production-readiness.md) | 运维 |
| PR 检查清单 | [PR_ARCHITECTURE_CHECKLIST.md](PR_ARCHITECTURE_CHECKLIST.md) | 开发者 |
| Org L5 运行手册 | [../contracts/ORG_L5_RUNBOOK.md](../contracts/ORG_L5_RUNBOOK.md) | 试点 Owner |
| 创建本体+Agent 合册 | [../contracts/FDE_ONTOLOGY_AGENT_OPS_MANUAL.md](../contracts/FDE_ONTOLOGY_AGENT_OPS_MANUAL.md) | FDE / 实施 |

---

## 专题合册

| 手册 | 路径 | 说明 |
|------|------|------|
| FDE 文档导航 | [fde/README.md](fde/README.md) | FDE 合册入口 |
| FDE 快速入门 | [fde/01-fde-quickstart.md](fde/01-fde-quickstart.md) | 合册分册 |
| FDE 交付操作 | [fde/02-fde-delivery.md](fde/02-fde-delivery.md) | 合册分册 |
| FDE 运维自演进 | [fde/03-fde-operations.md](fde/03-fde-operations.md) | 合册分册 |
| FDE 管理与扩展 | [fde/04-fde-admin.md](fde/04-fde-admin.md) | 合册分册 |
| FDE 实施流程 | [fde/05-fde-implementation-process.md](fde/05-fde-implementation-process.md) | 合册分册 |
| 域交付 SOP | [fde/06-sop-domain-delivery.md](fde/06-sop-domain-delivery.md) | 合册分册 |
| FDE 交付模板正文 | [fde/fde-delivery-manual.md](fde/fde-delivery-manual.md) | 模板合订（可系统生成） |
| FDE 模板目录 | [fde/templates/](fde/templates/) | 客户 Profile / 签收等模板 |
| 示例：标书评审交付 | [fde/examples/bid-review/delivery-manual.md](fde/examples/bid-review/delivery-manual.md) | 示例合册 |

---

## 过程与降权（路径保留 · 非主阅读）

| 项 | 路径 | R6 / 说明 |
|----|------|-----------|
| Wiki FTS5 分析 | [wiki-fts5-analysis.md](wiki-fts5-analysis.md) | **降权**：技术分析快照，非日常操作步骤 |
| FDE 旧散页 | [fde/_archive/](fde/_archive/) | **已归档**目录（只读） |
| M4 签收准备包 | [../contracts/ORG_M4_SIGNOFF_PACK.md](../contracts/ORG_M4_SIGNOFF_PACK.md) | **签收留存**（contracts §3.2）；≠ 日常 manuals 步骤 |

---

*最后更新: 2026-10-23（E1 责任分型）*
