---
doc_type: Specification
authority: primary
scope: workspace
language: zh-CN
---

# aiPlat 文档系统治理框架

> 本文档是 aiPlat 文档系统的"宪法"——定义目录结构、文档类型、边界规则、单一真相源映射和维护流程。
> 所有其他文档必须在本框架的约束下创建、维护和归档。

---

## 一、目录结构

```
workspace-root/
│
├── CLAUDE.md                          ← 工作区兜底规约（AI 编程行为约束）
├── AIPLAT_CAPABILITIES.md            ← 唯一能力清单（当前 464 项，代码交叉验证）
├── AIPLAT_ROADMAP.md                 ← 商业化路线图（评分 + 基线）
├── README.md                         ← 部署手册
│
├── docs/
│   ├── DOCUMENT_SYSTEM.md            ← 本文档 — 文档系统治理框架
│   ├── README.md                     ← 阅读导航（按角色 + 按主题）
│   │
│   ├── architecture/                 ← 架构设计
│   │   ├── overview.md               ← 权威架构全景（唯一出处）
│   │   ├── boundary-standard.md      ← 层边界判定标准
│   │   ├── core-layer1-latest.md     ← Core 层最新架构详述
│   │   ├── system-architecture-contract.md ← 跨层契约
│   │   ├── role_system.md            ← 角色体系
│   │   └── decisions/                ← 架构裁决记录 (ADR)
│   │       ├── evaluator_calibration.md
│   │       └── tot_reserve.md
│   │
│   ├── guides/                       ← 操作指南（How-To）
│   │   ├── DEPLOYMENT.md
│   │   ├── DEVELOPMENT.md
│   │   ├── TESTING_GUIDE.md
│   │   └── PR_ARCHITECTURE_CHECKLIST.md
│   │
│   ├── standards/                    ← 跨层规范（强制性）
│   │   ├── session-id-spec.md
│   │   ├── auth-identity-spec.md
│   │   └── trace-id-spec.md
│   │
│   ├── policy/                       ← 安全/运维策略
│   │   ├── external-allowlist.md
│   │   └── mcp-stdio-prod-allowlist.md
│   │
│   ├── design/                       ← 设计提案（非现状，是 Plan / To-Be）
│   │   ├── ontology-design.md
│   │   ├── knowledge-ontology-plan.md
│   │   ├── model-management.md
│   │   ├── ui-design.md
│   │   └── ui-implementation-status.md
│   │
│   ├── research/                     ← 调研报告（不维护，留档用）
│   │   └── effect-ts-di-research.md
│   │
│   ├── operations/                   ← 运维参考
│   │   └── management-manual.md
│   │
│   ├── reports/                      ← 生成报告（时间点快照，不手动编辑）
│   │   ├── README.md
│   │   ├── AIPLAT_ARCHITECTURE_REPORT.md
│   │   └── AIPLAT_DIAGNOSTIC_REPORT.md
│   │
│   ├── strategy/                      ← 战略分析 / 竞品对比（对外可发布）
│   │   └── comparison-vs-vendors.md   ← aiPlat vs 图数据库厂商
│   │
│   ├── articles/                     ← 技术文章（对外发布）
│   │   └── private-control-plane.md
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

## 二、文档类型与边界定义

### 2.1 五类文档

| 类型 | 定义 | 生命周期 | 维护频率 | 示例 |
|------|------|:--:|:--:|------|
| **规约（Specification）** | 强制性约束，变更需审核 | 长期维护，版本化 | 每次 PR 涉及相关领域 | CLAUDE.md、architecture-contract |
| **设计文档（Design）** | 描述系统架构和实现细节 | 随代码更新 | 每次架构变更 | harness/index.md、ontology-design.md |
| **指南（Guide）** | 操作步骤和最佳实践 | 随工具/流程更新 | 流程变更时 | DEPLOYMENT.md、TESTING_GUIDE.md |
| **报告（Report）** | 某个时间点的快照 | **不维护**，过期后归档 | 永不 | ARCHITECTURE_REPORT.md、DIAGNOSTIC_REPORT.md |
| **裁决（Decision/ADR）** | 架构决策的记录 | 永久留存 | 永不（除非决策推翻） | evaluator_calibration.md |
| **骨架（Draft/Skeleton）** | 预留的占位文档 | **最多 180 天**，过期归档 | 填充或删除 | Platform 文档中的骨架文件 |

### 2.2 骨架文档规则

1. **头部必须包含**：`status: draft` + `draft_date: YYYY-MM-DD`
2. **过期处理**：`draft_date` 超过 `180 天`（`AIPLAT_DOC_DRAFT_EXPIRY_DAYS`）仍未转为正式文档 → **自动归档或删除**
3. **CI 检测**：`verify_docs.py` Rule 8 会在 PR 时告警过期骨架文档

### 2.3 设计文档时效性规则

1. **头部必须包含**：`最后更新: YYYY-MM-DD` 或 `last_synced: YYYY-MM-DD`
2. **过期告警**：超过 `90 天`（`AIPLAT_DOC_DESIGN_STALE_DAYS`）未更新 → `verify_docs.py` Rule 7 告警
3. **这不会阻断 PR**，但会在 CI 中提醒作者确认文档是否仍然准确 |

### 2.2 边界规则

| 文档类型 | 可以包含 | 不可包含 |
|---------|---------|---------|
| **规约** | 强制性规则、违反后果、边界定义 | 实现细节、操作步骤、临时性方案 |
| **设计文档** | 架构描述、模块列表、数据流、API 契约 | 命令行操作指南、部署步骤 |
| **指南** | 操作步骤、命令示例、配置文件模板 | 架构理念、设计原则 |
| **报告** | 生成时间、快照数据、当时结论 | **禁止事后手动编辑**（要更新就重新生成） |
| **裁决** | 背景、决策、替代方案、后果 | 实现代码、操作指南 |

---

## 三、数字声明治理

### 3.1 规则

1. **所有数字声明必须有单一出处**。例如能力数 `464` 的唯一出处是 `AIPLAT_CAPABILITIES.md`。

2. **非出处文档必须引用出处**。例如 `ROADMAP.md` 写能力数时，不裸写数字，而是写 "见 AIPLAT_CAPABILITIES.md 当前计数"。

3. **标准引用格式**（Rule 12 的匹配目标）：
   ```
   （参见 AIPLAT_CAPABILITIES.md 当前计数）
   ```
   所有文档中的裸数字能力数将被自动替换为这个格式。整词匹配，不误替换 URL/端口号/文件路径中的数字。

4. **数字声明必须可自动化验证**。每个数字声明附带验证命令：
   ```bash
   grep -c '✅' AIPLAT_CAPABILITIES.md          # 能力总数
   ls engine/skills/*/SKILL.md | wc -l           # Engine Skills 数
   grep -c '^  - id:' arch_guard_rules.yaml      # Arch Guard 规则数
   ```

5. **CI 做数字变化检测，不阻断**。pre-commit 不校验当前计数是否等于某固定值，CI nightly 检测到数字变化时生成通知。

### 3.2 当前已验证的数字声明

| 声明 | 出处 | 验证命令 | 当前值 |
|------|------|---------|:--:|
| 能力总数 | `AIPLAT_CAPABILITIES.md` | `grep -c '✅' AIPLAT_CAPABILITIES.md` | 464 |
| Engine Skills | `engine/skills/*/SKILL.md` | `ls engine/skills/*/SKILL.md \| wc -l` | 32 |
| HookPhase 枚举 | `hook_manager.py:15` | `grep -c '= "' hook_manager.py \| head -1` | 20 |
| Arch Guard 规则 | `arch_guard_rules.yaml` | `grep -c '^  - id:' arch_guard_rules.yaml` | 172 |
| 本体引擎模块 | `ontology_engine/*.py` | `ls ontology_engine/*.py \| wc -l` | 23 |
| 本体引擎总行数 | `ontology_engine/*.py` | `wc -l ontology_engine/*.py` | ~6,800 |

---

## 四、单一真相源映射表

| 真相类型 | 唯一出处 | 验证方法 |
|---------|---------|---------|
| 能力总数 | `AIPLAT_CAPABILITIES.md` | `grep -c '✅'` |
| 能力详情 | `AIPLAT_CAPABILITIES.md` 各节 | 每行标注的文件路径 |
| 架构边界 | `docs/architecture/boundary-standard.md` | 引用 § 编号 |
| 架构契约 | `aiPlat-core/docs/contracts/01-08` | 文件存在 |
| 模型管理 | `aiPlat-infra/CLAUDE.md` §5.6 | `ModelManager.list_models()` |
| 身份/权限 | `aiPlat-platform/CLAUDE.md` | JWT → tenant/actor/scopes |
| AI 编程规则 | 各层 `CLAUDE.md` | 文件存在 |
| 路线图/评分 | `AIPLAT_ROADMAP.md` | 引用 CAPABILITIES 计数 |
| 部署步骤 | `docs/guides/DEPLOYMENT.md` | 操作可复现 |
| 废弃模块 | 根 `CLAUDE.md` §16 已知债务 | git log 确认删除 |

---

## 五、五个 CLAUDE.md 的定位与边界

| 文件 | 定位 | 作用范围 | 不应包含 |
|------|------|---------|---------|
| 根 `CLAUDE.md` | 工作区兜底规约 | 跨所有仓库 | 单仓库的架构细节 |
| `aiPlat-core/CLAUDE.md` | Core 层详尽规约 | aiPlat-core | Infra/Platform 的规则 |
| `aiPlat-infra/CLAUDE.md` | Infra 层规约 | aiPlat-infra | Core 的执行细节 |
| `aiPlat-platform/CLAUDE.md` | Platform 层规约 | aiPlat-platform | Core 的引擎实现 |
| `aiPlat-management/CLAUDE.md` | Management 层规约 | aiPlat-management | 后端 API 实现 |
| `aiPlat-app/CLAUDE.md` | App 层规约 | aiPlat-app | 平台层权限逻辑 |

---

## 六、文档生命周期管理

### 6.1 新增文档

1. [ ] 确认类型（规约/设计/指南/报告/裁决）
2. [ ] 放到正确的目录（见 §一）
3. [ ] 如包含数字声明，注明出处文件和验证命令
4. [ ] 如引用其他文档，使用相对路径引用
5. [ ] 如引用代码位置，使用 `file:line` 格式
6. [ ] 更新 `docs/README.md` 的导航（如适用）

### 6.2 审查文档

1. [ ] 所有数字声明是否与代码一致？（运行验证命令）
2. [ ] 是否有指向已删除文件的引用？
3. [ ] 规约类文档是否有违反后果定义？
4. [ ] 报告类文档是否已过期？是否应该归档？
5. [ ] 是否有两个文档在描述同一件事且不一致？

### 6.3 归档文档

- 移动到 `docs/archive/`
- 在文件名加日期后缀或版本号
- 归档文件**不维护**，仅做历史参考
- `docs/archive/README.md` 声明："归档内容仅做历史参考，不构成当前系统的约束。如有冲突，以 `docs/architecture/` 和 `CLAUDE.md` 为准。"

### 6.4 报告生成

- 报告类文档头部必须包含：生成时间、生成命令、"不手动编辑"声明
- 需要新数据时重新生成，不手动编辑报告
- 报告中的数字声明不视为"真相源"——引用时必须回到原出处
- `docs/reports/README.md` 中写明每个报告的生成命令

---

## 七、自动化验证

### 7.1 CI 验证（`.github/workflows/docs-verify.yml`）

| 检查项 | 类型 | 触发 |
|--------|:--:|------|
| by-role 链接有效性 | **阻断** | PR 触及 docs/ |
| 报告缺少"不手动编辑"头部 | **阻断** | PR 触及 docs/ |
| archive/README.md 缺少免责声明 | **阻断** | PR 触及 docs/ |
| 非 CAPABILITIES 文件裸写能力数 | **告警**（不阻断） | PR 触及 docs/ |
| 重复的"唯一真相源"声明 | **告警**（不阻断） | PR 触及 docs/ |
| 架构文件重复了控制平面内容 | **告警**（不阻断） | PR 触及 docs/architecture/ |
| 设计文档超过 90 天未更新 | **告警**（不阻断） | PR 触及 docs/design/ |
| 骨架 draft 超过 180 天 | **告警**（不阻断） | PR 全仓库 |

### 7.2 本地验证

```bash
python scripts/verify_docs.py
```

### 7.3 配置阈值

| 配置项 | 环境变量 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| 设计文档过期天数 | `AIPLAT_DOC_DESIGN_STALE_DAYS` | 90 | 超过此天数未更新即告警 |
| 骨架文档过期天数 | `AIPLAT_DOC_DRAFT_EXPIRY_DAYS` | 180 | 超过此天数仍为 draft 即归档 |

阈值均可通过环境变量覆盖，无需修改代码。

---

## 八、已知问题与待清理项

| # | 问题 | 计划 |
|---|------|------|
| 1 | 竞品对比文件 7+ 个，多版本文档 | 归档旧版到 `archive/`，保留 `docs/architecture/comparison.md` 为唯一入口 |
| 2 | Platform 文档 56% 为骨架占位 | 长期渐进补充，添加 `draft_date` 标记 |
| 3 | `docs/design/` 下部分文件未标注 `last_synced` | 渐进标注 |

---

*最后更新: 2026-07-04*
*版本: 1.0*
