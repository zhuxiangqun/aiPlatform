# 反馈循环系统 (Feedback Loops)（As-Is 对齐 + To-Be 规划）

> **As-Is**：Harness 已具备 HookPhase 接线与阻断语义（session/contract/approval/stop），并内置最小安全扫描与审批规则。  
> **To-Be**：本文档中 “Ralph Wiggum Loop / 三层反馈 / 两振出局” 属于规划型机制，需要与统一事件模型、评测回归与策略引擎结合后落地。  
> 统一口径参见：[架构实现状态](../ARCHITECTURE_STATUS.md)。

---

## 一句话定义

**反馈循环是 Harness 的质量保障机制**——通过多层自动验证，确保 Agent 的输出符合预期，并通过三层反馈实现自我进化。

---

## 核心概念

| 概念 | 说明 |
|------|------|
| **Hooks** | 触发式回调，在特定时机自动执行验证/拦截 |
| **Ralph Wiggum Loop** | 拦截"假完成"，强制外部验证 |
| **两振出局** | 重试2次后升级人类，防止无限循环 |
| **Exit Code** | 0=放行 / 1=警告 / 2=阻断 / 3=需人工确认 |
| **三层反馈** | LOCAL → PUSH → PROD 渐进式优化验证 |

---

## Hooks 架构

### 五层 Hooks

| 层级 | 触发时机 | 功能 | 类比 OS |
|------|---------|------|---------|
| **PostToolUse** | 每次文件写入后 | 自动格式化 | 自动保存 |
| **PreToolUse** | 命令执行前 | 危险操作拦截 + 敏感文件保护 | 安全沙箱 |
| **Stop** | Agent 准备"完成"时 | 强制验证(类型+Lint+测试) + AI自审查 | 编译器检查 + 代码评审 |
| **SessionStart** | 新会话开始时 | 注入上下文(分支/最近提交/项目信息) | 进程恢复 |
| **PreLoop** | 循环开始前 | 初始化状态 | 进程启动 |
| **PostLoop** | 循环结束后 | 清理和保存 | 进程结束 |

> **注**：AI 审查 AI 是 Stop Hook 的子功能——当 Agent 认为任务完成时，Stop Hook 会触发 AI 自审查，确保真的完成。

### Exit Code 语义

| Code | 语义 | 场景 |
|------|------|------|
| 0 | 放行 | 验证通过 |
| 1 | 警告 | 非关键问题，可选处理 |
| 2 | **阻断** | 验证失败，Agent 必须继续 |
| 3 | 需要人工确认 | 高危操作，Agent 不可自动放行 |

### 安全拦截规则

| 场景 | 拦截命令/文件 |
|------|---------------|
| 危险命令 | `rm -rf`, `DROP TABLE`, `git push --force`, `:!`, `sudo`, `chmod 777` |
| 敏感文件 | `.env`, `credentials`, `secrets`, `application-prod` |
| 依赖破坏 | `package-lock.json`, `poetry.lock`, `pom.xml` |

---

## Ralph Wiggum Loop

> 此模式专门解决 AI 的**自我评估偏差**——模型倾向于给自己的输出打高分，需要外部强制验证来打破这个偏差。

```
Agent: "写完了，看起来没问题"
   ↓ Stop Hook 触发
Harness: "跑过测试了吗？没有？继续干"
   ↓ 验证失败
Agent: "我改..."
   ↓ 再次 Stop Hook
Harness: "再验一次，通过才能停"
```

### 两振出局

```bash
if [ "$RETRY_COUNT" -ge 2 ]; then
  echo "升级人类处理"
  exit 0  # 放行
fi
```

---

## 三层反馈循环系统

### 层级说明

| 层级 | 说明 | 触发条件 |
|------|------|----------|
| **LOCAL** | 本地反馈，快速实验 | 开发/测试环境 |
| **PUSH** | 配置中心，版本管理 | 性能提升 > 10% |
| **PROD** | 生产环境，全局生效 | 通过灰度验证 |

### 上升机制

- LOCAL 层验证改进后，推送到 PUSH 层
- PUSH 层验证性能达标后，推送到 PROD 层

### 下降机制

- PROD 层检测异常，自动回滚到上一版本
- PUSH 层可手动回滚到任意历史版本
- LOCAL 层自动回滚，无需人工介入

### 触发条件

| 条件 | 说明 | 默认值 |
|------|------|--------|
| 最小样本 | 需要积累足够执行数据 | 10 次 |
| 性能阈值 | 成功率低于此值触发优化 | 70% |
| 进化间隔 | 避免频繁进化 | 1 小时 |

### 进化内容

- **参数调整**：温度、top_p、max_tokens 等 LLM 参数
- **策略切换**：调整工具选择、记忆检索策略
- **能力扩展**：注册新技能、启用新工具

---

## 观测驱动控制与 Hooks 的集成

观测驱动控制与 Hooks 形成**双向闭环**：

| 方向 | 说明 | 示例 |
|------|------|------|
| Hooks → 观测 | Hooks 执行产生观测数据 | Stop Hook 记录验证结果 |
| 观测 → Hooks | 观测触发额外的 Hooks | 检测到异常 → 触发 PreToolUse 校验 |

**观测驱动控制示例**：

- 检测到高失败率异常时，动态注入 PreToolUse 校验钩子
- 观测到异常模式时，触发 Stop Hook 进行强制验证

---

## 观测驱动控制与两振出局的集成

观测驱动控制与两振出局形成**分层防御**：

| 层级 | 机制 | 触发条件 |
|------|------|---------|
| 第1层 | 观测驱动控制 | 实时检测，自动修复 |
| 第2层 | 两振出局 | 重试 2 次后升级 |
| 第3层 | 人类介入 | 前两层均失败 |

---

## 关键参数

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| 最大重试次数 | 2 | 两振出局，防止无限循环 |
| 类型检查超时 | 60s | 避免阻塞过长 |
| 测试超时 | 300s | 大项目适当放宽 |
| 最小样本数 | 10 | 触发进化所需的执行数据量 |
| 性能阈值 | 70% | 触发优化的成功率阈值 |
| 进化间隔 | 1小时 | 避免频繁进化 |

---

## 评测系统集成

> 评测模块（`apps/evaluation/`）提供 Benchmark、Grader、RegressionDetector 能力，服务于反馈循环系统。

### 与反馈系统的集成

| 评测功能 | 反馈系统应用 | 说明 |
|---------|-------------|------|
| **Benchmark** | LOCAL/PUSH/PROD 效果评估 | 验证优化策略有效性 |
| **Grader** | Evaluator 质量评分 | 与 TriAgent 的 Evaluator 协作 |
| **RegressionDetector** | 能力退化检测 | 触发反馈循环 |
| **Tracker** | 轨迹分析 | Format Affinity 数据来源 |

### 数据流

```
反馈循环系统
     │
     ├──▶ LOCAL 评估 ──▶ Benchmark.run() ──▶ 优化策略验证
     │
     ├──▶ PUSH 评估 ──▶ Grader.grade() ──▶ 质量评分
     │
     └──▶ PROD 评估 ──▶ RegressionDetector.check() ──▶ 退化预警
```

### 核心组件

| 组件 | 位置 | 功能 |
|------|------|------|
| `Benchmark` | `apps/evaluation/benchmarks.py` | 任务级评测基准 |
| `LLmGrader` | `apps/evaluation/grader.py` | LLM 驱动的质量评分 |
| `RegressionDetector` | `apps/evaluation/regression.py` | 能力回归检测 |
| `TraceTracker` | `apps/evaluation/tracker.py` | 执行轨迹追踪 |

---

## 与其他模块的关系

| 模块 | 关系 |
|------|------|
| 执行系统 | Hook 拦截点集成 |
| 观察系统 | Hook 执行产生观测数据 |
| 权限系统 | 两振出局触发人类介入 |
| 评测系统 | Benchmark/Grader/RegressionDetector 效果评估 |

---

## 相关文档

- [Harness 索引](./index.md) - Harness 完整定义
- [执行系统](./execution.md) - Agent 循环执行
- [观察系统](./observability.md) - 状态监控
- [评测系统](./index.md) - Benchmark/Grader/RegressionDetector（在 apps/evaluation/ 模块）

---

*最后更新: 2026-04-14*

---

## 证据索引（Evidence Index｜抽样）

- HookPhase 接线：`core/harness/execution/loop.py: BaseLoop.run()`
- HookManager 默认 hooks：`core/harness/infrastructure/hooks/hook_manager.py`
- 审批前扫描（security_scan）：`core/harness/infrastructure/hooks/builtin.py`
