---
purpose: aiPlat 多仓库工作区级 AI 编程规约（兜底）
scope: workspace-root
language: zh-CN
---

# aiPlat 工作区级 AI 编程规约（Workspace Root）

此文件是 **工作区兜底规约**，用于在系统执行链路中自动推断到 workspace root 时仍然能注入/强制基本规则。

**能力全貌**：参见 [`AIPLAT_CAPABILITIES.md`](./AIPLAT_CAPABILITIES.md)（唯一真相源，890 项能力）

**架构定位**：企业大脑 — 从"工具集合"到"自演进操作系统"的 8 层架构：

| 层 | 定位 | 操作系统类比 | 核心实现 |
|:--:|------|:--:|------|
| 1 | 本体语义底座 | 文件系统 — 定义数据如何组织和理解 | 8域YAML + GraphIndex + EntityResolver |
| 2 | 知识创造引擎 | 进程调度 — 动态生成和转化知识 | SECI Bus (POST_LOOP → atom → convergence) |
| 3 | 上下文注入总线 | 内存管理 — 为运行中的任务提供上下文 | ContextBus (10层注入, 4子系统覆盖) |
| 4 | 质量评分总线 | 安全机制 — 确保输出符合标准 | Quality Bus (4子系统统一评分 0-100) |
| 5 | FDE诊断与交付闭环 | Shell — 用户直接交互的界面 | 诊断→证据映射→覆盖率→改进→交付手册→跟踪→评分→对比→基准→目标分解→自主部署→外部发现 |
| 6 | 治理工程化 | 系统日志 — 记录和度量所有操作 | 8项治理能力 + 自审计 + 配置驱动 + 术语自播种 |
| 7 | 自演进操作系统 | 自动更新 — 自我修复和进化 | 四阶段全自动(观察/诊断/修复/演化) + 后台每小时调度 |
| 8 | 编码宪法 | 内核约束 — 所有操作必须遵守的基本法则 | karpathy_v1 全局默认注入(编码前思考/简洁优先/精准修改/目标驱动) |

**编码宪法豁免机制（设计预留）**：Skill 执行时默认注入 karpathy_v1 规则。若某个 Skill 需临时豁免，可在其 metadata 中声明 `override_karpathy: true`，注入逻辑检查该字段后跳过宪法注入。当前阶段保持全局强制，后续按需开放。

**编码宪法默认启用（v2.4+）**：自 2026-07 起，`karpathy_v1` 编码宪法（编码前思考 / 简洁优先 / 精准修改 / 目标驱动）**全局默认启用**，通过 `_facade.py:_coding_policy_profile()` 中 `AIPLAT_CODING_POLICY_PROFILE_ENGINE` 和 `AIPLAT_CODING_POLICY_PROFILE_WORKSPACE` 环境变量控制，默认值为 `"karpathy_v1"`。此变更影响所有 workspace 和 engine Agent 的代码生成 Skill 执行。临时禁用：`export AIPLAT_CODING_POLICY_PROFILE_WORKSPACE=off`。按需覆盖：`export AIPLAT_CODING_POLICY_PROFILE_WORKSPACE=my_profile`。

### 规约冲突裁决规则（强制）

5 个 CLAUDE.md 文件（workspace + 4 个子仓库）构成系统规约体系。当不同层级的规约对同一事项的规定存在冲突时，按以下规则裁决：

| # | 规则 | 说明 |
|---|------|------|
| 1 | **执行层级优先** | 子仓库规约（core/infra/platform/management）> 根规约（workspace）> 设计文档（docs/） |
| 2 | **代码优先** | 任何规约声明与代码事实冲突时，以代码事实为准，规约须在 24 小时内同步修正 |
| 3 | **变更同步窗口** | 规约冲突发现后，最晚 24 小时内必须修正至少一方，并在 commit message 中标注 `clause-sync` |
| 4 | **审计兜底** | 每次架构审计（`architecture_guard.sh`）必须检查"根规约 vs 子规约"在关键事项上的一致性 |

**skip_claude_md 使用规范（v2.4+）**：`trace_context["skip_claude_md"] = True` 用于 LLM 调用时跳过 CLAUDE.md + 架构规则注入（~20K 字）。使用场景约束：

| 场景 | 是否允许 | 原因 |
|:---|:---:|:---|
| FDE 澄清对话 (`_clarify()`) | ✅ | 澄清场景聚焦业务问题，架构规则导致 hallucination |
| Prompt-type Skill 执行 | ✅ | Skill 自带 SOP，架构上下文为噪音 |
| Agent ReActLoop / 代码生成 | ❌ | 需要架构规则和编码宪法做决策引导 |
| 检索生成 (RAG) / 材料问答 | ❌ | 需要知识治理和引用规则 |

**内容归属规范（v2.5+）**：每段知识在系统中有且仅有唯一归属。同一份 SOP / 输出格式 / 域参考数据禁止出现在两个地方。

| 内容类型 | 唯一归属 | 反例（禁止） |
|---------|------|------|
| Agent 的执行步骤与决策逻辑 | `AGENT.md` 的 `system_prompt` + SOP body | workflow JSON 的 `config.prompt` |
| Skill 的输出格式 / 反模式 / 输入约束 | `SKILL.md` 的 SOP + 输出格式 / 反模式章节 | Agent 的 AGENT.md |
| 域级配置数据（通过率、可用域列表、成熟度） | `~/.aiplat/ontologies/{domain_id}.yaml → `DomainRouter.classify()` 运行时读取 | 硬编码在 prompt / 代码字符串中 |
| 运行时上下文（客户信息、部署模式、上游产出物） | `pipeline_state` 透传 | 模板变量 `{{placeholder}}` |
| Workflow 阶段级附加指令 | `PipelineStageConfig.prompt_extra` | JSON 的 `config.prompt` |
| LLM prompt 模板正文 | `prompt_loader._register("id", "...")` | 代码或 JSON 中内嵌 >1 行 prompt 字符串 |

**核心系统修改自检规则（v2.5+）**：修改 `core/harness/`、`core/apps/`、`core/schemas_`、`core/api/core_facade.py` 等共享模块时，必须在 diff 阶段执行以下自检：

| # | 检查项 | 验证方法 |
|---|------|------|
| 1 | 新逻辑是否硬编码了业务概念（域名/Agent名/角色名）？ | `grep -n 'domain_id ==\|agent_id ==\|_TARGET' <changed_files> → 应为空 |
| 2 | 新行为是否可用已有 `PipelineStageConfig` 字段驱动？ | 检查是否引入了新的 `if/elif` 条件链 |
| 3 | 修改是否改变了共享接口的签名或语义？ | `git diff` 检查所有 `def`/`async def` 的函数签名 |
| 4 | 是否需要更新本规范的对应章节？ | 对照上方 "内容归属规范" 表格逐项核对 |
| 5 | 降级/回退路径是否保留？ | 新增路径应保留原有路径作为 `except` 或 `if None` 的 fallback |
| **违反后果**：PR review 阶段发现违反 → 退回修改；合并后发现违反 → `architecture_guard.sh` 记录为违规 |

**业务应用模块目录规范（v2.5+）**：每个业务应用模块（FDE/Builder/Workbench/Value/Learning 等）有且仅有唯一的目录归属。详见 `docs/architecture/plans/app-module-layout.md`。

| 文件类型 | 正确目录 | 禁止位置 |
|---------|------|------|
| REST 端点 (`@router.get/post`) | `aiPlat-platform/apps/{module}/api/` | `core/api/routers/` |
| 无 HTTP 依赖的业务逻辑 | `aiPlat-core/core/apps/{module}/service/` | `core/harness/` |
| 模块 Prompt 模板 | `aiPlat-core/core/apps/{module}/prompts/` | `core/harness/utils/prompt_loader.py` |
| Harness 层代码硬编码模块名 | ❌ 禁止 | 应通过 `DomainRouter` 动态发现 |
| 新模块注册 | `aiPlat-platform/registry/apps.yaml` | 不应在代码中硬编码模块列表 |

**强制规则——代码变更必须同步文档**：

| # | 代码变更类型 | 必须更新的文档 |
|---|------------|--------------|
| 1 | 新增公共类/函数/模块/端点 | `AIPLAT_CAPABILITIES.md` 对应子系统增加一行 |
| 2 | 能力状态变化（⚠️→✅等） | `CAPABILITIES.md` 更新标记 + 评分统计 |
| 3 | 评分维度改变 | `ROADMAP.md` 更新基线表 |
| 4 | 已知债务新增/修复 | `CLAUDE.md` §16 更新 |
| **5** | **技术文档/文章中的可验证声明** | **附带 grep 命中文件:行号 验证证据** |
| **违反后果**：`phase_check.sh` Step 7 → `verify_doc_sync.sh → **退出码 1 阻断** |
| **自动修复**：`git commit` 时 pre-commit hook 自动运行 `auto_sync_docs.sh`，新模块自动生成条目并 stage |

**规则 5 详解——技术文档声明必须代码验证（强制）**：

技术文章、README、设计文档中的所有**可验证事实性声明**——
  - "X 模块已实现 Y 功能"
  - "系统支持 Z 种错误类型"
  - "A 是唯一入口 / B 已被全量修复"
  - 所有带数字的断言（"N 个模块"、"M 项测试"、"K 条规则"）

——在定稿或 commit 前，必须附带至少一条代码交叉验证证据：

```
grep -rn '<声明关键词>' <搜索路径> --include='*.py'
```

**禁止**将设计目标或 Plan 阶段构思当作当前实现状态写入描述现状的章节。

**示例**：
  ✅ "ApprovalGate 集成到 PolicyGate" — 验证：`grep -rn 'get_approval_gate' policy_gate.py → line 337
  ❌ "FeedbackTranslator 提供自然语言反馈" — 验证：`grep -rn 'FeedbackTranslator' * → 仅命中文章本身，代码中不存在
  ❌ "84% 的 busy_timeout 缺失已被全量修复" — 验证：`grep -rn 'sqlite3.connect' --include='*.py' | grep -v timeout → 仍有 70+ 处未迁移

如果你的任务明确针对某个仓库，请优先遵守对应仓库根目录的更细化规约：
- 后端引擎：`aiPlat-core/CLAUDE.md`
- 基础设施：`aiPlat-infra/CLAUDE.md`
- 平台服务：`aiPlat-platform/CLAUDE.md`
- 管理端：`aiPlat-management/CLAUDE.md`
- 应用端：`aiPlat-app/CLAUDE.md`

---

## 0. 架构守卫与审计铁律（强制——防止审计遗漏）

### 0.1 审计结果必须有可执行验证

前 8 轮审计反复遗漏同类问题的根因是：**审计结论标注"已修复"后，下一轮跳过验证**。

**强制规则**：任何标注为"已修复"的架构违规，必须附带以下至少一项可执行证据：

| 证据类型 | 示例 |
|---------|------|
| 通过率 | `bash scripts/architecture_guard.sh` 对应检查项 PASS |
| 测试通过 | `pytest tests/constitution/test_kernel_agnostic.py -v` 通过 |
| grep 验证 | `grep -rn '硬编码字符串' aiPlat-core/core/harness/ | wc -l` 输出 0 |

**禁止**：仅凭 CLAUDE.md 中的文字标注"✅ 已修复"就跳过检查。

### 0.2 架构守卫执行顺序（强制）

每次架构审计 / PR review / 代码生成后，必须按以下顺序执行：

```
1. bash scripts/architecture_guard.sh          ← grep 级快速扫描（0依赖，秒级完成）
2. pytest tests/constitution/ -v --tb=short    ← Python 级语义检查
3. 若 1 或 2 失败 → 修复后重新执行 → 直到全部通过
```

### 0.3 每次审计必须从零开始（防缩面）

- **禁止**："上次审计已经查过 X 层，这次只看增量"
- **必须**：每次架构审计都要跑全量扫描（`architecture_guard.sh` + `tests/constitution/`），花 30 秒确认存量无回归
- **禁止**：依赖 CLAUDE.md 中标注的"已修复"标签来跳过代码验证

### 0.4 标记"已修复"的证据标准

在 CLAUDE.md 中标注某问题已修复时，必须在备注中附带验证命令和输出：

```
✅ 正确写法：
- `infra/network/manager.py:50-54`: port→service mapping → AIPLAT_PORT_SERVICES 环境变量 ✅
  （验证：grep -rn '8002.*aiPlat' aiPlat-infra/infra/ | wc -l → 0）

❌ 错误写法（禁止）：
- `infra/network/manager.py`: 已修复 ✅
  （无证据，不可信）
```

### 0.5 审计范围六维度检查矩阵

每次审计必须覆盖以下全部 6 个维度（不能只看 1-2 个）：

| # | 维度 | 检查手段 | 检查对象 |
|---|------|---------|---------|
| 1 | **导入方向** | `architecture_guard.sh` §1 | 四层所有 .py 文件的 import 语句 |
| 2 | **职责归属** | `architecture_guard.sh` §2,§5,§6 | platform 是否执行 pipeline？app 是否运行 API 服务器？core 是否定义平台路由？ |
| 3 | **内核无关** | `tests/constitution/test_kernel_agnostic.py` | harness/engine 是否有业务角色名、artifact key、评分维度、SOP prompt？ |
| 4 | **基础设施独立** | `tests/constitution/test_infra_agnostic.py` | infra 是否有应用名默认值、GPU 型号、开发者路径？ |
| 5 | **门面使用** | `tests/constitution/test_layer_boundaries.py` | platform 是否通过 CoreFacade 访问 core？是否直接 new PipelineEngine？ |
| 6 | **接线完成** | 交叉搜索生产调用者 | 新增公共方法是否有至少 1 个非测试调用者？feature flag 是否隐藏未接线代码？ |

### 0.6 文件位置说明

```
scripts/architecture_guard.sh           ← 零依赖 grep 守卫（CI 第一步）
tests/constitution/test_layer_boundaries.py  ← 跨层导入 + 门面使用
tests/constitution/test_kernel_agnostic.py   ← Core 引擎去业务化
tests/constitution/test_infra_agnostic.py    ← Infra 去应用化
.github/workflows/aiplat-contracts-guard.yml ← CI 流水线（已集成）
scripts/validate_frontmatter.py         ← YAML frontmatter 解析校验（AGENT.md / SKILL.md / CLAUDE.md）
scripts/ruff_f821_ratchet.py           ← F821 未定义变量 ratchet 门禁（基线对比，仅新违规阻断）
scripts/ruff_f821_baseline.json        ← F821 基线快照（ratchet 对比基准，每次修复后重建）
```

---

## 通用强制规则（适用于所有仓库）
1. **不确定先问**：需求/边界不清晰先澄清，列选项与推荐默认方案。
2. **最小改动面**：只改需求相关代码；不顺手重构/格式化/改无关注释。
3. **简单优先**：不引入未要求的新抽象、新依赖、新框架层。
4. **验收闭环**：交付必须包含可验证证据（后端 pytest/py_compile，前端 npm build）。
4a. **路由文件修改后必须跑路由可达性验证**（2026-07 新增）：凡修改 `routers/*.py` 文件（新增/修改/删除路由），必须在验证步骤中额外跑：
   - `bash scripts/architecture_guard.sh`（§77 路由重复检测）— 检测同一路径重复注册
   - 对比前端 `fetch()` 调用的 API 路径与后端注册的路由，确保不 404
    - `py_compile` 不能替代路由验证 —— 路径错误的代码也能通过编译（案例：`/capability-boundary` vs `/diagnostics/capability-boundary`）
4b. **最小验证锚点（强制——每次代码变更后必须执行）**：

    编译通过 ≠ 正确。以下 2 分钟验证必须根据变更范围选择执行，**漏跑 = 改动未完成**。

    ```
    ① 编译 + 导入（所有变更必跑）
       $ python3 -m py_compile <所有变更的 .py 文件>
       $ python3 scripts/verify_imports.py
       $ npx tsc --noEmit                    # 前端变更时

    ② 模型选择回归（manager.py / model_injection.py / llm_profile.yaml 变更时）
       $ python3 -c "
         from core.harness.utils.model_injection import best_model_for_purpose
         for p in ['chat','code_gen','reasoning','skill_execution','clarify']:
             m = best_model_for_purpose(p)
             assert '32b' not in m, f'{p} still picks 32b: {m}'
         print('✅ 32b blocked')
       "

    ③ Wiki 同步验证（wiki.py / docs_sync.py / server.py 变更时）
       $ python3 -c "
         from core.harness.knowledge.docs_sync import sync_docs_to_wiki
         r = sync_docs_to_wiki()
         assert r['errors'] == 0, f'{r[\"errors\"]} errors'
         print(f'✅ created={r[\"created\"]}, skipped={r[\"skipped\"]}')
       "

    ④ 前端构建（.tsx / .ts 变更时）
       $ npm run build

    ⑤ 架构守卫（harness / infra 核心层变更时）
       $ bash scripts/architecture_guard.sh
    ```

    **归属矩阵**（按变更文件自动选择必须的验证项）：

    | 变更涉及 | 必须执行 |
    |---------|:---:|
    | `model_injection.py` / `manager.py` / `llm_profile.yaml` | ① + ② |
    | `wiki.py` / `docs_sync.py` / `server.py` | ① + ③ |
    | 任何 `.tsx` / `.ts` | ① + ④ |
    | `harness/` / `infra/` 核心模块 | ① + ⑤ |
    | 跨模块改动 | ① + ② + ③ + ④ |

    **违规信号**：
    - 改动完成后没跑验证 → **立即中断，先跑验证再继续**
    - 验证失败 → **立即修复，不推到下一轮**
    - 超过 3 轮交互没跑编译检查 → 主动提醒用户暂停，先编译
5. **配置驱动**：核心基础设施（引擎/harness/编排器）的行为必须通过配置字段驱动，禁止硬编码业务概念（如 agent_id 字符串匹配、业务阶段名判断）。任何新增的行为分叉应先问"能不能用已有配置字段表达"。
6. **代码优先于设计文档**：设计文档描述目标状态，代码才是当前真实状态。基于设计文档做判断时，必须先交叉验证代码是否已有不同形式的实现。两者冲突时以代码为准，设计文档标记为"已过期/设计已用不同方式实现"。审计/对比类任务必须先搜代码再做结论，禁止根据文档推断"缺失"，每次结论必须附带代码搜索证据（命中文件路径+行号）。
7. **设计文档优先**：架构边界、层间契约、依赖方向等出现冲突时，以 `docs/` 下的设计文档为权威来源。CLAUDE.md 是执行规约，`docs/` 是设计真理。详细原则参见 `docs/README.md`。跨层/跨仓库改动时，必须主动查阅涉及的各层 CLAUDE.md 及 `docs/README.md` 中的边界规则。
8. **内核无关应用（强制）**：aiPlat-core（Harness 内核）和 aiPlat-infra（基础设施）禁止包含任何特定应用的知识：
   - 禁止硬编码业务角色名（如 `"architect"`、`"pm_agent"`）
   - 禁止硬编码业务阶段名（如 `"awaiting_architecture_approval"`）
   - 禁止硬编码业务 artifact key（如 `state.get("prd")`）
   - 禁止硬编码业务评分维度、评估逻辑、角色 prompt 全文
   - 引擎行为分叉必须全部来自 PipelineStageConfig 字段，不允许 `if agent_id ==` / `if phase ==`
   - infra 不允许硬编码服务名映射、业务进程标签、开发者本地路径、GPU 型号等
9. **接线完成度（强制——新建文件必须立即接线）**：任何新增的 core 基础设施模块必须至少有一个生产代码调用者（非测试）。零调用者的模块必须在合并时标注为"待接线"或"待删除"。禁止用 feature flag=false 来掩盖未接线。全局单例（`get_*_registry()`）必须在所有消费进程中做初始化。**禁止批量创建 3 个以上文件而不逐个接线**：新建一个→接一个→grep 验证 caller→再建下一个。每轮实施结束时必须跑 caller 验证脚本，任何新建文件 0 caller = 实施未完成。详细自检命令见 `aiPlat-core/CLAUDE.md` §5.30 规则 6-8。

10. **API 入口唯一性（强制——防并行实现）**：同一能力的多个 API 端点，底层必须收敛到同一个的核心函数。**禁止**出现"两个 UI 入口做同一件事但调用不同的检索路径"、"三个 API 端点各自实现了自己的 RRF 融合"这类并行实现。**必须**：
    - 每项能力在 CoreFacade 中暴露唯一公共接口
    - 所有 HTTP 端点、CLI 入口、外部集成全部通过该接口调用
    - 新增能力前先搜已有实现：`grep -rn 'def <capability_name>'` 确认没有重复
    - 底层能力升级后必须确认所有入口都已收敛到统一路径（不能只有 MaterialsChat 受益，而问答 Tab 还走老路）

11. **审批单次检查（强制——防多重门禁）**：同一请求对同一资源的权限检查，整个调用链中只能执行一次，且由 PolicyGate（`sys_tool_call` / `sys_skill_call` 内）作为唯一执行点。**禁止**：RBAC guard 在 HTTP 层检查一遍 → Gateway 在调用层再查一遍 → PolicyGate 在 syscall 层又查一遍 → BaseTool 内部再自查一遍。**必须**：上游层只做身份注入（JWT → tenant/actor/scopes），不做权限判断。权限判断统一委托给 PolicyGate。

11b. **管理员 MFA 强制（安全策略建议）**：admin 角色拥有全权限（所有菜单组 + 9 个独占管理项），破坏半径极大。建议：admin 账号强制启用 MFA（TOTP / WebAuthn）；admin 账号不用于日常非管理操作（开发/运维应使用 developer/operator 角色）；admin 账号共享/泄露需记录安全审计事件。

12. **模型解析中心化（强制——防环境变量碎片化）**：模型名称的解析必须通过统一的 `get_default_model(purpose)` 函数，**禁止**各模块直接读取 `AIPLAT_DOC_LLM_MODEL`、`AIPLAT_CODE_GEN_MODEL`、`AIPLAT_LLM_MODEL` 等环境变量做独立判断。全局只有一个解析链：`purpose 参数 → 专用 env → infra ModelManager.list_models() → 系统默认`。**模型发现、启用/禁用、健康状态均以 infra ModelManager 为唯一权威。** core 不得自行维护模型列表（`model_registry.py` 已废弃）。**禁止 core/平台绕过 infra 直接加载模型**：❌ `import sentence_transformers`（embedding）、❌ `import faster_whisper`（语音转文字）、❌ `import PaddleOCR`（OCR）、❌ `from transformers import AutoModel`（reranker）。

13. **架构审计覆盖并行实现（强制——防漏检）**：`architecture_guard.sh` 必须包含"相同函数签名多定义"检测。每新增一个 `def <name>(query, ...)` 且与已有函数签名高度相似（参数名匹配 ≥3 个），视为并行实现警告。

14. **模型管理层级（强制——防架构绕行）**：

    ```
    infra (Layer 0) = 唯一模型目录
      ├─ 远程 API 模型（从 env vars 自动发现）
      ├─ 本地模型（Ollama/LM Studio/oMLX/vLLM 自动扫描）
      ├─ 健康检查（标记不可达模型）
      └─ 启用/禁用管理
    
    core (Layer 1) = 消费模型
      ├─ InfraLLMAdapter（唯一通用 LLM 适配器）→ infra LLMClient → provider API ✅
      ├─ InfraEmbeddingAdapter（通用嵌入适配器）✅
      ├─ InfraRerankerAdapter（通用重排适配器）✅
      ├─ InfraAudioAdapter（通用音频适配器）✅
    
    management (横切) = 展示模型列表
      └─ 从 infra ModelManager 获取模型列表 ✅
    ```
    
    **禁止** core 或 platform 自行维护模型注册表、自行加载模型文件、自行做模型路由。
    
    **Core 每种能力类型只有 1 个 Adapter**：LLM → InfraLLMAdapter，Embedding → InfraEmbeddingAdapter 等。
    不按 provider 分文件（禁止 `openai_adapter.py`、`deepseek_adapter.py` 等 per-provider 类）。
    
     **Infra 相同协议合并 Provider**：OpenAI / DeepSeek / Qwen / LM Studio 均走 `openai_compatible.py`。
     新增 OpenAI 兼容的模型提供商只需改配置，不需新代码。

15. **审计矩阵扩展——15 维覆盖（强制）**：2026-06 将审计矩阵从 10 维扩展到 15 维：

    | # | 维度 | 检查手段 | 检查对象 |
    |---|------|---------|---------|
    | 1-6 | 原有 6 维（导入方向/职责归属/内核无关/基础设施独立/门面使用/接线完成） | `architecture_guard.sh` §1-§41 + `tests/` | Python 代码 |
    | **7** | **前端代理路由** | `scripts/guard_frontend.py` §43 | `vite.config.ts` proxy 目标端口 |
    | **8** | **子进程 Python 一致性** | `arch_guard_rules.yaml` §42 | 检测 `subprocess.run(["python3"` 等裸 python3 调用 |
    | **9** | **跨语言 API 契约** | `scripts/guard_frontend.py` §44 | 检测 TS `fetch()` body 字段名 vs Python `data.get()` 字段名 |
    | **10** | **MCP 集成冒烟测试** | `tests/` MCP 相关 | spawn → init → list_tools → tools/call 完整链路 |
    | **11** | **模型解析集中化** | `arch_guard_rules.yaml` §40.2 + §40.4 | 禁止各模块直接读取 `AIPLAT_*_MODEL` env var；禁止硬编码模型名 |
    | **12** | **提示词模板管理** | `arch_guard_rules.yaml` §45 | 检测 router/apps 中硬编码 `你是一个`/`"You are a"` 多行 Prompt |
    | **13** | **Skill 执行真实性** | `arch_guard_rules.yaml` §46 | `execution_type:handler` 必须有 `handler.py`；`prompt`+`handler.py → WARNING |
    | **14** | **接线完成度标记** | `arch_guard_rules.yaml` §47 | 检测 `# TODO: wire/0 caller/待接线` 死代码标记 |
    | **15** | **Agent 边界** | `arch_guard_rules.yaml` §48+§50 | 禁止 Agent 直访 Harness 内部；禁止直接调用其他 Agent |
    | **11** | **git diff 新增API登记** |  §11 | 检测 git diff 中新增的 public 函数/类/端点是否在 CAPABILITIES 中登记 — 解决"已有文件新增能力不自动补登"问题 — 1 violation(s)
| **16** | **YAML frontmatter 解析** | `arch_guard_rules.yaml` §76 + `scripts/validate_frontmatter.py` | AGENT.md / SKILL.md / CLAUDE.md YAML frontmatter 完整性（缺失 `---` 分隔符、YAML 语法错误） |
    | **17** | **Python 未定义变量** | `arch_guard_rules.yaml` §76 (ruff F821 ratchet) + `scripts/architecture_guard.sh` 前端检查 | core/ 生产代码中引用未定义的变量名（NameError 风险） |

    **执行顺序（更新）**：
    ```
    1. bash scripts/architecture_guard.sh          ← 后端架构 §1-§76 + §42 子进程一致性 + §43-45 前端守卫
    2. pytest tests/ -v --tb=short                  ← Python 语义检查
    ```

16. **已知例外与永久债务（2026-06 → 2026-07-29 更新）- 11 条**：

    **✅ CLAUDE.md 证据验证强制执行（2026-07-29）**：本节所有 `（验证：grep ...）` 声明由 `scripts/verify_claude_md_evidence.py` 自动验证。该脚本已集成到 `architecture_guard.sh` Phase 1（并行执行），CI 每次运行时自动检查。

    | 编号 | 章节 | 内容 | 分类 |
    |------|------|------|------|
    | A | §1 | `workflow_manager.py → `platform/storage/sqlite.py` 跨层导入 | **✅ 已修复** — 当前 `core/management/workflow_manager.py` 已无任何 platform 层 import。跨层导入链路已消除。 （验证：grep -rn 'from.*platform.*import' aiPlat-core/core/management/ --include='*.py' → 空） |
    | A2 | — | `builder.py` 直导 `core.harness.knowledge.*`（2026-07-18 发现→修复） | **✅ 已修复 (2026-07-18)** — 3 处直导改为 `from core.api.core_facade import`：`DomainRouter`、`capability_health_report`、`build_capability_graph`。CoreFacade 已增加 canonical re-export。 （验证：grep -rn 'from core.harness' aiPlat-platform/apps/fde/orchestration/builder.py → 0） |
    | B | §35 | 2 个 execute 端点（引擎 + 工作区）被标记为 WARNING | **永久告警** — 2 是正确数量，若增至 ≥3 升级为 ERROR |
    | C | §40 | 模型注册/路由迁移 | **✅ 已完成 (2026-06-29)** — `model_router.py` 已删除，`get_model_registry()` 重命名为 `get_model_manager()`，llm.py 和 base.py 迁移到 `model_injection.create_selected_adapter()`。infra `ModelManager.select()` 已确认存在。 |
    | D | §65 | 4 个检索函数缺 tenant_id | **✅ 已修复 (2026-07-01)** — `KnowledgeQuery` 增加 `tenant_id` 字段，`WikiPageRetriever.retrieve()` tenant_id 不匹配时返回空结果（WARNING→ERROR 阻断），非只读放行。 |
    | E | §66 | `PipelineStageConfig` 校验识别为已知假阳性 | **假阳性** |
    | F | §65 | CRAG 3 级回退 | **✅ 已实现** — `materials_chat.py:380-498` |
    | G | §65 | WikiCircuitBreaker/DomainRouter 配置 | **✅ 已实现** — `harness/syscalls/retrieval.py:504`，`domain_router.py:26` |
    | H | §67 | ~953 个端点使用 `response_model=dict` 而非 typed schema（~1,064 端点中 111 已类型化） | **✅ 已修复 (2026-07-18)** — 全量 typed 化完成。FDE (76端点, FdeStatusResponse等) + 其余6模块 (134端点, StatusResponse等) + core routers (10端点)。全系统 `response_model=dict` 已清零。arch_guard §83 确保不再增长。 |
    | I | — | Episodic 记忆 LLM 摘要不可达 | **✅ 已修复 (2026-06-29)** — `MemoryManager.__init__` 自动注入 `best_model_for_purpose("doc_llm")`，LLM 摘要路径从不可达变为激活。 （验证：grep -rn "best_model_for_purpose" aiPlat-core/core/harness/memory/manager.py | wc -l → >0）  |
    | J | — | FeedbackLoops DB 后端未实现 | **✅ 已修复 (2026-06-29)** — `_store_to_db()` 实现 SQLite INSERT/retrieve/delete/cleanup 全路径。 |
    | K | — | DatabaseTool 占位符 | **✅ 已修复 (2026-06-29)** — SQLite/PostgreSQL/MySQL 三后端完整实现，默认 SQLite（零依赖），异步驱动可选。 （验证：ls aiPlat-core/core/apps/tools/database.py → 存在）  |
    | L | — | BrowserTestEngine 缺失 action | **✅ 已修复 (2026-06-29)** — 新增 `select_option`/`scroll`/`hover`/`press_key`/`file_upload` 五个 action。 |
    | M | — | 31 个 engine Skill 缺 `execution_type` 字段 | **✅ 已修复 (2026-06-29)** — 全部 31 个 SKILL.md 已添加 `execution_type: prompt`。 （验证：grep -rl "execution_type:" aiPlat-core/core/engine/skills/*/SKILL.md | wc -l → 42）  |
    | N | — | architecture_guard.sh 超时 | **✅ 已修复 (2026-06-29)** — 移除 golden_path E2E 测试（→CI 独立 job）+ 并行化 4 个独立脚本 + 排除 .venv/node_modules。 （验证：grep "timeout" scripts/architecture_guard.sh → 已配置）  |
    | O | — | 3 builder stub routers (死代码) | **✅ 已修复 (2026-06-29)** — `builder_projects.py`/`builder_pipeline.py`/`builder_teams.py` 已删除（未挂载的失源码死代码）。 （验证：ls aiPlat-core/core/api/routers/builder_projects.py builder_pipeline.py builder_teams.py 2>/dev/null | wc -l → 0）  |
    | P | — | 3 platform endpoint stubs | **✅ 已修复 (2026-06-29)** — `ingest-directory`/`kb/watch → （参见 AIPLAT_CAPABILITIES.md 当前计数） Not Implemented + WARNING 日志；`studio/sessions → WARNING 日志。 |
    | Q | — | EmailNotifier 假成功 | **✅ 已修复 (2026-07-18)** — `core/harness/infrastructure/email_notifier.py`：零依赖 smtplib 实现，支持 TLS/认证，开发模式自动降级为 console log。环境变量：`AIPLAT_SMTP_HOST/PORT/USER/PASS/FROM/TLS`。 （验证：`python3 -c "from core.harness.infrastructure.email_notifier import EmailNotifier; n=EmailNotifier(); assert n.send('test@test.com','test','test')"` → True） |
    | R | — | 5 infra management 占位符 | **✅ 已修复 (2026-06-29)** — 全部改为 `raise NotImplementedError` + 清晰的接线说明。 |
    | S | — | `cancel_pipeline` no-op stub | **✅ 已修复 (2026-06-29)** — 真实实现：append_run_event(cancel_requested) + cancel_queued_run + EventBus.publish。pipeline engine 主循环定期检查 is_cancel_requested()。 |
    | T | — | `set_knowledge_providers` no-op stub | **✅ 已修复 (2026-06-29)** — 真实实现：委托 kb_facade → kb_provider 的 4 个 setter 函数 (ingest_fn/query_fn/enqueue_fn/load_doc_kinds_fn)。 （验证：grep -rn "set_knowledge_providers\|kb_facade" aiPlat-core/core/api/core_facade.py | wc -l → >0）  |
    | U | §40 | `auto_trigger.py` 4 处直接读 `AIPLAT_SFT_*_MODEL` env var | **已知例外 (2026-07-01)** — SFT 训练的目标模型是运维决策，与 arch_guard_rules.yaml §40.2 `grep_exclude` 一致。 |
    | V | §76 | diagnostics.py 12 个 `_check_*` 函数引用在列表中但对应的嵌套函数已被移除 — 剩余 2 个模块级函数（`_check_core_runtime` + `_check_doc_sync`）正常通过 HealthCheckRegistry 注册。（2026-07-04 清理：移除 12 条死代码字符串引用。） （验证：grep -c '_check_前缀死代码引用' — 已全部清理） |
    | W | — | workbench/prompt/learning 模块 router 残留（2026-07-18 发现） | **✅ 已修复 (2026-07-18)** — prompt 43→4 端点、learning 17→3 端点去重完成。workbench 0 重叠（routes 完全不同，各自独立）。 （验证：grep -c '@router\.' aiPlat-core/core/api/routers/prompt_*.py → 4, learning_*.py → 3） |
    | X | — | FDE 20 个 router 薄代理（2026-07-18 发现） | **✅ 已修复 (2026-07-18)** — 全量实迁移完成。20 个文件从 `core/api/routers/fde_*` 移至 `platform/apps/fde/api/`，core 文件已删除，`server.py`/`system.py`/`workbench.py` 引用路径已更新。arch_guard §80 现已 clean。 （验证：grep -rn 'from core.api.routers.fde' aiPlat-core/ aiPlat-platform/ --include=*.py | wc -l → 0） |
    | Y | — | 前端 FDE API 路径未更新（2026-07-18 发现，2026-07-29 修复） | **✅ 已修复 (2026-07-29)** — `FdeDashboard.tsx`、`ClarifyDialog.tsx`、`FloatingFeedback.tsx` 3 处 `/api/core/fde` 已全部统一为 `/api/platform/apps/fde`。 （验证：grep -c '/api/core/fde' aiPlat-management/frontend/src/pages/Diagnostics/ --include='*.tsx' → 0） |
    | Z | — | Phase 0-4 6 个模块（2026-07-18 发现）：`on_error_reflector`(1 producer caller)、`hallucination_tracker`(9 callers)、`parallel_executor`(3 callers)、`gateway`(26 callers)、`implicit_feedback`(3 callers)、`semantic_cache`(11 callers) | **✅ 已修复 (2026-07-18)** — 验证：全部 6 模块有 ≥1 非测试生产调用者。原 xfail 标记为误报（搜索范围仅限 `sys_skill_call`，模块通过其他路径接入）。详见 Core CLAUDE.md §5.30 案例表 （验证：grep -rn 'sys_skill_call' core/ --include='*.py' → 模块通过其他路径接入） |
    | AA | — | 管理画面菜单按技术层分组 (8组)，任务流跨组断裂；27个诊断工具仅4个在侧边栏，治理仪表盘完全不可见（2026-07-20 发现→修复） | **✅ 已修复 (2026-07-20)** — 菜单重构为5组按任务流分组，13个子区域标题，URL自动展开+高亮，治理/审计/安全/可观测从工具箱提升到侧边栏，FDE工作台移入AI应用工厂，审批中心合并到诊断与治理。能力数从776→788。 （验证：grep -n "group: 'dashboard'" aiPlat-management/frontend/src/components/layout/AppLayout.tsx → 1匹配） |
    | AB | — | ~496 处 `except Exception: pass` 静默吞错（2026-07-25 审计发现→2026-07-29 彻底清理） | **✅ 已修复 (2026-07-29)** — 225 存量全量治理完毕：14 处 `except Exception: pass` 加入 logging，192 处合法模式（ImportError/OSError/OperationalError/CancelledError/WebSocketDisconnect）加 `# noqa:` 注释，守卫 `scan_silent_except()` 支持 `# noqa:` 豁免。基线 0，architecture_guard.sh 阻断新增。 |
    | AC | — | 企业级可治理 AI 执行层（Action Registry v3） | **✅ 已完成 (2026-07-29)** — 10 个文件完整实施。`ActionContractModel`（Pydantic v2 + 实体约束 + 安全沙箱）、`AsyncActionRegistry`（7 步异步执行流水线 + 审批回调 + 审计持久化）、`EntityLock`（mutex/stake 双语义锁）、`ActionStore`（aiosqlite + entity_snapshot 不可变审计）、`builtin_actions`（2 业务 + 4 legacy 桥接 + YAML 自助注册）、`builtin_handlers`（4 个可调用 handler）、`engine.py` StateMachine 桥接（零停机 migration）、`action_routes.py` REST API + FDE AcceptTab 前端动作卡片。 |
    | AD | — | 知识生命周期三层管线（Knowledge Pipeline v3） | **✅ 已完成 (2026-07-30)** — `extractor.py`（DocumentIngestor 分块 + EntityExtractor LLM 9实体10关系抽取 + DraftYamlWriter YAML草稿 + PendingExtractionStore SQLite待审）、`resolver.py`（CrossDomainResolver 三级匹配 精确键/Jaro-Winkler/向量余弦 + 跨域边写入 + registry.json seed）、`retriever.py`（GraphRAGRetriever 实体路由→BFS 2跳子图→定向检索→推理路径 + ActionRegistry 上下文注入）、`extraction_routes.py` REST API（抽取/待审/确认/跨域候选/跨域边/GraphRAG上下文）、FDE 工作台 ① 知识抽取面板。 |

    **验证命令（排查已知例外后）**：
    ```bash
    bash scripts/architecture_guard.sh  # 预期：0 ERROR + 0 WARNING (v2.5+ 全面修复)
    # M2 验证：model_registry.py / model_router.py 已物理删除
    find aiPlat-core -name "model_registry.py" | wc -l  # 预期：0
    find aiPlat-core -name "model_router.py" | wc -l    # 预期：0
    ```

## 17. 技能执行真实性（强制——2026-06 新增 §44）

所有 workspace 技能的 `SKILL.md` 必须显式声明 `execution_type`：
- `handler` — 有 `handler.py` 真实执行代码
- `python_class` — 有 Python 类实现
- `prompt` — 纯 LLM 推理（仅适用于 text_generation/summarization 等 LLM 本身就是执行引擎的场景）

### 强制规则

| # | 规则 | 说明 |
|---|------|------|
| 1 | `execution_type` 必须在 `SKILL.md` frontmatter 中**显式声明**，无声明时默认走 `prompt` 模式并**记录 WARNING** |
| 2 | `execution_type: handler` 必须在同级目录下存在可执行的 `handler.py`，否则**报错而非静默走 LLM 模拟** |
| 3 | 有 `handler.py` 但 `execution_type` 声明为 `prompt → **WARNING**（可能误配） |

### 禁止

| ❌ 禁止 | ✅ 应做 |
|--------|--------|
| `execution_type` 未声明，静默走 LLM 模拟 | 显式声明 `execution_type: handler/prompt/python_class` |
| `execution_type: handler` 但 `handler.py` 不存在 | 要么补 `handler.py`，要么改声明为 `prompt` |
| 搜索工具失败时静默返回 mock 假数据 | 返回 error；如需 mock 设定 `AIPLAT_MOCK_SEARCH_ENABLED=true` |

### 生产环境审计

设置 `AIPLAT_EXECUTION_AUDIT=true` 后，每次 `sys_skill_call` 执行时记录：
- `skill_name` — 哪个技能
- `execution_type` — 声明模式
- `actual_mode` — handler/prompt/mock（实际走的是哪个路径）
- `success` — 是否成功

审计事件写入 `execution_store` 的 `audit_log` 表，可通过诊断中心查看。

## 18. Autoreview 技能 — 自动代码审查与上下文工程（2026-07-02 新增）

### 18.1 Autoreview Skill (v2.1, engine skill)

首个 `execution_type: handler` 的 engine skill，位于 `aiPlat-core/core/engine/skills/autoreview/`（8 文件，~1070 行）。

**三种执行模式**：
- **单引擎**（默认）：reasoning(P0/P1) + code_gen(P2)，2-3s，适合日常 PR
- **硬投票面板**（quick）：三引擎并行 + 行号锚点投票，2-3s，适合 CI 门禁
- **MoA Deep Mode**（deep）：Reference 引擎高温发散 + Aggregator LLM 综合裁决，10-15s，适合高风险审查

**核心设计**：
- Diff-only：绝不审查全量文件，入口防御拒绝 `. / *` 等全仓库 target
- 引擎隔离：审查者使用独立 system prompt，`sys_llm_generate` 调用时 `inject_agent_config=False`
- Scope Governor：修复不扩散为重构（文件边界/净增行数/收敛三重检查，P0 安全修复阈值翻倍）
- Auto Fixer：P2 问题自动修复 + `git stash -u` checkpoint 回滚
- 3 套 MoA preset：`code_review` / `architecture` / `security`（presets.yaml）

**证据链 (v2.2)**：
- clean 报告末尾自动附加证据卡（`build_evidence()` + `clean_evidence()`）
- 审查结果持久化到 `execution_store`（key=`autoreview:last:{target}`）
- 诊断面板展示审查历史 + clean 率趋势
- 人工否决端点：`POST /agents/{id}/override-autoreview → 触发 deep mode 重审

### 18.2 上下文工程升级（P0-P2）

**P0 级**：
- P0-1 审计隔离：`skill.py → `llm.py → `MemoryManager.build_context()` 全链路，autoreview 执行时强制跳 Episodic/Semantic
- P0-2 温度感知剪枝：高温(≥0.6)保留 60% 消息供探索，低温(<0.3)仅保留 15% 供决策
- P0-3 语义相关性排序：InfraEmbeddingAdapter + LRU 缓存计算消息与任务 cosine similarity，替代位置启发性规则
- P0-4 跨层重排：Working/Episodic/Semantic 统一语义排序 + 最近 3 轮时效性保护

**P1 级**：
- P1-1 工具动态高亮：不改物理顺序（避免 Positional Bias），System Prompt 末尾追加 `[TOOL HINT]`
- P1-2 Token 预估算：tiktoken 采样预估，超标先压缩再调用 LLM
- P1-3 Pipeline 预算重分配：前序 stage 未用完 token 均分给剩余 stage

**P2 级**：
- 模板版本化：`_sync_resolve("id@version")` + `get_versions()` / `get_latest_version()`
- 重复函数清理：移除 llm.py 中 136 行死代码版本的 `_try_inject_claude_md`

### 18.3 Pipeline + Agent 集成

- `autoreview_reviewer` AGENT.md：薄 agent，唯一技能 `autoreview`
- `programmer_agent` + `architect_agent`：`required_skills` 中加入 `autoreview`
- `pipeline_stage.yaml`：`depends_on: [code_gen, test_gen]`，`failure_strategy: skip_stage`
- `scripts/pre-commit-autoreview.sh`：git pre-commit hook 模板

### 18.4 审查触发方式与结果查看

| 触发方式 | 结果位置 |
|------|------|
| 诊断中心完整模式 | 诊断面板 → LLM审查卡片 → v2.2 证据历史 |
| Pipeline 收尾 | Pipeline 运行记录 → autoreview_gate stage 输出 |
| Agent 自动调用 | ReActLoop 推理中间步骤 → `sys_skill_call` 日志 |
| 管理端 Execute | Core → Skills → autoreview → Execute → 弹窗报告 |
| Pre-commit Hook | 终端输出 → `✅ clean` 或 `❌ P0=N P1=M score=X` |

### 18.5 验证命令

```bash
# 确认 autoreview skill 注册成功
ls aiPlat-core/core/engine/skills/autoreview/SKILL.md

# 确认审查 agent 配置
grep autoreview ~/.aiplat/agents/autoreview_reviewer/AGENT.md
grep autoreview ~/.aiplat/agents/programmer_agent/AGENT.md
grep autoreview ~/.aiplat/agents/architect_agent/AGENT.md

# 确认上下文工程改动已生效
python -c "from core.harness.memory.compression import get_cached_embedding; print('OK')"
python -c "from core.harness.memory.manager import _re_rank_messages; print('OK')"
```

---

## 19. 架构治理状态 (v2.5, 2026-07-16)

### 19.1 已解决债务

| 编号 | 内容 | 解决方式 |
|------|------|------|
| 路由迁移 | 46个应用路由在 core/api/routers/ | ✅ 全部迁移到 platform/apps/{module}/api/ |
| 边界守卫 | 9 errors, 4 warnings → 无条件提升 | ✅ 0 issues (0 errors, 0 warnings) |
| Harness硬编码 | 43处 fde-delivery / 业务字符串匹配 | ✅ 全部替换为 DomainRouter 动态发现 |
| Platform→Core | 100+处绕过 CoreFacade 直接 import | ✅ 全部改为 import from core.api.core_facade |
| Core域常量 | DOMAIN_FDE / DOMAIN_AI_KNOWLEDGE 硬编码 | ✅ 删除,改为 DomainRouter.list_domains() |
| skills/registry.py | GraphIndex.load("fde-delivery") 硬编码写入 | ✅ 改为 DomainRouter 迭代所有域 |
| 模块注册 | 无声明机制 | ✅ platform/registry/apps.yaml (7模块) |
| 目录规范 | 无应用模块目录标准 | ✅ docs/architecture/plans/app-module-layout.md |
| FDE模块 | 业务逻辑混在 router 文件中 | ✅ core/apps/fde/agent.py + prompts.py 独立 |
| CoreFacade | 平台层无法安全访问核心能力 | ✅ 30+新增导出 |
| 前端API缺口 | 3条缺失后端路由 | ✅ 添加 501 占位路由 (parse/parse-and-process/feedback) |
| 架构守卫规则 | 无自动化边界检测 | ✅ boundary_rules.yaml + generate_guard_rules.py |
| Pre-commit | 无新路由/硬编码检测 | ✅ Step 1.75 + Step 1.8 |
| Human HITL feedback | bug: feedback 丢失 | ✅ 透传修复 |
| 域健康 widget | 空数据/无折叠 | ✅ 彩色药丸 + ▲/▼ 切换 |
| 进度条 | workflow 模式不更新 | ✅ 从 state 变量推导 done/active |
| 自动技能选择 | 无机制 | ✅ classifier mode=filter, 17种意图覆盖 |
| 行业推断 | 需手动填写 | ✅ LLM 自动推断 (infer-industry endpoint) |
| lock-service 域 | 江苏锁安无匹配域 | ✅ 6类18实体新建 |

### 19.2 已知残留 (v2.8 scope, 2026-07-19 更新 — K1-K11 全部闭环)

| 编号 | 内容 | 类型 |
|------|------|------|
| K1 | core/schemas_policy.py DeprecationWarning 副本 | 过渡期 (v2.2 删除) |
| K2 | 前端API路径 baseline (16条, 多数为路径格式差异) | 已知基线 |
| K3 | Phase 4 Agent边界约束注入 | ✅ 已实现 (llm.py _try_inject_boundary_rules + pre-commit hook) |
| K4 | 种子数据注入端到端 — 需 server 运行 | 待运行时 |
| K5 | CLAUDE.md §16 已知债务 H (~60+ routes 缺 response_model) | **✅ 已修复 (2026-07-18)** — 全量 typed 化完成 |
    | K6 | sla_monitor 后台线程未调用 start() — server.py 启动时需接线 | **✅ 已修复 (2026-07-19)** — server.py startup lifecycle 中 start_sla_monitor()。 |
    | K7 | process_orchestrator.check_step_completion() 未在 engine.py 侧作用完成后接入 | **✅ 已修复 (2026-07-19)** — engine.py Step 3.5 StateMachine 后立即调用 check_step_completion。 |
    | K8 | 跨域流程编排 (processes.domains) 预留设计但未实现 | **✅ 已修复 (2026-07-19)** — supply-chain.yaml 新增 cross_domain_quality_trace 跨域流程。 |
    | K9 | registry.json 场景字段 (priority/maturity/scenarios/industries) 待填充 | **✅ 已修复 (2026-07-19)** — server.py startup 中 refresh_domain_maturity() 自动填充。 |
    | K10 | OntologyAgent 缺少 Golden Query 评测数据 (eval_score=None) | **✅ 已修复 (2026-07-19)** — golden_queries.yaml 17 条查询 + _load_golden_eval_score()。 |
    | K11 | GovernancePipeline 调度未接入 server.py cron 定时任务 | **✅ 已修复 (2026-07-19)** — AIPLAT_GOVERNANCE_CRON_HOURS 默认 24。 |

### 19.3 自动化防护生效

```
pre-commit hook → 检测新路由/core硬编码
architecture_guard_rules.sh → 边界规则检测 (0/0)
architecture/boundary_rules.yaml → 数据化规则,可版本控制
platform/registry/apps.yaml → 模块声明,无硬编码
```

---

## 20. 新能力成本阶梯（强制——hermes-agent 借鉴）

新增能力时，必须按以下阶梯从低到高选择实现方式。PR review 时必须确认阶梯未跳过：

| 级别 | 实现方式 | Token 成本 | 适用场景 | 决策规则 |
|:--:|------|:---:|------|------|
| 1 | **扩展已有代码** | 0 | 变体能力 | 能用已有模块解决的，不新建文件 |
| 2 | **CLI 命令 + Skill** | 低 | 配置/状态/基础设施操作 | 能用 shell 命令 + Skill SOP 表达的不写代码 |
| 3 | **Service-gated Tool** | 中 | 需要结构化 I/O 但非全局需要 | 通过 `check_fn` 条件启用，未配置时为 0 成本 |
| 4 | **Plugin** | 中 | 第三方/利基/用户特定 | 放 `~/.aiplat/plugins/`，不进入核心树 |
| 5 | **MCP Server** | 高 | 需要工具形式但非核心基础 | 通过 MCP 协议接入，零核心 schema 占用 |
| 6 | **Syscall / Core Tool** | 高 | 基础、通用、不可替代 | **最后手段。** 必须在 PR 中论证为什么 1-5 不可行 |

**验证命令**：
```bash
# 新增文件超过 3 个 → 检查是否跳过了阶梯
git diff --stat HEAD | grep "+" | grep -E "new file|create mode" | wc -l
# > 3 → warning: check footprint ladder
```

---

## 21. 贡献红线（"我们不要什么"）

以下类型的 PR 会被直接拒绝，无论代码质量如何。提前检查避免往返：

| # | 红线 | 说明 |
|---|------|------|
| 1 | **投机性基础设施** | 没有具体消费者的 Hook、回调、抽象层。加一个扩展点容易，删一个依赖它的插件难。必须有真实的、已声明的使用场景 |
| 2 | **行为配置混入 .env** | `.env` 仅用于凭据 (API key/token/密码)。超时、阈值、特征开关等行为配置放在 YAML `config.yaml` 或 `PipelineStageConfig` |
| 3 | **新增核心 Syscall 不走阶梯** | 如果 terminal + file + skill 已能完成，说明选错了阶梯。必须在 PR 中论证为什么不能放在 MCP/Plugin 层 |
| 4 | **Lazy-reading 逃生舱口** | 在指示型工具（Skill、Prompt、Playbook）上不加 `offset/limit` 分页。模型会读第一页然后跳过剩下的 |
| 5 | **安全修复毁掉功能本身** | 杀死功能目的的安全修剪不是正确的修剪。修复必须保留功能的核心意图 |
| 6 | **破坏 Prompt Cache 的中途注入** | 改变历史上下文、交换工具集、重建 system prompt 会破坏会话级 prompt cache（双倍 API 调用成本）。这是架构层约束，不是性能优化 |
| 7 | **无 caller 的新建文件** | 新建 `.py` 文件必须有至少 1 个非测试的生产代码调用者。一次提交超过 3 个无 caller 文件 → CI 直接拒绝 |
| 8 | **文档未同步的 PR** | 新增 public API/端点/功能 → AIPLAT_CAPABILITIES.md 必须同步更新。`check_doc_sync.sh` 在 pre-commit 中强制执行 |

---

## 22. Prompt Cache 不可侵犯（架构约束）

单次会话的 prompt cache 稳定性是架构层约束，不是性能优化。以下行为**禁止**：

| ❌ 禁止 | ✅ 替代做法 |
|--------|-----------|
| 会话中途改变 system prompt 前缀 | 变化量作为 ephemeral overlay 追加到尾部 |
| 会话中途切换工具集 | 工具集在会话开始时确定，通过 `ControlProfile.tool_whitelist` 控制 |
| 会话中途重建上下文结构 | 上下文深度/源数通过 `ControlProfile.context_layers` 在会话开始时确定 |

**设计依据**：CacheAwareRouter 通过 D1/D2 离散化哈希键检测变化。如果 cache key 变了，模型提供商侧的缓存前缀失效，后续每次调用都重新计算全量上下文。对抗方式：在 CacheAwareRouter.evaluate() 返回 `freeze=["D1","D2"]` 时，只允许 D3-D6 通过 overlay 追加。详见 `harness/meta/cache_aware_router.py`。

