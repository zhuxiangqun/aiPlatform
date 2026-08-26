# 系统整体架构规范（System Architecture Contract）

> 适用范围：aiPlatform 全系统（management / app / platform / core / infra）  
> 目标：提供**系统级**的分层职责、依赖方向、跨层契约与边界约束。  
> 说明：各层的细化规范请参考各层 `docs/`，本文件只定义跨层“硬约束”和最小必要契约。

---

## 1. 系统分层与职责（MUST）

aiPlatform 采用“业务四层架构 + 独立管理系统”：

- **Management（管理平面）**：`aiPlat-management`  
  横切四层业务架构，提供运维、诊断、配置、告警、审计视图。
- **Layer 3（应用层）**：`aiPlat-app`  
  面向用户的应用入口（消息网关、多渠道接入、CLI、Workbench 等）。
- **Layer 2（平台服务层）**：`aiPlat-platform`  
  对外 API 网关与平台能力（认证鉴权、多租户、限流熔断、路由、审计等）。
- **Layer 1（AI 核心层）**：`aiPlat-core`  
  AI 运行时与核心能力（Harness/Runtime、Agents、Skills、Memory、ExecutionStore、Tools/MCP 等）。
- **Layer 0（基础设施层）**：`aiPlat-infra`  
  提供数据库、配置、向量存储、LLM 客户端、监控等基础设施，**完全独立**。

---

## 2. 依赖方向与禁止依赖（MUST）

### 2.1 静态依赖（编译时/设计时）

**允许依赖方向（单向依赖）**：

```
aiPlat-app → aiPlat-platform → aiPlat-core → aiPlat-infra
```

**禁止依赖（MUST NOT）**：
- `aiPlat-app` 直接依赖 `aiPlat-core`（必须经由 `aiPlat-platform`）
- `aiPlat-app` 直接依赖 `aiPlat-infra`
- `aiPlat-platform` 直接依赖 `aiPlat-infra`（必须经由 `aiPlat-core`）
- 任何下层依赖上层（infra/core/platform/app）

### 2.2 运行时调用链（请求处理链）

典型链路：

```
外部渠道/用户 → Layer 3（app） → Layer 2（platform） → Layer 1（core） → Layer 0（infra）
```

> 注：management 为横切管理平面，不参与业务调用链，但可调用各层“管理接口/观测接口”。

---

## 3. 跨层身份、权限与多租户透传（MUST）

### 3.1 单一权威原则

- `aiPlat-platform` 是**唯一权威**的身份与权限解析/签发方（JWT/API key → tenant/actor/scopes）。
- 下游（app/core）**只消费** platform 注入的身份信息，**不得推断**或自行扩权。

### 3.2 标准透传 Headers（platform → app/core）

platform 在调用下游服务时 **MUST** 注入/透传：

- `X-AIPLAT-REQUEST-ID`：请求唯一标识（用于审计、幂等、追踪）
- `X-AIPLAT-TENANT-ID`：租户 ID
- `X-AIPLAT-ACTOR-ID`：调用方 ID（用户或服务主体）
- `X-AIPLAT-SCOPES`：权限 scopes（推荐）
- `X-AIPLAT-ACTOR-ROLE`：可选（以 scopes 为准）

详见：[`规范-platform-鉴权与身份透传.md`](../../规范-platform-鉴权与身份透传.md)

---

## 4. 跨层执行标识与可观测契约（MUST）

### 4.1 request_id

- `request_id` 由 platform 生成并透传（见上文 `X-AIPLAT-REQUEST-ID`）。
- 所有层的日志/审计 **MUST** 打印（脱敏后）`request_id + tenant_id + actor_id`。

### 4.2 run_id / trace_id

- AI 执行（agent/skill/tool）由 `aiPlat-core` 运行时生成 `run_id`，并可输出 `trace_id`。
- management/UI 展示与排障时应以 `run_id/trace_id` 作为核心定位信息。

详见：[`规范-core-run_id-trace_id-request_id.md`](../../规范-core-run_id-trace_id-request_id.md)

---

## 5. 错误透传与网关行为（MUST）

- platform 作为网关层，对下游（core/app）的非 2xx 响应，**MUST 透传可诊断信息**（至少包含 `detail` 或等价字段）。  
- 禁止仅返回“500 Internal Server Error”而吞掉上游错误上下文（除非涉及敏感信息，需要脱敏/替换）。

### 5.1 部署与执行完整性（MUST，2026-08-25 P0 修复固化）

以下契约约束 builder 应用工厂的**执行安全**与**接线完整性**，来自 `docs/research/应用工厂分析报告.md` §7.5 实现代码审计的 5 个 P0 缺陷修复：

| # | 契约 | 实现位置 | 违反后果 |
|---|------|---------|---------|
| 1 | builder 流水线启动入口 `start_pipeline` / `start_pipeline_background` 必须由 `BuilderProjectService` 定义并委托 `rebuild_project`（PRD 前置检查：无 `confirmed_prd` 拒绝启动） | `aiPlat-platform/builder/builder_project_service.py` | AttributeError / 静默空跑 |
| 2 | PRD 解析**禁止** `eval()` 执行 LLM 返回字符串（任意代码执行）；Python dict 字面量解析必须用 `ast.literal_eval` | `aiPlat-platform/builder/builder_project_service.py` | RCE |
| 3 | `PipelineEngine._deploy_result_files` 写 LLM 声明的 `## FILE:` 时**必须**经 `_safe_join` 约束（防 `../` 穿越逃逸 `deploy_files_target_dir`）；穿越尝试跳过该文件并告警 | `aiPlat-core/core/harness/execution/pipeline_engine.py` | 任意路径写文件 |
| 4 | `_run_stage_skill` 域注入段使用 `_prd` 前**必须**先解析（`state.prd_data` 优先 → `description` 尾部 JSON 兜底 → `{}`），禁止引用未定义变量（NameError 被吞 → 注入静默失效） | `aiPlat-core/core/harness/execution/pipeline_engine.py` | 域分类 100% 失效 |
| 5 | 部署签名验证**失败即拒绝**（fail-closed）：验证抛异常或签名不通过时，`POST /platform/builder/projects/{id}/deploy-to-app` 必须返回 403，**禁止** warning 后跳过继续部署 | `aiPlat-platform/api/routers/builder.py` | 未验签项目部署上线 |

回归测试：`aiPlat-core/core/tests/unit/test_pipeline_engine_p0_fixes.py`（P0-3/P0-4，6 项）+ `aiPlat-platform/tests/test_builder_p0_fixes.py`（P0-1/P0-2/P0-5，12 项）。

### 5.2 应用工厂 P1 修复契约（MUST，2026-08-25）

同源审计（§7.5.4）的 14 项 P1 修复固化 + 生成物契约（SBA 借鉴）：

| # | 契约 | 实现位置 | 违反后果 |
|---|------|---------|---------|
| 1 | 团队模板 HITL 合并：`TeamTemplate.stages` 是 YAML dict 列表，**必须** dict 访问（`.get`）；对模板项做属性访问（AttributeError 被吞）使 v3.1 HITL gates 静默失效 | `aiPlat-platform/builder/builder_project_service.py` | HITL 门禁不生效 |
| 2 | `PipelineEngine._exec_test_runner` 上游代码落盘块**必须**位于 `continue` 之前（可执行）；写文件误放 except 内 continue 之后 = 被测代码从不落盘 | `aiPlat-core/core/harness/execution/pipeline_eval.py` | 测试永远空目录运行，pass_rate 失真 |
| 3 | builder 项目删除权限**必须**与创建对齐（`require_admin_access`）：`DELETE /projects/{id}`、`POST /projects/batch-delete` 不得低于 create 的权限等级 | `aiPlat-platform/api/routers/builder.py` | 授权反向（低权限可删高权限创建的资源） |
| 4 | merge apply **必须**如实上报部分失败：`failed` 非空时 status 不得为 `ok`（用 `partial` + detail 透传失败数） | `aiPlat-platform/builder/merge_engine.py` | 前端误报成功，掩盖写入失败 |
| 5 | `_run_chained_skill` **禁止**引用函数签名之外的变量：超时读取必须用函数内已定义的 `_chain_stage`（未定义 `stage` → NameError 被吞 → 链式技能永不执行） | `aiPlat-core/core/harness/execution/pipeline_engine.py` | 链式技能静默失效 |
| 6 | skip_pytest_gate 落盘**必须**收敛到唯一实现 `_apply_skip_pytest_gate`（§10 防并行实现）；禁止在 `_run_stage_skill` 与 `_exec_test_runner` 各自内联 APPROVED_SKIPPED 落盘 | `aiPlat-core/core/harness/execution/pipeline_eval.py`（helper）+ `pipeline_engine.py`/`pipeline_eval.py`（调用点） | 双份漂移、字段语义不一致 |
| 7 | 跨模块 merge 契约门禁的存活性检查文本**必须**包含模块内未修改文件（再生文件）的现有内容；仅扫 previews 新内容会漏掉依赖方引用声明 → 误判 broken 阻断合法合并 | `aiPlat-platform/builder/cross_module.py`（`_new_version_text`/`verify_changed_module_contracts`）+ `builder_project_service.py`（传 module_root） | 合法合并被误阻断 |
| 8 | 并行实现收敛（§10 唯一实现）：节点→stage 转换**唯一**实现为 `WorkflowService._nodes_to_stages`（`AppService._build_stages_from_nodes` 必须委托，禁止内联精简版）；Markdown PRD 解析**唯一**实现为 `BuilderProjectService._parse_markdown_prd`（`BuilderSessionService` 必须委托） | `aiPlat-platform/builder/builder_workflow_service.py` + `builder_app_service.py` + `builder_session.py` | 双份漂移、字段语义不一致 |
| 9 | app 服务 base URL **禁止**硬编码 `http://localhost:8004`：后端必须经 `AIPLAT_APP_BASE_URL` 环境变量（默认 8004）；前端必须走 `/app` 相对路径（vite proxy 转发），不得直连 8004 | `aiPlat-platform/api/routers/builder.py`（`_APP_BASE_URL`）+ `aiPlat-management/frontend/vite.config.ts`（`/app` proxy）+ `AppPage.tsx`/`Factory/index.tsx`（相对路径） | 跨进程/部署环境端口耦合，生产无法同源承载 |
| 10 | pipeline 状态读取**必须**收敛到 SQLite 直读（`_get_state_via_core` 唯一实现，`get_project_state` 复用）；禁止走 Core HTTP 状态端点（单 worker 事件循环被流水线阻塞时超时） | `aiPlat-platform/builder/builder_project_service.py` | HTTP 超时 → 状态读取失败 |
| 11 | 引擎层模型用途推断**必须**配置驱动（§5.29/v4.1）：禁止按技能名关键词（architecture/design/code/generation/test）推断 `skill_model_purpose`；解析链 = team YAML 显式 → AGENT.md frontmatter → SKILL.md frontmatter → 默认 `chat` | `aiPlat-core/core/harness/execution/team_planner.py`（`_load_skill_frontmatter`）+ 7 个 engine SKILL.md（`skill_model_purpose` 声明） | 业务/能力类型推断违反内核无关原则 |
| 12 | HITL 审批**必须**收敛到 `BuilderProjectService.approve_stage`/`reject_stage`（v3.1 Core HTTP 唯一实现）；`BuilderTeamService`/`BuilderSessionService` 的 approve/reject **禁止**走本地 `session.approve`/`pipeline.approve`（PipelineSession 旧语义，与生产路径不一致） | `aiPlat-platform/builder/builder_team_service.py` + `builder_session.py`（委托） | 三套审批语义漂移 |
| 13 | `BuilderProjectService` **禁止**超过 1000 行/40 方法（God Class 红线）：L2-L5（导入/合并/模块/迁移/发布）必须放 `BuilderL2L5Mixin`，部署/健康/洞察必须放 `BuilderDeployMixin`；核心类只保留 CRUD/对话/流水线 | `aiPlat-platform/builder/builder_project_service.py`（核心类 2421→目标 ≤1000 行）+ `builder_l2l5_mixin.py` + `builder_deploy_mixin.py` | 类职责混杂、维护成本指数增长 |
| 14 | 应用工厂生成物（AGENT.md/SKILL.md）注册前**必须**经 `generated_conformance` 契约校验（借鉴 SBA conformance 模式）：首行必须是 `---`（防 ```markdown/空行 残留）、必须含治理字段（execution_type/input_schema/output_schema/version/status/effects）、`input_schema`/`output_schema` 必须为对象格式（含 type/required/description）；不通过则**跳过注册**并告警 | `aiPlat-platform/builder/generated_conformance.py` + `generated_conformance.yaml` + `builder_project_service.py` 注册循环；`aiPlat-core/core/engine/skills/agent_engineering/SKILL.md`（生成规范要求 input_schema/output_schema 对象格式） | 生成物缺治理字段/schema 丢失/格式残留污染工作区 |
| 15 | 应用工厂生成物**骨架化**（B1）：`agent_engineering` 生成规范必须内嵌 AGENT.md/SKILL.md 完整骨架模板（frontmatter 字段不得删减：execution_type/input_schema/output_schema/version/status/description；SKILL.md 必须含输入校验/核心处理/错误处理三执步）；LLM 只填语义值，结构由模板保证——与 conformance 契约（#14）构成双保险 | `aiPlat-core/core/engine/skills/agent_engineering/SKILL.md`（SKILL.md 模板子节） | 生成物字段不全的根因（规范弱）未根治 |
| 16 | 生成 skill **路由-知识分离**（B2）：必须声明 `triggers:` 触发短语（description 命中率依赖）；正文行数**必须** ≤ `body_max_lines` 预算（默认 150 行，防大而全——知识应拆分而非堆砌） | `aiPlat-platform/builder/generated_conformance.yaml`（triggers 必填 + body_max_lines）+ `generated_conformance.py`（预算检查）+ `agent_engineering/SKILL.md` 模板（triggers 字段） | 触发路由命中率低 / 单文件上下文超载 |
| 17 | 生成 skill **description/triggers 一致性**（B2 深化）：每个 `triggers` 触发短语**必须**出现在 `description` 中（用户自然语言 → trigger → description 命中的路由链成立）；**生成物验收基线**（C3）：真实生成产物（frozen fixture）纳入回归——旧格式产物必须被拒、新模板产物必须通过 | `generated_conformance.py`（triggers_in_description）+ `aiPlat-platform/tests/fixtures/generated/`（video_sense 真实产物基线）+ `test_generated_conformance.py` | 路由命中断裂 / conformance 变更无真实产物回归 |

回归测试：`aiPlat-core/core/tests/unit/test_pipeline_eval_p1_fixes.py`（P1-2，2 项）+ `aiPlat-platform/tests/test_builder_p1_fixes.py`（P1-1/P1-3/P1-4/P1-8/P1-9/P1-11/P1-12/P1-13，21 项）+ `aiPlat-core/core/tests/unit/test_team_planner_p1_fixes.py`（P1-5，4 项）+ `aiPlat-core/core/tests/unit/test_pipeline_engine_p1b_fixes.py`（P1-6/P1-7，5 项）。

---

## 6. 层内细化规范（References）

系统整体规范只定义跨层契约；各层内部规范请参考：

- `aiPlat-core`（Layer 1）
  - 核心能力层架构与执行流程（As‑Is）：[`docs/architecture/core-layer1-latest.md`](core-layer1-latest.md)
  - core 内部边界契约（harness/policy/agent/skill）：`aiPlat-core/docs/contracts/01-architecture-contract.md`
- `aiPlat-platform`（Layer 2）：`aiPlat-platform/docs/index.md`（Auth/Tenants/Gateway 等）
- `aiPlat-app`（Layer 3）：`aiPlat-app/docs/index.md`
- `aiPlat-infra`（Layer 0）：`aiPlat-infra/docs/index.md`
- `aiPlat-management`（Management）：`aiPlat-management/docs/index.md`

