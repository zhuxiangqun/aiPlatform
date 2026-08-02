---
name: test_executor
display_name: 测试用例执行器
description: >
  Agent模式: 逐条发对话测试问题给Agent，评估回复。
  代码模式: 读取pytest文件，subprocess执行，解析输出。
category: execution
version: 2.1.0
status: enabled
execution_type: prompt
tags:
  - 测试
  - 执行
  - Agent验证
triggers:
  - 执行测试
  - 跑用例
  - pytest
permissions:
  - file:read
  - file:write
effects:
  - type: read
    resources: ["filesystem:test*"]
    idempotent: true
    rollback_available: false
  - type: write
    resources: ["filesystem:test_output"]
    idempotent: false
    rollback_available: true
input_schema:
  test_cases:
    type: array
    required: true
    description: 测试用例数组(来自test_case_generation)
  mode:
    type: string
    required: false
    description: "agent_conversation|code_pytest"
  agent_name:
    type: string
    required: false
    description: Agent模式下的被测Agent名
output_schema:
  markdown:
    type: string
    required: true
    description: Markdown测试报告
trigger_conditions:
  - 用户提供测试用例
  - pipeline QA阶段自动触发
---

# 测试用例执行器 v2.1

## Step 0: 模式检测

```
检查 mode 或上下文
  → "agent_conversation" → Agent对话执行SOP
  → "code_pytest" 或默认 → 代码pytest执行SOP(保留)
```

---

## Agent 对话执行 SOP

### Agent Step 1: 准备对话环境

1. 确认 agent_name 可用(输入中存在)
2. 确认 test_cases 每条包含 question 和 min_expectation

### Agent Step 2: 逐条对话测试

对每条测试问题:
1. `core_chat(agent_name, question)` → 获取 Agent 回复
2. 记录: 问题 / Agent回复 / trace_id / 耗时
3. 评估: 回复是否满足 min_expectation

**重要**: 必须通过 core_chat(agent_name)，不直接调 Skill。保证测试也走 ReActLoop。

### Agent Step 3: 平台能力验证

每轮对话后检查运行时数据确认能力激活:
- `_trace_{id}.domain_id` 非空 → Domain Router ✅
- `_trace_{id}.context_enriched` → Context Bus ✅
- `_trace_{id}.model_tier` 非空 → Model Tier ✅
- POST_LOOP 事件有记录 → SECI ✅
- save_interaction 有日志 → Memory ✅
- core_chat 返回 trace_id → Trace ✅

### Agent Step 4: 评估与汇总

| 维度 | 1-5分 | 含义 |
|------|:---:|------|
| 准确性 | | 回复是否满足预期 |
| 完整性 | | 是否遗漏关键信息 |
| 稳定性 | | 有无幻觉/矛盾 |

### Agent Step 5: 生成报告

```markdown
## 测试报告 — {agent_name}
**测试模式**: Agent 对话验证
**执行时间**: {timestamp}

### 汇总
| 指标 | 值 |
|:---|---:|
| 问题总数 | {total} |
| ✅ 通过 | {passed} |
| ❌ 失败 | {failed} |
| 通过率 | {pass_rate}% |

### 平台能力验证
| 能力 | 状态 | 详情 |
|------|:---:|------|
| Domain Router | {✅/❌} | {详情} |
| Context Bus | {✅/❌} | {详情} |
| Model Tier | {✅/❌} | {详情} |
| SECI | {✅/❌} | {详情} |
| Memory | {✅/❌} | {详情} |
| Trace | {✅/❌} | {详情} |

### 对话测试详情
| # | 问题 | Agent回复 | 预期 | 评估 |
|:---|------|------|------|:---:|
| 1 | {question} | {reply[:100]} | {min_expectation} | {✅/❌} |

### 决策摘要
```json
{"pass_rate": 85.7, "recommendation": "APPROVED", "issues": [...]}
```

---

## 代码 pytest SOP（保留）

### Code Step 1-4

- 解析 pytest 文件
- 构建请求并执行
- 判定 PASS/FAIL/SKIP/ERROR
- 生成 Markdown 报告

---

## 反模式

| ❌ 错误 | ✅ 正确 |
|--------|--------|
| Agent 模式跑 pytest | Agent 模式用 core_chat 对话测试 |
| 代码模式发"请帮我上传" | 代码模式用 pytest 断言 |
| 只测 happy path | 必须覆盖边界 + 异常 |
| 不验证平台能力 | Agent 模式检查 _trace_ 字段 |
