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

### 5.1.1 意图路由统一检索契约（MUST，2026-08-28）

`sys_routed_retrieve`（`aiPlat-core/core/harness/syscalls/retrieval.py`）是检索类 syscall（**非** LLM/tool/skill 三通道）：

| 契约 | 说明 |
|------|------|
| 通道路由 | `_route_intent` 按查询意图判定 code/knowledge/web 三通道（T1 关键词，无 LLM），避免全域盲搜 |
| harness 单向依赖 | web 通道 **禁止** import apps 层（§5.14），以 urllib 直调 DuckDuckGo JSON 实现 |
| 降级语义 | 通道不可用降级（code→knowledge→web），web 可关（`include_web=False` 隐私场景）；失败返回空结果不伪装命中 |
| 结构化交付 | 返回 `{route, results, sources}`：`results` 统一 `{text, score, source}` 事实条目，`sources` 信源标注（source/url/text） |
| 可信度评估（2026-08-28） | web 通道结果经 `web_result_quality.assess_web_results`（`aiPlat-core/core/harness/knowledge/web_result_quality.py`）注入 `quality`：域名权威（官方/知名 vs 低质）+ 查询相关性 + 多源一致 + 置信度 → `avg_score`；`pass` → use_results / `flag_for_human`（结果污染风险人工复核，best-effort 不阻断检索） |
| 接线 | `RoutedRetrieveTool`（`aiPlat-core/core/apps/tools/routed_retrieve.py`）经 server.py 工具注册表供 Agent `sys_tool_call` 调用 |

### 5.1.2 运行时路径解析契约（MUST，2026-08-28）

core 层运行时数据库/状态文件路径**必须**经 `core.utils.paths.get_aiplat_home()` 解析（AIPLAT_HOME 优先，回退 `~/.aiplat`）：

| 契约 | 说明 |
|------|------|
| 禁止硬编码 `~/.aiplat` | `expanduser("~/.aiplat/xxx")` 绕过 AIPLAT_HOME（`paths.py` 已标注反模式）——受限环境（~/.aiplat 只读）下启动写库抛 `readonly database` → 服务僵死 |
| 已修复 | `TripleStore`（`core/harness/ontology_engine/triple_store.py`）：`ontology_triples.sqlite3` 路径改经 `get_aiplat_home()`；`code_graph_persist`/`cap_graph_persist`（图谱缓存库 `code_graph.db`/`cap_graph.db`）与 `capability_graph` 工作区扫描同改（2026-08-28）；其余存量硬编码（memory/file_store、knowledge_pipeline、management/* 等）为已知存量，逐步迁移 |
| 验证 | 受限 HOME 启动 core server → `/api/core/diagnostics/*` 三端点 200 毫秒响应（修复前全超时） |

### 5.1.3 诊断时效性契约（MUST，2026-08-28）

诊断判定**必须反映当前状态**，历史残留不得永久拖累：

| 契约 | 说明 |
|------|------|
| 时效窗口 | `check_model_health`（`aiPlat-core/core/diagnostics/checks/model_health.py`）：失败记录按 `last_failure_at` 距今 ≤7 天（`stale_days`）才计入 fail/warn；超期（历史残留，如旧模型集中失败后无新调用）忽略 |
| 保守原则 | 有失败但 `last_failure_at` 缺失 → 无法确认时效，保守计入 fail（不放过疑似当前故障） |
| 降级 | DB 表缺失/锁冲突 → warn 不崩溃；DB 路径经 `get_aiplat_home()` 解析 |
| 图谱构建超时 | 诊断端点 `_get_or_build_graph`（`aiPlat-core/core/api/routers/diagnostics.py`）代码图谱全量构建为后台线程 + 超时降级：`AIPLAT_DIAG_GRAPH_BUILD_TIMEOUT` 默认 15s，超时返回空图（`{}, [], []`）不阻塞端点，后台线程继续构建供下次缓存命中；冷启动由 `server.py` 预热默认开启（`AIPLAT_WARM_GRAPHS` 默认 true）消除首个诊断请求的同步全量构建（5 仓库实测 68s） |
| 事件循环防护 | 诊断端点（system-health/adoption-metrics/ontology-audit/ontology-audit-summary/drift-status）**必须**为同步 `def`（FastAPI 线程池执行），禁止 `async def` 内同步重活——uvicorn 单 worker（`-w 1 --threads 4`）事件循环被阻塞 7s+ 会导致所有并发请求（含 openapi/health）排队超时 502（2026-08-28 实测：system_health.compute 阻塞事件循环）；`system_health.py` 的 `import logging` 必须在模块级（docstring 之外） |
| 模型发现缓存 | `config_drift_detector.scan_all_agents` 对多 agent 循环内的 `ModelManager` 查询**必须**复用候选列表（模块级缓存）——`ModelManager()` 首次实例化触发 `import sentence_transformers`（实测 5.1s）+ Ollama 扫描（4.7s），逐 agent 实例化导致单次 scan 6.5s 并随 agent 数放大 |
| 验证 | 真实库（12 天前 6 模型历史失败）修复前 fail → 修复后 pass；当前健康模型（deepseek 系）不受影响；图谱超时单测（`test_diag_graph_timeout.py`）缓存命中毫秒返回 + 慢构建超时降级空图；并发验证：system-health + openapi + summary 同发均 <1s 返回（修复前 system-health 阻塞时其余超时） |

### 5.1.4 流水线上下文纯净契约（MUST，2026-08-28）

产品流水线（PRD/架构/代码/测试生成）的上下文**必须纯净**，不得注入 FDE 诊断会话语义：

| 契约 | 说明 |
|------|------|
| 注入边界 | `assemble_pipeline_context`（`aiPlat-core/core/harness/knowledge/context_bus.py`）**必须**返回空（不注入任何上下文）；领域上下文由 DomainRouter 域 prompt 承担 |
| 禁止内容 | 流水线上下文禁止包含 `_inject_self_optimization`（诊断自优化 §1/§6/§7）、`_inject_term_dictionary`（业务语义字典 FDE/RAG/本体）、`_inject_delivery_history`（FDE 交付跟踪 §4.6 ROI/历史诊断总数）——这些是 FDE 诊断会话（`assemble_field_assessment`）专用层 |
| 违反后果 | 注入 FDE 诊断语义会误导 LLM 跳过 skill SOP，产出污染 + 空壳产物（实测 2026-08-28：视频解析平台 PRD 混入「诊断自优化 (250条历史)」且 description/acceptance_criteria 全空） |
| 验证 | `test_pipeline_context_clean.py`：流水线上下文为空 + FDE 层不在其中 |

### 5.1.5 Syscall 事件存储契约（MUST，2026-08-28）

LLM syscall 事件记录（`add_syscall_event`）**必须**写入 `execution_store`（`syscall_mixin` 提供），禁止使用 `get_tenant_store()`：

| 契约 | 说明 |
|------|------|
| 存储归属 | `sys_llm_generate` 的 syscall 事件（trace/cost/usage）写入 `runtime.execution_store`（含 `add_syscall_event`）——与 llm.py 其他 6 处调用点一致 |
| 禁止 | 平台 `TenantStore`（`aiPlat-platform/tenants/tenant_store.py`）仅承载租户配额/策略/用量，**不得**承担 syscall 事件记录；`get_tenant_store()` 不得作为 LLM syscall 事件的 store |
| 违反后果 | platform 注入 tenant store 后每次 LLM 调用抛 `AttributeError: 'TenantStore' object has no attribute 'add_syscall_event'` → chat 端点超时 → 前端「发送失败，请重试」（实测 2026-08-28） |
| 验证 | `test_llm_syscall_store.py`：llm.py store 获取走 execution_store + TenantStore 无 add_syscall_event |

### 5.1.6 KB 查询 syscall 遥测契约（MUST，2026-10-14）

`POST /platform/kb/query` 与 collection query 成功路径**必须** soft-fail 写入 `execution_store.syscall_events`，供 Delivery kb-health（`%kb_retrieve%`）消费；身份透传不变：

| 契约 | 说明 |
|------|------|
| 写入点 | `aiPlat-platform/kb/query_telemetry.py` → `record_kb_query_syscall`；由 `api/rest/routes.py` 的 `kb_query` / `collection_query` 调用 |
| 事件名 | `knowledge_retrieve` / `platform_kb_retrieve`（与 metrics 过滤对齐） |
| 身份 | `tenant_id` / actor 仍来自既有 platform 鉴权与身份透传；遥测**不得**改变鉴权语义 |
| soft-fail | 遥测失败不得影响查询响应（`except Exception: pass  # noqa`） |
| 验证 | `test_kb_query_telemetry.py` + `GET /platform/delivery/kb-health` 在有查询流量后不再 `insufficient_data` |

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
| 18 | 生成 skill 路由**字段统一**（B2 注册路由侧）：`discovery.SKILLMD_parser` 解析 `trigger_conditions` **必须** fallback 到 `triggers`/`trigger_keywords`（与 `registry.match` 读 `triggers` 对齐）——生成物（agent_engineering 声明 `triggers:`）注册后 SkillMatcher 必须可命中 | `aiPlat-core/core/apps/skills/discovery.py` + `core/tests/unit/test_skill_routing_triggers.py` | 生成物注册后路由 miss（字段名分歧） |
| 19 | 生成物 conformance 契约**必须**自举校验（CI 门禁）：`architecture_guard.sh §95` 对真实生成物基线（frozen fixture）断言旧格式必拒——契约被改弱后 guard 必须 FAIL（防静默放行不合格生成物） | `scripts/architecture_guard.sh §95` + `aiPlat-platform/tests/fixtures/generated/` | conformance 契约改弱后不合格生成物被放行 |
| 20 | 生成 pipeline **证据门控**（SBA 原则 10：产物完整/成功退出码 ≠ 阶段完成）：`deploy_to_app` 在真实 pytest pass_rate=0（全失败）时**必须拒绝部署**；无测试证据（estimated/skip_pytest_gate）放行但标记风险。**验收派生**（SBA 原则 17：需求是根）：`agent_engineering` 生成前必须从 PRD `acceptance_criteria` 派生验收标准，SKILL.md `completion_criterion` 必须引用对应验收项，禁止偷换/缩窄验收 | `aiPlat-platform/builder/builder_deploy_mixin.py`（门控）+ `aiPlat-core/core/engine/skills/agent_engineering/SKILL.md`（Step 1.5 验收派生）+ `tests/test_builder_evidence_gate.py` | pass_rate=0 仍部署 / 生成物验收与需求脱节 |
| 21 | conformance 拒绝**必须写回审计并聚合**（SBA 原则 13：改变未来动作的失败经验立即写回）：注册循环拒绝生成物时记录 `AIPLAT_HOME/builder/conformance_rejections.jsonl`（项目/类型/违规），`aggregate_rejections()` 统计高频缺失字段并产出生成规范改进建议（喂回 agent_engineering 模板迭代） | `generated_conformance.py`（record_rejection/aggregate_rejections）+ `builder_project_service.py` 注册循环 + `test_generated_conformance.py::TestPrinciple13FailureWriteback` | 失败经验沉淀为被动日志，规范不迭代 |
| 22 | pipeline stage **产物 key 链契约**（SBA 原则 12 Change Contract）：`validate_pipeline_stages` 必须校验下游 `input_artifacts` 引用存在于上游 `output_artifact`（或内置输入 description/user_input/start.inputs）——缺失即 error 阻断，防上游改产物 key、下游仍读旧 key 的隐性断裂 | `aiPlat-core/core/api/core_facade.py`（validate_pipeline_stages）+ `core/tests/unit/test_stage_change_contract.py` | stage 产物 key 隐性断裂 |
| 23 | 生成 skill **确定性校验规则**（SBA 原则 18：低自由度判断下沉）：`agent_engineering` 输入校验必须写成可逐条执行的规则（枚举白名单列全/范围给数值边界/格式给模式），禁止模糊措辞。生成物 `effects` 声明**必填**（§5.19——registry 注册强制，conformance 契约 must_contain 已含 effects）。`seed_for_platform` 注册子目录生成物时**必须**透传 effects（此前缺失→静默拒）；registry 扫描**跳过** TEMPLATE/下划线前缀模板文件 | `agent_engineering/SKILL.md`（Step 2 确定性校验）+ `generated_conformance.yaml`（effects 必填）+ `core/apps/skills/registry.py`（seed_for_platform effects 透传 + TEMPLATE 跳过）+ `core/tests/unit/test_skill_routing_e2e.py` | 生成物注册被静默拒 / 校验不可执行 / 模板误注册 |
| 24 | workspace agent（~/.aiplat/agents/）**AGENT.md 规范符合度**（2026-08-26 治理）：① 输出格式/反模式唯一归属 SKILL.md（AGENT.md 只留引用——qa/test_executor/frontend/backend 已去重，模板迁入 test_case_generation/test_executor/app_page_generation/code_generation SKILL.md）② 交接协议 5 字段完整（做了什么/产出物/如何验证/已知问题/下一步）③ 行数 ≤100（超限拆分 docs/，qa_agent 242→87、backend 158→76）④ 禁止 model 硬编码（§12，7 个 agent 已删，走 skill_model_purpose 路由） | workspace agents（运行时配置）+ `aiPlat-core/core/engine/skills/*/SKILL.md`（格式归属）| 输出格式双份漂移 / 交接断裂 / 模型硬编码违反 §12 |
| 25 | workspace agent 符合度**机器门禁**（2026-08-26）：`agent_conformance.py` 断言 AGENT.md 行数≤100 / 无 model 硬编码 / 交接 5 字段 / 输出格式归属 SKILL.md；`architecture_guard.sh §96` ratchet 模式（存量违规入基线容忍、新增违规阻断——同 ruff F821 先例）；基线 `scripts/baselines/agent_conformance_baseline.json`（49 个存量 agent 违规快照，治理一批更新一批） | `aiPlat-platform/builder/agent_conformance.py` + `scripts/architecture_guard.sh §96` + `scripts/baselines/agent_conformance_baseline.json` + `tests/test_agent_conformance.py` | workspace agent 规范漂移无门禁复发 |
| 26 | 评测观测端点 **`GET /governance/eval-observability`**（HarnessEval 落地，2026-08-27）：只读聚合证据树（`AIPLAT_EVIDENCE_TREE_OUT`）+ 守卫路由 trace（`AIPLAT_GUARD_TRACE_OUT`）+ 经验状态（`AIPLAT_EXPERIENCE_FILE`）三评测产物为统一视图，供 Governance 面板"评测观测"区块消费；**无写操作、不涉及租户数据**，产物缺失返回空视图而非报错 | `aiPlat-platform/governance/eval_observability.py`（aggregate）+ `aiPlat-platform/api/rest/routes.py`（governance_eval_observability）+ `aiPlat-management/frontend/src/pages/Governance/index.tsx`（评测观测区块） | 评测决策（为什么过/挂、跳过了哪些检查）不可追溯 |
| 27 | 后台任务托管端点 **`/governance/jobs`**（prime-agent 断线续跑借鉴，2026-08-27）：`GET /governance/jobs`（列表）、`POST /governance/jobs`（启动 {name, command, cwd?}，新会话组脱离终端）、`GET /governance/jobs/{id}`（状态）、`GET /governance/jobs/{id}/output`（attach 输出尾部）、`POST /governance/jobs/{id}/kill`（连同会话组终止）；**命令为运维语义（shell 执行），仅限受信任调用方**，启动命令不校验参数注入面 | `aiPlat-platform/governance/daemon_jobs.py`（DaemonJobStore）+ `aiPlat-platform/api/rest/routes.py`（governance_jobs_*） | 长任务绑定终端，关闭即终止，进度/经验无法留存 |
| 28 | agent 消息总线端点 **`/governance/agents*`**（prime-agent agent_message.send 借鉴，2026-08-27）：`GET /governance/agents`（在线列表，pid 存活刷新心跳）、`POST /governance/agents/{id}/register|unregister`（上线/下线）、`POST /governance/agents/messages`（点对点发 {from, to, message}，**不经用户中转**）、`GET /governance/agents/{id}/messages?unread&mark_read`（收件箱）；**消息为 agent 间协作语义，不做内容校验**，仅限受信任调用方 | `aiPlat-platform/governance/agent_messages.py`（AgentMessageStore）+ `aiPlat-platform/api/rest/routes.py`（governance_agent_*） | 运行中 agent/任务无法直连互发，协作必经用户/主编排器中转 |
| 29 | 生成 app 运行时端点 **`/platform/builder/projects/{id}/runtime*`**（生成物侧接线，2026-08-27）：`POST .../runtime/launch`（detect 入口 → daemon_jobs 托管启动，派生端口 18000-18999 + 127.0.0.1 绑定）、`GET .../runtime`（daemon job 存活 + 端口 + 入口类型）、`POST .../runtime/stop`（kill 会话组 + 清理记录）、`POST .../runtime/smoke`（detect→launch→HTTP 健康探测→报告，keep_alive 可选）、`POST .../runtime/real-tests`（**测试经理真实测试**：递归发现生成物测试用例 backend/tests/ 等任意层级 test_*.py → 可写临时目录跑 pytest（装依赖 + PYTHONPATH + conftest）→ test_report（header/meta/test_results/bug_summary，对齐 test_executor；失败分类 env/配置/实现 + suggested_fix））、`POST .../runtime/auto-repair`（**自动修复闭环**：真实测试失败 → LLM（经 CoreFacade llm_generate）按测试输出修复生成代码 → 临时区验证 → 改进才写回部署目录（_sync_repair_writeback，路径段匹配防逃逸）→ 重跑，最多 max_rounds 轮）、`GET .../last-test-report`（最近一次真实测试报告持久化 last_test_report 读取，未测试返回 200 `status=empty`，禁止 404 以免列表 N+1 刷控制台）；**运行范围限制在 `AIPLAT_HOME/apps/{project_id}/current` 白名单入口（FastAPI/Flask/Node/静态页 http.server），不执行任意命令；LLM 修复仅作用于部署目录内生成代码（abspath 前缀校验防路径逃逸）**；`POST /projects/{id}/test` 的 e2e_smoke 从"目录存在"升级为真实冒烟 + repo_tests 从"仅根目录 tests/"升级为递归真实测试 + 结果持久化；管理端 ProjectDetailPage 提供运行时控制（启动/停止/自动修复）+ 测试报告 bug 清单/修复建议展示 | `aiPlat-platform/builder/app_runtime.py`（detect_runtime/launch/health_check/stop/smoke_test/real_tests/auto_repair）+ `aiPlat-platform/api/routers/builder.py`（7 端点）+ `aiPlat-platform/builder/builder_project_service.py`（runtime_* + run_tests 升级 + last_test_report）+ `aiPlat-management/frontend/src/pages/App/Builder/ProjectDetailPage.tsx` | 生成 app 无运行能力 → 无法自动测试（e2e_smoke 假通过），生成物"死产物" |
| 30 | **Builder PRD 域质量门禁**（2026-09）：Harness 仅解释 YAML pack（`prd_gate_packs/_common` + `workspace_seeds/prd_gates/*` + `~/.aiplat/prd_gates`）；生成前 `format_pm_gate_guidance` 注入 `pm_hints`；`factory_finalize_prd` 做 enrich/scrub，语义矛盾（`block_finalize_wash`）不可仅靠洗绿放行，须 `structural_repairs` 整段改写 FR/US 后复检通过才 READY。Platform Builder 对话/`_extract_prd_from_chat`/`confirm_prd` 经 CoreFacade 消费，**不在 platform 内重实现门禁逻辑** | `aiPlat-core/core/harness/execution/prd_quality_gate.py` + `prd_gate_loader.py` + `workspace_seeds/prd_gates/media.yaml` + `aiPlat-platform/builder/builder_project_service.py` + `aiPlat-platform/api/routers/builder.py` | 媒体等垂直域 PRD 自相矛盾（如不转写却承诺主题摘要）被静默定稿 |
| 31 | **契约化多 Agent 门禁**（2026-09，2026-10 人话补强）：生成默认 `mode: single`；`multi_agent` 必须五条 AND（rationale/success_metrics/upgrade_criteria）经 `validate_manifest` 机器拒绝；工厂阶段 `allow_dynamic_spawn=False` + `spawn_policy` 阻断自由 spawn/`sys_agent_call`；`execute_skill` 经 `skill_hop_gate` 校验 `input_schema`；hop JSONL + `promotion_gate` 四维「跑通」（N≥20 / failed_stage / conformance·real_tests 物理证据 / PolicyGate）；`GET /platform/builder/projects/{id}/promotion` 只读快照；`agent_messages` **仅身份/通知层**，不替代 Pipeline handoff / schema 门 / HITL。**Harness 选型边界（强制）**：生成入口（`agent_engineering` / builder prompts / AddAgentModal）只选内部 `agent_type`/`architecture_profile`/`mode`，**禁止**在 LangGraph/CrewAI/AutoGen/LangChain 等外部框架间选型；运行时固定原生 StageRunner→ReActLoop/Pipeline。**门禁可读性**：`evaluate_multi_agent_upgrade` 失败须附 `summary`/`how_to_fix`/`next_actions`（`format_upgrade_fix_hint`），部署 `rejected_artifacts` 与 promotion 快照可读 | `agent_engineering/SKILL.md` + `core/apps/builder/prompts` + `AddAgentModal`/`AssetBoundaryHint` + `generated_conformance.py` + `spawn_policy.py` + `skill_hop_gate.py` + `hop_metrics.py` + `promotion_gate.py`/`promotion_gate.yaml` + `api/routers/builder.py` | 无门控自由多 Agent / 假「跑通」晋升 / 消息总线冒充协同主路径 / 外部框架选型幻觉 / 门禁失败不可行动 |
| 32 | **媒体 true_test PRD 词表对齐**（2026-09）：`media_skill_handlers` 对 FR 考卷输出 `status=queued`（创建）/`error_code=DOWNLOAD_FAILED`/`source_type=url\|upload`/`skipped_reason=NO_AUDIO_TRACK\|NO_SOFT_SUBTITLE_TRACK`/`start_ms`/`end_ms`，以及 `language_estimate`/`emotion_tendency`/`ANALYSIS_FAILED`/`label`/`category`/`highlight`/`no_soft_subtitle_track`；报告顶层 `transcription`/`vision`；软字幕缺失保持 `completed`、显式 skip 才 `completed_with_skips`；`audio_ref`/`video_ref` remap；`report_json_export` 在 `skipped_stages` 时输出 `status=completed_with_skips` + `skip_reason`；`status_in`/`modules.status`/`track_type`/`objects`/`actions` 词表对齐；`true_test_runtime` 同义词表兜底；**Factory「一键修复」不改平台 handler 词表**（仅 remap 技能名 / regenerate regenerate）——媒体测真失败须修 harness handler 或重跑测真 | `media_skill_handlers.py` + `media_ops.remap_fixture_path` + `true_test_runtime._CONTAINS_SYNONYMS` + `test_media_skill_handlers_vocab.py` | VideoSense 等媒体生成物 50% 假失败 / 一键修复空转 |
| 33 | **可执行本体收尾**（2026-09）：运行时权威为域 YAML(TBox)+GraphIndex(ABox)+Action L1（**非** OWL/HermiT 运行时）；路径 B `POST .../graph/import` + `.../graph/webhook/{source_id}` + table_map CSV；ABox ACL（`graph_abox_acl` / `X-AIPLAT-ACTOR-ROLE`）；推理仅建议层经 `assert_inferred_*` Action；多域种子 it-ops/retail-ops/data-gov + connector 模板；离线 OWL 审稿禁假绿；契约见 `docs/contracts/ONTOLOGY_EXECUTABLE_MODEL.md` | `abox_connector.py` + `graph_abox_acl.py` + `action_routes.py` + `ontology_pillars.py` + `offline_owl_review.py` + `workspace_seeds/ontologies/*` | 路径 B/ACL/多域演示与契约不同步；假绿 OWL |
| 34 | **Harness closeout 横切评测与记忆**（2026-10）：Code Review Gold（租户黄金 PR × autoreview → P/R/P0，`POST /api/platform/apps/code-review-gold/*`）+ org harness Amdahl/HITL 聚合（Governance 只读）+ Session Wiki / IDE→Team Brain 捕获（opt-in env）；**不改变**鉴权签发权威（仍仅 platform JWT/API key）。platform `api/rest/routes.py` / `memory_import` 增量仅为治理观测与记忆导入薄代理，须经 CoreFacade，禁止平行评测/记忆实现 | `code_review_gold.py` + `org_harness_metrics.py` + `session_wiki.py` + `ide_capture.py` + `team_brain.py` + `aiPlat-platform/apps/eval/api/code_review_gold.py` + Governance UI | 黄金集与组织串行比不可观测；IDE 会话经验无法入 Team Brain |
| 35 | **物理合入闸门 P0**（2026-10）：合入时（CI/pre-commit）通胀门 + 形态门否决智能体代码通胀——净增行/文件/新依赖/新类/新目录阈值 + 禁 `generic`/`framework`/`EventBus`/过深继承；`mode: warn` → `block_after`（默认 **2026-10-25**）升级；**豁免即负债**：必须 `owner` + `reason` + `expires`，`max_active_exemptions`（默认 3）超限不生效，YAML 残留过期/非法项 → debt finding + 值班板 `merge_gates=block`；`profile_neutral_globs`（CAPABILITIES/docs/registry）不参与 business/framework 选型（仍计入通胀）。**≠** 运行时入口快速失败（框架/模板），**≠** PolicyGate 权限检查。配置：`workspace_seeds/org/physical_merge_gates.yaml`（env/`$AIPLAT_HOME/org` 可覆盖）；入口：`scripts/check_physical_merge_gates.py` + `CoreFacade.evaluate_physical_merge_gates` / `assess_exemption_debt` | `physical_merge_gates.py` + `check_physical_merge_gates.py` + contracts-guard / pre-commit + `test_physical_merge_gates.py` | 零成本生成击穿人工复审；样板/深继承/事件总线堆进主分支；文档同步误逼 business 阈值；豁免静默后门 |
| 36 | **可测性闸门 P1**（2026-10）：核心 `handler.py` 必须有纯函数/无状态单元测（含 assert；禁 DB/网络/消息队列）；`@pytest.mark.integration` 或 impure 测试**不算完成**。接线：`done_verify.require_testability`（编码 stage 默认开）+ 合入脚本同跑 `testability_gate`（从磁盘补齐已有测试）；`mode: warn` → `block_after`（默认 **2026-11-01**）。配置：`workspace_seeds/org/testability_gate.yaml`。**采集**：`collect_files_from_context` 须从 stage 产物/`## FILE:` 块抽取（经 `factory_bloat_metrics`），**禁止**仅依赖空 `_written_files` 导致 done_verify 空转放行。**llm skill 路径**：`gate_llm_file_output_stage` 在 `_run_stage_skill` 落盘前跑同一 done_verify（`review_gate` 跳过；peer-review 须 agent backend）。**工作区 Execute**：`inject_workspace_coding_defaults`（`uses_file_output` 技能 / `coding_closed_loop` / `coding_intensity`）对齐工厂闭环 | `testability_gate.py` + `done_verify.py` + `gate_llm_file_output_stage` + `schemas_builder.apply_coding_stage_defaults` / `inject_workspace_coding_defaults` + `check_physical_merge_gates.py` + `test_testability_gate.py` + `test_gate_llm_file_output.py` + `test_workspace_coding_defaults.py` | 全栈才测得动的黑盒胶水；integration-only 冒充完成；有产物无路径时闸门失效；llm oneshot 绕过 ReActLoop 空 DONE 落盘；工作区手改绕过工厂 defaults |
| 37 | **治理闭环补齐**（2026-10）：① Gold JSONL → `gold_regression.trend` / `trend_summary`（值班板一等字段，禁假绿）；② `duty_board.yaml` playbook（go/watch/block/unavailable 固定动作）；③ FE proxy 从 `registry/apps.yaml` `api_prefix` + `proxy_prefixes` 生成 platform:8003 路由（禁手写 pin 漂移，#226） | `org_harness_metrics.py` + `duty_board.yaml` + Governance UI + `proxy_server._apps_yaml_platform_routes` + `apps.yaml` | 有传感器无趋势/无剧本；代理 pin 与模块注册脱节 |
| 38 | **合入闸门姿态上值班板**（2026-10）：`collect_merge_gates_posture` 暴露 physical/testability 的 `mode`/`block_after`/活跃豁免；豁免**必须**在值班板可见（禁静默后门）；活跃豁免或 warn→block≤14d → checks.merge_gates=watch；形态 AST 扫描覆盖变更文件（不只新增路径） | `org_harness_metrics.collect_merge_gates_posture` + `build_duty_board` + Governance UI + `physical_merge_gates` AST | 豁免成后门；warn 迁移期不可见 |
| 39 | **Evidence Envelope（诚实结论信封）**（2026-10）：结论/发现必须带 `status`/`confidence`/`evidence[]`/`limitations`/`next_check`；**confirmed ⇒ measured + 非空 evidence**（否则 demote→suspected）；**release block ⇒ measured + 非空 limitations**；derived→最多 watch，speculative→backlog，不可单独拦发布。**反形式主义**：`compact_evidence` 去重+高信号采样（默认 cap=8）；`mode=reject` / `assert_envelope_integrity` 对非法 confirmed/block **硬拒**（`ok=False`，仍返回安全 demote 信封）；`attach_envelopes_to_issues(reject_fake=True)` 标记 `envelope_integrity_rejected`；summary/`autoreview` 暴露 `integrity_ok`。接线：`evidence_envelope.py` + autoreview `ReviewReport.build_evidence`/`to_dict` + `CoreFacade.validate_evidence_envelope` / `attach_evidence_envelopes` / `assert_evidence_envelope_integrity` / `allow_evidence_release_block` / `fold_findings_for_duty` + experience_feedback register 强制信封。**值班板**：`payload.findings` 经 `fold_findings_for_duty`；gold BLOCK 经 `envelope_for_gold_block` + `gate_duty_status_with_envelopes`；无 `allow_release_block` → demote watch；Governance 展示信封摘要。LLM 静态审查默认 confidence=derived，禁止自动 confirmed | `evidence_envelope.py` + `org_harness_metrics.build_duty_board` + experience_feedback + Governance UI + `review_report.py` + `core_facade.py` + `test_evidence_envelope.py` + `test_org_harness_metrics.py` + `test_experience_feedback.py` | 无证据「confirmed」假绿；非法信封仅静默 demote；证据列表通胀淹没审查；推测性结论冒充发布门禁 |
| 40 | **门禁元评估 + 豁免负债**（2026-10）：合入闸门本身须被校准——JSONL（`run`/`skip`/`appeal`）窗口率驱动值班板 watch/block；低样本→unavailable（禁发明绿）；豁免须 `owner`+`reason`+`expires`+cap，过期/非法项为 debt；`SKIP_*` 经 `record_gate_meta` 记账非静默。接线：`gate_meta_eval.py` + `record_gate_meta.py` + `check_physical_merge_gates` persist + pre-commit skip 记账 + `collect_merge_gates_posture.gate_meta`/`exemption_debt` + `envelope_for_gate_meta_block` / `envelope_for_exemption_debt_block` + Governance | `gate_meta_eval.py` + `physical_merge_gates.assess_exemption_debt` + `org_harness_metrics` + `duty_board.yaml` 阈值 + `test_gate_meta_eval.py` | 闸门变流程装饰；豁免/SKIP 静默后门；阈值无反馈环 |
| 41 | **合入后仓库健康扫描**（2026-10）：合入闸门只看 diff；全树周度/按需扫描（LOC/god files/multi-base/import fan-out/declared deps）写入 `org/repo_health` JSONL；绝对阈值 + Δloc/Δdeps 驱动值班板 `repo_health` go/watch/block；无快照→unavailable（禁发明绿）。接线：`repo_health_scan.py` + `scripts/scan_repo_health.py` + `collect_merge_gates_posture.repo_health` + `envelope_for_repo_health_block` + `CoreFacade.assess_repo_health` / `scan_repo_health` + `duty_board.yaml` + Governance + **cron `repo_health_weekly`**（`register_builtin_jobs`，默认 168h，`AIPLAT_ENABLE_REPO_HEALTH_CRON` / `AIPLAT_REPO_HEALTH_CRON_HOURS`）+ **值班板 CTA** `POST /governance/repo-health/scan`（vite/proxy `/api/governance`→platform 前缀，timeout 600s） | `repo_health_scan.py` + `cron.py` + `org_harness_metrics` + `evidence_envelope.py` + `test_repo_health_scan.py` + `test_proxy_rewrite` repo-health + golden_path cron 断言 | 温水煮青蛙式膨胀在合入后不可见；仅靠 diff 闸门漏累积债；有扫描无周期调度 / 无值班板一键入口 |
| 42 | **执行决策矩阵闭环**（2026-10）：Living Spec **v1.9**——完整 Stage×Skill 组合矩阵；未知类型默认 fail closed；E5 FAIL_OPEN 治理+健康告警/24h 过期提醒；handler/hybrid 先于 backend；路径卡含 `hybrid_semantics`+`stage_id`/`skill_name`/`handler_present`/`fail_closed_reason`；E1/E2 工厂；E4/O1 成本阶梯证明质量；O2 YAML 漂移 lint（可选）；O3 Eval/Memory 接口契约 §6.1 | `execution_type_policy.py` + `decision_trace.py` + `generated_conformance` + `lint_engine_skills.py` + `check_cost_ladder.py` + `lint_team_yaml_profile_drift.py` + living spec | 拼写错误静默走 LLM；handler 被绕过；组合/边界不清；工厂意图不可控；跳级 MCP/Syscall；形式化 ladder-ok |
| 43 | **Platform Approvals 懒加载 ExecutionStore/ApprovalManager**（2026-10）：`GET/POST /platform/approvals*` 在无 KernelRuntime 时须经 CoreFacade `get_execution_store` + `ApprovalManager(...)` 懒建，**禁止**因 platform 进程未挂 runtime 而固定 503（否则 Pi hybrid / 管理端只能绕到 `/api/core/approvals`）。鉴权仍走 platform `require_auth`；权限裁决不在 router 内重实现。**不改变** JWT/API key 签发权威 | `aiPlat-platform/api/routers/approvals.py`（`_store`/`_approval_mgr`）+ `test_approvals_lazy_store.py` + Pi `enterprise_approval` / hybrid live smoke | Platform 审批列表假死；混合回连被迫双路径 |
| 44 | **工厂运行可观测面板「跑到哪 / 为何卡」**（2026-10）：失败/HITL/完成时聚合 `_current_stage`/`_hitl_stage_id` + handoff.next/known_issues + promotion `next_actions`/hop；一键续跑（`POST .../resume/{stage_id}`，保留产物）或从此阶段重建；**无新后端**；阶段 ID 解析须与 Core resume/regenerate 一致（优先 `_hitl_stage_id`，兼容 id/agent_id/output_artifact，失败可回落 hop `by_failed_stage`） | `Factory/runObsSnapshot.ts` + `index.tsx` + `builderTeamApi.resumeFromStage`/`getPromotion` + acceptance 1.70 | 失败后不知卡在哪/下一步；续跑 stage_id 错位 |
| 45 | **工厂列表卡为何卡短提示**（2026-10）：列表 `failed`/HITL 软聚合 promotion+state → `formatCardStuckHint` 截断行；不阻断列表；无新后端 | `Factory/index.tsx` `projectStuckHints` + `formatCardStuckHint` + acceptance 1.71 | 列表只见「执行失败」无下一步 |
| 46 | **工厂 pageData 卡顿样本**（2026-10）：`reportPageData('/app/factory')` 上报 `failed`/`awaitingApproval`/`stuckHintCount` + 最多 3 条 `stuckHints`，供数字人答「哪些项目卡住」；无新后端 | `Factory/index.tsx` pageData + acceptance 1.72 | 数字人只知项目数不知卡顿原因 |
| 47 | **Agent RACI 责任边界**（2026-10）：创建时可选 `raci` 写入 AGENT.md；边界提示缺省提醒；**非运行时门禁**；升 multi 仍五条 AND；责任单元叙事（闭环优先单 Agent） | `boundary_hints.normalize_raci` + `AgentManager` + AddAgentModal/AssetBoundaryHint + `agent_engineering` Step 0 + acceptance 1.73 | 先拆多 Agent 再补责任；为拆而拆 |
| 48 | **LLM response_format 硬解码透传**（2026-10）：`json_schema`/`json_object` 从 Pipeline/`sys_llm_generate` 经 `LLMConfig`→`InfraLLMAdapter`→`ChatRequest`→OpenAI 兼容 provider 下传，解码期硬约束；未设不传 | `LLMConfig` + `infra_llm_adapter` + `ChatRequest` + `openai_compatible` + acceptance 1.74 | Schema 在 pipeline 组装后被 adapter/infra 丢弃，结构化输出只靠 Prompt |
| 49 | **Skill/Pipeline output_schema → response_format**（2026-10）：`build_llm_response_format` 统一组 schema；prompt Skill `output_schema` 与 Pipeline `llm_output_schema` 自动硬解码；kill-switch `AIPLAT_LLM_RESPONSE_FORMAT=0`；ReAct+tools 仍 parse | `json_utils.build_llm_response_format` + `skills/registry` + `pipeline_engine` + acceptance 1.75 | 有 schema 声明仍只靠 Prompt 劝 JSON |
| 50 | **对话创建 JSON 提取收敛**（2026-10）：`extract_json_object` → `parse_json`/`extract_json_safe`；Agent/Skill create-dialog 去掉本地 `_extract_json` | `create_dialog_utils` + agent/skill create_dialog + acceptance 1.76 | 清洗正则碎片化，fence/尾随解说偶发解析失败 |
| 51 | **LLM JSON 容忍解析收敛**（2026-10）：`parse_json` 含确定性修复（尾逗号/Python bool·None/单引号值）；true_test / workspace auto-fill 委托同一入口 | `json_utils.parse_json` + `true_test_runtime` + `workspace_agents` + acceptance 1.77 | 分散 bracket-fallback；尾逗号/True 致解析失败 |
| 53 | **Sticky / session-archive 记忆租户隔离**（2026-10）：`GET/POST /platform/memory/sticky` 与 `GET /platform/memory/archive` 须 `require_auth`，租户来自 `X-AIPLAT-TENANT-ID`（缺省 `default`），经 CoreFacade 传入 `tenant_id`（及 archive 的 `session_id`）；**禁止**跨租户读写 pinned MEMORY.md / archives。鉴权签发权威仍仅 platform JWT/API key | `aiPlat-platform/api/routers/memory_import.py` + `core_facade.sticky_memory_slice` / `upsert_pinned_memory` / `query_session_archive` + `file_store` tenant dirs + `test_review_known_defects.py` | sticky/archive 串租；作者回执式假绿掩盖隔离缺口 |
| 54 | **编码环路与交付否决**（2026-10）：`StageRunner.resolve_stage_loop_type` 须尊重显式 `architecture_profile=plan_execute`；仅 `done_verify.require_review` 强制回落 ReAct（PlanExecute 可封口但不自动派 autoreview）。`uses_file_output` **不得**再覆盖 `plan_execute`。`coding_deliverable_veto` 次数耗尽后：默认软封口（交给 quality_review 判阶段失败）；`AIPLAT_PROFILE=production` 或 `AIPLAT_CODING_VETO_FAIL_CLOSED` 继续否决、禁止未完成绿；`AIPLAT_CODING_VETO_FAIL_OPEN` 可覆盖为软封口 | `stage_runner.resolve_stage_loop_type` + `execution_seal.coding_deliverable_veto` + `test_coding_deliverable_veto.py` + `test_review_known_defects.py` | file-output 阶段无视 plan_execute；否决耗尽后生产环境未完成仍绿 |
| 55 | **完成回执与 LLM 熔断半开**（2026-10）：`infer_receipt_status` 须把 `approval_required`、`aiplat_tool_execute_approval_required`、`aiplat_approval_wait_denied`、`aiplat_unattended_wait_denied`、`handler_missing`、`invalid_skill_name` 记为 failed，禁止待审批或否决回执支撑「已修好」。编译 ReAct reason/observe 与 facade reason finish-directly / observe 终止须走 `is_terminal_done_marker`（句首 DONE/FINAL/FINISHED；reason 路径用 `strip_terminal_done_marker` 去前缀），禁止 `"DONE" in text.upper()` / 仅 `startswith("DONE:")`。编译 ReAct `act` 与 facade 的工具步骤须用同一 seal 写回执：`success=False` 或失败前缀不得记 `ok`；无工具的 `Action:` / `No action` 不写回执。`CircuitBreaker` 与 LLM syscall 熔断在 `half_open` 只放行一个探测；`is_open` 只读、不得切入 half-open 放行；MCP `call_tool` 经 `allow()` 取探测，传输异常须 `record_failure`。分类错误路径必须 `record_failure` 清掉 `probe_in_flight`，否则半开永久占锁 | `completion_receipt.infer_receipt_status` + `compiled_graphs/react.py` + `loop/_facade.py` + `infrastructure/circuit_breaker.py` + `syscalls/llm.py` + `apps/mcp/client.py` + `test_completion_receipt.py` + `test_review_known_defects.py` + `test_circuit_half_open.py` | 待审批被当成成功回执；编译图工具失败仍 success=True；半开探测失败后熔断不再放行；MCP 冷却后并发打满 |
| 56 | **评测裁决句首 token**（2026-10）：tri_agent evaluator、reflection critic、producer–reviewer 禁止 `"APPROVED"/"PASS"/"YES" in text` 中段子串。须走 `eval_verdict.is_approved_evaluation`（句首 APPROVED；句首 REJECTED 否决）、`is_pass_keyword_verdict`（`STATUS:` 行优先，否则句首 pass keyword；`BYPASS`/`NOT APPROVED` 不得假绿）、`is_yes_review`（句首 YES；句首 NO / 中段 YES 否决）。模型指纹 logic 探针同样禁止 `"yes" in text` / `"是的" in text` / `"shorter" in text`：只认句首 YES/NO（可带标点）或句首 是的/是/对、不是/不对/否。完成度评估 `_llm_completion_evaluate` 禁止 `"COMPLETE" in text`：JSON `complete` 字段优先（`false` 不得因键名通过），否则只认句首 COMPLETE（`INCOMPLETE` / `NOT COMPLETE` / `COMPLETELY` / 中段 COMPLETE 否决）。任务连续性 `_llm_decide` 禁止 `"SAME" in text`：JSON `same_task` 字段优先（`false` 不得因键名判为同一任务），否则只认句首 SAME（句首 NEW / 中段 SAME / `SAMENESS` 否决） | `eval_verdict.py` + `langgraph/graphs/tri_agent.py` + `langgraph/graphs/reflection.py` + `coordination/patterns/base.py` + `knowledge/model_fingerprint.py` + `loop/_facade.py` + `loop/target_continuity.py` + `test_eval_verdict.py` + `test_model_fingerprint_logic.py` | NOT APPROVED / BYPASS / 中段 YES / yesterday / 不是的 / `{"complete":false}` / `{"same_task":false}` 被当成通过 |
| 57 | **ACTION/SKILL 行首标记**（2026-10）：`parse_tool_call` / `parse_action_call` 与 compiled ReAct `_parse_action_from_text` 禁止 `"ACTION:" in text.upper()` / `"SKILL:" in text.upper()` 中段子串。须走行首（可缩进）`ACTION:` / `SKILL:`；`INACTION:` / `RETRACTION:` / `FRACTION:` / `UPSKILL:` / 行内 `No ACTION:` 不得触发假工具调用 | `tool_calling.line_marker_content_start` + `compiled_graphs/react.py` + `test_tool_calling.py` | INACTION/RETRACTION 被解析成工具名 |
| 59 | **Platform 身份不可伪造**（2026-10）：`X-AIPLAT-TENANT-ID` + `X-AIPLAT-ACTOR-ID` 不是凭据。仅 `AIPLAT_PLATFORM_DEV_MODE` 或 `X-AIPLAT-IDENTITY-SECRET` 匹配 `AIPLAT_PLATFORM_IDENTITY_SECRET` 时才采纳 header 身份。JWT 验签失败返回 401，禁止回落未验签 payload。`POST /platform/gateway/execute` 与 `POST /api/v1/agents/{id}/execute` 拒绝 `auth_type=anonymous`（dev mode 除外）。已配置 Redis 的限流在连接/执行失败时拒绝请求。已配置配额上的未知资源名拒绝 | `auth/request_identity.py` + `api/rest/routes.py` + `governance/rate_limit/limiter.py` + `governance/quota/quota_manager.py` + `test_platform_identity_spoof.py` | 请求头冒充 admin；坏签名 JWT 仍登录；匿名执行；Redis 故障无限流 |
| 62 | **管理端前端不伪造身份**（2026-10）：请求头只来自已写入的 `localStorage`（`storedIdentityHeaders`）。缺省不得发送 `X-AIPLAT-ACTOR-ID/ROLE=admin`、`X-AIPLAT-SCOPES=kb:read,kb:write` 或 `X-AIPLAT-API-KEY=apl_dev_local`。Step-Run 不得写死 `X-AIPLAT-ACTOR-ROLE: admin` | `frontend/src/services/identityHeaders.ts` + `apiClient.ts` + `kbApi.ts` + `UploadModal.tsx` + `WorkflowCanvas/index.tsx` + `identityHeaders.test.ts` | 打开页面即冒充 admin 并带开发用 API key |
| 63 | **Slack KB webhook 与 widget XSS**（2026-10）：`POST /platform/kb/slack/query` 须先 `require_slack_request`（`AIPLAT_SLACK_SIGNING_SECRET` HMAC；缺密钥失败关闭，仅 `AIPLAT_CHANNEL_ALLOW_UNSIGNED=1` 放行）。KB widget 回答经 `esc()`/`textContent`，禁止把 `j.answer` 直接拼进 `innerHTML`。ResultDashboard markdown 须转义 `&<>"` | `auth/slack_signature.py` + `api/routers/kb_integration.py` + `ResultDashboard.tsx` + `test_kb_slack_signature.py` | 未签名 Slack 请求触发 KB/LLM；回答脚本注入宿主页 |
| 64 | **Gateway 执行默认鉴权**（2026-10）：`POST …/gateway/execute` 与 `…/gateway/webhook/message` 默认要求 `X-AiPlat-Gateway-Token`（`AIPLAT_GATEWAY_TOKEN` 或 store `validate_gateway_token`）。`AIPLAT_GATEWAY_REQUIRE_AUTH` 默认 `true`；仅 `AIPLAT_GATEWAY_ALLOW_UNSIGNED` 或 `AIPLAT_PLATFORM_DEV_MODE` 可跳过。管理类 pairing/token 路由须 `AIPLAT_GATEWAY_ADMIN_TOKEN`（未配置返回 503，禁止无 token 开放）。`routes.py` 代理入口同样走 `require_gateway_execute_auth` | `auth/gateway_auth.py` + `api/routers/gateway.py` + `api/rest/routes.py` + `test_gateway_require_auth.py` | 未带 token 的任意 body 触发 gateway 执行 |
| 65 | **Wiki loop webhook 默认鉴权**（2026-10）：`POST /wiki/loop/webhook` 与 `/wiki/loop/triggers*` 默认要求 `X-AiPlat-Wiki-Loop-Token`（`AIPLAT_WIKI_LOOP_WEBHOOK_TOKEN`，缺省回落 `AIPLAT_API_KEY` / `X-AIPLAT-API-KEY`）。`AIPLAT_WIKI_LOOP_REQUIRE_AUTH` 默认 `true`；仅 `AIPLAT_WIKI_LOOP_ALLOW_UNSIGNED` 可跳过。禁止未鉴权注册触发器或启动流水线 | `core/api/wiki_loop_auth.py` + `routers/wiki_loop_triggers.py` + `test_wiki_loop_auth.py` | 未带 token 的任意 webhook body 启动 pipeline |
| 66 | **Studio 应用注册默认鉴权**（2026-10）：`POST /platform/apps/register-from-studio` 默认要求 `X-AiPlat-Studio-Register-Token`（`AIPLAT_STUDIO_REGISTER_TOKEN`，缺省回落 `AIPLAT_API_KEY`）。`AIPLAT_STUDIO_REGISTER_REQUIRE_AUTH` 默认 `true`；仅 `AIPLAT_STUDIO_REGISTER_ALLOW_UNSIGNED` 可跳过。管理端 studio 部署回调须带同一 token | `auth/studio_register_auth.py` + `api/routers/apps.py` + `management/api/studio.py` + `test_studio_register_auth.py` | 未带 token 的任意 body 向平台注册应用 |
| 61 | **App 静态托管与渠道验签**（2026-10）：会话文件须落在 `apps/{id}/current` 内（`session_file_under_root`），`../` 与非法 `project_id` 不得读出目录。默认绑 `127.0.0.1`；非 loopback 无 `AIPLAT_APP_API_TOKEN` 拒绝启动。token 配置后除 `GET /health` 外须 Bearer 或 `X-AIPLAT-APP-TOKEN`。Docker 发布端口须 `AIPLAT_APP_BIND=0.0.0.0:8004` 且配置 token。Telegram/Slack 未配置 secret 时验签失败，仅 `AIPLAT_CHANNEL_ALLOW_UNSIGNED=1` 放行。`APIClient` 空 `base_url` 使用 `AIPLAT_PLATFORM_URL` | `api/auth.py` + `api/rest/routes.py` + `gunicorn.conf.py` + `channels/telegram.py` + `channels/slack.py` + `services/client.py` + `test_app_session_path.py` | `../` 读出 app 目录；`0.0.0.0` 无 token；缺 secret 的 webhook 验签通过；平台 URL 被空字符串覆盖 |
| 60 | **Management 管理面鉴权**（2026-10）：管理 API 默认绑 `127.0.0.1`；非 loopback 无 `AIPLAT_MANAGEMENT_API_TOKEN`（或 `AIPLAT_MANAGEMENT_API_KEY`）拒绝启动（`run_server` 与 gunicorn）。Docker 发布端口须 `AIPLAT_MANAGEMENT_BIND=0.0.0.0:8000` 且配置 token（compose 已设；`GET /health` 仍免 token）。token 配置后除 `GET /health` 外须 Bearer 或 `X-AIPLAT-MANAGEMENT-TOKEN`。`AIPLAT_MANAGEMENT_REQUIRE_AUTH=1` 且未配置 token 时返回 503。前端开发代理默认 `127.0.0.1` | `management/auth.py` + `management/server.py` + `gunicorn.conf.py` + `config/management.yaml` + `frontend/proxy_server.py` + `tests/test_management_auth.py` | 无鉴权的审批/仓库提交/渗透扫描/反向代理暴露在 `0.0.0.0` |
| 58 | **Infra 假成功**（2026-10）：管理 API 默认绑 `127.0.0.1`；非 loopback 无 `AIPLAT_INFRA_API_TOKEN` 拒绝启动；token 配置后除 `GET /health` 外须 Bearer / `X-AIPLAT-INFRA-TOKEN`。LLM 指标/成本为零且 `synthetic`，健康检查不得报 `api=connected`。K8s 分配失败不得返回 `k8s-pool` 成功单。GPU 内存无 NVML 时默认失败（`AIPLAT_MEMORY_SIMULATE=1` 才模拟）。GPU 检测失败记 0 卡。向量检索用余弦，禁止固定 `0.95`。`embed()` 用配置模型。embedding 连通性须路径存在；MinerU 仅 `returncode==0`。健康/延迟过滤异常 fail-closed。密钥轮换分类失败不得一律 rotatable。澄清质量评分关键词仅来自 `AIPLAT_CLARIFY_KEYWORDS`，禁止硬编码 FDE/业务词 | `management/api/auth.py` + `run_server.py` + `llm/manager.py` + `compute/manager.py` + `memory/manager.py` + `scheduler/manager.py` + `vector/manager.py` + `openai_compatible.py` + `health_checker.py` + `model/manager.py` + `quality_validator.py` + `test_infra_fake_success.py` | 无鉴权暴露写接口；虚构指标/分配/分数被当成真实；infra 渗入业务词 |
| 52 | **工具治理 Hard floors + RiskClass + Unattended Inbox + Auto-Approve Reviewer + Session Write Provenance**（2026-10，OpenWorker 启发）：`ApprovalGate` CRITICAL / shell 启发式（opaque、arg-executor、`-c`、`find -exec`）为 **hard floor**——`auto_approve`、session 批准、`AIPLAT_APPROVALS_DISABLED` **不可降低**（仅 `AIPLAT_HARD_FLOOR_DISABLED` 逃生）；工具 `RiskClass`（READ/EGRESS/WRITE_LOCAL/EXEC/EXTERNAL）覆盖只可加严；无人值守 `attendance=attended\|inbox\|auto` 经 `approval_inbox` 持久 park，`auto` **禁自批** hard floor；**P2 Reviewer**：`AIPLAT_APPROVAL_REVIEWER=1` + `_auto_approve` 时第二模型仅可将**非** hard-floor 的 ASK→ALLOW（fail-closed→unsure；禁读 body/密钥；熔断转人工；**不可解** hard floor）；**P3**：本会话 `sys_file_write`/`edit`/`FileOperationsTool` 写入路径登记于 `session_write_provenance`，后续 shell/code 执行该路径 → CRITICAL hard floor（防 agent 写后自跑）；`PolicyGate.check_tool` 返回 `inbox_item_id`/`approval_provenance`；platform `GET/POST /platform/approvals/unattended*` 经 CoreFacade，鉴权仍 `require_auth`，**禁止**在 router 内重做裁决。`sys_tool_call` 可透传 `_attendance`（trace / `AIPLAT_TOOL_ATTENDANCE`）；**任务语境闸门**（§0.3 P0）：`write_local`/`exec`/`external`/`egress` 在 Reviewer 可 ALLOW 前必须带 owner task（`_user_goal` 等；`sys_tool_call` 从 trace `user_goal|task|goal|owner_request` 或 `AIPLAT_USER_GOAL` 注入，截断 400）；缺失 → `missing_task_context`（不调 LLM，fail-closed）；`AIPLAT_REVIEWER_REQUIRE_TASK=0` 可关 | `approval_gate.py` + `risk_class.py` + `shell_command_risk.py` + `approval_inbox.py` + `approval_reviewer.py` + `session_write_provenance.py` + `policy_gate.py` + `file.py` + `tool.py` + `core_facade` unattended_* / `list_session_write_provenance` + `api/routers/approvals.py` + `test_openworker_governance_p0/p1/p2/p3.py` | auto 模式绕过高危；无人值守自批 shell；评审模型解 hard floor；同命令不同任务被无语境放行；agent 写脚本后自跑；审批无 provenance；platform 平行门禁 |

回归测试：`aiPlat-core/core/tests/unit/test_pipeline_eval_p1_fixes.py`（P1-2，2 项）+ `aiPlat-platform/tests/test_builder_p1_fixes.py`（P1-1/P1-3/P1-4/P1-8/P1-9/P1-11/P1-12/P1-13，21 项）+ `aiPlat-core/core/tests/unit/test_team_planner_p1_fixes.py`（P1-5，4 项）+ `aiPlat-core/core/tests/unit/test_pipeline_engine_p1b_fixes.py`（P1-6/P1-7，5 项）+ `aiPlat-core/core/tests/unit/test_harness/test_prd_quality_gate.py`（PRD 门禁）+ `test_spawn_policy.py` / `test_hop_metrics.py` / `test_skill_hop_gate.py`（多 Agent 门禁）+ `test_physical_merge_gates.py`（物理合入闸门）+ `test_testability_gate.py`（可测性闸门）+ `test_org_harness_metrics.py`（Gold 趋势/值班剧本/合入闸门姿态）+ `test_evidence_envelope.py`（Evidence Envelope）+ `test_gate_meta_eval.py`（门禁元评估）+ `test_repo_health_scan.py`（合入后仓库健康）+ `test_execution_type_policy.py`（执行决策矩阵闭环）。

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

