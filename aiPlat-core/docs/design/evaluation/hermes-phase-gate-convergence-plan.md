# Hermes Phase Gate 借鉴：评估盲区分析 + 三评估架构收敛实施计划

> 本文档把"借鉴 Hermes 容错/循环引擎文章"的结论落成可执行工程计划。核心不是"补缺失能力"，而是**收敛已有的三套评估架构**并**把确定性否决闸门接进主执行循环**。
>
> 所有事实性声明附带代码交叉验证证据（file:line + grep），遵循根 `CLAUDE.md` §规则5 与 §0.1。

last_synced: 2026-07-06
status: implemented
owner: harness/evaluation
---

> **实施状态（2026-07-06）**：全部 5 项改动已落地并验证。
> - 改动 1（否决闸门接进 loop）：`loop/_facade.py:117 _acceptance_gate` + `:162 _apply_acceptance_veto`，在 DONE/FINAL 与 auto-done 两处终止路径调用。
> - 改动 2（统一 schema）：`review_report.py:to_evaluation_report` + `tri_agent.py:_to_evaluation_report`，均通过 `workbench.validate_report`。
> - 改动 3（修 placeholder）：`tri_agent.py` 硬编码 0.85 已删除，改为 `run_events`/`security_findings` 真实提取。
> - 改动 4（temp 0.0）：`integration.py:1115` + `tri_agent.py` evaluator `_llm_temperature=0.0`（planner/generator 不变）。
> - 改动 5（语义接线断言）：`tests/wiring/test_acceptance_gate_wired.py`（7 tests 全绿）。
> - 回归：`tests/wiring/` 77 tests 全绿；`test_react_loop_done_detection.py` 2 tests 全绿。

## 0. 背景与定位

Hermes 两篇文章（容错四层纵深防御 / 循环引擎六层确定性约束）的对标表 7.2 声称 aiPlat 缺失 8 项能力。经代码核验，**6/8 已存在**（无进展计数器 `intervention/howl.py:63`、Credential Pool `aiPlat-infra/.../credential_pool.py`、上下文压缩 `memory/compression.py`、确定性快速判断 `evaluation/compare.py:48` + Howl、ReAct 循环 `loop/_facade.py:42`、迭代上限 `loop/base.py:215`）。

真正值得借鉴的收敛为一个主题：**Hermes 的 Phase Gate 之所以有效，是因为"评估"与"拦截"是同一段内联代码——判定即否决。而 aiPlat 把它拆成了"三套离线评估"+"主循环自行终止"两半，没有任何机制检查这两半是否连着。**

---

## 1. 盲区分析（为什么现有体系发现不了这些差距）

aiPlat 有两套检查体系，这些差距恰好掉进它们中间：

```
评估框架（3套）  →  评"运行时输出好不好"（黑盒行为，看不到自身接线拓扑）
静态守卫         →  查"grep/AST 层结构违规"（跨层import、0 caller）
                ↑
           盲区：语义接线正确性
   "对的函数，在对的地方被调用，跑在真实(非placeholder)数据上，且全局只有一个"
```

### 1.1 三套评估框架为何看不到

| 架构 | 评估对象 | 盲区原因 |
|------|---------|---------|
| 一（离线 eval `evaluation/eval_runner.py`） | agent 对 eval set 的答案质量 | eval set 仅 normal/missing_info/tool_failure/high_risk/noise，无一条测"loop 是否否决假 DONE"（`eval_runner.py:350`） |
| 二（`tri_agent.py`） | 生成内容质量 | 自身跑在 `_extract_metrics_from_generated:250-260` 硬编码 0.85 假数据上——自身失明 |
| 三（`autoreview`） | diff 内 P0/P1/P2 | diff-only（`handler.py:24` `FORBIDDEN_TARGETS` 拒绝全仓）+ 显式不读 CLAUDE.md（`handler.py:46`）。跨文件"未接线"事实看不见 |

### 1.2 静态守卫为何也漏检（关键）

| 差距 | 为何绕过守卫 | 验证证据 |
|------|------------|---------|
| 否决闸门未接进 loop | `apply_threshold_gate` **有** caller（离线 eval 路径），§5.30 只查"≥1 caller"，通过 | `grep -rn apply_threshold_gate core/` → `integration.py:1144`（离线 auto-eval JSON 解析路径）、`runs_eval.py:66`（路由）；`grep -rn "get_active_change_contract\|acceptance_criteria" core/harness/execution/loop/` → **空** |
| tri_agent placeholder | 能编译 + 有 caller + 有产出；唯一线索是 docstring `(placeholder implementation)`，arch guard 不扫 "placeholder" | `grep -rn placeholder scripts/arch_guard_rules.yaml scripts/architecture_guard.sh` → **空** |
| 三评估未收敛成一个门 | §10 API入口唯一性 / §13 相同签名多定义 **无对应脚本**，仅书面原则；三判官签名各异 | `grep -rni "入口唯一\|parallel implementation\|相同函数签名" scripts/arch_guard_rules.yaml` → **空** |
| 完成判定 judge 非 temp=0.0 | 配置语义属性，无扫描项覆盖 | `integration.py:1115` `sys_llm_generate(llm, msgs, ...)` 未传 temperature；`tri_agent.py:236/361` `_evaluator.run(...)` 未传 temperature |

### 1.3 盲区结论

这四个差距 **既不是"坏输出"**（评估框架抓不到）**也不是可 grep 的干净违规**（静态守卫抓不到）。它们属于"语义接线正确性"，是当前无人负责的第三类检查。第 5 项改动就是为这一类盲区建立自动断言。

---

## 2. 三套评估架构现状（As-Is）

| # | 架构 | 位置 | 定位 | 关键能力 | 缺陷 |
|---|------|------|------|---------|------|
| 一 | 离线评估子系统 | `core/harness/evaluation/` | 旁路 / post-hoc | `auto.py:70-94` LLM-as-Judge（已强制 evidence + 信息不足倾向 fail）；`workbench.py:80-133` `apply_threshold_gate` **确定性否决**（维度低于阈值强制 pass=False）；`compare.py:48-152` `pairwise_judge` **纯代码零 LLM** 判 improved/flat/regressed + 贝叶斯不确定性；`eval_runner.py:230-257` 关键词验收 | 未强制 temp=0.0；否决逻辑只在离线路径，未接主 loop |
| 二 | 循环内共识评估器 | `execution/langgraph/graphs/tri_agent.py` | 在线（LangGraph，未接主 ReActLoop） | 独立 Evaluator（`:207-248`），APPROVED/REJECTED 驱动迭代（max 3，`:305`） | `_extract_metrics_from_generated:250-260` **placeholder 硬编码 0.85**；无 temp=0.0；无 evidence 强制 |
| 三 | Autoreview 代码审查 | `core/engine/skills/autoreview/` | 旁路 / diff-only | 温度分层（ref 0.6/agg 0.3，`handler.py:186,212`）、硬投票面板、MoA deep 聚合、`scope_governor` 确定性范围否决、证据卡 `build_evidence()`、持久化 | 无（此架构已超 Hermes 描述，仅作为 schema 收敛目标，不改行为） |

---

## 3. 五项改动

每项标注：现状 → 问题 → 改动 → 涉及文件 → 验收 → 风险 / 工作量。

### 改动 1：把确定性否决闸门接进主 ReActLoop（★最高价值）

- **现状**：`_facade.py:267-311`（`DONE:`/`FINAL:` 终止）与 `:315-344`（纯文本 auto-done）在 LLM 声称完成时**直接置 `FINISHED` 返回**，从不校验验收标准。验收机器已存在但离线：`ActiveChangeContract.acceptance_criteria`（`kernel/execution_context.py:300-323`，在 `syscalls/skill.py:732-753` 写入）+ `workbench.apply_threshold_gate`（`workbench.py:80-133`）。
- **问题**：这正是 Hermes 的"Phase Gate 否决 LLM 的 done"缺口——是**接线缺口，非建设缺口**。
- **改动**：在 `_facade.py` 两处终止路径置 `FINISHED` 之前插入一个**纯代码验收关卡** `_acceptance_gate(state)`：
  1. 通过 `get_active_change_contract()` 读取 `acceptance_criteria`（无契约 → 跳过，保持向后兼容）；
  2. 对每条 criteria 执行确定性检查（复用 `eval_runner._determine_level` 的关键词/文件存在/文件数量判定风格）；
  3. 未通过 → 否决 done：`state.current` 保持 `RUNNING`，向 messages 注入未通过项清单（复用 Howl 注入风格），`state.context["_acceptance_veto"]=reason`，继续循环；
  4. 通过 → 放行 `FINISHED`。
- **涉及文件**：`core/harness/execution/loop/_facade.py`（新增 `_acceptance_gate`，两处调用）；只读复用 `kernel/execution_context.py`、`evaluation/eval_runner.py`。
- **配置驱动**（遵守 §5.16 决策边界 = Agent 负责"基于完成度终止"）：闸门行为受 env `AIPLAT_ACCEPTANCE_GATE_ENABLED`（默认 true）+ 迭代保护（否决不得突破 `max_steps`，防止死循环）。
- **验收**：
  - `python -m py_compile core/harness/execution/loop/_facade.py`
  - 新增 `tests/wiring/test_acceptance_gate_wired.py`：断言终止路径调用 `_acceptance_gate`（见改动 5）
  - 单测：构造带未满足 acceptance_criteria 的 contract → 断言首次 `DONE:` 被否决、循环继续
- **风险**：中。可能引入循环延长 → 用 `max_steps` 硬上限 + env 开关兜底。**工作量**：中。

### 改动 2：三套评估收敛到统一 EvaluationReport schema（遵守 §10）

- **现状**：三套 schema 各异——离线 `{pass, score, issues}`（`workbench.py`）、tri_agent `APPROVED/REJECTED`（`tri_agent.py:239`）、autoreview `{clean, issues:[P0/P1/P2]}`（`review_report.py`）。
- **问题**：违反根 `CLAUDE.md §10 API入口唯一性`——同一"判定"能力三个并行实现，无统一门。
- **改动**：以 `workbench.py`（已声明 "LLM-agnostic accepts any evaluator report JSON"，`workbench.py:9-11`）为**唯一收敛点**：
  1. 定义/固化 `EvaluationReport` 规范（`pass:bool` + `score:dict` + `issues:list`），作为 `validate_report` 的契约；
  2. tri_agent evaluator 输出适配：`APPROVED/REJECTED` → `{pass, score, issues}`；
  3. autoreview 增加 `to_evaluation_report()` 适配器（P0/P1/P2 → issues + clean → pass），**不改其审查行为**。
- **涉及文件**：`evaluation/workbench.py`（固化 schema）、`execution/langgraph/graphs/tri_agent.py`（`_evaluator_wrapper` 返回适配）、`core/engine/skills/autoreview/review_report.py`（新增适配方法）。
- **验收**：`validate_report()` 对三套 evaluator 输出均返回 `(True, "ok")`；新增契约测试。
- **风险**：低（适配层，不改判定逻辑）。**工作量**：中。

### 改动 3：修复 tri_agent placeholder 指标

- **现状**：`tri_agent.py:250-260` `_extract_metrics_from_generated` 返回硬编码 `test_pass_rate=0.85` 等 → `_evaluate_dimensions`（`:262-298`）的确定性维度门跑在假数据上。
- **问题**：架构二自身失明（§1.1），且是死代码级 stub 掩盖（违反 §5.30 精神）。
- **改动**：从真实来源提取指标：
  - `test_pass_rate` ← run_events 中 test_runner 结果（复用 `eval_runner._collect_events` 风格）；
  - `vulnerabilities`/`permission_issues` ← 复用 autoreview P0 security 计数（改动 2 收敛后可直接读 issues）；
  - 无真实数据 → 返回 `None` 并标注 `evidence_missing`，**禁止**回填假分（对齐 §5.70 执行真实性）。
- **涉及文件**：`execution/langgraph/graphs/tri_agent.py`。
- **验收**：单测断言无 run_events 时 `_extract_metrics_from_generated` 不再返回 0.85 常量；`grep -rn "test_pass_rate=0.85" core/` → 空。
- **风险**：低。**工作量**：低。

### 改动 4：完成判定类 judge 强制温度 0.0（Hermes evaluator 铁律）

- **现状**：`integration.py:1115` auto-eval `sys_llm_generate(llm, msgs, ...)` 未传 temperature；`tri_agent.py:236/361` `_evaluator.run(...)` 未传 temperature（走模型默认）。
- **问题**：Hermes 强调 evaluator temp=0.0 最大化判定一致性；当前判定不可复现。
- **改动**：
  - auto-eval 调用点显式 `temperature=0.0`；
  - tri_agent evaluator 走 temp=0.0（通过 evaluator agent 配置或调用参数）；
  - **autoreview 保持 0.3-0.6 不动**（审查需要发散，`handler.py:186,212` 是刻意设计）。
- **涉及文件**：`core/harness/integration.py`、`execution/langgraph/graphs/tri_agent.py`。
- **验收**：`grep -n "temperature=0.0" core/harness/integration.py` 命中 auto-eval 调用点；新增断言测试（见改动 5）。
- **风险**：极低。**工作量**：低。

### 改动 5：语义接线断言测试（为盲区建立自动守卫）

- **现状**：`tests/wiring/` 只做 caller 计数（`test_methods_wired.py` grep "≥1 caller"），不做语义位置断言。
- **问题**：改动 1/3/4 的正确性无自动回归保护，下次仍会掉进同一盲区。
- **改动**：新增 `tests/wiring/test_acceptance_gate_wired.py`，断言语义而非计数：
  1. `_facade.py` 的 `FINISHED` 终止路径调用了 `_acceptance_gate`（AST/grep 双验）；
  2. 完成判定 judge 调用点 `temperature==0.0`（grep `integration.py`）；
  3. 全局只有一个 `validate_report`/EvaluationReport schema 定义（防再度分裂）；
  4. `grep "test_pass_rate=0.85"` 必须为空（placeholder 回归防护）。
- **涉及文件**：`core/tests/wiring/test_acceptance_gate_wired.py`（新建，复用 `conftest.py` 的 `has_production_caller`/`assert_wired`）。
- **验收**：`python -m pytest core/tests/wiring/test_acceptance_gate_wired.py -v` 全绿。
- **风险**：无。**工作量**：低。

---

## 4. 实施顺序与阶段

依赖关系：改动 2（统一 schema）为改动 1/3 提供 issues 数据源；改动 5 依赖 1/3/4 落地后才能断言。

| 阶段 | 内容 | 依赖 | 产出验收 |
|:---:|------|------|---------|
| P1 | 改动 3（修 placeholder）+ 改动 4（temp 0.0） | 无 | 低风险、独立、先落地建立信心 |
| P2 | 改动 2（收敛 schema） | 无（可与 P1 并行） | `validate_report` 接纳三套输出 |
| P3 | 改动 1（接线否决闸门） | P2 提供 issues 契约 | loop 否决假 DONE 单测通过 |
| P4 | 改动 5（语义接线断言测试） | P1/P3/P4 | wiring 测试全绿，盲区被自动守卫 |

---

## 5. 统一验收命令

```bash
cd aiPlat-core

# 语法
python -m py_compile core/harness/execution/loop/_facade.py \
  core/harness/execution/langgraph/graphs/tri_agent.py \
  core/harness/integration.py core/harness/evaluation/workbench.py

# 改动 3 回归：placeholder 已清除
grep -rn "test_pass_rate=0.85" core/ --include="*.py" | grep -v __pycache__   # 期望：空

# 改动 4：温度断言
grep -n "temperature=0.0" core/harness/integration.py                          # 期望：命中 auto-eval

# 改动 1：否决闸门已接进 loop（盲区修复的核心证据）
grep -rn "get_active_change_contract\|_acceptance_gate" core/harness/execution/loop/ # 期望：非空

# 改动 5：语义接线断言
python -m pytest core/tests/wiring/test_acceptance_gate_wired.py -v

# 全量守卫回归（§0.2 执行顺序）
bash ../scripts/architecture_guard.sh
python -m pytest core/tests/wiring/ -v --tb=short
```

---

## 6. 风险与回滚

| 风险 | 缓解 | 回滚 |
|------|------|------|
| 否决闸门导致循环延长/死循环 | `max_steps` 硬上限不可突破 + `AIPLAT_ACCEPTANCE_GATE_ENABLED` env 开关 | 关 env 即恢复旧行为 |
| schema 收敛破坏既有离线 eval 消费者 | 适配层只加不改，`validate_report` 保持向后兼容 | git revert 适配层 |
| temp=0.0 改变 auto-eval 既有基线分数 | 仅判定类 judge 改，审查类不动 | 移除 temperature 参数 |

**接线完成度自检（§5.30 规则 7）**：改动 1 的 `_acceptance_gate` 必须有主 loop 生产 caller（非测试）；改动 5 的 wiring 测试即为其接线断言。

---

## 附录 A：证据索引（可复现）

| 声明 | 验证命令 | 命中 |
|------|---------|------|
| 主 loop 完全未用验收标准 | `grep -rn "get_active_change_contract\|acceptance_criteria" core/harness/execution/loop/` | 空 |
| 否决逻辑仅在离线路径 | `grep -rn "apply_threshold_gate" core/ --include=*.py` | `integration.py:1144`、`runs_eval.py:66`、tests |
| arch guard 不扫 placeholder | `grep -rn placeholder scripts/arch_guard_rules.yaml scripts/architecture_guard.sh` | 空 |
| §10/§13 无脚本强制 | `grep -rni "入口唯一\|parallel implementation\|相同函数签名" scripts/arch_guard_rules.yaml` | 空 |
| tri_agent placeholder | `sed -n '250,260p' core/harness/execution/langgraph/graphs/tri_agent.py` | 硬编码 0.85 |
| auto-eval 无 temp | `sed -n '1112,1116p' core/harness/integration.py` | `sys_llm_generate(llm, msgs, ...)` 无 temperature |
