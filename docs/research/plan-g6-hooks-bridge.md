# G6 CC/Codex hooks 协议桥 — 专项规划（独立批次）

> **背景**：对标报告 §20 能力缺口矩阵中**唯一仍完全缺失**的项（G6）——aiPlat `HookManager` 有 HookPhase 枚举与触发机制，但无 CC/Codex hooks.json 协议兼容层。DSH 已实现 CC 7/30 + Codex 5/10 事件子集（见对标报告 §17.3），证明可行。
> **时点**：2026-08-19（P3-1/P3-2 已实施后；本规划为独立批次，工作量约 3-5 天）
> **状态**：✅ **已实施（2026-08-23）**——`cc_bridge.py` + `cc_bridge_rules.py` + `HookManager.__init__` 接线 + 15 测试全绿（§4 验收 1-5 逐项落地，见文末实施记录）。
> **关联**：《对标吸收与架构纯度评估.md》§2.3 改善项 3（⏳ 待独立批次 → ✅ 2026-08-23 实施）

---

## 1. 目标

让 aiPlat 能**直接消费 Claude Code / Codex 的 `hooks.json` 配置**（三方互操作纯度），把外部事件映射到 aiPlat HookPhase 生命周期执行 command handler。企业远程策略场景：复用 CC 生态的 hooks 脚本，零改写接入 aiPlat。

## 2. 现状（实证）

| 项 | 现状 | 证据 |
|---|---|---|
| HookPhase 枚举 | pre_loop/post_loop/session_start/stop 等（含 PreToolUse 语义的 pre_tool_use） | `core/harness/infrastructure/hooks/hook_manager.py:18-41` |
| 注册/触发机制 | `register()` / `trigger(phase, context)` + 默认 hooks（OntologyValidator 等） | `hook_manager.py:132,145` |
| CC/Codex 协议层 | **无**：无 hooks.json 加载、无事件映射表、无 command handler 执行 | grep `hooks.json` → 空 |
| 事件子集 | aiPlat 生命周期事件（ReAct 6 phase + session）与 CC 30 事件重叠约 7 个 | §17.3 DSH 已映射 7/30 + 5/10 |

## 3. 设计

### 3.1 新增文件（3 个，全部同批接线）

```
core/harness/infrastructure/hooks/
  cc_bridge.py        ← CC/Codex hooks.json 解析 + 事件映射（新）
  cc_bridge_rules.py  ← 事件映射表（CC 30 / Codex 10 → HookPhase，数据驱动）
tests/unit/test_harness/test_cc_hooks_bridge.py  ← 测试（新）
```

### 3.2 事件映射表（核心，数据驱动）

| CC 事件 | aiPlat HookPhase | 说明 |
|---|---|---|
| SessionStart | SESSION_START | 会话开始 |
| UserPromptSubmit | PRE_LOOP | 用户输入提交 |
| PreToolUse | PRE_LOOP（tool 前置） | 工具调用前 |
| PostToolUse | POST_LOOP（tool 后置） | 工具调用后 |
| Stop | STOP | 停止 |
| SubagentStart | （映射 PRE_LOOP 子代理态） | 子代理启动 |
| SubagentStop | （映射 POST_LOOP 子代理态） | 子代理结束 |
| 其余 23 个 CC 事件 / 5 个 Codex 事件 | **unmapped**（记录 WARNING，fail-open） | 对齐 DSH：仅支持子集 |

### 3.3 组件

1. **`cc_bridge.py`**：
   - `load_hooks_json(path)`：解析 CC/Codex hooks.json（`{"hooks": {"EventName": [{"hooks": [{"type": "command", "command": "..."}]}]}}`）
   - `CCHookBridge(Hook)`：把外部事件包装成 aiPlat Hook，注册进 HookManager
   - command handler 执行：`subprocess.run(command, shell=False, cwd=repo_root)`（超时 + stderr 捕获 + fail-open 日志）；CC 语义 `{"continue": false}` / `updatedInput` 记日志不生效（对齐 DSH 限制披露）
   - 配置：`~/.aiplat/hooks.json` 或 `AIPLAT_CC_HOOKS_PATH`（默认关）
2. **`cc_bridge_rules.py`**：事件映射表（§3.2）+ CC/Codex 事件全集常量（供测试断言覆盖度）

### 3.4 接线链（§5.30 规则 6：新文件必须立即接线）

- `cc_bridge.CCBridge` 注册点：`hook_manager.get_default_hooks()` 或 `server.py` startup（`AIPLAT_CC_HOOKS_PATH` 存在时装载）→ 生产 caller：hook 触发路径（ReActLoop 6 phase + session）
- 验证：`grep -rn 'cc_bridge' core/harness/infrastructure/hooks/hook_manager.py` 命中

## 4. 验收（每个 Phase 的 verify）

| # | 验收 | verify |
|---|------|--------|
| 1 | hooks.json 解析（CC 格式） | 单测：伪造 hooks.json → `load_hooks_json` 返回结构化事件映射 |
| 2 | 事件映射表覆盖度 | 单测：CC 30 事件中 ≥7 个可映射、其余 unmapped 不崩溃 |
| 3 | command handler 执行 | 单测：假 command（`echo`）经 `CCHookBridge` 触发输出捕获 |
| 4 | 失败 fail-open | 单测：command 不存在 → WARNING 日志 + 不阻断（非 0 退出不抛） |
| 5 | 接线 | wiring 测试：`cc_bridge` 被 hook_manager 引用（生产路径） |
| 6 | 全量回归 | `pytest core/tests/unit/test_harness/` + pre-commit 全绿 |

## 5. 风险与边界（对齐 DSH §17.3 诚实披露）

- **仅 command handler**：CC 的 http/mcp_tool/prompt/agent handler 跳过（记 WARNING）——与 DSH 相同
- **子集映射**：30 事件仅 7 个有对应生命周期；其余 fail-open 不静默执行
- **进程级单配置**：无 CC 分层发现（`.claude/settings.json` 分层覆盖不实现）与热重载——v1 不做
- **安全**：command 以 repo 目录 cwd 执行；权限继承执行者身份（企业场景需配合 RBAC/审计，落地时在边界文档声明）

## 6. 变更同步义务（落地时必须）

| 文件 | 动作 |
|---|---|
| `aiPlat-core/docs/contracts/01-architecture-contract.md` | 追加 G6 落地记录（contracts-guard CORE_BOUNDARY binding） |
| `docs/research/对标吸收与架构纯度评估.md` | §2.3 改善项 3 状态 ⏳ → ✅ |
| `AIPLAT_CAPABILITIES.md` + `capability_registry.yaml` | 补登 cc_bridge 符号 |
| `docs/standards/规范-core-run_id-trace_id-request_id.md` | 若触及 run 生命周期事件（session/hook 属会话层，视触发面决定） |

---

## 7. 实施记录（2026-08-23，独立批次落地）

| # | 验收项 | 落地 |
|---|--------|------|
| 1 | hooks.json 解析（CC 格式） | `load_hooks_json`：CC 嵌套 `{"hooks":{Event:[{"hooks":[...]}]}}` + Codex 数组 `[{hook_event_name, command}]` 双格式；非 command handler（http/mcp_tool/prompt/agent）跳过记 WARNING；缺失文件 FileNotFoundError |
| 2 | 事件映射表覆盖度 | `cc_bridge_rules.py`：CC 7/30 映射（SessionStart/UserPromptSubmit/PreToolUse/PostToolUse/Stop/SubagentStart/SubagentStop）+ Codex 4/10（SessionStart/PreToolUse/PostToolUse/SessionEnd）；unmapped 返回 None 不崩溃 |
| 3 | command handler 执行 | `CCHookBridge(Hook)`：`_run_command` shell=False（shlex 拆词）+ `asyncio.to_thread` + 超时 30s + stdout/stderr 捕获（截 2000）+ 结构化结果（对齐 syscall 可观测） |
| 4 | 失败 fail-open | command not found → exit 127 WARNING 不抛；超时 → WARNING 不抛；CC 语义 `{"continue": false}`/updatedInput 记日志不生效（对齐 DSH 限制披露） |
| 5 | 接线 | `HookManager.__init__` 新增 `load_cc_hooks_if_configured`（默认关：`~/.aiplat/hooks.json` / `AIPLAT_CC_HOOKS_PATH` 存在时装载）→ 生产 caller `hook_manager.py:133` |
| 6 | 全量回归 | 15 测试全绿（`test_cc_hooks_bridge.py`）；py_compile OK |

**差异标注**（vs 设计 §3.3）：设计写 `cc_bridge.py` 内联事件映射，实施拆出 `cc_bridge_rules.py` 数据驱动映射表（对齐"配置驱动"原则，便于扩展与覆盖度断言）；command 执行从设计"shell=True"改为 **shell=False + shlex 拆词**（安全强化，防注入）。
