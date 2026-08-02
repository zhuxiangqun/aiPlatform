---
name: test_case_generation
display_name: 测试用例生成
description: 根据 PRD 的 acceptance_criteria 生成可执行 pytest 文件 + Markdown 测试报告。触发条件：QA阶段自动触发。
category: analysis
version: 2.0.0
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
output_schema:
  test_files:
    type: array
    required: true
    description: "## FILE: test_*.py 文件列表（可执行 pytest 用例）"
  report:
    type: string
    required: true
    description: Markdown 格式测试报告（含汇总表、需求覆盖表、失败详情表）
  decisions:
    type: string
    required: false
    description: JSON 决策摘要（pass_rate, recommendation, issues, skipped_reasons）
metadata:
  trigger_conditions:
  - 测试用例
  - 生成测试
  - 单元测试
  - pytest用例
  - 测试覆盖
  keywords:
    objects:
    - 测试用例
    - pytest
    - 验收标准
    actions:
    - 生成
    - 编写
  negative_triggers:
  - 不要编造不存在的数据
  sop_goal: 生成可执行 pytest 测试文件 + Markdown 测试报告
sop_flow:
  - "读取 PRD 的 functional_requirements 和 acceptance_criteria"
  - "按风险分级：高风险→全组合判定表；标准→核心+2边界+1异常；低风险→happy+1异常"
  - "为每个接口生成 ## FILE: tests/{name}_test.py（可执行 pytest 代码）"
  - "输出 Markdown 测试报告：汇总表 + 需求覆盖表 + 失败详情表"
  - "末尾附 JSON 决策摘要"
protected: true
idempotent: false
completion_criterion: |
  1. 每个 acceptance_criteria 至少有一个 test_ 函数
  2. 测试覆盖 happy path + 至少一个边界/异常 case
  3. 每个断言含失败提示信息
keywords:
  objects:
  - 测试用例
  - 测试场景
  actions:
  - 生成
  - 编写
  - 设计
  constraints:
  - 覆盖率
  - 边界条件
trigger_conditions:
- when: 用户要求生成测试用例
  query: 生成测试/写测试用例
skip_when: 代码模块过小或已有充分测试覆盖时不触发
---

# 测试用例生成（Engine）v2

## SOP
1. 读取 PRD 的 `functional_requirements` 和 `acceptance_criteria`
2. 按风险分级策略：高风险接口→全组合判定表；标准→核心+2边界+1异常；低风险→happy+1异常
3. 为每个接口生成 **`## FILE: tests/{name}_test.py`** — 可执行 pytest 文件
4. 输出 **Markdown 测试报告**：汇总表 + 需求覆盖表 + 失败详情表
5. 报告末尾附 **JSON 决策摘要**

## 输出格式

### 可执行 pytest 文件（用 `## FILE:` 格式输出）

```
## FILE: tests/video_upload_test.py
```python
import pytest
import requests

BASE = "http://localhost:8000"

def test_upload_valid_mp4():
    """合法MP4上传 — happy path"""
    with open("test_fixtures/sample.mp4", "rb") as f:
        resp = requests.post(f"{BASE}/api/upload", files={"video": f})
    assert resp.status_code == 201, f"期望201，实际{resp.status_code}"
    data = resp.json()
    assert "task_id" in data, "响应缺少task_id"

def test_upload_oversized():
    """超限文件 — 边界"""
    ...
```

### Markdown 测试报告

```
## 测试报告 — {项目名称}

### 汇总
| 指标 | 值 |
|:---|---:|
| 用例总数 | 28 |
| ✅ 通过 | 22 |
| ❌ 失败 | 4 |
| ⏭ 跳过 | 2 |
| 通过率 | 78.6% |

### 需求覆盖
| PRD需求 | 接口 | 用例数 | 状态 |
|---------|------|:---:|:---:|
| US-001 链接解析 | /api/link | 8 | ✅ |
| US-002 视频上传 | /api/upload | 12 | ⚠ 2 fail |

### 失败详情
| ID | 接口 | 预期 | 实际 | 建议 |
|----|------|------|------|------|
| TC-001-06 | /api/upload | 413 | 500 | 加文件大小中间件 |

### 所有用例
| ID | 接口 | 用例 | 方法 | 状态 | 耗时 |
|:---|------|------|:---:|:---:|:---:|
| TC-001-01 | /api/upload | 有效MP4 | POST | ✅ | 45ms |
```

### JSON 决策摘要（嵌入报告末尾）

```json
{
  "pass_rate": 78.6,
  "recommendation": "REJECTED",
  "issues": ["文件大小校验缺失", "链接可达性检测不可靠"],
  "decisions": {"skipped_US-004": "第三方AI服务不可达"}
}
```

## 禁令（违反即不合格）

| ❌ 禁止 | ✅ 必须 |
|--------|--------|
| 输出嵌套 `test_suites` JSON | 输出 `## FILE: test_*.py` |
| `coverage_matrix` JSON | 需求覆盖写入 Markdown 表格 |
| 自然语言步骤（"发送 POST"） | `def test_xxx():` 可执行函数 |
| 预期写 "正常返回" | 断言含具体值（201, task_id, 413） |

## Checklist
- [ ] 每个接口一个 `test_*.py` 文件
- [ ] 每个 `test_` 函数有 docstring
- [ ] 每个断言含失败提示信息
- [ ] 报告含汇总表 + 需求覆盖表
- [ ] 失败用例有预期 vs 实际对比和建议
- [ ] 禁止输出嵌套 JSON（test_suites/coverage_matrix）
