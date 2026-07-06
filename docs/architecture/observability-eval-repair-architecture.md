# 评估 / 诊断 / 修复体系架构（As-Is 存档）

> 本文档存档 aiPlat "评估—诊断—告警—修复" 全链路的当前真实架构，含代码交叉验证证据（file:line）。
> 遵循根 `CLAUDE.md` §规则5：所有事实性声明附带 grep/file:line 证据。

last_synced: 2026-07-06
status: as-is
owner: harness/observability + evaluation

---

## 0. 一句话总览

系统有 **三套并行评估架构** + **五个管理画面** + **八条自动修复能力**。三者过去彼此独立、存在重复与断裂；本轮（提交 `a8371ce`→`8f0e22b`）完成收敛与接线，形成 "评估→诊断→告警→建议→人工审批→修复" 的闭环，且**自主写入刻意默认关闭**。

---

## 1. 三套评估架构（评估对象各不相同）

| 体系 | 评估对象 | 位置 | 触发 |
|------|---------|------|------|
| A. 三评估器 | 单次输出 / 生成内容 / 代码 diff | 见 §1.1 | 旁路/pipeline/anomaly |
| B. 诊断中心（32 维） | 系统级：代码/架构/知识/安全/runtime | `core/api/routers/diagnostics.py` | 后台每 300s（`server.py:1352`） |
| C. 管理端告警 | 四层聚合指标阈值 | `aiPlat-management/management/api/alerting.py` | 每 60s（`server.py:174`） |

### 1.1 三评估器（A）
| 评估器 | 位置 | 定位 |
|------|------|------|
| 离线 eval | `core/harness/evaluation/` (`eval_runner.py`, `eval_metrics.py` 6维, `workbench.py` 阈值门, `compare.py` 纯代码回归判定) | 运行输出质量 |
| tri_agent | `core/harness/execution/langgraph/graphs/tri_agent.py` | 循环内 Planner→Generator→Evaluator |
| autoreview | `core/engine/skills/autoreview/` | diff-only 代码审查（温度分层/硬投票/MoA） |

**收敛（本轮）**：三者统一到 `workbench.validate_report` 的 `{pass, score, issues}` schema
（`review_report.py:to_evaluation_report`、`tri_agent.py:_to_evaluation_report`；`a8371ce`）。

---

## 2. 五个管理画面 → 后端映射

| 画面 | 前端 | 关键 API |
|------|------|---------|
| 诊断程序 | `pages/Diagnostics/Diagnostics.tsx` | `POST /api/core/diagnostics/run-all`、`/guard/run`、`/latest` |
| 系统概览 | `pages/SystemOverview/SystemOverview.tsx` | `GET /api/core/overview`（四层聚合，`overview.py:230`） |
| 修复中心 | `pages/Diagnostics/RepairCenter.tsx` | `/repairs-latest` + **`/repairs/history`**（本轮新增） + **`/goals`**（本轮新增） |
| Agent评估 | `pages/Diagnostics/EvalDashboard.tsx` | `GET /api/core/evaluation/overview`（含 **`production_success`**，本轮新增） |
| 告警中心 | `pages/Alerts/Alerts.tsx` | `GET /api/alerting/alerts`（本轮合并 core 告警） |

---

## 3. 本轮修复的问题（原分析→现状）

### 3.1 重复/重叠 → 已收敛
| 问题 | 修复 | 证据 |
|------|------|------|
| 告警双轨断裂：管理端只算层指标，core 的熵/漂移/危机/文档告警不进告警中心 | 新增统一聚合 + 管理端合并 | `diagnostics.py:1685 aggregate_all_alerts`、`1767 get_all_alerts`；`server.py:174` 合并 `core:`/`mgmt:` |
| 评估序列化重复（router 手工 50 行） | 抽取共享序列化 | `eval_runner.py:122 serialize_eval_result`（router + loop 共用） |
| 三评估器 schema 各异 | 统一 EvaluationReport | `a8371ce`（见 §1.1） |

### 3.2 真实性缺口 → 已补
| 缺口 | 修复 | 证据 |
|------|------|------|
| Agent 真实运行质量非自动评估（Agent评估页常空） | 每次运行 fire-and-forget 6维自动打分 | `base.py:223 _try_auto_score_run`；`eval_runner.py:184 persist_runtime_eval`（保留上限） |
| 无生产真实任务成功率 | 从 auto-runtime 结果连续汇总 | `evaluation.py:160 production_success`（仅统计 `eval_set_id=="auto-runtime"`） |

### 3.3 自动修复 → 已可见 + 已闭环
| 缺口 | 修复 | 证据 |
|------|------|------|
| 修复中心 ≠ 真实修复全景 | 汇入自愈/AutoLearner/autoreview 历史 | `diagnostics.py:1059 aggregate_repair_history` |
| 诊断发现不驱动修复 | 诊断→建议→人工审批→执行闭环 | `diagnostics.py:1145 list_repair_goals`、`1164 execute_repair_goal`；`goal_executor.py:145 execute_goal` |

---

## 4. 自动修复能力全景（8 条）

| # | 能力 | 自动 | 已接线 | 证据 |
|---|------|:---:|:---:|------|
| 1 | 流水线自愈（5 策略） | ✅4/5 | ✅ | `pipeline_engine.py:4484-4581` |
| 2 | GoalExecutor 自主循环 | 定义 | ❌ 未启用（安全） | `goal_executor.py:63 enabled=False` |
| 3 | autoreview 自动修 P2 | ⚠️ | ✅ | `autoreview/auto_fixer.py` |
| 4 | 学习/canary 回滚 | ✅ | ✅ | `learning/autorollback.py`、`deployment/canary.py` |
| 5 | AutoLearner 草稿+确认 | ✅高置信 | ✅ | `learning/__init__.py:372` |
| 6 | ToolBootstrap | ⚠️只读 | ✅ | `optimization/tool_bootstrap.py` |
| 7 | JSON/消息修复 | ✅ | ✅ | `postprocess.py:45`、`pipeline_engine.py:972` |
| 8 | on-error 反思 | ✅ | ✅ | `hooks/on_error_reflector.py` |

---

## 5. 诊断→修复闭环安全模型（P1, `8f0e22b`）

闭环补全了 "诊断→建议→人工审批→执行"，但**刻意不开启自主后台执行**：

| 门禁 | 机制 | 证据 |
|------|------|------|
| 无自主循环 | 未调用 `GoalExecutor(enabled=True).start()` | grep 确认为空 |
| 执行默认关闭 | `AIPLAT_GOAL_EXECUTE_ENABLED` 默认 false → 403 | `diagnostics.py:1140 _goal_execute_enabled` |
| 仅可逆目标 | 非 `auto_executable` → 400 | `diagnostics.py:1164` 内校验 |
| 逐项人工触发 | 每次执行是 UI 显式动作 | `RepairCenter.tsx` 执行按钮仅 `execute_enabled` 时显示 |

---

## 6. 本轮提交记录

| 提交 | 内容 |
|------|------|
| `a8371ce` | Hermes Phase Gate 借鉴 — 三评估器收敛 + 盲区修复 |
| `f2d0dbe` | CLAUDE.md 瘦身 -19% + 分流守卫 |
| `7546087` | P0-1 告警聚合 + P0-2 Agent 自动打分 |
| `2bce6a1` | P1 修复中心统一视图 |
| `108a597` | P2 生产任务成功率 |
| `8f0e22b` | P1 诊断→修复闭环（安全默认） |

---

## 附录 A：证据索引（可复现）

```bash
# 告警聚合
grep -n "aggregate_all_alerts\|get_all_alerts" aiPlat-core/core/api/routers/diagnostics.py
grep -n "get_core_alerts\|core:" aiPlat-management/management/server.py

# Agent 自动打分
grep -n "_try_auto_score_run" aiPlat-core/core/harness/execution/loop/base.py
grep -n "serialize_eval_result\|persist_runtime_eval" aiPlat-core/core/harness/evaluation/eval_runner.py

# 生产成功率
grep -n "production_success" aiPlat-core/core/api/routers/evaluation.py

# 修复历史 + 闭环
grep -n "aggregate_repair_history\|list_repair_goals\|execute_repair_goal\|_goal_execute_enabled" aiPlat-core/core/api/routers/diagnostics.py
grep -n "execute_goal" aiPlat-core/core/harness/optimization/goal_executor.py

# 安全: 确认无自主循环启用
grep -rn "enabled=True).start()\|\.enabled = True" aiPlat-core/core/api aiPlat-core/core/server.py | grep -i goal   # 预期空
```
