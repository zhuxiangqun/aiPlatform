# aiPlatform 文档导航

> 最后更新: 2026-07-01

## 按时间投入分层 — 从哪里开始读

### 第 1 层：5 分钟了解系统

| 文档 | 回答什么问题 |
|------|------------|
| [README.md](../README.md) | 这个项目是干什么的？ |
| [AIPLAT_CAPABILITIES.md](../AIPLAT_CAPABILITIES.md) | 系统能做什么？398 项能力全清单 |

### 第 2 层：30 分钟知道怎么工作

| 文档 | 回答什么问题 |
|------|------------|
| [CLAUDE.md](../CLAUDE.md) | 开发规约是什么？什么能做、什么不能做？ |
| [AIPLAT_ROADMAP.md](../AIPLAT_ROADMAP.md) | 做完了什么、下一步做什么？评分 99/100 |
| [standards/](standards/) | 鉴权怎么透传？trace_id 怎么规范？session 怎么设计？ |
| [architecture/comparison.md](architecture/comparison.md) | 和 Hermes/ClaudeCode/OpenClaw/Octo 比怎么样？ |
| [architecture/system-architecture-contract.md](architecture/system-architecture-contract.md) | 四层架构的边界合约是什么？ |

### 第 3 层：深入具体子系统

| 文档 | 回答什么问题 |
|------|------------|
| [architecture/role_system.md](architecture/role_system.md) | 14 个角色怎么分工？哪些已 Agent 化？ |
| [architecture/user_journey_map.md](architecture/user_journey_map.md) | 用户从哪进、怎么走、到哪结束？ |
| [architecture/deployment_checklist.md](architecture/deployment_checklist.md) | 怎么部署到生产？ |
| [harness/README.md](harness/README.md) → aiPlat-core | 执行引擎怎么设计？(12 个详细文档) |
| [aiPlat-core/docs/skills/architecture.md](../aiPlat-core/docs/skills/architecture.md) | Skill 系统架构 |
| [aiPlat-core/docs/memory/index.md](../aiPlat-core/docs/memory/index.md) | 四层记忆系统 |
| [aiPlat-core/docs/contracts/](../aiPlat-core/docs/contracts/) | 8 份架构契约 |

### 第 4 层：各仓库规约

| 文档 | 适用对象 |
|------|---------|
| [../aiPlat-core/CLAUDE.md](../aiPlat-core/CLAUDE.md) (2067 行) | 后端开发者 |
| [../aiPlat-infra/CLAUDE.md](../aiPlat-infra/CLAUDE.md) | 基础设施开发者 |
| [../aiPlat-platform/CLAUDE.md](../aiPlat-platform/CLAUDE.md) | 平台层开发者 |
| [../aiPlat-management/CLAUDE.md](../aiPlat-management/CLAUDE.md) | 管理端/前端开发者 |
| [../aiPlat-app/CLAUDE.md](../aiPlat-app/CLAUDE.md) | 应用接入层开发者 |

---

## 按角色导航

| 角色 | 必读文档 |
|------|---------|
| **FDE (前线部署工程师)** | CAPABILITIES → comparison.md → role_system.md → user_journey_map.md |
| **后端开发者** | CLAUDE.md (根) → aiPlat-core/CLAUDE.md → contracts/ → harness/ |
| **前端开发者** | CLAUDE.md (根) → aiPlat-management/CLAUDE.md → architecture/management-ui-action-map.md |
| **架构师** | architecture/comparison.md → system-architecture-contract.md → contracts/ → design/ |
| **运维** | deployment_checklist.md → standards/ → guides/DEPLOYMENT.md |

---

## 特殊目录说明

| 目录 | 内容 | 维护策略 |
|------|------|---------|
| `docs/archive/` | 历史对标/白皮书/一致性审查报告 | 不主动维护 |
| `../2026年及更早/` | 旧版路线图/PR拆解/执行计划 | 已整合入 ROADMAP |
| `../reports/` | 自动生成的审计/复审报告 | 快照数据，非手写文档 |
| `aiPlat-core/docs/design/` | Phase 9 Kernel Orchestrator 详细设计 | 实现完成后归档 |
| `aiPlat-management/docs/` | 管理端文档 — 大部分是链接，详细内容在源仓库 | 持续维护 |
