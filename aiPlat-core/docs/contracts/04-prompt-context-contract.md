# Prompt & Context Contract（提示词/上下文契约）

本文件约束“提示词工程与上下文管理”的行为边界，避免 token 失控与不可预测的上下文污染。

## 1. Stable / Ephemeral 分层（MUST）

Prompt 组装 **MUST** 分为：
- **Stable System**：跨轮稳定（系统规则、固定框架、关键契约）
- **Ephemeral Overlay**：每轮可变（本轮输入、检索结果、repo diff、工具结果摘要等）

## 2. Stable Cache Key（MUST）

如果启用 prompt cache：
- stable cache key **MUST 仅依赖 stable system 层**（以及 workspace 级稳定上下文 hash）
- **MUST NOT** 依赖每轮 ephemeral 内容，否则会造成“伪缓存”

## 3. Prompt Mode（MUST）

系统 **MUST** 支持 prompt_mode，至少包含：
- `full`：允许全部上下文注入（repo diff / session search / memory…）
- `minimal`：仅注入必要且稳定的上下文（例如 project context），跳过重型注入
- `none`：禁用几乎所有注入（用于极简/高可靠场景）

规则：
- 子代理/cron/job/scheduler **SHOULD** 默认使用 `minimal`（降低成本与噪声）
- 显式指定 `prompt_mode` 时必须尊重

## 4. 上下文压缩（Compaction）（MUST）

当历史消息体积超过阈值：
- 系统 **MUST** 触发 compaction（可配置阈值与保护尾部消息数）
- compaction **MUST** 保留关键标识符（UUID/哈希/文件名/ID）
- compaction **MUST** 产出可继续执行的摘要（CONTEXT_SUMMARY），并记录统计（before/after/preserved_ids）

## 5. Transcript Guard（MUST）

在发送给 LLM 之前必须执行 guard：
- 修复/归一化 role（避免 provider 拒收）
- 合并相邻同 role
- 单条消息限制与整体限制（防止超长）
- 记录 guard 统计到 syscall 事件

## 6. 可观测性（SHOULD）

Prompt 组装 **SHOULD** 输出如下可观测字段（至少部分）：
- stable_prompt_version（stable system hash）
- workspace_context_hash
- prompt_mode
- injected_sections 列表与大小（如 repo_diff/session_search 等）

