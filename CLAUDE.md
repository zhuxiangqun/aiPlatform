---
purpose: aiPlat 多仓库工作区级 AI 编程规约（兜底）
scope: workspace-root
language: zh-CN
---

# aiPlat 工作区级 AI 编程规约（Workspace Root）

此文件是 **工作区兜底规约**，用于在系统执行链路中自动推断到 workspace root 时仍然能注入/强制基本规则。

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
  （验证：`grep -rn '8002.*aiPlat' aiPlat-infra/infra/ | wc -l` → 0）

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
```

---

## 通用强制规则（适用于所有仓库）
1. **不确定先问**：需求/边界不清晰先澄清，列选项与推荐默认方案。
2. **最小改动面**：只改需求相关代码；不顺手重构/格式化/改无关注释。
3. **简单优先**：不引入未要求的新抽象、新依赖、新框架层。
4. **验收闭环**：交付必须包含可验证证据（后端 pytest/py_compile，前端 npm build）。
5. **配置驱动**：核心基础设施（引擎/harness/编排器）的行为必须通过配置字段驱动，禁止硬编码业务概念（如 agent_id 字符串匹配、业务阶段名判断）。任何新增的行为分叉应先问"能不能用已有配置字段表达"。
6. **代码优先于设计文档**：设计文档描述目标状态，代码才是当前真实状态。基于设计文档做判断时，必须先交叉验证代码是否已有不同形式的实现。两者冲突时以代码为准，设计文档标记为"已过期/设计已用不同方式实现"。审计/对比类任务必须先搜代码再做结论，禁止根据文档推断"缺失"，每次结论必须附带代码搜索证据（命中文件路径+行号）。
7. **设计文档优先**：架构边界、层间契约、依赖方向等出现冲突时，以 `docs/` 下的设计文档为权威来源。CLAUDE.md 是执行规约，`docs/` 是设计真理。详细原则参见 `docs/index.md`。跨层/跨仓库改动时，必须主动查阅涉及的各层 CLAUDE.md 及 `docs/index.md` 中的边界规则。
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
    | **13** | **Skill 执行真实性** | `arch_guard_rules.yaml` §46 | `execution_type:handler` 必须有 `handler.py`；`prompt`+`handler.py` → WARNING |
    | **14** | **接线完成度标记** | `arch_guard_rules.yaml` §47 | 检测 `# TODO: wire/0 caller/待接线` 死代码标记 |
    | **15** | **Agent 边界** | `arch_guard_rules.yaml` §48+§50 | 禁止 Agent 直访 Harness 内部；禁止直接调用其他 Agent |

    **执行顺序（更新）**：
    ```
    1. bash scripts/architecture_guard.sh          ← 后端架构 §1-§52 + §42 子进程一致性 + §43-45 前端守卫
    2. pytest tests/ -v --tb=short                  ← Python 语义检查
    ```

16. **已知例外与永久债务（2026-06）- 3 条**：

    | 编号 | 章节 | 内容 | 分类 |
    |------|------|------|------|
    | A | §1 | `workflow_manager.py` → `platform/storage/sqlite.py` 跨层导入 | **已知例外** — 管理工具允许跨层访问 |
    | B | §35 | 2 个 execute 端点（引擎 + 工作区）被标记为 WARNING | **永久告警** — 2 是正确数量，若增至 ≥3 升级为 ERROR |
    | C | §40 | 模型注册/路由迁移尚未完成（33 条规则） | **迁移中** — CLAUDE.md §14 已规划从 core 迁到 infra，`model_registry.py`/`model_router.py` 标记 deprecated。`model_injection.py` 为集中注入点（canonical）。`kb_eval.py`/`packages_registry.py`/`prompt_eval.py` 等含裸 `sqlite3.connect()` 为已批准模式。`base.py:get_model()` 为 Agent 级别模型（与 model_injection 区分）。待到 infra ModelManager 提供完整 `select()` 后再统一迁移。 |
    | D | §65 | 2 个检索函数缺 tenant_id：`wiki_fts.py:fts_search`、`retriever.py:retrieve` | **已知债务** — 多租户隔离参数待补齐，当前为单租户模式运行 |
    | E | §66 | `PipelineStageConfig` 校验识别为已知假阳性 | **假阳性** — `failure_strategy` 字段已存在于第 247 行，grep 行级匹配策略无法检测跨行存在 |
    | F | §65 | 1 个检索路径未实现 3 级 CRAG 回退 | **待修复** — `materials_chat.py` 检索路径需确认已实现 normal→FTS5→HyDE |
    | G | §65 | 1 个检索鲁棒性组件缺配置字段 | **待修复** — `WikiCircuitBreaker`/`DomainRouter` 需确认配置完整性 |
    | H | §67 | 约 15 个路由端点缺 `response_model` | **已知债务** — API 契约化改造尚未完成，不影响功能 |

    **验证命令（排查已知例外后）**：
    ```bash
    bash scripts/architecture_guard.sh  # 预期：1 ERROR (§1) + 2 WARNING (§35) + 4 ERROR/WARN (§65-§66) = 7 total，其中 4 个 §65-§66 为已知债务，其余已排除
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
| 3 | 有 `handler.py` 但 `execution_type` 声明为 `prompt` → **WARNING**（可能误配） |

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

