# aiPlat 文档导航

> 系统文档的唯一入口。按角色或主题找到你需要的文档。

---

## 新手必读

| 顺序 | 文档 | 说明 |
|:---:|------|------|
| 1 | [manuals/getting-started.md](manuals/getting-started.md) | 5 分钟体验 |
| 2 | [knowledge-system.md](knowledge-system.md) | 知识管理完整指南（管线/存储/本体/RAG/运维） |
| 3 | [manuals/deployment.md](manuals/deployment.md) | 部署指南 |

---

## 按角色导航

| 角色 | 入口文档 |
|------|------|
| **架构师** | [architecture/README.md](architecture/README.md) → [architecture/overview.md](architecture/overview.md) |
| **开发者** | [manuals/development.md](manuals/development.md) → 对应层的 `CLAUDE.md` |
| **运维** | [manuals/deployment.md](manuals/deployment.md) → [manuals/management.md](manuals/management.md) |
| **知识管理员** | [knowledge-system.md](knowledge-system.md) |
| **FDE 交付工程师** | [manuals/README.md](manuals/README.md)（手册总目录）→ 按需选择 |
| **新用户** | [manuals/getting-started.md](manuals/getting-started.md) → [AIPLAT_CAPABILITIES.md](../AIPLAT_CAPABILITIES.md) |
| **Pi Thin Runtime（当前交付）** | [../packages/aiplat-pi-runtime/README.md](../packages/aiplat-pi-runtime/README.md) · living 摘要 [architecture/plans/pi-thin-runtime.md](architecture/plans/pi-thin-runtime.md)（≠ 五产品目标 Enterprise Runtime） |
| **要完整平台现状白皮书** | [whitepaper/aiplat-platform-status-whitepaper.md](whitepaper/aiplat-platform-status-whitepaper.md) · 五维分卷 [whitepaper/volumes/](whitepaper/volumes/) · 体系 [WHITEPAPER_SYSTEM.md](whitepaper/WHITEPAPER_SYSTEM.md) |

---

## 按目录导航

### 架构设计（architecture/）
[architecture/README.md](architecture/README.md) — 核心参考含 [execution-decision-matrix.md](architecture/execution-decision-matrix.md) 与 [execution-quality-gates.md](architecture/execution-quality-gates.md)；另有 ADR / 规划（非现状）/ 合规

### 操作手册（manuals/）
[manuals/README.md](manuals/README.md) — 开发/部署/测试/本体/知识/FDE 交付等操作手册

### 设计提案（design/）
[design/](design/) — To-Be 设计文档（非当前实现状态，以代码为准）

### 框架评估（framework/）
[framework/](framework/) — 成熟度评估/对比/评分

### 安全（security/）
[security/](security/) — 安全架构与测试

### 跨层规范（standards/）
[standards/](standards/) — 跨层强制性规范（`规范-*.md`）

### 契约（contracts/）
[contracts/README.md](contracts/README.md) — FDE / Ontology 等跨仓契约索引（阅读顺序见该 README）

### 策略配置（policy/）
[policy/](policy/) — 安全/运维策略

### API 协议（API/）
[API/](API/) — API 参考与归因协议

### 项目（project/）
[project/PHASE_STATUS.md](project/PHASE_STATUS.md) — Phase 实施状态快照

### 其他
[agents/](agents/) · [articles/](articles/) · [audit/](audit/) · [by-role/](by-role/) · [compliance/](compliance/) · [guides/](guides/) · [harness/](harness/) · [matrix/](matrix/) · [mcp/](mcp/) · [reports/](reports/) · [research/](research/) · [skills/](skills/) · [strategy/](strategy/) · [tools/](tools/) · [whitepaper/](whitepaper/) · [archive/](archive/)

---

## 目录速查

> **统计口径**：`docs/**/*.md`，排除路径含 `node_modules`。  
> **时点**：`2026-10-23`（S4 归档后现算）。口径：`docs/**/*.md`，排除 `node_modules`。静态计数会再漂。

| 目录 | 内容 | 文件数 | 维护？ |
|------|------|:---:|:---:|
| `contracts/` | 跨仓契约（FDE / Ontology 等） | 43 | 是（索引见 README） |
| `manuals/` | 操作手册 | 39 | 是 |
| `architecture/` | 架构设计 + ADR + 规划 | 38 | 核心参考是；plans 非现状 |
| `research/` | 研究报告 / 对标 / 方案 | 35 | 混有收官稿；见目录 README |
| `archive/` | 历史文档 | 32 | **否**（只读） |
| `whitepaper/` | 白皮书体系与分卷 | 16 | 生成物按 suite；体系文档是 |
| `standards/` | 跨层强制性规范 | 10 | 是 |
| `design/` | 设计提案（To-Be） | 6 | 过期标注 |
| `framework/` | 成熟度评估框架 | 6 | 评估时更新 |
| `security/` | 安全架构与测试 | 4 | 是 |
| `by-role/` | 角色索引 | 4 | 是 |
| `reports/` | 生成报告快照 | 3 | **否**（重新生成） |
| `API/` | API 协议 | 2 | 是 |
| `policy/` | 安全/运维策略 | 2 | 是 |
| `audit/` | 合规审计 | 2 | 按需 |
| `project/` | 项目管理 | 1 | 是 |
| `matrix/` | 能力影响矩阵 | 1 | 是 |
| `guides/` | 补充指南（如 PR 架构检查清单） | 1 | 按需 |
| 根下散文件 + 其余 1 文件专题 | knowledge-system 等 | 其余 | 按需 |
| **合计** | | **258** | |

顶层子目录数：**26**（含上表各簇）。

---

## 文档治理

- **[DOCUMENT_SYSTEM.md](DOCUMENT_SYSTEM.md)**：文档系统宪法（分类、边界、验证）
- **[research/docs-system-status-analysis-2026-10.md](research/docs-system-status-analysis-2026-10.md)**：文档系统现状快照（2026-10；事实与机制诊断，非改造方案）
- **[AIPLAT_CAPABILITIES.md](../AIPLAT_CAPABILITIES.md)**：能力声明/接线索引（计数见该文件；不等于行为验收）
- **[whitepaper/aiplat-platform-status-whitepaper.md](whitepaper/aiplat-platform-status-whitepaper.md)**：平台现状白皮书（**从 CAPABILITIES 生成**，`--check` 防过期；非手写第二清单）

### 校验脚本覆盖面（勿过度解读）

| 脚本 | 实际覆盖 | CI（`docs-verify.yml`） |
|------|----------|-------------------------|
| `scripts/verify_doc_structure.py` | `docs/` **一级目录**是否已在 DOCUMENT_SYSTEM §一登记 | **已接入** `docs-verify.yml`（2026-10-23） |
| `scripts/verify_doc_links.py` | **仅 3 个文件**：DOCUMENT_SYSTEM、docs/README、manuals/README | 未作为独立 job 列出时勿称「全站链接已检」 |
| `scripts/verify_docs.py` | by-role 链接、报告头、archive 免责、能力数裸写等（见 DOCUMENT_SYSTEM §七） | **有**（workflow 调用此脚本） |
| 白皮书 `--check` | 生成物相对指定权威源的**新鲜度** | 按白皮书/suite 流水线；≠ 无重复正文 |

---

*最后更新: 2026-10-23（S1 入口与宪法对齐；计数时点见上）*

## 按阅读目的查找

| 我想… | 看这个 | 典型路径 |
|:---|:---|------|
| 查 CI/规约会拦截的规则 | 核心规约 | 根 `CLAUDE.md`、各子仓 `CLAUDE.md`、`AIPLAT_CAPABILITIES.md` |
| 理解系统怎么设计的 | 架构设计 | `architecture/`、`harness/`、`contracts/`、`agents/` |
| 查某一层怎么实现 | 层设计 | `aiPlat-core/docs/`、`aiPlat-infra/docs/`、`aiPlat-platform/docs/` 等（不在根 `docs/` 一级目录） |
| 学怎么操作交付 | 用户手册 | `manuals/`、`manuals/fde/`、`by-role/` |
| 看目标态/规划 | 设计与规划 | `design/`、`architecture/plans/`（含五产品；**非现状**） |
| 用 Pi Thin Runtime | Pi 现行交付 | `packages/aiplat-pi-runtime/README.md`、`architecture/plans/pi-thin-runtime.md` |
| 查本体/Wiki/RAG | 知识引擎 | `knowledge-system.md`、`contracts/ONTOLOGY_*`、`manuals/ontology.md`（指向知识系统） |
| 查安全红线 | 合规与安全 | `compliance/`、`security/`、`policy/` |
| 查 MCP/测试工具 | 工具与框架 | `mcp/`、`tools/`、`manuals/testing.md` |
| 看系统状态报告 | 报告与审计 | `reports/`、`archive/`、`research/` |
