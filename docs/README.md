# aiPlat 文档导航

> 系统文档的唯一入口。按角色或主题找到你需要的文档。

---

## 🚀 新手必读

| 顺序 | 文档 | 说明 |
|:---:|------|------|
| 1 | [manuals/getting-started.md](manuals/getting-started.md) | 5 分钟体验 |
| 2 | [manuals/knowledge-management.md](manuals/knowledge-management.md) | 知识管理全管线 |
| 3 | [manuals/deployment.md](manuals/deployment.md) | 部署指南 |

---

## 👤 按角色导航

| 角色 | 入口文档 |
|------|------|
| **架构师** | [architecture/README.md](architecture/README.md) → [architecture/overview.md](architecture/overview.md) |
| **开发者** | [manuals/development.md](manuals/development.md) → 对应层的 `CLAUDE.md` |
| **运维** | [manuals/deployment.md](manuals/deployment.md) → [manuals/management.md](manuals/management.md) |
| **知识管理员** | [manuals/knowledge-management.md](manuals/knowledge-management.md) → [manuals/ontology.md](manuals/ontology.md) |
| **FDE 交付工程师** | [manuals/README.md](manuals/README.md)（手册总目录）→ 按需选择 |
| **新用户** | [manuals/getting-started.md](manuals/getting-started.md) → [AIPLAT_CAPABILITIES.md](../AIPLAT_CAPABILITIES.md) |

---

## 📂 按目录导航

### 架构设计（architecture/）
[architecture/README.md](architecture/README.md) — 23 份文档，分核心参考（6 份）/ ADR（2 份）/ 规划（13 份）/ 合规（1 份）

### 操作手册（manuals/）
[manuals/README.md](manuals/README.md) — 22 份手册，覆盖开发/部署/测试/本体管理/知识管理/FDE 交付

### 设计提案（design/）
[design/](design/) — 5 份设计文档（To-Be，非当前实现状态，以代码为准）

### 框架评估（framework/）
[framework/](framework/) — 6 份成熟度评估/对比/评分文档

### 安全（security/）
[security/](security/) — 4 份安全架构/测试/渗透报告

### 跨层规范（standards/）
[standards/](standards/) — 3 份强制性规范（run_id/trace_id、鉴权透传、session_id）

### 策略配置（policy/）
[policy/](policy/) — 2 份安全/运维策略

### API 协议（API/）
[API/](API/) — 2 份 API 参考/归因协议

### 项目（project/）
[project/PHASE_STATUS.md](project/PHASE_STATUS.md) — Phase 实施状态快照

### 其他
[agents/](agents/) · [articles/](articles/) · [audit/](audit/) · [by-role/](by-role/) · [compliance/](compliance/) · [harness/](harness/) · [mcp/](mcp/) · [reports/](reports/) · [skills/](skills/) · [strategy/](strategy/) · [tools/](tools/) · [whitepaper/](whitepaper/) · [archive/](archive/)

---

## 📋 目录速查

| 目录 | 内容 | 文件数 | 维护？ |
|------|------|:---:|:---:|
| `architecture/` | 架构设计 + ADR + 规划 | 23 | 是 |
| `manuals/` | 操作手册（唯一手册入口） | 22 | 是 |
| `design/` | 设计提案（To-Be，非现状） | 5 | 过期标注 |
| `framework/` | 成熟度评估框架 | 6 | 评估时更新 |
| `security/` | 安全架构与测试 | 4 | 是 |
| `standards/` | 跨层强制性规范 | 3 | 是 |
| `policy/` | 安全/运维策略 | 2 | 是 |
| `API/` | API 协议与契约 | 2 | 是 |
| `project/` | 项目管理（Phase 状态等） | 1 | 是 |
| `reports/` | 生成报告快照 | 3 | **否**（重新生成） |
| `archive/` | 历史文档 | 27 | **否**（只读） |
| 其他 | 1 文件专题目录 | 10 | 按需 |

---

## 📐 文档治理

- **[DOCUMENT_SYSTEM.md](DOCUMENT_SYSTEM.md)**：文档系统宪法（分类、边界、验证）
- **[AIPLAT_CAPABILITIES.md](../AIPLAT_CAPABILITIES.md)**：唯一能力清单（881 ✅）
- **verify_doc_structure.py**：目录树一致性验证
- **verify_capability_consistency.py**：能力统计表一致
- **verify_imports.py**：导入模块存在性验证

---

*最后更新: 2026-07-18*

## 📂 按阅读目的查找

| 我想… | 看这个分类 | 典型路径 |
|:---|:---|------|
| 查 CI 会拦截的规则 | 📜 核心规约 | CLAUDE.md, AIPLAT_CAPABILITIES.md |
| 理解系统怎么设计的 | 🏗️ 架构设计 | architecture/, harness/, contracts/, agents/ |
| 查某一层怎么实现 | 📋 层设计 | api/, database/, llm/, deployment/ |
| 学怎么操作交付 | 📖 用户手册 | manuals/fde/, by-role/ |
| 看下个版本规划 | 🎨 设计方案 | design/ |
| 查本体/Wiki/RAG | 🧠 知识引擎 | knowledge/, memory/ |
| 查安全红线 | 🔒 合规与安全 | compliance/, security/ |
| 查 MCP/测试工具 | 🛠️ 工具与框架 | mcp/, tools/, testing/ |
| 看系统状态报告 | 📄 报告与审计 | reports/, archive/ |
