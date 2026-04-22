# Architecture Contract（架构契约）

本文件定义 aiPlat 的架构“硬约束”。目标是防止实现随意演进导致：循环依赖、边界失守、治理失效、可观测断裂。

## 1. 分层与边界（MUST）

aiPlat 逻辑上分为：

1) **Kernel / Runtime（内核运行时）**  
负责：上下文传播、syscall 边界、可观测事件、资源/隔离抽象。

2) **Harness（执行框架）**  
负责：Loop（ReAct/Plan&Execute）、Agent/Tool/Skill 调度、context 管理、gates（policy/approval/resilience/trace）。

3) **Apps（业务组件）**  
负责：tools、skills、exec backends、gateway/channels、learning loop 等具体能力。

4) **Server/API（外部接口）**  
负责：HTTP 契约、鉴权、tenant 解析、将请求注入到 Harness。

### 1.1 依赖方向（MUST）

- `core/apps/*` **MUST NOT** 通过包级 `core.harness` 触发 Harness 的重型导入链路。  
  允许导入 **具体子模块**（例如 `core.harness.kernel.runtime`），但必须确保不会引发循环依赖。
- `core/harness/__init__.py` **MUST** 保持轻量（lazy export），不得在 import 时加载 execution/loop/tools 等重型模块。
- `core/server.py` **MAY** 依赖 apps/harness，但 apps/harness **MUST NOT** 反向依赖 server。

> 说明：这条约束用于避免“任意 import 都把系统启动一遍”，并降低循环依赖风险。

## 2. 契约优先（MUST）

当出现以下冲突时，处理顺序必须是：
1) 更新实现以符合契约；或
2) 变更契约（需要明确理由 + 风险），并补齐验收用例。

## 3. 扩展点与插件化（SHOULD）

新增能力应优先以“注册/声明”的方式接入，而不是在核心路径硬编码：
- ToolRegistry：工具注册/查询/动态发现
- Skill registry / Skill packs：技能包发布与安装
- ExecDriver registry：执行后端扩展（local/docker/ssh…）
- Gateway adapters/connectors：渠道适配与交付

## 4. 错误与返回结构（MUST）

对外 API 与 syscall 边界处的错误 **MUST** 使用“结构化错误封装”，至少包含：
- `ok`（成功布尔）
- `error.code`（稳定错误码）
- `error.message`（可读信息，避免泄漏敏感内容）
- `trace_id/run_id`（若可用）

## 5. 变更控制与 ADR（SHOULD）

对下列变更 **SHOULD** 写 ADR 或至少在 PR 描述中给出“决策记录”：
- syscall/gate 行为变化
- prompt 组装逻辑变化（stable/ephemeral、cache key、compaction）
- tool/skill 权限模型变化
- exec backend 引入/删除
- gateway/多入口链路变化

推荐将 ADR 放在：
- `docs/architecture/` 或 `docs/design/` 对应子目录

