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
  code:
    type: object
    required: false
    description: "代码产物(## FILE: 格式后端代码, 代码模式时必传)。有 code 则生成 pytest 文件"
  agent_app:
    type: object
    required: false
    description: Agent应用产出(纯Agent模式、无 code 时才用)
output_schema:
  test_cases:
    type: array
    required: true
    description: "代码模式→pytest文件列表; Agent模式→对话测试问题对象数组(含id/ac_ref/category/question/min_expectation)"
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

# 测试用例生成（Engine）v2.2

## Step 0: 模式检测（精确版 — 按产物类型区分，勿按 `## FILE:` 字样判断）

```
检查输入上下文中的产物：
1. 有 `code` 产物，且其 `## FILE:` 路径以 `.py` 结尾（如 main.py / routers/*.py / models/*.py / app.py）→ 走 "代码 pytest" (Step B)
2. 有 `agent_app` 产物，且内容含 `agent_manifest.json`（Agent 应用定义）→ 走 "Agent 对话测试" (Step A)
3. 两者都没有 → 默认走 "代码 pytest" (Step B)

⚠️ 关键区分：`## FILE: AGENT.md` / `## FILE: SKILL.md` / `## FILE: agent_manifest.json` 是 Agent 应用定义（.md/.json），
不是代码。只有 `## FILE:` 路径以 `.py` 结尾的才是代码产物。切勿因输入含 `## FILE:` 字样就判定为代码模式。
```

---

## 代码 pytest SOP（Step B — 默认模式，只要输入含 `## FILE:` 代码就执行本 SOP）

### Code Step 1: 建立测试范围

读取 PRD 的 functional_requirements / acceptance_criteria，以及 code 产物里**真实存在的路由路径**（`@app.get("/api/xxx")` / `@router.post("/xxx")`）。按风险分级：高风险接口→全组合判定表；标准→核心+2边界+1异常；低风险→happy+1异常。

### Code Step 2: 生成 pytest 文件（HTTP 行为测试，禁止调用内部方法）

用 `## FILE: tests/{name}_test.py` 格式输出**可执行 pytest 代码**。**一律通过 FastAPI TestClient 发 HTTP 请求测路由行为**：

```python
# tests/test_video.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_upload_video_success():
    resp = client.post("/api/video/upload", json={...})
    assert resp.status_code == 200
    assert "task_id" in resp.json()
```

规则（违反即大量 AttributeError 失败）：
- 每个测试函数必须以 `def test_` 开头，含明确的 `assert`
- **只测 HTTP 路由行为**：`client.get/post/put/delete("路由路径")` + 断言 `status_code`/响应 JSON 字段
- **路由路径必须从 code 产物里 grep 真实存在**（`@app.get("/api/xxx")` 里的路径），禁止凭空编造
- **禁止直接调用内部类/方法**（如 `security_manager.hash_url()`、`upload_service.create()`）——这些方法名 code 产物里未必存在，会 AttributeError。只通过 HTTP 路由间接测试
- **禁止 import 具体符号**（`from app.core.security import security_manager`），只允许 `from app.main import app` + `TestClient`
- 每个 FR 至少覆盖 happy_path + boundary + exception 各 1 条

### Code Step 3: 输出

**只输出 `## FILE: tests/*_test.py` 代码块**（可多个文件）。禁止输出 JSON、禁止输出 `test_questions`、禁止输出自然语言"测试问题"。

---

## Agent 对话测试 SOP（Step A — 仅当输入含 agent_app 且**不含** `## FILE:` 后端代码时使用）

> 纯 Agent 应用（无代码）才走本 SOP。若输入含 `## FILE:` 代码，一律走上面的代码 pytest SOP。

### Agent Step 1: 从 PRD 提取测试问题

对每条 acceptance_criteria，生成 1-3 句自然语言测试问题（happy/boundary/exception），问题用真实用户口吻。

### Agent Step 2: 为每个测试问题定义字段

每条问题标注：id / ac_ref / category / question / min_expectation / assertions / target_skill。
其中 target_skill 从 agent_manifest.json 的 skill_routing 反查该问题对应的 Skill 名（用于测试执行器路由到目标 Agent）。

### Agent Step 3: 输出 JSON

只输出 `{"mode": "agent_conversation", "test_questions": [{..., "target_skill": "video_upload"}]}`。

---

## 输出禁令

| ❌ 禁止 | ✅ 必须 |
|--------|--------|
| 有 `## FILE:` 代码时还输出 test_questions | 有代码 → 输出 `## FILE: tests/*_test.py` |
| 代码模式输出 JSON / 自然语言"测试问题" | 代码模式输出 `def test_xxx()` 可执行代码 |
| 测试函数凭空编造不存在的函数/路由 | 从 code 产物里找真实函数/路由/字段 |
| ac_ref 为空或写 "-" / "N/A" | 每行必须有对应的 FR 编号 |
| min_expectation 写 "正常返回" / "符合预期" | 写明具体的可验证预期值 |

## ⚠️ 输出前强制自检

1. PRD 中有多少个 FR？（到 `functional_requirements` 中数）
2. 若输入含 `## FILE:` 代码 → 确认输出的是 `## FILE: tests/*_test.py` 而非 JSON
3. 每个 FR 至少有 1 条测试
4. 全部 FR 覆盖后才输出
