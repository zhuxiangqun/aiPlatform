# Skill 规范模板 v2（管理台生成 → 开发者精修）

> 本文是 **“目录化技能（SKILL.md）”** 的官方规范模板（v2）。目标是让 Skill 从“提示词片段”升级为 **可发现、可治理、可测试、可演进** 的资产。
>
> 设计参考：Microsoft *ai-agents-for-beginners* 中 `.agents/skills/*/SKILL.md`（强调 When-to-use / Decision tree / Workflow / Validation + scripts/assets/references 的 L3 稳定化）。

---

## 0. 设计目标（平台级）

1. **管理台可生成**：80% 场景无需手写 YAML，避免格式错误；开发者只需补充 SOP/脚本。
2. **开发者可精修**：允许在 UI 之外手动增强（更精细的 triggers、异常处理、评测样例、脚本化）。
3. **可治理**：permissions → risk_level → gate/approval；高风险变更可阻断或审批。
4. **可回归**：输出契约稳定（JSON + Markdown），可 lint、可巡检、可告警、可一键修复。

---

## 1. 推荐工作流（最优实践）

### 1.1 “先生成，再精修”是否更好？

是的：**管理台生成**能保证字段完整性与一致性；**开发者精修**能保证表达的准确性与生产细节（边界条件、脚本化、回滚）。

建议流程：

1. 管理台用“Skill 创建向导”生成：
   - frontmatter（L1/L2：metadata + schemas + governance）
   - SOP 骨架（L2：章节模板）
2. 开发者在仓库/目录中补齐：
   - 更具体的 decision tree、workflow、异常处理
   - `scripts/`、`assets/`、`references/`（L3）
3. 平台自动：
   - lint + fix proposals
   - 定时巡检 + 告警
   - 一键应用安全修复（Phase-1：markdown/schema）

---

## 2. 目录结构（L2/L3）

```
<skill_id>/
├── SKILL.md                  # L2：规范化定义（frontmatter + SOP body）
├── scripts/                  # L3：可执行逻辑（确定性/可测试）
├── assets/                   # L3：模板/提示片段/固定资源
└── references/               # L3：参考资料/质量清单/约束说明
```

约定：
- **SOP** 放在 `SKILL.md` body（L2），便于阅读与审查。
- **稳定逻辑**（易漂移/复杂的步骤）放到 `scripts/`（L3），减少模型不确定性。

---

## 3. SKILL.md 规范（v2）

### 3.1 文件结构

`SKILL.md` 分为两段：

1) **Frontmatter（L1/L2）**：YAML 元信息 + 契约 + 治理字段（平台可解析）  
2) **Body（L2）**：SOP（给 Agent/人类执行的说明书）

#### 示例骨架

```markdown
---
name: my_skill
display_name: "我的技能"
description: "当用户需要……时使用（<=280字）"
category: analysis
version: 1.0.0
status: enabled

# 路由/触发（建议）
trigger_conditions:
  - "用户可能说法1"
  - "用户可能说法2"

# 类型与治理
skill_kind: executable # rule|executable
permissions:
  - llm:generate

# 契约（强约束：output_schema 必含 markdown）
input_schema:
  input:
    type: string
    required: true
    description: "输入文本"
output_schema:
  result:
    type: string
    required: true
  markdown:
    type: string
    required: true
    description: "面向人阅读的 Markdown 输出，与结构化字段一致"

# （可选）决策树：用于引导路由与执行策略（推荐逐步规范化）
decision_tree:
  - if: "用户想要教学/教程"
    then: "走 tutorial 模式"
  - if: "用户想要实验/探索"
    then: "走 experiment 模式"

# （可选）资源声明（用于 L3 发现/审计）
resources:
  scripts:
    - scripts/run.py
  assets:
    - assets/template.md
  references:
    - references/quality-checklist.md
---

# 概述

## 目标
...

## 何时使用 / 何时不用
...

## 输入 / 输出
...

## 决策树（Decision tree）
...

## 工作流程（SOP）
...

## 异常处理与回滚
...

## 验收清单（Checklist）
- [ ] ...
```

---

## 4. Frontmatter 字段规范（管理台生成的“表单模型”）

### 4.1 必填字段（平台强约束）

| 字段 | 说明 | 约束 |
|---|---|---|
| `name` | skill_id（目录名建议一致） | `[a-z][a-z0-9_-]{2,}` |
| `description` | 路由召回与可解释性核心 | 建议 8~280 字 |
| `category` | 任务分类（用于路由、治理、统计） | enum（见下） |
| `skill_kind` | 执行形态 | `rule` / `executable` |
| `output_schema` | 输出契约 | **必须包含 `markdown` 字段** |

### 4.2 推荐字段（强烈建议，lint 会提示）

| 字段 | 说明 |
|---|---|
| `trigger_conditions` | 3~10 条用户常用说法，提升路由稳定性 |
| `input_schema` | 输入契约，提升复用/评测 |
| `version` | semver，便于资产演进 |
| `resources` | 明确 scripts/assets/references 的依赖清单 |

### 4.3 category 推荐枚举

`general / execution / retrieval / analysis / generation / transformation / reasoning / coding / search / tool / communication`

> `skill_kind` 表达“是否可执行（脚本/工具）”，`category` 表达“做什么”。

### 4.4 permissions（治理核心）

原则：**最小权限**。

常见例子：
- `llm:generate`（低风险）
- `tool:webfetch` / `tool:websearch`（中风险）
- `tool:run_command` / `tool:workspace_fs_write`（高风险：启用/发布应门控或审批）

---

## 5. Body（SOP）章节模板（开发者精修重点）

你可以把它当成一个“可测试的 runbook”。

必须包含（lint 会提示缺失）：

1. **目标**：一句话说清“完成什么任务”
2. **流程/步骤**：可执行的步骤，不要写散文
3. **Checklist**：验收点（用于回归/巡检）

强烈建议包含：
- **异常处理**：失败如何降级、重试、回滚、提示用户补信息
- **输出格式说明**：字段含义、边界条件、示例输出

---

## 6. 不同 Skill 类型的差异化要求

### 6.1 规则型（prompt/SOP）
- 重点：清晰 SOP + 输入/输出契约 + checklist
- 适用：低风险、短链路、对稳定性要求不极端

### 6.2 可执行型（带 scripts）
- 重点：把确定性逻辑下沉到 `scripts/`，SOP 只负责编排
- 必须：permissions、超时/重试、幂等说明

### 6.3 检索型（RAG/Docs/Search）
- 重点：证据链（sources）、去重策略、时间/范围校验、引用格式
- 建议：输出中显式包含 `sources[]`（并在 markdown 中引用）

### 6.4 工具编排型（plan/tool calls）
- 重点：dry_run、工具调用计划 schema、权限边界、回滚说明
- 建议：输出结构中包含 `plan`（可审计、可回放）

---

## 7. 平台 lint / auto-fix / apply-fix 约束（与你当前系统对齐）

### 7.1 lint（示例）
- `missing_output_schema`（error）
- `missing_markdown`（error，**可自动修复**）
- `missing_permissions`（executable 必填，error）
- `missing_triggers`（warning）
- `sop_missing_goal/flow/checklist`（warning）

### 7.2 fix proposals（建议输出）
平台会返回：
- `fixes[]`：`frontmatter_merge` patch ops + preview + markdown 说明
- Phase-1 一键应用（安全白名单）：仅允许 `output_schema.markdown` 的 schema 修复

---

## 8. 附：管理台生成字段建议（分层展示）

### 基础（默认展示）
- name / display_name / description / category / skill_kind
- trigger_conditions
- input_schema / output_schema（带模板按钮）

### 高级（折叠）
- permissions（executable 必填）
- decision_tree（结构化编辑）
- resources（脚本/模板/参考）

### SOP（大文本）
- 生成章节模板，开发者再精修

