---
name: test_case_generation
display_name: 测试用例生成
description: >-
  根据PRD生成测试用例。Agent模式→对话测试问题；代码模式→pytest文件。
  触发条件：QA阶段自动触发。
category: analysis
version: 2.5.0
skill_model_purpose: code_gen
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
  2. Agent模式: mode=agent_true_test；优先 platform_check/skill_invoke/page_smoke，conversation 仅用于编排澄清
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

# 测试用例生成（Engine）v2.3

## 输出禁令（所有模式）
1. **直接输出产物**：第一个可见字符必须是 `{`（Agent 模式 JSON）或 `#`（`## FILE:` pytest）。禁止「步骤1–6」「方案A/B」「路由为合理推断」。
2. **禁止编造路由**：没有任何 `@app.`/`@router.` 真实路径时，**不得**输出 pytest。

## Step 0: 模式检测（精确版 — 显式 architecture_mode 优先）

```
0. 【最高优先级】输入含 `## architecture_mode` 字段时，直接按其值决定：
   - architecture_mode=agent → 走 "Agent 对话测试" (Step A)
   - architecture_mode=code  → 走 "代码 pytest" (Step B)
   （显式字段是权威，不要被产物内容推翻）

1. 无 architecture_mode 时，按产物类型区分：
   - 存在以 `.py` 结尾的 `## FILE:`（main.py / routers/*.py / app.py 等）→ Step B
   - 有 `agent_app` / `agent_manifest.json` / `## FILE: .../AGENT.md` → Step A
   - 仅有 architecture JSON（agents/skill_routing，无 .py）→ Step A
   - 两者都没有 → **默认 Step A**（禁止默认 Step B）

⚠️ 关键区分：`## FILE: AGENT.md` / `## FILE: SKILL.md` / `## FILE: agent_manifest.json` 是 Agent 应用定义，
**不是**后端代码。不要因为看到 `## FILE:` 就走 Step B。
```

---

## 代码 pytest SOP（Step B — 仅当 architecture_mode=code 或存在 .py 代码 FILE）

### Code Step 1: 建立测试范围

1. **先列出 code 产物中真实存在的路由**（从 `@app.get/post` / `@router.get/post` / `APIRouter` 路径字面量提取）。
2. 若 **0 条真实路由** → **停止 Step B**，改走 Step A（或输出空并说明无代码路由）；**禁止**「基于 PRD 推断」路径。
3. 读取 PRD 的 AC，把每条 AC 映射到**已列出的真实路径**；无法映射的 AC 用跳过说明，不得发明路径。

### Code Step 2: 生成 pytest 文件（HTTP 行为测试，禁止调用内部方法）

用 `## FILE: tests/{name}_test.py` 格式输出**可执行 pytest 代码**。**一律通过 FastAPI TestClient 发 HTTP 请求测路由行为**：

```python
# tests/test_video.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_upload_video_success():
    resp = client.post("/api/upload", files={...})  # 路径必须来自 code 产物
    assert resp.status_code == 200
    assert "task_id" in resp.json()
```

规则（违反即大量 AttributeError / 404 失败）：
- 每个测试函数必须以 `def test_` 开头，含明确的 `assert`
- **只测 HTTP 路由行为**：`client.get/post/put/delete("路由路径")` + 断言 `status_code`/响应 JSON 字段
- **路由路径必须从 code 产物字面量复制**，禁止凭空编造（如擅自写 `/api/video/upload`）
- **异步任务**：若架构/代码标明异步，上传后须轮询任务状态至 completed（或 mock 完成），禁止假设同步立即可取分析报告
- **禁止直接调用内部类/方法**；**禁止 import 具体符号**，只允许 `from app.main import app` + `TestClient`
- 每个 FR 至少覆盖 happy_path + boundary + exception 各 1 条（在真实路由可支撑的前提下）

### Code Step 3: 输出

**只输出 `## FILE: tests/*_test.py` 代码块**。禁止输出 JSON、`test_questions`、自然语言"测试问题"、步骤推理。

---

## Agent 测真 SOP（Step A — architecture_mode=agent；默认）

> 纯 Agent 应用（无 .py 代码）必须走本 SOP。目标是**测真**：用例可被 `test_executor` 以
> `platform_check` / `skill_invoke` / `page_smoke` / `conversation` 执行，而不是只评话术。

### Agent Step 1: 从 PRD 提取可验证场景

对每条 acceptance_criteria，生成用例，并遵守**分类配额**（相对整份 `test_questions`，不含仅 page_smoke）：

| category（英文枚举，禁止只用中文） | 目标占比 | 说明 |
|-----------------------------------|----------|------|
| `happy_path` | **50%～55%** | 每条核心 FR 至少 1 条可执行正路径 |
| `exception` | **20%～25%** | 拒绝/失败/无轨跳过；同类平台规则勿堆砌 |
| `boundary` | **15%～20%** | 上限、空结果、分段边界 |
| `smoke` | **≤10%** | page_smoke / wizard I/O（通常 1～2 条） |

强制：
1. **平台规则封顶**：`platform.ssrf_block` 合计 ≤2（内网与 `file://` 可各 1，或合并表述）；`platform.file_rules` 超限类 ≤1。禁止为 FR-001 单独堆 4+ 条 SSRF/大小用例而挤掉核心能力正路径。
2. **读 `decisions.speech_pipeline`（或上下文 `## speech_pipeline`）**：
   - `asr` / `hybrid`：至少 1 条 `skill_invoke` 断言 `result.contains: transcript`（目标 skill ∈ routing 的语音分析）；至少 1 条报告类 invoke 断言含 `transcript`（若 routing 有报告 skill）。**禁止**再写「不得出现 transcript / 不转写」。
   - `audio_features_only`：语音用例断言语种/说话人/VAD 等；**禁止**要求 transcript。
3. 入口正路径优先测 **PRD 已声明且平台可测** 的来源（如直链 `.mp4` / 本地上传）；未声明「平台页下载」时不要写 YouTube/B站 为必过正常用例。
4. 无音轨跳过：转写与语音分析可合并为 1 条 exception，避免重复两条同构用例。

### Agent Step 2: 为每条用例选择 execution（禁止一律 conversation）

按**可观察性**选执行类型（不要按产品域名硬编码）：

| execution | 何时使用 | 必填字段 |
|-----------|----------|----------|
| `platform_check` | 安全/格式/大小等可用平台确定性规则验证（如 URL 是否应被 SSRF 拦截、扩展名/大小是否合规） | `asserts` 含 `platform.*`；或 `platform_check` 对象 |
| `skill_invoke` | 需调用某个 Skill 并断言返回 JSON/文本 | `invoke: {skill, params}` + `asserts`（`result.*`） |
| `page_smoke` | 验证前端 stage 的 component/skill 接线 | `stage_id`（可选）+ `asserts`（`stage.*`） |
| `conversation` | 仅编排/澄清/自然语言摘要等无法结构化调用的场景 | `question` + `min_expectation` + `target_skill` |

规则：
1. 凡 AC 涉及「拒绝内网 URL / file:// / 扩展名白名单 / 大小上限」→ **必须** `platform_check`（参数与允许列表取自本轮 PRD，写入 asserts，禁止臆造未在 PRD 出现的格式）。
2. 凡 AC 对应某 Skill 的输入→输出 → 优先 `skill_invoke`；`invoke.skill` 与 `target_skill` 必须 ∈ `skill_routing` keys。
3. 至少 1 条 `page_smoke`（或依赖执行器自动追加的整页冒烟）；不要把页面接线测全写成 conversation。
4. `conversation` 占比应明显低于结构化用例；编排澄清类才用。

### Agent Step 3: asserts 类型（通用，无业务硬编码）

- `platform.ssrf_block` / `platform.ssrf_allow`：`url` 或 `url_from`
- `platform.file_rules`：`file_name`、`file_size`、`allowed_extensions`、`max_bytes`、`expect_ok`
- `result.contains` / `result.must_not_contain`
- `result.field_equals` / `result.field_in` / `result.status_in`
- `stage.component_known` / `stage.skill_in_routing`

### Agent Step 4: 输出 JSON

```json
{
  "mode": "agent_true_test",
  "test_questions": [
    {
      "id": "TQ-001",
      "ac_ref": "FR-001",
      "category": "exception",
      "execution": "platform_check",
      "question": "用户粘贴内网地址…",
      "min_expectation": "平台拒绝内网 URL",
      "target_skill": "video_download",
      "asserts": [
        {"type": "platform.ssrf_block", "url": "http://192.168.1.10/a.mp4", "expect_blocked": true}
      ]
    },
    {
      "id": "TQ-002",
      "ac_ref": "FR-001",
      "category": "happy_path",
      "execution": "skill_invoke",
      "target_skill": "video_download",
      "invoke": {"skill": "video_download", "params": {"url": "https://example.com/v.mp4", "task_id": "t-1"}},
      "question": "分析公网直链",
      "min_expectation": "返回 pending 或明确错误且不含内网拦截误报",
      "asserts": [
        {"type": "result.contains", "text": "status"}
      ]
    },
    {
      "id": "TQ-PAGE",
      "ac_ref": "FR-001",
      "category": "smoke",
      "execution": "page_smoke",
      "invoke_skills": false,
      "question": "前端阶段接线",
      "min_expectation": "每个 stage 的 component 为平台组件且 skill ∈ routing",
      "asserts": [
        {"type": "stage.component_known"},
        {"type": "stage.skill_in_routing"}
      ]
    }
  ]
}
```

`mode` 必须为 `agent_true_test`（兼容旧字段 `agent_conversation`，但新生成禁止只出纯对话题）。

---

## 输出禁令表

| ❌ 禁止 | ✅ 必须 |
|--------|--------|
| agent 模式输出 pytest / 编造 `/api/...` | agent → `test_questions` JSON |
| 有 `## FILE: AGENT.md` 却走 Step B | AGENT.md 不是代码 → Step A |
| 「路由为基于 PRD 的合理推断」 | 无真实路由则改 Step A |
| 先写步骤1–6再写产物 | 直接输出 JSON 或 `## FILE:` |
| ac_ref 为空或写 "-" / "N/A" | 每行必须有对应的 FR 编号 |
| min_expectation 写 "正常返回" | 写明具体可验证预期 |
| `asr` PRD 却大量 SSRF、几乎无 transcript 断言 | happy_path 含转写/报告 transcript；SSRF ≤2 |
| category 只用「正常流程」中文且无 happy_path | 使用 `happy_path` / `exception` / `boundary` / `smoke` |
| 为同一无音轨场景写 2+ 条同构 exception | 合并为 1 条 |

## ⚠️ 输出前强制自检（勿写入回复）

1. 当前 architecture_mode 是什么？agent→A，code→B
2. 若走 B：真实路由列表是否非空？为空则改 A
3. 每个 FR 至少 1 条测试
4. happy_path 是否约占一半？platform SSRF 是否 ≤2？
5. speech_pipeline=asr/hybrid 时是否已有 transcript 断言？
6. 回复是否以 `{` 或 `## FILE:` 开头？
