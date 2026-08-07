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
  header:
    type: object
    required: true
    description: "报告头部: report_id/project/test_mode/date"
  meta:
    type: object
    required: true
    description: "总体统计: total/passed/failed/warnings/pass_rate"
  test_results:
    type: array
    required: true
    description: "逐条测试结果，含上游全部字段+result/score/is_bug/reason"
  bug_summary:
    type: object
    required: true
    description: "Bug清单: total_bugs + bugs[] (severity/title/FR/reproduction/expected/actual/suggested_fix)"
  quality_analysis:
    type: object
    required: true
    description: "质量分析: functional_coverage + case_quality + risk_assessment + root_cause"
  recommendation:
    type: string
    required: true
    description: "APPROVED|CONDITIONAL_APPROVAL|REJECTED"
  improvements:
    type: array
    required: true
    description: "改进建议，按优先级 MUST_FIX|SHOULD_FIX|NICE_TO_HAVE 分组"
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

### Agent Step 2: 逐条分析测试用例

对 test_cases 中的**每条测试用例**逐一分析，不要跳过任何一条:

1. 解析全部字段: id, ac_ref, category, question, min_expectation
2. 判定 result:
   - PASS: min_expectation 明确可验证，覆盖对应 FR
   - FAIL: min_expectation 无法满足(设计缺陷/方法缺陷/逻辑矛盾)
   - WARNING: min_expectation 模糊、无法判定是否满足
3. 判定 is_bug:
   - true: min_expectation 明确但 app 设计/逻辑无法满足(设计缺陷或方法缺陷)
   - false: min_expectation 模糊(用例质量问题)或测试通过
4. 给出 1-5 分和 1-2 句 reason

### Agent Step 3: 生成质量分析

**3a. Functional Coverage Assessment**
- 统计每个 FR 的 acceptance_criteria 总数 vs 被测试覆盖的数量
- 列出未覆盖的 AC

**3b. Test Case Quality Assessment**
- 统计 happy_path/boundary/exception 的分布
- 统计 min_expectation 明确度: 明确/模糊/缺失 的分布

**3c. Risk Assessment**
- 高风险: FR 覆盖不足, 或 boundary/exception 缺失
- 中风险: min_expectation 部分模糊
- 低风险: 所有 AC 覆盖且 min_expectation 明确

**3d. Root Cause Analysis**
对每个 FAIL 或 is_bug=true 的用例，分类根因:
- design_gap: app 设计未覆盖该场景
- requirement_gap: PRD 未定义该场景
- implementation_gap: 实现方式不适用于当前 Agent 模式
- environment_gap: 环境限制(如缺 runtime)

### Agent Step 4: 生成完整报告（强制格式）

**必须输出以下 JSON**（紧凑一行，不要 ``` 包裹）:

```json
{
  "header": {
    "report_id": "TR-2026-0001",
    "project": "视频解析平台",
    "test_mode": "document_analysis",
    "date": "2026-08-07",
    "executor": "test_executor"
  },
  "meta": {
    "total_test_cases": 12,
    "passed": 8,
    "failed": 3,
    "warnings": 1,
    "pass_rate": 66,
    "by_fr": {
      "FR-001": {"total": 5, "passed": 4, "failed": 1},
      "FR-002": {"total": 4, "passed": 3, "failed": 1}
    },
    "by_category": {
      "happy_path": 4, "boundary": 4, "exception": 4
    }
  },
  "test_results": [
    {
      "id": "AQ-001",
      "ac_ref": "FR-001",
      "category": "happy_path",
      "question": "输入合法视频链接后点击解析按钮",
      "min_expectation": "5秒内返回视频标题和可播放地址",
      "result": "PASS",
      "score": 4,
      "is_bug": false,
      "reason": "min_expectation 包含具体时间阈值和返回字段，明确可验证"
    },
    {
      "id": "AQ-003",
      "ac_ref": "FR-001",
      "category": "exception",
      "question": "输入一个不存在的域名链接",
      "min_expectation": "返回链接无效提示",
      "result": "FAIL",
      "score": 2,
      "is_bug": true,
      "reason": "错误处理逻辑缺失——当前 agent 对无效域名返回通用 500 错误，非'链接无效'友好提示"
    },
    {
      "id": "AQ-009",
      "ac_ref": "FR-004",
      "category": "exception",
      "question": "未登录用户能否查看他人记录",
      "min_expectation": "仅返回当前用户自己的记录",
      "result": "WARNING",
      "score": 3,
      "is_bug": false,
      "reason": "min_expectation 合理但依赖运行时权限系统，文档分析无法验证实际隔离效果"
    }
  ],
  "bug_summary": {
    "total_bugs": 2,
    "bugs": [
      {
        "id": "BUG-001",
        "test_id": "AQ-003",
        "severity": "medium",
        "title": "无效域名链接缺少友好错误提示",
        "FR": "FR-001",
        "reproduction": "输入 https://notexist.example.com → 点击解析",
        "expected": "明确提示'链接无效或平台不支持'",
        "actual": "返回通用 500 Internal Server Error",
        "suggested_fix": "在异常处理分支增加域名校验，返回用户友好的错误消息"
      },
      {
        "id": "BUG-002",
        "test_id": "AQ-012",
        "severity": "low",
        "title": "删除历史记录后缺少成功确认",
        "FR": "FR-004",
        "reproduction": "删除一条历史记录",
        "expected": "返回操作成功确认并刷新列表",
        "actual": "直接刷新列表，无成功提示",
        "suggested_fix": "在删除操作完成后增加 toast 提示'✅ 已删除'"
      }
    ]
  },
  "quality_analysis": {
    "functional_coverage": {
      "overview": "4个FR共12条AC，测试覆盖了10条，2条未覆盖",
      "by_fr": [
        {"fr": "FR-001", "ac_total": 4, "ac_covered": 3, "coverage_pct": 75, "uncovered_ac": ["多平台支持(Bilibili/Vimeo专项)"]},
        {"fr": "FR-002", "ac_total": 4, "ac_covered": 4, "coverage_pct": 100, "uncovered_ac": []}
      ]
    },
    "case_quality": {
      "expectation_clarity": {"explicit": 8, "vague": 3, "missing": 1},
      "category_distribution": {"happy_path": 4, "boundary": 4, "exception": 4},
      "assessment": "边界和异常覆盖充分，3条用例的 min_expectation 较模糊"
    },
    "risk_assessment": {
      "high_risk": ["FR-001 缺失并发场景测试，高并发下响应时间未知"],
      "medium_risk": ["3条用例 min_expectation 模糊，可能导致误判"],
      "low_risk": []
    },
    "root_cause_analysis": {
      "design_gap": 1,
      "requirement_gap": 0,
      "implementation_gap": 1,
      "environment_gap": 0,
      "details": [
        {"bug_id": "BUG-001", "root_cause": "design_gap", "detail": "app 架构未包含域名有效性校验逻辑"},
        {"bug_id": "BUG-002", "root_cause": "implementation_gap", "detail": "Agent 模式下的 prompt-only Skill 缺少 UI 反馈机制"}
      ]
    }
  },
  "recommendation": "CONDITIONAL_APPROVAL",
  "improvements": [
    {"priority": "MUST_FIX", "item": "FR-001 增加域名校验和友好错误提示", "ref": "BUG-001"},
    {"priority": "SHOULD_FIX", "item": "FR-004 删除操作后增加成功确认反馈", "ref": "BUG-002"},
    {"priority": "NICE_TO_HAVE", "item": "增加并发解析场景测试(Bilibili/Vimeo)"}
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
| 只输出 pass_rate 总结没有逐条 test_results | 必须逐条列出全部测试用例的结果 |
| test_results 数量与上游 test_cases 不一致 | 一一对应，不增不减 |
| 没有 is_bug 字段 | 每条必须有 is_bug 布尔值 |
| 没有 root_cause_analysis | 对每个 bug 分析根因分类 |
| 没有 risk_assessment | 按 FR 覆盖薄弱点分级风险 |
| improvements 没有优先级 | 使用 MUST_FIX/SHOULD_FIX/NICE_TO_HAVE |
| 不验证平台能力 | Agent 模式检查 _trace_ 字段 |
