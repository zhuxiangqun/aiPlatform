---
name: test_case_generation
display_name: 测试用例生成
description: >-
  根据PRD生成测试用例。Agent模式→对话测试问题；代码模式→pytest文件。
  触发条件：QA阶段自动触发。
category: analysis
version: 2.1.0
status: enabled
execution_mode: prompt
execution_type: prompt
triggers:
  - 生成测试用例
  - test case
  - 写测试
permissions:
- fs:write
- fs:read
effects:
- type: write
  resources:
  - filesystem:/tmp
  idempotent: false
  rollback_available: true
input_schema:
  prd:
    type: object
    required: true
  agent_app:
    type: object
    required: false
    description: Agent应用产出(Agent模式时必传)
output_schema:
  test_cases:
    type: array
    required: true
    description: "代码模式→pytest文件列表; Agent模式→对话测试问题列表"
  report:
    type: string
    required: true
    description: Markdown格式测试报告
protected: true
idempotent: false
completion_criterion: |
  1. 每个 acceptance_criteria 至少有一个测试(case或问题)
  2. Agent模式: 覆盖happy+边界+异常, 问题用自然语言模拟真实用户
  3. 代码模式: 每个断言含失败提示信息
keywords:
  objects:
  - 测试用例
  - 测试问题
  - pytest
  actions:
  - 生成
  - 编写
trigger_conditions:
- when: QA阶段自动触发
  query: 生成测试
skip_when: 代码模块过小或已有充分测试覆盖
---

# 测试用例生成（Engine）v2.1

## Step 0: 模式检测

```
检查上下文中有 agent_app 或 _generated_agent
  → YES: 走 "Agent 对话测试" (Step A)
  → NO:  走 "代码 pytest" (Step B)
```

---

## Agent 对话测试 SOP

### Agent Step 1: 从 PRD 提取测试问题

对每条 acceptance_criteria，生成 1-3 句自然语言测试问题：

- **Happy path**: 模拟用户正常使用
- **边界**: 测试极限情况
- **异常**: 测试错误处理

问题必须用**真实用户说话的方式**——不技术化，不写"测试"二字。

示例:

| AC | Happy path 问题 | 边界/异常问题 |
|----|------|------|
| 用户上传视频后返回 task_id | "请帮我上传这个视频文件" | "我传的文件500MB，能处理吗？" / "我上传了一个空的文件" |
| 分析结果包含标签/语音/动作 | "刚才分析的结果里有哪些标签？" | "视频没有声音你也能分析吗？" |

### Agent Step 2: 标注预期行为

每个问题标注最低预期：

| 测试问题 | 最低预期 |
|---------|------|
| "请帮我上传这个视频" | 返回 task_id；提示上传成功 |
| "我传的文件500MB" | 返回文件大小限制提示或开始处理 |
| "我上传了空文件" | 返回"文件无效"或"不支持处理"提示 |

### Agent Step 3: 组织为测试计划

**先输出 JSON**（紧凑一行，不要 ``` 包裹），**再输出 Markdown 报告**。

JSON:
```json
{
  "mode": "agent_conversation",
  "test_questions": [...]
}
```

Markdown 报告:
```markdown
## 对话测试计划 — {项目名称}

### 汇总
| 指标 | 值 |
|:---|---:|
| 测试问题总数 | {total} |
| 覆盖 FR | {n} |
| Happy path | {happy} |
| 边界 | {boundary} |
| 异常 | {exception} |

### 测试问题
| # | FR | 问题 | 最低预期 |
|:---|----|------|------|
| 1 | FR-001 | 我用手机拍摄的视频能上传吗？ | 支持MP4上传，显示元数据 |
```

---

## 代码 pytest SOP（保留，向后兼容）

### Code Step 1: 建立测试范围

读取 PRD 的 functional_requirements 和 acceptance_criteria，按风险分级策略：高风险接口→全组合判定表；标准→核心+2边界+1异常；低风险→happy+1异常。

### Code Step 2: 生成 pytest 文件

用 `## FILE: tests/{name}_test.py` 格式输出可执行 pytest 代码，每个断言含失败提示信息。

### Code Step 3: 输出 Markdown 测试报告

汇总表 + 需求覆盖表 + 失败详情表 + JSON 决策摘要。

---

## 输出禁令

| ❌ 禁止 | ✅ 必须 |
|--------|--------|
| Agent 模式输出 `## FILE: test_*.py` | Agent 模式输出对话测试问题 |
| 代码模式输出"请帮楼上个视频" | 代码模式输出 `def test_xxx()` |
| 测试问题只有 happy path | 至少覆盖 happy + 边界 + 异常 |
| 预期写"正常返回" | 写明具体预期值 |
