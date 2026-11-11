---
doc_id: DOCUMENT_SYSTEM
doc_type: Specification
status: active
authority: primary
scope: workspace
language: zh-CN
version: 2.4
supersedes: 2.3
owner: TBD
approved: 2026-11-11
effective: 2026-11-11
last_reviewed: 2026-11-11
review_cycle: 90d
---

# aiPlat 文档系统治理框架 v2.4（已批准）

> **状态：Approved，2026-11-11 生效。**
> 本版定义目标文档结构；当前仓库仍处于迁移期，当前目录结构与目标结构的差异见 §一、§十一。
> 未完成迁移前，不得声称仓库已符合 v2.4 目标目录。

## 零、文档宪法自检（Batch 0）

v2.4 的结构批准不等于文档宪法自洽。Batch 0（2026-11-11）已完成：

- 恢复数字声明治理，验证命令必须指向真实路径；
- 恢复“六个 CLAUDE.md”定位；
- 清理 `docs/index.md` 僵尸条目；
- 修复章节编号、计数、失效引用；
- 新增 `scripts/verify_document_system.py`。

清单：

```text
docs/audit/document-system-2026-11/BATCH-0-DOCUMENT-SYSTEM.md
```

Batch 0 已通过，自检脚本见 §十七。

## 一、目录结构

```
workspace-root/
│
├── CLAUDE.md                          ← 工作区兜底规约（AI 编程行为约束）
├── AIPLAT_CAPABILITIES.md            ← 唯一能力清单（当前计数见该文件统计表）
│                                      ↑ reports/whitepapers/aiplat-platform-status-whitepaper.md
│                                        由此生成（scripts/generate_platform_whitepaper.py）
├── AIPLAT_ROADMAP.md                 ← 商业化路线图（评分 + 基线）
├── README.md                         ← 部署手册
│
├── docs/
│   ├── DOCUMENT_SYSTEM.md            ← 本文档 — 文档系统治理框架
│   ├── README.md                     ← 唯一导航入口（合并原 index.md）
│   │
│   ├── project/                       ← 项目管理
│   │   └── PHASE_STATUS.md           ← Phase 实施状态快照
│   │
│   ├── architecture/                 ← 架构设计
│   │   ├── overview.md               ← 权威架构全景（唯一出处）
│   │   ├── boundary-standard.md      ← 层边界判定标准
│   │   ├── system-architecture-contract.md ← 跨层契约
│   │   ├── core/                     ← Core 层详述
│   │   │   └── core-layer1-latest.md
│   │   ├── plans/                    ← 规划（非现状；含 pi-thin-runtime、五产品等）
│   │   └── decisions/                ← 架构裁决记录 (ADR)
│   │       ├── evaluator_calibration.md
│   │       └── tot_reserve.md
│   │
│   ├── contracts/                    ← 跨仓契约（FDE / Ontology 等；索引见 README.md）
│   │   └── README.md
│   │
│   ├── decisions/                    ← v2.4 顶层 ADR（迁移中；旧 architecture/decisions 保留）
│   ├── products/                     ← v2.4 产品定义（迁移中）
│   ├── reference/                    ← v2.4 参考/API/模板/非规范解释材料（迁移中）
│   │   └── explanatory/
│   │
│   ├── guides/                       ← 补充指南（如 PR 架构检查清单）
│   │   └── PR_ARCHITECTURE_CHECKLIST.md
│   │
│   ├── design/                       ← 设计文档（To-Be / Plan）
│   │   └── ...（见目录；非现状）
│   │
│   ├── framework/                     ← 成熟度评估框架
│   │   ├── assessment-scores.json     ← 唯一评估分数源
│   │   └── ...
│   │
│   ├── security/                      ← 安全架构与测试
│   │
│   ├── policy/                        ← 安全/运维策略
│   │   ├── external-allowlist.md
│   │   └── mcp-stdio-prod-allowlist.md
│   │
│   ├── standards/                     ← 跨层规范（强制性；`规范-*.md` 多份）
│   │
│   ├── agents/                        ← Agent 架构设计
│   │   └── subagent.md
│   │
│   ├── mcp/                           ← MCP 协议集成
│   │   └── index.md
│   │
│   ├── skills/                        ← Skill 动态进化
│   │   └── evolution.md
│   │
│   ├── tools/                         ← 工具系统增强
│   │   └── enhancement.md
│   │
│   ├── strategy/                      ← 战略分析 / 竞品对比
│   │   └── comparison-vs-vendors.md
│   │
│   ├── reports/                       ← 生成报告（不手动编辑）
│   │   ├── README.md
│   │   ├── AIPLAT_ARCHITECTURE_REPORT.md
│   │   └── AIPLAT_DIAGNOSTIC_REPORT.md
│   │
│   ├── harness/                       ← 跨仓库 Harness 索引
│   │   └── README.md
│   │
│   ├── audit/                         ← 合规审计
│   │   └── compliance-matrix.md
│   │
│   ├── compliance/                    ← 法规合规评估
│   │   └── eu-ai-act-assessment.md
│   │
│   ├── articles/                     ← 技术文章（对外发布）
│   │   └── private-control-plane.md
│   │
│   ├── matrix/                        ← 能力影响矩阵
│   │   └── capability-impact-matrix.md
│   │
│   ├── research/                      ← 研究报告（审计/对标/方案；含收官稿与现行主报告）
│   │   ├── README.md
│   │   └── ...
│   │
│   ├── archive/                      ← 归档（历史版本，只读）
│   │   ├── README.md                 ← 归档说明 + "仅做历史参考"免责声明
│   │   └── ...（历史文件）
│   │
│   └── by-role/                      ← 角色导航（索引，指向其他文件的链接集合）
│       ├── architect/
│       ├── developer/
│       ├── ops/
│       └── user/
│
├── aiPlat-core/
│   ├── CLAUDE.md                     ← Core 层 AI 编程规约
│   └── docs/                         ← Core 层设计文档
│
├── aiPlat-infra/
│   ├── CLAUDE.md                     ← Infra 层 AI 编程规约
│   └── docs/                         ← Infra 层设计文档
│
├── aiPlat-platform/
│   ├── CLAUDE.md                     ← Platform 层 AI 编程规约
│   └── docs/                         ← 设计文档（部分为骨架/To-Be）
│
├── aiPlat-management/
│   ├── CLAUDE.md                     ← Management 层 AI 编程规约
│   └── docs/                         ← Management 层设计文档
│
└── aiPlat-app/
    ├── CLAUDE.md                     ← App 层 AI 编程规约
    └── docs/                         ← App 层设计文档
```

---

## 二、目标目录结构（v2.4）

```text
aiPlatform/
├── README.md
├── AIPLAT_CAPABILITIES.md
├── AIPLAT_ROADMAP.md
├── SECURITY.md
├── CLAUDE.md
│
├── docs/
│   ├── README.md
│   ├── DOCUMENT_SYSTEM.md
│   ├── standards/
│   │   ├── README.md
│   │   └── knowledge-system/
│   │       ├── README.md
│   │       └── v4.3.1/
│   │           ├── technical-whitepaper.md
│   │           ├── normative-appendix.md
│   │           ├── schemas/
│   │           ├── assets/
│   │           └── ADR-KS-v4.3.1-2026-11-11.md
│   ├── architecture/
│   │   ├── README.md
│   │   ├── overview.md
│   │   ├── system-architecture-contract.md
│   │   ├── boundary-standard.md
│   │   └── plans/
│   ├── contracts/
│   │   ├── README.md
│   │   ├── core/
│   │   ├── fde/
│   │   ├── org/
│   │   ├── knowledge/
│   │   └── products/
│   ├── products/
│   │   ├── README.md
│   │   └── five-products/
│   │       ├── README.md
│   │       ├── modules/
│   │       └── plans/
│   ├── decisions/
│   │   ├── README.md
│   │   ├── architecture/
│   │   ├── product/
│   │   ├── security/
│   │   └── process/
│   ├── guides/
│   │   ├── README.md
│   │   ├── knowledge/
│   │   ├── development/
│   │   ├── deployment/
│   │   ├── operations/
│   │   └── fde/
│   ├── reference/
│   │   ├── API/
│   │   ├── glossary.md
│   │   ├── templates/
│   │   └── explanatory/
│   ├── project/
│   │   ├── PHASE_STATUS.md
│   │   └── roadmap/
│   ├── audit/
│   │   └── document-system-2026-11/
│   └── archive/
│       ├── standards/
│       ├── architecture/
│       ├── guides/
│       └── reports/
│
├── reports/
│   ├── README.md
│   ├── products/
│   │   └── five-products/
│   │       ├── ops/
│   │       └── _archive/
│   ├── security/
│   │   └── evidence/
│   ├── docs-governance/
│   └── archive/
│
├── packages/
│   ├── README.md
│   ├── aiplat-central/
│   ├── aiplat-diagnosis/
│   ├── aiplat-evaluation/
│   │   ├── README.md
│   │   └── docs/
│   │       ├── README.md
│   │       ├── product/
│   │       ├── modules/
│   │       ├── evidence/
│   │       └── _archive/
│   ├── aiplat-fde/
│   ├── aiplat-ontology/
│   └── aiplat-pi-runtime/
│
├── aiPlat-core/
│   ├── README.md
│   ├── CLAUDE.md
│   └── docs/
│       ├── README.md
│       ├── architecture/
│       ├── contracts/
│       ├── harness/
│       ├── knowledge/
│       └── testing/
│
├── aiPlat-infra/
│   ├── README.md
│   ├── CLAUDE.md
│   └── docs/
│       ├── README.md
│       ├── architecture/
│       ├── testing/
│       └── ...
│
├── aiPlat-platform/
│   ├── README.md
│   ├── CLAUDE.md
│   └── docs/
│       ├── README.md
│       ├── architecture/
│       ├── gateway/
│       └── ...
│
├── aiPlat-management/
│   ├── README.md
│   ├── CLAUDE.md
│   └── docs/
│       ├── README.md
│       ├── architecture/
│       ├── core/
│       └── design/
│
└── aiPlat-app/
    ├── README.md
    ├── CLAUDE.md
    └── docs/
        ├── README.md
        ├── architecture/
        ├── guides/
        └── runtime/
```

> 目标结构是 v2.4 的 canonical 模型；当前迁移期仍保留旧目录。迁移映射见 §十一。

## 三、结构说明与合理性

### 3.1 为什么“类型优先”

一级目录按**文档类型**分，而不是按团队/产品分：

```text
standards / architecture / contracts / products / guides
reference / project / audit / archive
```

理由：

1. **生命周期一致**：标准需审批/版本化；指南随流程更新；报告只追加；归档只读。
2. **CI 可按类型检查**：标准查版本，契约查接口，报告查生成头，归档查免责声明。
3. **避免多权威**：按域分会复制 architecture/contracts/reports，形成多套真相。
4. **owner 放元数据，不靠目录**：团队归属写在 `owner`，不靠物理目录表达。

### 3.2 每个目录的职责

目标结构中的每个目录职责如下（当前迁移期仍保留的旧目录见 §一，不在本表重复）：

| 目录 | 放什么 | 不放什么 |
|---|---|---|
| `standards/` | 已批准标准、附录、schema、批准记录 | 草稿、实现指南、报告 |
| `architecture/` | 架构全景、跨层规范、边界、规划 | 具体 API 教程、生成报告、ADR |
| `contracts/` | 跨层/跨仓行为约束 | 架构叙事、教程、模板 |
| `decisions/` | ADR：架构/产品/安全/流程决策 | 架构叙事、教程、实现代码 |
| `products/` | 产品定义、模块边界、产品计划 | 运行证据、生成报告 |
| `guides/` | 任务步骤、SOP、操作手册 | 架构权威、标准正文 |
| `reference/` | API、术语、模板、非规范解释材料 | 规范、教程正文 |
| `project/` | 状态快照、路线图快照 | 长期架构定义 |
| `audit/` | 审计报告、盘点、决策建议 | 规范、操作指南 |
| `archive/` | 历史版本，只读 | 当前 canonical |
| `reports/` | 运行证据、生成报告、快照、`_archive` | 手写规范、产品定义 |
| `packages/*/docs/` | 包内产品/模块/证据文档 | 根级标准、跨层契约 |
| `aiPlat-*/docs/` | 各子仓内部架构/契约/指南 | 根级标准、跨层唯一权威 |

### 3.2.1 目录角色边界（architecture / contracts / decisions / audit / packages）

同一个系统会有多份文档，每份回答不同问题：

| 目录 | 回答的问题 | 不是 |
|---|---|---|
| `architecture/` | 系统现在如何分层、边界在哪、当前设计是什么 | 不是决策历史，不是审计发现 |
| `contracts/` | 跨层/跨仓/跨团队必须遵守什么 | 不是包内实现说明，不是架构叙事 |
| `decisions/` | 为什么选 A 不选 B，替代方案和后果是什么 | 不是当前架构全文 |
| `audit/` | 某时点检查了什么、发现什么、建议什么 | 不是规范，不是决策 |
| `packages/*/docs/` | 这个包内部怎么实现、怎么使用、有什么证据 | 不是跨包契约，不是根级标准 |

判断顺序：

```text
1. 是“记录选择”吗？          → decisions/
2. 是“某时点检查结果”吗？    → audit/
3. 是“跨边界强制约束”吗？    → contracts/
4. 是“当前架构/边界”吗？     → architecture/
5. 是“单个包内部文档”吗？    → packages/*/docs/
6. 是“已批准标准”吗？        → standards/
```

防重复规则：

| 内容 | 只能放 |
|---|---|
| 当前架构分层 | `architecture/` |
| 跨边界强制约束 | `contracts/` |
| 为什么做这个选择 | `decisions/` |
| 某次审计发现 | `audit/` |
| 单包实现/使用/证据 | `packages/*/docs/` |

如果同一内容出现在两个目录，视为缺陷：

```text
architecture 复制 contract 的接口细节 → 错
contract 复制 architecture 的分层叙事 → 错
decision 复制 architecture 全文 → 错
audit 直接定义新规范 → 错
package docs 定义跨包契约 → 错
```

例子：Fact Store

```text
architecture：Fact Store 是事实层；GraphIndex/Wiki 是投影。
contracts：运行时权威必须读 Fact Store revision；审计快照必须含 revision。
decisions：ADR 记录为什么选 Fact Store，而不是 GraphIndex 双写。
audit：2026-11 审计发现 45 份文档仍把 GraphIndex 写成权威。
packages：aiplat-evaluation 包如何通过 Fact Store API 读取评测数据。
```

### 3.3 为什么 `reports/` 不放产品定义

`reports/` 只放：

```text
运行证据 / 收口凭证 / 生成报告 / 历史快照 / _archive
```

产品定义放 `docs/products/`，因为它需要维护、评审、版本化；
运行证据只追加、按保留期归档，两者生命周期不同。

### 3.4 为什么保留子仓 `docs/`

每个子仓的文档都保留在各自目录：

```text
aiPlat-core/docs/
aiPlat-infra/docs/
aiPlat-platform/docs/
aiPlat-management/docs/
aiPlat-app/docs/
packages/*/docs/
```

- 内部细节属于各自仓库；
- 根 `docs/` 只放跨层契约和索引；
- 子仓文档由子仓 owner 维护，根 docs 不复制。

### 3.5 为什么 `decisions/` 独立

`Decision` 是一种文档类型，不是架构的子类型。

放在 `docs/architecture/decisions/` 的问题：

- 产品、安全、流程决策无处安放；
- ADR 被降级为架构附属物；
- 与“类型优先”原则冲突。

推荐：

```text
docs/decisions/
  README.md
  architecture/
  product/
  security/
  process/
```

理由：

- ADR 生命周期不同：接受后不可改，只能新增 superseding ADR；
- 决策跨域：不只架构有决策；
- 架构 README 可以链接相关 ADR，但不需要把 ADR 藏在 architecture 下。

### 3.6 架构三文档的拆分判据

只有满足“不同权威、不同读者、不同变更节奏、不同 CI 约束”中的至少两项，才拆文档。

| 文档 | 权威 | 读者 | 变更节奏 | CI |
|---|---|---|---|---|
| `system-architecture-contract.md` | 规范 | 架构师/开发 | 慢，需评审 | 强约束 |
| `overview.md` | 非规范摘要 | 新人/管理层 | 快，可生成 | 无 |
| `boundary-standard.md` | 规范/判定规则 | 评审/CI | 中 | 条件性 |

判断：

```text
contract = 必须遵守什么
overview = 系统大概长什么样
boundary = 具体怎么判断越界
```

`boundary-standard.md` 已确认被 CI / architecture guard 独立引用，
保留为独立规范文档，不合并进 contract。

### 3.7 白皮书按权威分，不按格式分

“白皮书”是格式，不是权威类型。分三类：

| 类型 | 位置 | 例子 |
|---|---|---|
| 规范性技术白皮书 | `docs/standards/<domain>/<version>/` | v4.3.1 知识体系标准 |
| 非规范解释材料 | `docs/reference/explanatory/` | 平台介绍/行业方案 |
| 生成的白皮书/状态报告 | `reports/` | 平台状态白皮书 |

`docs/whitepaper/` 不再作为顶层类型目录。

### 3.8 代价

- 需要一次迁移和 redirect map；
- 需要补 owner/purpose/scope；
- 需要更新链接；
- 不能一次性大搬迁。

收益：

```text
一个主题一个 canonical
一种类型一种生命周期
CI 可执行
报告不污染规范
```

## 四、文档类型与边界

| 类型 | 定义 | 典型目录 | 生命周期 |
|---|---|---|---|
| Standard | 已批准规范/标准 | `docs/standards/` | 版本化、审批后生效 |
| Architecture | 架构全景/边界/规范 | `docs/architecture/` | 随架构变更 |
| Contract | 跨层/跨仓行为约束 | `docs/contracts/`、子仓 `docs/contracts/` | 随接口变更 |
| Product | 产品定义/模块边界/计划 | `docs/products/` | 随产品演进 |
| Guide | 操作步骤/最佳实践 | `docs/guides/` | 随流程更新 |
| Runbook | 运维/应急/交付流程 | `docs/guides/` | 随流程更新 |
| Reference | API/术语/模板/索引 | `docs/reference/` | 随接口/术语更新 |
| Report | 时间点快照 | `reports/`、`docs/reports/` | 不维护，过期归档 |
| Decision | ADR/裁决 | `docs/decisions/` | 永久留存 |
| Index | 导航入口 | 各目录 README | 随目录变化 |
| Agent Instruction | AI 编程规约 | 根/子仓 `CLAUDE.md` | 随规则变更 |
| Archive | 历史只读 | `docs/archive/`、`reports/**/_archive/` | 只读 |
| Draft | 未完成文档 | 任意 | 180 天过期 |

边界规则：

| 类型 | 可以包含 | 不可包含 |
|---|---|---|
| Standard | 强制要求、符合性、边界 | 实现细节、部署步骤 |
| Architecture | 架构描述、模块、数据流、架构级约束 | 具体接口契约、CLI 操作、部署步骤 |
| Contract | 接口、约束、违反后果 | 架构叙事、教程 |
| Product | 产品定义、模块边界、产品计划 | 运行证据、生成报告 |
| Guide | 操作步骤、命令、模板 | 架构权威、标准正文 |
| Runbook | 运维/应急/交付步骤、检查项、回滚 | 架构理念、标准定义 |
| Reference | API、术语、模板、索引 | 强制要求、规范正文 |
| Report | 生成时间、快照、当时结论 | 手工维护的规范 |
| Decision | 背景、决策、替代方案、后果 | 实现代码、操作指南 |
| Index | 导航链接、目录说明 | 规范、架构正文 |
| Agent Instruction | AI 行为约束、工作区规约 | 业务规范、实现细节 |
| Archive | 历史文件、旧版本 | 当前 canonical |
| Draft | 未完成内容、待评审草稿 | canonical、发布版本 |

Whitepaper 不是独立类型，按权威归类：

```text
规范性技术白皮书 → Standard
非规范解释材料   → Reference
生成的白皮书/报告 → Report
```

## 五、Scope 登记

`verify_doc_structure.py` 必须检查：

```text
docs/
reports/
packages/*/docs/
packages/*/README.md
aiPlat-*/docs/
```

新增一级文档目录必须在 `DOCUMENT_SYSTEM.md` 登记，否则阻断。

## 六、必填元数据

每份新文档 frontmatter 或文首必须包含：

```yaml
doc_id:
doc_type:
status: active | draft | generated | historical
authority: canonical | supporting | reference | obsolete | index
purpose:
scope_in:
scope_out:
owner:
version:
last_reviewed:
review_cycle:
```

规则：

- canonical 文档必须有 owner、purpose、scope_in/out；
- 无 owner 不得进入 canonical；
- `purpose` 不得写成“介绍 X”，必须写“为谁解决什么问题、支持什么决策”；
- `scope_out` 必须明确不覆盖什么。

## 七、单一真相源

| 真相类型 | 唯一出处 |
|---|---|
| 知识体系标准 | `docs/standards/knowledge-system/v4.3.1/` |
| 文档治理 | `docs/DOCUMENT_SYSTEM.md` |
| 文档入口 | `docs/README.md` |
| 非规范解释材料 | `docs/reference/explanatory/` |
| 生成白皮书/状态报告 | `reports/` |
| 能力清单 | `AIPLAT_CAPABILITIES.md` |
| 架构规范 | `docs/architecture/system-architecture-contract.md` |
| 架构全景 | `docs/architecture/overview.md`（摘要，非规范） |
| 架构边界 | `docs/architecture/boundary-standard.md` |
| Core 运行时契约 | `aiPlat-core/docs/contracts/01-architecture-contract.md` |
| FDE/Org 契约 | `docs/contracts/README.md` + 各契约 |
| FDE 工作台 | `docs/contracts/FDE_WORKBENCH_CONTRACT.md` |
| Eval 产品 | `docs/products/five-products/modules/evaluation/README.md` |
| FDE 指南 | `docs/guides/fde/README.md` |

规则：

- 每个主题只能有一个 canonical；
- 其他文档只能引用，不得重复定义；
- 同一结论出现两处即视为缺陷。

## 八、报告与归档

### 8.1 报告

- 根 `reports/` 纳入登记，但标记 `report/generated`；
- 报告禁止手工编辑；更新 = 重新生成；
- 报告头必须包含生成时间、生成命令、“不手动编辑”声明；
- 运行证据只追加，不参与 canonical 评审。

### 8.2 归档

- `docs/archive/` 与 `reports/**/_archive/` 均为 historical；
- 归档必须带 `supersedes` / `superseded_by`；
- 归档文档不参与 canonical 评审；
- 归档目录不得成为第二个文档系统。

## 九、生命周期

| 类型 | 复审周期 | 过期处理 |
|---|---|---|
| Standard | 版本变更时 | 旧版本归档 |
| Architecture | 90 天 | 告警 |
| Contract | 接口变更时 | 更新或废弃 |
| Product | 90 天 | 告警 |
| Guide | 流程变更时 | 更新 |
| Report | 不维护 | 归档 |
| Draft | 180 天 | 告警 + owner 确认后归档（无自动脚本） |
| Archive | 只读 | 不处理 |

## 十、CI 验证

必须新增：

| 检查 | 阻断 |
|---|---|
| 文档类型不在 v2.4 列表 | 是 |
| canonical 缺 owner/purpose/scope | 是 |
| 维护区断链 | 是 |
| 重复 canonical 声明 | 是 |
| 生成报告被手工修改 | 是 |
| 归档文档被 canonical 引用 | 告警 |
| 半年未复审 canonical | 告警 |
| 旧版本标准留在主目录 | 是 |
| 文档宪法数字/引用/章节自检 | 是 |

> v2.4 起结构、metadata、canonical、全量链接均以 strict 运行。
> 全量链接只检查维护区（archive/_archive 只读，不纳入 strict）；
> 使用 `scripts/doc_link_baseline.json` 基线，仅新增断链阻断。

脚本：

```text
scripts/verify_doc_structure.py
scripts/verify_docs.py
scripts/verify_doc_links.py
scripts/verify_doc_metadata.py    # 新增
scripts/verify_canonical.py       # 新增
scripts/verify_document_system.py # 新增（Batch 0 自检）
```

生成器路径统一从注册表读取，禁止在生成器中硬编码 `docs/whitepaper` 或 `reports/whitepapers`：

```text
docs/doc-paths.yaml
```
```

## 十一、迁移

### 11.1 映射

| 当前 | 目标 |
|---|---|
| `docs/whitepaper/knowledge-system/...v4.3.1` | `docs/standards/knowledge-system/v4.3.1/` |
| `docs/knowledge-system.md` | `docs/guides/knowledge/knowledge-system.md` |
| `docs/contracts/ONTOLOGY_*` | `docs/contracts/knowledge/` 或 `fde/` |
| `docs/manuals/fde/**` | `docs/guides/fde/**` |
| `docs/manuals/*.md` | `docs/guides/development|deployment|operations/**` |
| `docs/architecture/decisions/**` | `docs/decisions/architecture/` |
| `docs/whitepaper/**` | 规范 → `docs/standards/`；非规范 → `docs/reference/explanatory/`；生成 → `reports/` |
| `docs/architecture/plans/**` | 保留 `architecture/plans/`（非 canonical） |
| `docs/reports/**` | 根 `reports/docs-governance/` 或归档 |
| `reports/five-products/modules/**` | `docs/products/five-products/modules/` |
| `reports/five-products/contracts/**` | `docs/contracts/products/five-products/` |
| `reports/five-products/plans/**` | `docs/products/five-products/plans/` |
| `reports/five-products/ops/**` | `reports/products/five-products/ops/` |
| `packages/*/docs/**` | 保留包内；根 docs 只索引 |
| `docs/archive/**` | `docs/archive/` 下按类型归档 |

### 11.2 顺序

1. 批准 v2.4；
2. 扩展 `verify_doc_structure.py`；
3. 新增 metadata/canonical 检查；
4. 给 canonical 文档补 frontmatter；
5. 归档旧标准/历史；
6. Batch A：断链/重定向；
7. Batch B/C：合并/归档。

### 11.3 禁止

- 一次性大搬迁；
- 未建 redirect map 就移动；
- 只改版本声明就称“对齐”；
- 生成报告与手写规范混放。

## 十二、验收

- 954 份文档全部有 `doc_type`；
- canonical 文档有 owner/purpose/scope；
- 根 `reports/`、`packages/*/docs` 纳入登记；
- CI 能阻断维护区断链；
- 不再出现“只加版本声明就称对齐”；
- 每个主题只有一个 canonical。

## 十三、未决问题

1. 文档系统 owner；
2. 架构 canonical 的最终 owner；
3. `reports/` 保留期；
4. `docs/products` 迁移时间；
5. 旧 `docs/manuals` 与 `docs/guides` 的合并节奏。

## 十四、数字声明治理

数字声明必须有单一出处、可执行验证命令，并由 `scripts/verify_document_system.py` 检查。

| 声明项 | 当前值 | 验证命令 |
|---|---:|---|
| Engine Skills | 13 | `find aiPlat-core/skills -name SKILL.md | wc -l` |
| HookPhase 枚举 | 21 | `grep -c '^    [A-Z_]* = "' aiPlat-core/core/harness/infrastructure/hooks/hook_manager.py` |
| Arch Guard 规则 | 195 | `grep -c '^  - id:' aiPlat-core/core/management/arch_guard_rules.yaml` |
| 本体引擎模块 | 32 | `ls aiPlat-core/core/harness/ontology_engine/*.py | wc -l` |
| 本体引擎总行数 | 12423 | `wc -l aiPlat-core/core/harness/ontology_engine/*.py | tail -1 | awk '{print $1}'` |
| 文档一级目录数 | 26 | `find docs -mindepth 1 -maxdepth 1 -type d | wc -l` |

规则：

- 当前值不是永久常量；每次验证更新“当前值 + 日期”；
- 验证命令失败/返回空 → 阻断；
- 数字变化但命令仍可执行 → 告警并更新值；
- 禁止在正文裸写无法验证的数字。

## 十五、六个 CLAUDE.md 的定位与边界

| 文件 | 定位 | 作用范围 |
|---|---|---|
| 根 `CLAUDE.md` | 工作区兜底规约 | 跨所有仓库 |
| `aiPlat-core/CLAUDE.md` | Core 层规约 | aiPlat-core |
| `aiPlat-infra/CLAUDE.md` | Infra 层规约 | aiPlat-infra |
| `aiPlat-platform/CLAUDE.md` | Platform 层规约 | aiPlat-platform |
| `aiPlat-management/CLAUDE.md` | Management 层规约 | aiPlat-management |
| `aiPlat-app/CLAUDE.md` | App 层规约 | aiPlat-app |

## 十六、已知问题

| # | 问题 | 状态 |
|---|---|---|
| 1 | `docs/index.md` 已合并到 `docs/README.md` | 关闭（2026-11-11） |
| 2 | 954 份文档尚未迁入目标目录 | open |
| 3 | canonical 文档 owner 仍为 TBD | open |
| 4 | 骨架过期没有自动归档脚本 | open（改为人工确认） |
| 5 | `reports/` 生命周期仍在迁移 | open |

## 十七、文档宪法自检

运行：

```bash
python3 scripts/verify_document_system.py
```

检查：

- 章节编号是否重复；
- 数字声明命令是否执行成功；
- 当前值是否与命令输出一致；
- 六个 CLAUDE.md 是否存在；
- `docs/index.md` 僵尸条目是否已清除；
- 关键引用文件是否存在。
