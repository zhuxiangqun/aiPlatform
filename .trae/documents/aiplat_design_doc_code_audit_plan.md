# aiPlat 设计文档与代码一致性审查（计划）

## Summary（目标与交付物）
本计划用于**仔细审查本仓库全部设计文档的正确性与完整性**（重点：整体架构与 Harness / Agent / Skill / Tool 设计），并核对**代码实现是否与设计文档一致**、是否存在**明显不合理实现**。  
交付物为一份**中文 Word（.docx）审查报告**，内容包括：结论摘要、问题清单（含证据与风险评级）、文档↔代码对照矩阵、以及可执行的修复建议与验证方法。

> 备注：本计划仅覆盖“审查与报告产出”。除非你后续明确要求修复，本次执行阶段不直接修改业务代码。

---

## Current State Analysis（基于仓库实证的现状）

### 代码与文档的主要分布
仓库包含多个子项目，其中与本次“架构/执行系统（Harness/Agent/Skill/Tool）”以及其运行依赖/边界契约最直接相关的是：
- `aiPlat-core/`：核心执行层与主要设计文档（docs）
- `aiPlat-management/`：管理/运营侧 API 与前端（其 docs 描述与 core 的边界/契约必须核对）
- `aiPlat-infra/`：基础设施抽象与实现（与 core 的 adapters/服务边界、配置与观测体系必须核对）
- 根目录 `docs/`：跨子项目的设计/规范汇总（需检查是否与各子项目 docs 发生漂移）

### “权威状态文档”与潜在自相矛盾风险
存在一份标记为“唯一真相来源”的实现状态文档：
- [View file](computer:///sessions/69df99acf22671cacf117ebb/workspace/aiPlat-core/docs/ARCHITECTURE_STATUS.md)

该文档对系统状态（✅/⚠️/🔧/❌/📝）进行了集中声明，适合作为审查的**索引入口**；但也出现了**同一主题在不同段落表述不一致**的风险（例如“Coordination 模式是否已接入并被调用”在不同表格/段落中存在冲突表述）。  
因此本次审查将对其进行**一致性复核**：把它当作“重要线索”，但仍以“文档原文 + 代码证据”最终落判。

### 已通过抽样确认的实现可疑点（将纳入审查清单）
以下点来自对关键文件的快速抽样阅读，属于“高价值起点”，但仍需在全面审查中验证其影响范围：
1) **Skill fork 模式疑似构造参数不匹配，可能运行即错**  
   - 证据：`SkillExecutor._execute_fork()` 直接以 `name/system` 方式构造 `ConversationalAgent`  
   - [View file](computer:///sessions/69df99acf22671cacf117ebb/workspace/aiPlat-core/core/apps/skills/executor.py)  
   - 对照：`ConversationalAgent.__init__(config: AgentConfig, ...)` 并提供 `create_conversational_agent()` 工厂  
   - [View file](computer:///sessions/69df99acf22671cacf117ebb/workspace/aiPlat-core/core/apps/agents/conversational.py)
2) **PermissionManager.grant_permission() 的数据结构写入可疑**  
   - 证据：同时写入 `self._permissions[key]` 与 `self._permissions[user_id]`，但 `check_permission()` 仅读取 `self._permissions[user_id][tool_name]`  
   - [View file](computer:///sessions/69df99acf22671cacf117ebb/workspace/aiPlat-core/core/apps/tools/permission.py)
3) **Skill 版本查询接口返回丢失配置**  
   - 证据：`GET /skills/{skill_id}/versions/{version}` 读取了 `registry.get_version()` 但返回 `{"config": {}}`  
   - [View file](computer:///sessions/69df99acf22671cacf117ebb/workspace/aiPlat-core/core/server.py)

---

## Proposed Changes（执行阶段将做什么）

### A. 建立“文档↔代码”可追溯审查清单（结构化数据）
**目标**：把所有设计声明变成可逐条核对的检查项（check items），并为每项填入代码证据与结论。  

**拟新增（最终产物）**
- `reports/audit_findings.json`（或 `.yaml`）：结构化问题清单与对照矩阵（便于复用与生成 docx）

**检查项统一字段（每条都必须可落到证据）**
- `id`：如 `HARN-EXEC-001`
- `source_doc`：设计文档路径 + 小节标题
- `design_statement`：可验证的一句话（“应当如此”）
- `code_evidence`：实现文件路径 + 关键函数/类/片段（必要时附行号或关键片段）
- `verdict`：✅一致 / ⚠️部分一致 / ❌不一致 / 📝仅文档 / 🔧结构未接通
- `issue_type`：契约不一致/桥接缺失/权限绕过/死代码/重复实现/错误处理缺口/测试缺失…
- `risk`：高/中/低（或 P0/P1/P2）
- `recommendation`：可执行修复建议（指向具体文件/接口）
- `verification`：验证方法（单测/接口调用/静态检查/手工步骤）

### B. 按 Harness / Agent / Skill / Tool 四条主线“逐条核对”
**目标**：覆盖你特别强调的整体架构与关键子系统设计，输出可复现、可落地的结论。

#### B1. Harness 审查
**文档输入（主审）**
- `aiPlat-core/docs/harness/*.md`（index/execution/interfaces/coordination/observability/security…）

**代码核对入口（主审）**
- `aiPlat-core/core/harness/`（尤其 interfaces、execution、approval/hook/monitor 相关）
- `aiPlat-core/core/server.py`（lifespan 注入与端到端执行链路）

**核对要点（必须落到检查项）**
- 层次结构/依赖方向是否符合文档：apps vs harness vs adapters 的边界、禁止反向依赖
- 接口契约是否可实现且签名一致：`AgentContext/SkillContext/ToolSchema/...`
- Loop 驱动是否真实落地：Agent 是否委托 BaseAgent / Loop，Hook/Approval 的挂载点是否存在且可触达
- Observability/Heartbeat 是否从“结构存在”变为“运行中”：启动路径是否真的启动 monitor
- Coordination patterns：是否“仅存在目录/类”还是“已接入并被调用”，并处理文档内部冲突表述

#### B2. Agent 审查
**文档输入**
- `aiPlat-core/docs/agents/*.md`

**代码核对入口**
- `aiPlat-core/core/apps/agents/`（base + 各具体 agent）
- `aiPlat-core/core/harness/interfaces/agent.py`

**核对要点**
- Agent 类型体系与工厂映射：文档列出的类型是否都可创建/可注册/可执行
- 生命周期/状态枚举：状态图与真实流转是否一致
- 注入策略：model/tools/skills 从 server/manager/registry 到 agent/loop 的链路是否闭环
- “实现不合理”专项：死代码、重复实现、override 破坏统一执行模型、对接口的滥用（如强耦合内部字段）

#### B3. Skill 审查
**文档输入**
- `aiPlat-core/docs/skills/*.md`

**代码核对入口**
- `aiPlat-core/core/apps/skills/`（registry/executor/base…）
- `aiPlat-core/core/management/skill_manager.py`
- `aiPlat-core/core/server.py`（Skill versions/execute 等端点）

**核对要点**
- Manager ↔ Registry 桥接是否覆盖 CRUD 全路径，是否存在“创建可见但不可执行”的断裂
- inline / fork 两模式是否能端到端执行；fork 是否复用 Agent 工厂或正确构造 AgentConfig
- SkillContext.tools 的注入语义是否一致（字符串名 vs Tool 实例；权限如何二次校验）
- 版本管理：版本数据是否可查询、可回滚、API 是否返回可用配置（当前已见返回空 config 的证据）
- 文档完整性：lifecycle/进化机制若为“仅文档”，需标注并建议文档降级/补齐或实现补齐

#### B4. Tool 审查
**文档输入**
- `aiPlat-core/docs/tools/*.md`

**代码核对入口**
- `aiPlat-core/core/apps/tools/`（base/registry/permission + 各工具）
- `aiPlat-core/core/server.py`（lifespan 注册清单）

**核对要点**
- ToolRegistry 的注册来源与启动时机：文档列举是否与实际注册一致（含 stub/桩工具的真实状态披露）
- 权限控制闭环：是否存在绕过点（例如 skill/agent 间接调用 tool 时是否仍能触发审批/权限）
- Schema/参数校验：是否与文档声明一致（required、类型、返回结构）
- 工程化：错误处理、超时、统计、审计日志是否可用且一致

#### B5. 跨项目架构边界审查（core ↔ infra ↔ management）
**目标**：审查“整体架构与模块边界”是否自洽：职责是否清晰、依赖方向是否正确、契约是否稳定且与实现一致，避免出现“文档边界 ≠ 代码依赖边界”的漂移。

**主要文档输入（至少覆盖）**
- `aiPlat-management/docs/architecture-boundary.md` 与 `aiPlat-management/docs/core/*.md`
- `aiPlat-infra/docs/index.md` 及关键分区（di/config/http/logging/monitoring/observability/mcp 等）
- 根目录 `docs/` 中与平台架构、测试、运行、治理相关的规范（若与子项目 docs 重复/冲突，需显式指出）

**代码核对入口**
- `aiPlat-infra/infra/`（各子系统的基类、factory、schemas、manager、utils、安全等）
- `aiPlat-management/management/`（core_client/infra_client、dashboard/diagnostics/monitoring 等对 core/infra 的依赖方式）
- `aiPlat-core/core/`（adapters/services/management 与 infra 的集成方式）

**核对要点（必须落到检查项）**
- 依赖方向：core 是否“只依赖 infra 的抽象”，还是反向耦合到 infra 的具体实现；management 是否通过稳定 client/adapter 调用 core/infra，而非直接穿透内部模块
- 配置边界：配置文件结构（yaml/json）在 docs 与 loader/manager 的真实结构是否一致
- 可观测性/日志/追踪：infra 的 tracing/logging 规范是否在 core/management 侧被实际使用（或明确为“仅文档”）
- API 契约：management 调用 core 的 API/数据结构是否与 core server/schemas 一致；是否存在未实现或返回结构漂移（例如版本/审计/执行记录字段）

### C. 生成中文 docx 审查报告（docx-js）
**目标**：把结构化 findings（JSON/YAML）渲染成可交付的 Word 文档。

**拟新增（最终产物）**
- `reports/aiPlat_设计文档与实现一致性审查报告.docx`

**实现约束（来自 docx Skill，执行阶段必须遵守）**
- 必须使用 JavaScript `docx`（docx-js）生成新 docx；不要用 Python/XML 模板拼装
- 必须只使用 **1 个 section**（避免空白页）
- 显式设置页大小与页边距（避免默认 A4/格式漂移）
- 中文必须配置 `eastAsia` 字体（如 Microsoft YaHei / Noto Sans CJK SC）
- 表格必须设置**table width** + **columnWidths** + **cell width**（双重宽度）以确保跨平台渲染一致

**建议报告结构**
1. 封面信息（仓库/版本/范围/方法）
2. 结论摘要（整体一致性评价、关键风险）
3. 问题总览（按风险排序的 Top Issues）
4. 文档↔代码对照矩阵（按 Harness/Agent/Skill/Tool 分类）
5. 分模块详查（每条含：设计声明、代码证据、判定、建议、验证）
6. 附录（接口清单、关键流程图引用、术语）

---

## Assumptions & Decisions（关键假设与已决策事项）
1) **交付格式**：输出为中文 `.docx` 报告（用户已确认）。  
2) **审查深度**：尽可能“逐条对照”（用户已确认），以检查项（check items）方式保证可追溯。  
3) **范围优先级**：整体架构与模块边界 + Harness/Agent/Skill/Tool 为最高优先级，其次是工程化与文档缺口（用户已确认）。  
4) **不直接改代码**：本次默认仅产出审查与建议；若需要修复，将在你确认后另开执行。  
5) **“唯一真相来源”处理**：`ARCHITECTURE_STATUS.md` 作为索引与重要证据之一，但若其内部表述冲突，以“设计文档原文 + 代码实证”裁决，并在报告中显式标注冲突与建议修订点。

---

## Verification（如何验证本次交付有效）
执行阶段完成后，按以下步骤自证：
1) 生成物存在且可打开：
   - `reports/aiPlat_设计文档与实现一致性审查报告.docx` 可被 Word/WPS 正确打开，中文不乱码，表格不变形，无额外空白页。
2) 报告可追溯性：
   - 报告中的每条问题均包含“来源文档路径 + 对应代码文件路径（与函数/类名）”，随机抽查若干条可直接定位。
3) 覆盖性：
   - Harness / Agent / Skill / Tool 四部分均有对照矩阵与问题清单；并补充“core ↔ infra ↔ management 边界审查”章节；显式列出“仅文档/未实现/结构存在未接通”项。
4) 一致性：
   - 报告中若引用 `ARCHITECTURE_STATUS.md` 的结论，必须在同条检查项中给出对应代码证据或指出其与其他文档冲突之处。
