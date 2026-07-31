---
name: test_executor
display_name: 测试用例执行器
description: >
  接收结构化测试用例(JSON)，逐条调用API/脚本执行测试，
  对比预期与实际结果，输出pass/fail矩阵和结构化测试报告。
  输入来自 test_case_generation 的产出。
category: execution
version: 1.0.0
status: enabled
execution_type: prompt
tags:
  - 测试
  - 执行
  - 验收
  - API
  - 回归
triggers:
  - 执行测试
  - 跑用例
  - 运行测试
  - 测试执行
  - 跑一遍
  - 验证接口
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
    description: 测试用例数组（来自 test_case_generation 产出）
    items:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        endpoint:
          type: string
        method:
          type: string
        params:
          type: object
        expected:
          type: object
  target_url:
    type: string
    required: false
    description: 目标API基础URL
output_schema:
  test_report:
    type: object
    description: 结构化测试报告
  markdown:
    type: string
    required: true
    description: 格式化测试报告(Markdown)
trigger_conditions:
  - 用户提供测试用例JSON
  - 用户请求执行测试/运行用例
  - pipeline 测试阶段自动触发
---
# 测试用例执行器

## 触发条件

当提供结构化测试用例(JSON格式)时调用。输入来自 `test_case_generation` 的输出，执行后生成可审计的测试报告。

## SOP

### Step 1: 解析测试用例
- 从 `input_schema.test_cases` 解析测试用例列表
- 验证必要字段：id, endpoint, method, expected
- 缺失必要字段的用例标记为 skip

### Step 2: 逐条执行
按以下顺序执行每条测试用例：
1. 构建请求：method + endpoint + params/body
2. 调用目标接口
3. 记录实际响应：status code, response body, latency(ms)
4. 按 expected 字段对比：
   - `expected.status` → 检查 HTTP 状态码
   - `expected.body` → 检查响应体中关键字段
   - `expected.contains` → 检查响应是否包含某字符串
   - `expected.latency_ms` → 检查响应时间是否在预期内

### Step 3: 判定结果
每条用例判定为以下状态之一：
- ✅ PASS — 所有 expected 条件满足
- ❌ FAIL — 任一 expected 条件不满足
- ⏭ SKIP — 缺少必要字段
- ⚠ ERROR — 执行过程中异常(如网络不可达)

### Step 4: 生成报告
- 汇总统计：total/passed/failed/skipped/error
- 逐条详情：pass/fail + 预期值 vs 实际值 + 证据
- 失败用例自动标记为待排查
- 输出到 `output/test_report_{timestamp}.md`

## 输出格式

```markdown
## 测试报告

**执行时间**: {timestamp}
**总用例数**: {total}
**通过率**: {pass_rate}%

### 汇总

| 状态 | 数量 | 占比 |
|:---:|:---:|:---:|
| ✅ PASS | {passed} | {pct}% |
| ❌ FAIL | {failed} | {pct}% |
| ⏭ SKIP | {skipped} | {pct}% |
| ⚠ ERROR | {errors} | {pct}% |

### 失败用例详情

| ID | 名称 | 预期 | 实际 | 差异 |
|:---|:---|:---|:---|:---|
| TC-003 | {name} | status=200 | status=500 | 服务端错误 |
| TC-007 | {name} | body.token存在 | body.token=null | 鉴权失败 |

### 所有用例

| ID | 名称 | 方法 | 端点 | 状态 | 延迟 |
|:---|:---|:---|:---|:---:|:---:|
| TC-001 | {name} | GET | /api/users | ✅ | 45ms |
| TC-002 | {name} | POST | /api/login | ✅ | 120ms |
| TC-003 | {name} | GET | /api/orders | ❌ | 5000ms |
```

## 反模式 (Anti-patterns)

| ❌ 错误做法 | ✅ 正确做法 |
|---------|---------|
| 所有失败都归为"预期不对" | 区分 FAIL(结果不符预期) vs ERROR(执行失败) |
| 不记录实际返回值 | 每条 FAIL 用例必须附带预期 vs 实际对比 |
| 执行后不生成报告 | 每次执行生成 markdown 报告文件 |
| 跳过所有用例因为"格式不对" | 只有必要字段缺失才 skip，不因格式微差全量跳过 |

## 证据链

每条用例的判定结果写入 lineage:
- PASS → outcome_status=success, evidence="status={actual}, latency={ms}ms"
- FAIL → outcome_status=failed, evidence="expected={expected}, actual={actual}"
