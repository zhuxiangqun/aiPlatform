# aiPlat 文档导航

> 从哪里开始读，取决于你的角色和目标。

## 按角色导航

| 角色 | 首先读 | 然后读 |
|------|--------|--------|
| **架构师** | `architecture/overview.md` → `architecture/boundary-standard.md` | `DOCUMENT_SYSTEM.md` |
| **开发者** | `guides/DEVELOPMENT.md` → 对应层的 `CLAUDE.md` | `architecture/core-layer1-latest.md` |
| **运维** | `guides/DEPLOYMENT.md` → `operations/management-manual.md` | `AIPLAT_ROADMAP.md` |
| **用户** | `AIPLAT_CAPABILITIES.md` | `by-role/user/index.md` |

## 按主题导航

| 主题 | 入口文档 |
|------|---------|
| **系统能做什么** | `AIPLAT_CAPABILITIES.md`（能力清单） |
| **文档系统本身** | `DOCUMENT_SYSTEM.md`（治理框架） |
| **架构全貌** | `architecture/overview.md` |
| **层边界规则** | `architecture/boundary-standard.md` |
| **架构契约** | `architecture/system-architecture-contract.md` + `aiPlat-core/docs/contracts/` |
| **AI 编程规约** | 各层 `CLAUDE.md`（根 → core → infra → platform → management → app） |
| **有哪些已知债务** | 根 `CLAUDE.md` §16 |
| **技术文章** | `articles/private-control-plane.md` |
| **部署** | `guides/DEPLOYMENT.md` |
| **测试** | `guides/TESTING_GUIDE.md` |
| **历史参考** | `archive/`（仅供历史参考，不保证时效性） |

## 目录说明

| 目录 | 内容 | 维护？ |
|------|------|:--:|
| `architecture/` | 权威架构设计 | 是 |
| `guides/` | 操作指南 | 是 |
| `standards/` | 跨层强制性规范 | 是 |
| `policy/` | 安全/运维策略 | 是 |
| `design/` | 设计提案（To-Be） | 是 |
| `reports/` | 生成报告快照 | **否**（重新生成） |
| `archive/` | 历史文档 | **否**（只读） |
| `by-role/` | 角色导航索引 | 是 |
| `strategy/` | 战略分析 / 对外的厂商对比 | 是 |
| `research/` | 调研报告 | **否**（留档） |
| `operations/` | 运维参考 | 是 |
| `articles/` | 技术文章 | 是 |
| `comparison/` | 竞品对比 | 已归档，入口在 `architecture/comparison.md` |

## 文档治理

- **DOCUMENT_SYSTEM.md**：文档系统治理框架（分类、边界、验证规则）
- **verify_docs.py**：自动化文档验证脚本（`python scripts/verify_docs.py`）
- **CI 验证**：`.github/workflows/docs-verify.yml`（PR 时自动运行）

---

*最后更新: 2026-07-04*
