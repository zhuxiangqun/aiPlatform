# 执行产物质量门禁矩阵（产物类型 → 规则）

> **真相源（代码）**：`aiPlat-core/core/management/execution_quality_review.py`  
> **配置审核**：Agent `workspace_agents.audit_agent_config`；Skill/Tool/MCP/Workflow 各自 `*/audit`  
> **能力登记**：[`AIPLAT_CAPABILITIES.md`](../../AIPLAT_CAPABILITIES.md)「执行后产物质量复核」等条目  
> **生成物**：平台横切治理；生成应用若走同一 `review_execution_output` / 资产 audit 则适用（管理端执行弹窗与 pipeline stage 已接线）。

本文回答三件事：

1. **编辑 / 执行壳是共通的**——不要给每个 Agent 复制 Modal。  
2. **假 A 按产物形状加规则**——PRD ≠ 架构 ≠ 代码。  
3. **Skill / Tool / MCP / Workflow** 要不要「像 Agent 一样再处理一遍」、**画面优化**是共通还是各改各的。

---

## 1. 资产类型总表（Skill / Tool / MCP / Workflow / Agent）

| 资产 | 配置 AI 审核 | 执行后产物复核 | 还要不要「像 Agent 那样整轮重做」 |
|------|--------------|----------------|----------------------------------|
| **Agent** | ✅ `POST /workspace/agents/{id}/audit` | ✅ `review_execution_output(kind=agent)` | 否。配置侧已对齐「引擎 Skill 未在库」；产物侧按形状加规则 |
| **Skill** | ✅ `POST /workspace/skills/{id}/audit` + lint/apply-fix | ✅ 同一 `review_execution_output` + `review-output` API | **否重做壳**。新假 A → `_looks_*` + 规则 |
| **Tool** | ✅ `POST /tools/{name}/audit` | ✅ 已接线（偏 schema / 空输出 / logical_failure） | 一般够用；特殊 Tool 产物再加规则 |
| **MCP** | ✅ `POST /workspace/mcp/servers/{name}/audit` | ⚠️ 无对等「调用产物质量门」 | 审核已有；若要对 tools/call 结果建门再扩展 |
| **Workflow** | ✅ `POST /platform/workflows/{id}/audit` | ✅ `review_pipeline_stage`（按节点） | **否重做壳**。阶段产物走节点绑定的 Skill/Agent 规则 |

原则：

- **配置假 A**（未在库 / 未上架）→ 走各资产 `audit`，改共通门禁逻辑，不是按资产复制 UI。  
- **产物假 A**（PRD 软 AC、架构公有云等）→ 只扩 `execution_quality_review.py`，Workflow 阶段自动吃到同一套。

验证：

```bash
grep -n "audit_agent_config\|audit_tool_config\|review_execution_output\|review_pipeline_stage\|resolve_review_io_from_store" \
  aiPlat-core/core/api/routers/workspace_agents.py \
  aiPlat-core/core/api/routers/tools.py \
  aiPlat-core/core/management/execution_quality_review.py
```

**Stream 输入连续性**（防假 fail / 误判定稿）：

1. Agent/Skill seed + final upsert **必须**写入 `input`（Agent 经 `run_workspace_agent(input_payload=…)`）。  
2. 完成时 `metadata.quality_review` 由服务端写入；`GET /executions/{id}/status` 回传 `input` + `quality_review`。  
3. `POST …/review-output` 在 body.input 空时用 `execution_id` → `resolve_review_io_from_store` 回填。  
4. 输入仍空时：`review_input_missing`（warning）+ 按 OQ 形状 last-resort draft；**禁止**在无 input 时跑 `invented_nfr`（否则产物短语全变「编造」）。

---

## 2. 画面：统一渲染（schema 驱动）vs 可选专属打磨

**答案：不必一个 Agent 一个画面。** 统一扩展点是 Skill 的 `output_schema`（+ 可选 `x-display-profile`）；UI 默认用通用结构化树渲染。

| 层 | 是否必做 | 说明 |
|----|:--------:|------|
| **执行壳 / 质量面板 / 审核** | ✅ 一次到位 | `Execute*Modal`、`ExecutionQualityReviewPanel`、`AssetAuditPanel` |
| **`GenericObjectOverview`** | ✅ **统一默认** | 任意对象/数组：按 `output_schema.properties` 排序/标签；无 schema 时按结构推断。**新 Skill 声明契约即可，零 UI 白名单** |
| **`PrdOverview` / `ArchitectureOverview`** | ⚪ 可选加分 | 仅当 schema `x-display-profile` / 产物 `document_type` 显式声明时启用 |
| **按 Agent 名复制 Modal** | 🚫 禁止 | 入口共通，结果走同一 `StructuredSkillOutput` |

| UI 块 | 共通？ | 说明 |
|-------|--------|------|
| `ExecutionQualityReviewPanel` | ✅ 共通壳 | Skill / Agent / Tool / 全屏流程复用 |
| `ExecuteResultPanel` | ✅ 共通壳 | 透传 `outputSchema` → `StructuredSkillOutput` |
| `AssetAuditPanel` | ✅ 共通 | Skill / MCP / **Agent** 共用；问题项优先，通过项（`*_binding_ok` / 引擎 Skill）可折叠 |
| `StructuredSkillOutput` | ✅ **统一路由器** | profile（schema/document_type）→ 专属 Overview；否则 `GenericObjectOverview(schema)` |
| `Edit*` / `Execute*` Modal | ⚠️ 文件分开 | 载荷/表单不同；**禁止**再按角色拆 Modal |

### 2.1 渲染优先级

1. Skill 声明 `output_schema.x-display-profile: prd|architecture`（或产物 `document_type`）→ 专属 Overview  
2. **任意其它 JSON** → `GenericObjectOverview`（读 schema 排序/描述；无 schema 仍可读）  
3. Markdown `##` → `MarkdownCards`  
4. 纯文本 → `<pre>`

**扩展规则（统一方法）**：

```yaml
# SKILL.md
output_schema:
  x-display-profile: prd   # 可选：仅当需要专属布局（UI 元数据，不是 LLM 必填字段）
  type: object
  properties:
    title: { type: string, description: 标题 }
    # …字段顺序与 description 驱动管理端分区
```

**契约坑（强制）**：`x-display-profile` / `type` / `required` / `description` 是 schema 脚手架，**禁止**当作 LLM 顶层输出键。
Skill 执行器经 `_output_schema_payload_keys` 只取 `properties.*`（或过滤 meta 后的扁平字段）写入 JSON-override；
解析失败时回落 `{"text": …}`，**禁止**再 wrap 进 `x-display-profile`（否则会出现「步骤1 CoT 塞进 display-profile」的假产物，见 run-cadf97）。

新 Agent / Skill：**默认只改 SKILL.md 契约，不改前端。** 仅当通用树不够用时才加专属 Overview。后端假 A 规则仍按产物形状扩展 `execution_quality_review.py`，与 UI 解耦。

**改审核红灯 / 质量面板** → 改共通壳。  
**改「何为合格产物」** → 后端规则。  
**改「执行结果能不能读」** → `GenericObjectOverview` + `output_schema`；专属 Overview 只做观感加分。

---

## 3. 共通壳（配置 + 执行）

| 能力 | 入口 | 说明 |
|------|------|------|
| Agent 编辑 / 绑定 / AI 审核 | `EditAgentModal` + `audit_agent_config` | 绑定含引擎 Skill（标「引擎」）；工作区 Skill 看上架态 |
| Skill / Tool / MCP / Workflow 审核 | 各自 Edit* + `*/audit` | 与 Agent 同模式；多走 `AssetAuditPanel` |
| 执行 / 流程 / 质量面板 | Execute* + `review_execution_output` | 跑通 ≠ 产物合格；复核 fail 压过「自评 A」观感 |
| Skill 库 vs 引擎目录 | `engine_skill_binding`（info）/ `skill_not_listed` | **引擎 Skill 可直接绑定执行**；仅工作区副本才查上架态 |
| 绑定通过态可见 | `tool_binding_ok` / `mcp_binding_ok` / `sub_agent_binding_ok` / `workflow_binding_ok` | 通过用 info 汇总；失败用 error/warning；未绑定不提示 |

```bash
grep -n "engine_skill_binding\|_looks_prd_skill\|_looks_architecture" \
  aiPlat-core/core/api/routers/workspace_agents.py \
  aiPlat-core/core/management/execution_quality_review.py
```

---

## 4. 执行产物复核如何选型

`review_execution_output(...)` **不按 Agent 显示名**，按：

1. `asset_id` / `asset_name` / `hints` 关键词  
2. 输出 JSON 形状（如是否含 `functional_requirements`、`components`）

| 检测函数 | 典型资产 / 形状 | 代码 |
|----------|-----------------|------|
| `_looks_prd_skill` | `requirement_analysis`、产品经理；含 FR / OQ / user_stories | `execution_quality_review.py` |
| `_looks_architecture` | `architecture_design`、系统架构师；含 components / api_contracts / architecture_mode | 同上 |
| （通用） | 任意 kind（含 Tool） | `empty_output` / `logical_failure` |
| Workflow 阶段 | `review_pipeline_stage` → 解析节点绑定后再调用上表 | 同上 |

---

## 5. PRD / 需求分析门禁（`_looks_prd_skill`）

| 规则码 | 严重度 | 拦什么 |
|--------|--------|--------|
| `missing_hard_constraint` | error | 口述「不上公网 / 钉钉 API」未保留 |
| `soft_acceptance_criteria` | warning | 「通过看板查看 / 成功提示」等软 AC |
| `fr_without_ac` | error | FR 无非空 `acceptance_criteria` |
| `missing_required_ac_tokens` | error | 输入要求的 `pending_approval` 等未进 AC |
| `insufficient_functional_requirements` | error | FR &lt; 3 |
| `missing_core_flow_fr` | error | 缺上报 / 审批派修 / 看板 |
| `constraint_as_functional_requirement` | error | 不上公网等约束冒充 FR |
| `constraint_bucket_mismatch` | error | 安全项写进 performance |
| `empty_open_questions_on_draft` | error | 非定稿轮 OQ 空却仍有未决信号 |
| `premature_prd_ready` | error | 未决却 PRD_READY |
| `out_of_scope_reopened` | error | 明确不做又进 open_questions |
| `out_of_scope_as_feature` | error | 明确不做写成正向 FR |
| `invented_nfr` | error | 编造 SLA / 加密 / 多语言等 |
| `pending_as_acceptance_criteria` | error | 待确认当 AC |
| + `assess_prd(assessment_round, input_text)` | 视 pack / round | `draft` 允许 open_questions；垂直 pack 按输入匹配且剥离「明确不做/不转写」等否定触发，防产物编造误触 media_* |

一键修复：对应 `_QUALITY_SOP_FIXES` → `apply_quality_sop_for_skill_id`。

---

## 6. 架构设计门禁（`_looks_architecture`）

| 规则码 | 严重度 | 拦什么 |
|--------|--------|--------|
| `public_cloud_photo_storage` | error | 输入要求不上公网，却选用阿里云 OSS / 公有云对象存储等 |
| `architecture_sections_thin` | error | 输入要求的章节缺失（上下文与假设 / 数据流 / 安全合规 / 分期风险） |
| `architecture_sections_thin`（API） | warning | 端点缺少请求/响应要点 |

---

## 7. 通用执行复核 / 编码交付硬门

| 规则码 | 说明 |
|--------|------|
| `empty_output` | status=completed 但输出空 |
| `logical_failure` | 产物 `success: false` |
| `clarification_only` | 任务要求交付，输出只在追问确认 |
| `thin_code_stub` | DONE / 空 `## FILE` / 无实质函数体 |
| `language_mismatch` | 任务要求 TS/JS/Python，产物语言不一致（如要 TS 却交 `.py`）→ **硬失败**，`quality_review_blocks_success` |
| `off_spec_coding` | 缺约定 `/api/...` 路径，或 print/placeholder 脚手架冒充交付 → 硬失败 |
| `autoreview_incomplete` | 任务/绑定要求 autoreview，但 skill 未 success（含 `approval_required`）或产物伪造 `autoreview.py` → 硬失败 |

编码门实现：`_coding_contract_fail_codes` / `_output_misses_stated_contracts`（供 `is_non_deliverable_coding_output` 与循环 veto 共用）。

**`skill_delivery=once` 跟跑**：主技能（如 `code_generation`）实质交付后，ReAct observe 会**确定性自动调用**绑定的 follow-up（`autoreview` → …），不再依赖第二轮 LLM 自己想起调用；收口源记为 `observe_auto_followup_seal`（避免 `autoreview_incomplete` 假失败与嵌套 LLM 挂死）。

前端工程师测试用例须要 **TypeScript `apiClient`**，禁止把 FastAPI/Pydantic 样例套给 FE（见 `execution_examples` / `executionSamples.ts`）。

---

## 8. 配置 AI 审核要点

### 8.1 Agent（绑定门禁最全）

| category | 含义 |
|----------|------|
| `engine_skill_binding` | info：引擎内置 Skill，可直接绑定执行（无需工作区副本） |
| `tool_binding_ok` / `mcp_binding_ok` / `sub_agent_binding_ok` / `workflow_binding_ok` | info：对应绑定已检查且通过（**通过用 info 可见，失败用 error/warning**；未绑定不提示） |
| `sop_empty` / `sop_short` / `sop_missing_role` / `sop_missing_flow` / `sop_missing_goal` / `sop_missing_quality` | **SOP 内容**：空/过短/缺角色/缺流程/缺产出/缺验收（对齐 Skill lint 信号，规则驱动） |
| `sop_skills_unreferenced` / `sop_tools_unreferenced` | SOP 未引用已绑定 Skill/Tool id（绑定与指引脱节）；**Skill 可一键修**：`append_sop_skill_refs` 幂等追加「已绑定 Skill（审核附录）」只列 id |
| `sop_content_ok` | info：SOP 内容门禁通过（无 sop_* warning 时汇总可见） |
| `skill_not_listed` | 工作区有，但 status ∉ {published, listed} |
| `tool_not_listed` / `invalid_tool` | 工具未上架或未注册 |
| `mcp_not_listed` / `sub_agent_not_listed` / `workflow_not_listed` | 同类绑定门禁 |
| 模型 / toolset / permissions / SOP | 见 `audit_agent_config` 全文 |

### 8.2 Skill / Tool / MCP / Workflow

| 资产 | 审核重点（摘要） |
|------|------------------|
| Skill | lint / SOP / status 上架 / 签名与治理字段；`apply-lint-fix` |
| Tool | description / parameters schema / status；勿空 parameters 占位 |
| MCP | validate_mcp_server、URL/stdio、连通性探测（报告向） |
| Workflow | 画布节点必填、孤立节点、环路、绑定 Agent/Tool 存在性 |

细节以各 `*/audit` 实现为准；扩展时优先复用 `asset_audit.summarize_audit_issues`。

---

## 9. 「自评 A 级」vs「质量复核」

| 来源 | 含义 |
|------|------|
| `result.eval` 🏆 A 级 | Agent 任务评分维度，**不是**合规门禁 |
| `quality_review.verdict` | 规则复核；`fail` 时管理端应以降级展示为准 |

---

## 10. 缺口与扩展清单

| 产物 / 能力 | 现状 | 扩展方式 |
|-------------|------|----------|
| 代码生成 / 实现 | 多靠 `autoreview` skill | 新增 `_looks_codegen` + 规则，勿新 Modal |
| 代码审查报告 | 无统一 execution_quality 形状 | 可选：P0 未清零不得 pass |
| MCP tools/call 产物 | 仅配置 audit | 若要对调用结果建门 → `kind=mcp` + 形状检测 |
| 测试计划 / 评测报告 | 无 | 按需 |
| 纯对话 | 仅通用 empty/logical | 通常够用 |
| Agent 审核区 | ✅ 已用 `AssetAuditPanel` | 与 Skill/MCP 共通；通过项折叠展示 |

**扩展清单**：新假 A → 判定产物形状 → 在 `execution_quality_review.py` 增加 `_looks_*` + issues +（可选）`_QUALITY_SOP_FIXES` + 单测；同步本文件与 `AIPLAT_CAPABILITIES.md`。  
**禁止**：为单个 Agent/Skill 复制 `Edit*` / `Execute*` Modal。

验证命令：

```bash
../.venv/bin/python -m pytest aiPlat-core/core/tests/unit/test_apps/test_execution_quality_review.py \
  aiPlat-core/core/tests/unit/test_api/test_agent_audit_tool_lifecycle.py -q
```
