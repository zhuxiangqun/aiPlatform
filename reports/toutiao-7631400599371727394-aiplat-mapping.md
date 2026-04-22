# Claude Code 架构文章 → aiPlat 对照表（覆盖/缺口/建议）

来源文章：`Claude Code 架构深度解析：5 个架构层级，7 个核心组件，13 项原则`（今日头条 7631400599371727394）

本文目的：把文章中的概念映射到你们当前 aiPlat 实现，并标注：
- ✅ 已覆盖（已有实现/已接线）
- 🟡 部分覆盖（有雏形/缺关键治理或产品化）
- 🔴 缺口（建议优先补齐）

---

## 1) 5 层架构 / 7 个核心组件对照

| Claude Code 组件/层级 | 文章描述 | aiPlat 对应组件（代码/模块） | 覆盖度 | 备注/建议 |
|---|---|---|---|---|
| User / Interfaces | CLI/SDK/IDE 统一服务 | aiPlat-management UI + management API + aiPlat-core REST | ✅ | 多入口需保证门控一致性（统一 policy/approval/audit） |
| Agent Loop (queryLoop) | ReAct while 循环 + 工具分发 | `core/harness/execution/loop.py`（ReActLoop） | ✅ | 你们已把 tools_desc/skills_desc 注入，并加预算统计 |
| Permission System | deny-first、ask/allow、会话信任 | `core/harness/infrastructure/gates/policy_gate.py` + ApprovalManager | 🟡 | 工具门控已强；skills 侧目前主要对 `skill_load` 做 allow/ask/deny（可继续扩展到 installer/exec 等） |
| Tools | 工具池组装、模式过滤、预过滤 | `core/apps/tools/*` + ToolRegistry + MCPRuntime | 🟡 | 已有 tool registry + MCP 管理；建议做“工具池组装流水线”的显式可观测 stats（见第3节） |
| State & Persistence | JSONL、事件流、会话恢复不恢复权限 | ExecutionStore + run/events（你们已有 run contract & 审计） | 🟡 | 你们已实现 run/events + approval replay；建议补“会话恢复不继承权限”的显式规则说明与测试 |
| Execution Environment | shell/exec backend/隔离 | Exec backends（local/docker/ssh）+ capabilities | ✅ | 已在 contracts 中固化 exec capabilities；建议把“风险等级/隔离强度”与 policy 更紧密绑定 |
| Extensibility | hooks/skills/plugins/mcp | Skills（rule+executable 判别）、MCP、（未来 plugins/hooks） | 🟡 | Skills 与 MCP 已落地；Hooks/Plugins 若要对齐文章，可作为后续 roadmap（见第4节） |

---

## 2) 文章关键机制 → aiPlat 现状对照

### 2.1 “98.4% 基础设施”对应的基础能力

| 文章点 | aiPlat 已做 | 覆盖度 | 建议 |
|---|---|---:|---|
| deny-first + ask/allow | PolicyGate + Approval | ✅ | 继续把所有入口纳入同一套 gate（避免绕过路径） |
| 上下文预算与压缩 | tools/skills desc budgets | ✅ | 下一步：做“多阶段整形流水线”并暴露可观测 stats |
| 故障恢复 | 超时/回退/重试（部分） | 🟡 | 建议固化：重试策略、fallback、降级时的安全姿态（不能绕过 gate） |

### 2.2 “共享失效模式 / 绕过安全分析”的警示

| 风险 | aiPlat 相关点 | 当前状态 | 建议（P0） |
|---|---|---|---|
| 性能压力导致安全降级 | tool 执行/并发/回退路径 | 🟡 不确定 | 做一次“绕过路径审计”：列出所有执行入口与回退路径，确保都走 PolicyGate/ApprovalGate/审计 |
| 子命令/分支绕过 | installer/exec/tool/mcp | 🟡 | 给每类入口加统一的 audit 事件与 trace_id/run_id 关联，便于事后定位 |

---

## 3) “5 层压缩整形器” → aiPlat 的建议落地形态

文章的启发：压缩不是“一个开关”，而是“按成本递增的流水线”，并且每一阶段可观测、可回放。

### 建议你们做成 4~5 阶段（示例）
1. **Budget Trim（预算削减）**：基于硬上限裁剪 skills/tools 列表与附加上下文（已做一部分）  
2. **Prune（剪枝）**：丢弃低价值历史/重复日志/低相关检索结果  
3. **Micro-Compress（微压缩）**：对长段落/日志做局部摘要（保留关键字段）  
4. **Fold（折叠）**：把多个轮次折叠成结构化状态（任务进度/已决策/待办）  
5. **Auto-Compress（自动压缩）**：兜底（最贵），确保模型调用不炸

### 可观测性建议（你们已具备 run/events 基础）
- 每阶段输出：`input_chars`、`output_chars`、`dropped_items`、`reason`  
- 绑定到 run_id / trace_id  
- 让“压缩导致的信息损失”可追踪（debug 关键）

---

## 4) “Hooks → Skills → Plugins → MCP” → aiPlat 的分层准入建议

你们当前已落地：
- ✅ Skills（rule vs executable 判别 + find/load + 权限）
- ✅ MCP（管理与运行）

建议对齐文章的“按风险/成本递增”的产品化分层（可用于治理与 UI 导航）：

1) **Rule Skills（最低成本）**  
   - 默认 allow（或对第三方默认 ask）  
   - 主要影响 prompt，不直接执行代码  

2) **Executable Skills / Plugins（中高风险）**  
   - 必须：permissions + provenance + integrity + approval  
   - 建议：沙箱执行、网络/文件写入强门控  

3) **MCP（外部连接器，高风险）**  
   - 强隔离 + allowlist + 运行时健康检查  
   - 建议：工具级别权限与租户隔离

---

## 5) 你们已落地的“可借鉴亮点”总结（对齐文章精神）

- ✅ 你们把 **skills 的发现/按需加载**做成工具（skill_find/skill_load），避免默认注入 SOP 全文（对齐“成本递增/渐进披露”）。  
- ✅ 你们把 installer 做成 **plan → plan_id（签名+TTL+digest）→ confirm/approval → install**，这非常接近文章提倡的“边界重构以减少审批疲劳”。  
- ✅ 你们在 prompt 构建阶段加入了 skills_desc 预算与统计，为“压缩流水线可观测”打基础。  

---

## 6) P0/P1 建议清单（可直接进 roadmap）

**P0（建议尽快做）**
1) 绕过路径审计：列出所有执行入口（API/UI/回退/重试/installer/mcp），确保统一走 gate + audit  
2) context shaping 分阶段 + events 统计：让压缩/裁剪可观察、可回放  

**P1（下一阶段）**
1) 扩展权限光谱到“可执行 skills / plugins”并完善 provenance/integrity 校验链  
2) 形成可复用 evaluator（QA）工位：结构化报告 + tool-playbook + 阈值门控  

