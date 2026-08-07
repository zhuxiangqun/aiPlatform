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
  test_results:
    type: array
    required: true
    description: "逐条测试结果数组，每项含id/question/min_expectation/result/score/reason"
  pass_rate:
    type: integer
    required: true
    description: "通过率百分比(0-100)"
  recommendation:
    type: string
    required: true
    description: "APPROVED|CONDITIONAL_APPROVAL|REJECTED"
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

### Agent Step 2: 逐条文档分析

对 test_cases 中的每条测试用例，**逐一分析**（不需要调用 core_chat，基于文档即可）:

1. 读取每条测试用例的全部字段: id, ac_ref, category, question, min_expectation
2. 分析 min_expectation 是否明确、可验证
3. 分析测试问题是否覆盖对应的 FR 验收标准
4. 分析覆盖类型(happy/boundary/exception)是否完整

对每条给出:
- result: ✅(通过) / ❌(失败) / ⚠️(需改进)
- score: 1-5 分
- reason: 简短理由(1-2句)

### Agent Step 3: 汇总评分

按 3 维对整体测试用例集评分(1-5):

| 维度 | 含义 |
|------|------|
| 完整性 | min_expectation 是否明确可验证 |
| 覆盖度 | 是否覆盖全部 FR 验收标准 |
| 合理性 | 测试问题是否模拟真实用户场景 |

### Agent Step 4: 生成报告（强制格式）

**必须输出以下 JSON**（紧凑一行，不要 ``` 包裹）:

```json
{
  "pass_rate": 75,
  "recommendation": "CONDITIONAL_APPROVAL",
  "test_results": [
    {
      "id": "AQ-001",
      "question": "输入合法视频链接后点击解析按钮",
      "min_expectation": "5秒内返回视频标题和可播放地址",
      "result": "✅",
      "score": 4,
      "reason": "min_expectation 有具体时间限制和返回内容，可验证"
    },
    {
      "id": "AQ-002",
      "question": "上传一个500MB的MP4文件",
      "min_expectation": "3秒内显示视频基本信息",
      "result": "✅",
      "score": 5,
      "reason": "格式、大小、时间限制明确，边界清晰"
    }
  ],
  "summary": "12条测试用例覆盖4个FR，happy/boundary/exception 完整",
  "issues": [
    {
      "id": "AQ-012",
      "severity": "medium",
      "description": "缺少明确的删除确认消息",
      "suggestion": "删除后返回确认提示并更新记录列表"
    }
  ],
  "strengths": [
    "边界测试覆盖充分（文件大小、格式限制）",
    "min_expectation 具体可验证"
  ]
}
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
| Agent 模式只输出 JSON 总结 | Agent 模式输出包含逐条 test_results 的 JSON |
| 代码模式发"请帮我上传" | 代码模式用 pytest 断言 |
| 只测 happy path | 必须覆盖边界 + 异常 |
| test_results 数组只有 1-2 条 | 必须逐条列出，与上游 test_cases 数量一致 |
| reason 只写"通过"/"不通过" | 必须写具体的 1-2 句理由 |
| 不验证平台能力 | Agent 模式检查 _trace_ 字段 |
