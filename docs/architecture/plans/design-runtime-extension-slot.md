# 设计：运行时扩展缝（Runtime Extension Slot）

> 状态：设计稿（P2-A2，2026-08-16）· 范围：仅设计 + 能力缝声明，**不落地代码执行**（对齐 DSH"自修改不是安全边界"原则）

## 1. 目标

为企业大脑"自演进操作系统"第 7 层愿景提供受限的**运行中挂载/卸载能力**——在保持安全边界（白名单 + 审批 + 审计）内，不开放任意代码执行。

## 2. 现状基线

| 机制 | 状态 | 说明 |
|------|------|------|
| `EvolutionEngine` | 离线夜间演化 | 改技能/知识/配置，无运行中挂载 |
| `PluginManager`（apps/plugins/manager.py:8） | DB 管理 | 注册/启停/回滚，无代码注入 |
| `action_contract.py:125` 模块白名单 | ✅ 已有 | `ALLOWED_PREFIXES`（builtin_handlers / custom_handlers）+ `DANGEROUS` 模块拦截 |
| `register_handler` / `dispatch`（core_facade.py:29） | ✅ 已有 | platform → core handler 注册（P1 成果） |

## 3. 能力缝声明（本阶段产出）

在 `core/api/core_facade.py` 的 handler 注册机制上声明以下扩展缝（**仅声明，不实现**）：

```
扩展缝 1: 运行时 handler 注册（白名单）
  - 入口: register_handler(name, handler)（已存在）
  - 约束: handler 模块必须在 action_contract.py ALLOWED_PREFIXES 内
  - 审计: dispatch 调用记录 handler 名 + 调用方（现有 audit 体系）

扩展缝 2: 审批化插件启停
  - 入口: PluginManager 注册/启停（已存在，DB 管理）
  - 约束: 高风险插件(type=execute)需审批（复用 ApprovalManager）
  - 审计: 插件生命周期事件入 audit_logs

扩展缝 3: 模型 provider 插件目录（P2-A3 关联）
  - 入口: infra ModelManager 目录扫描（已存在）
  - 约束: provider 实现必须走 openai_compatible 协议
```

## 4. 安全边界（强制，不放松）

| 原则 | 说明 |
|------|------|
| 白名单优先 | 新 handler 必须在允许模块前缀内，禁止任意 import |
| DANGEROUS 拦截 | os/sys/subprocess/shutil/builtins 模块禁止（已实现） |
| 审批 | 写/执行类插件必须走 ApprovalManager 审批 |
| 审计 | 所有注册/调用/启停事件入审计 |
| 不做 | **不开放任意代码执行**（bash 级信任拒绝）；不引入热代码重载 |

## 5. 后续落地节奏（不在本期）

1. 将扩展缝 1 从"声明"转为"运行时检查"（dispatch 时校验白名单）
2. 插件目录扫描（`~/.aiplat/plugins/` 动态发现）
3. 审批化启停 API 接线

## 6. 验证（本期）

```bash
# 白名单机制已存在
grep -n "ALLOWED_PREFIXES" aiPlat-core/core/harness/infrastructure/action_contract.py
# handler 注册通道已存在
grep -n "def register_handler" aiPlat-core/core/api/core_facade.py
```
