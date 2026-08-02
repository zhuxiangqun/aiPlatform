---
name: test_executor
display_name: 测试用例执行器
description: >
  读取 pytest 测试文件，pytest 执行，解析输出，
  生成 Markdown 测试报告（汇总 + 需求覆盖 + 失败详情）。
category: execution
version: 2.0.0
status: enabled
execution_type: prompt
tags:
  - 测试
  - 执行
  - 验收
  - 回归
triggers:
  - 执行测试
  - 跑用例
  - 运行测试
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
  test_files:
    type: array
    required: true
    description: "## FILE: test_*.py 文件列表（来自 test_case_generation）"
    items:
      type: object
      properties:
        path:
          type: string
          description: "tests/{name}_test.py"
        content:
          type: string
          description: pytest 文件完整内容
output_schema:
  markdown:
    type: string
    required: true
    description: Markdown 测试报告
trigger_conditions:
  - 用户提供 pytest 文件
  - pipeline 测试阶段自动触发
---

# 测试用例执行器 v2

## SOP

### Step 1: 写入测试文件
- 从 input_schema.test_files 读取 pytest 内容
- 写入 `tests/` 目录下的实际文件

### Step 2: 运行 pytest
- 执行 `pytest tests/ -v --tb=short` 
- 记录 stdout/stderr 完整输出
- 记录每个用例的耗时

### Step 3: 判定结果
每条用例判定为以下状态之一：
- ✅ PASS — 断言全部通过
- ❌ FAIL — 任一断言失败
- ⏭ SKIP — 前置条件不满足
- ⚠ ERROR — 执行过程异常（导入错误、网络不可达等）

### Step 4: 生成报告

## 输出格式

```markdown
## 测试报告 — {项目名称}

**执行时间**: {timestamp}
**测试框架**: pytest

### 汇总
| 指标 | 值 |
|:---|---:|
| 测试文件 | {file_count} |
| 用例总数 | {total} |
| ✅ 通过 | {passed} |
| ❌ 失败 | {failed} |
| ⏭ 跳过 | {skipped} |
| ⚠ 错误 | {errors} |
| 通过率 | {pass_rate}% |

### 需求覆盖
| PRD 需求 | 测试文件 | 用例数 | 状态 |
|---------|---------|:---:|:---:|
| {us_id} | {filename} | {n} | {pass/fail/skip} |

### 失败详情
| ID | 文件 | 函数 | 断言 | 预期 | 实际 |
|----|------|------|------|------|------|
| TC-003 | test_upload.py | test_oversized | status_code | 413 | 500 |

### 所有用例
| ID | 文件 | 函数 | 状态 | 耗时 |
|:---|------|------|:---:|:---:|
| 1 | test_upload.py | test_valid_mp4 | ✅ | 45ms |
| 2 | test_upload.py | test_oversized | ❌ | 12ms |
```

## 反模式

| ❌ 错误做法 | ✅ 正确做法 |
|---------|---------|
| 失败归为"预期不对" | 区分 FAIL(断言失败) vs ERROR(执行崩溃) |
| 不记录实际值 | 每条失败附预期 vs 实际对比 |
| 跳过因为"格式不对" | 只有必要字段缺失才 skip |
| 未执行就写 pass_rate=100 | 必须附 pytest stdout 作为证据 |
