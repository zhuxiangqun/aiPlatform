---
name: requirement_analysis
display_name: 需求分析
description: >-
  分析用户需求并输出结构化PRD（JSON + Markdown）。触发条件：pipeline需求阶段 / PM 定稿。
  输出必须含 functional_requirements（含 acceptance_criteria）、user_stories、
  constraints（performance+security）、decisions、open_questions=[]。
category: analysis
version: 1.2.0
status: enabled
execution_mode: prompt
execution_type: prompt
triggers:
  - 需求分析
  - PRD
  - 需求文档
permissions:
- fs:read
effects:
- type: read
  resources:
  - filesystem:~
  idempotent: true
  rollback_available: true
input_schema:
  user_requirement:
    type: string
    required: true
    description: 用户的原始需求描述
output_schema:
  prd:
    type: object
    required: true
    description: 结构化PRD JSON
  markdown:
    type: string
    required: true
    description: 面向人阅读的Markdown版PRD
protected: true
idempotent: false
completion_criterion: |
  1. functional_requirements至少3条,每条包含acceptance_criteria
  2. user_stories覆盖所有核心功能
  3. constraints 含 performance 与 security（结构化，勿只写功能 AC）；客户已声明的硬约束必须原样保留
  4. decisions 为对象（可为空对象，但媒体/URL/语音等边界出现时必须填对应键）
  5. open_questions 为空数组才可视为定稿；草稿轮允许非空，但须标「待确认」
  6. 用户可见输出不得含「步骤1/方案比较」推理过程
  7. 禁止编造客户未提供的 NFR/渠道/集成细节；未知项进 open_questions 或标「待确认」
keywords:
  objects:
  - PRD
  - 需求
  - 验收标准
  actions:
  - 分析
  - 生成
  - 输出
trigger_conditions:
- when: pipeline需求阶段
  query: 生成PRD/需求分析/输出PRD
skip_when: 已有完整PRD文档
---

# 需求分析（Engine）

根据用户需求描述，生成结构化 PRD。

## 输出铁律（强制）

1. **直接输出产物**：第一个可见字符必须是 `{`（JSON）或 `## 项目名称`。禁止先输出「步骤1/步骤2」「分析关键约束」「列出方案」「比较优劣」「取舍」。
2. 定稿/修复轮：整段只能是产物；禁止任何「步骤1–4 / 方案A/B/C」前缀。FR 用 `### FR-001:`（勿用 `**FR-1：**` 粗体行代替标题）。
3. 若上下文出现「## PRD 域质量约束」：生成前必须遵守；边界写入 `decisions`；禁止依赖事后洗绿；BAD 口径须按 GOOD 重写。
4. `acceptance_criteria` 必须具体可验证；`constraints.performance` 与 `constraints.security` 必须为非空列表。
5. 出现 URL 导入时：写清直链 vs 平台页，并写 SSRF（拒绝内网 IP / `file://`）；`decisions.url_source_scope` 必填。
6. 出现「不转写」时：禁止主题/语义/要点/关键词类验收；仅允许声学粗标签；`decisions.speech_pipeline=audio_features_only`（或显式允许 `asr`/`hybrid`）。
7. 「字/分钟」语速：须区分有字幕/无字幕双路径，或改用音节密度。
8. **范围锁定**：若上下文有 `## pm_chat_history` 或 `## confirmed_prd_baseline`，以二者为范围上限——禁止发明用户未要求的能力（如未要求的 OCR、ASR/转写、额外 FR/模块）；重建时覆盖旧稿但不得扩 scope。
9. **证据优先（强制）**：客户已口述的硬约束（如「不上公网」「无 API 文档」「试点范围」）必须在 FR/constraints/决策中显式出现，不得弱化改写。
10. **禁止编造**：客户未提及的多语言、具体 SLA 数值、加密方案、交付渠道（如「钉钉小程序内完成全流程」）不得写成已确认需求；只能进 `open_questions` 或正文标「待确认」。
11. **AC 可测**：禁止「清晰可见 / 实际操作测试 / 功能正常」等软 AC；优先可计数、可复现步骤、可判定通过/失败的条件。
12. **输出形态**：定稿/草稿直接输出 Markdown（或 JSON+Markdown）；禁止在文末再套一层 ```markdown 复读全文。

## SOP（内部思考，勿写入用户可见输出）

1. 理解需求关键词、已确认决策、功能 vs 非功能
2. 分解 FR（FR-001…），每条含可验证 AC 与 priority
3. 生成 US，关联 high 优先级 FR
4. 填写 constraints + decisions + open_questions=[]
5. 输出 JSON，再输出 Markdown（对话定稿场景可只输出 Markdown + `<!-- PRD_READY -->`）

## 输出格式

### JSON（结构化，放最前；单行合法 JSON，勿用 ``` 包裹）

```json
{
  "title": "项目名称",
  "description": "一句话概述",
  "functional_requirements": [
    {
      "id": "FR-001",
      "name": "功能名称",
      "description": "功能描述",
      "priority": "high|standard|low",
      "acceptance_criteria": ["可验证条件1", "可验证条件2"]
    }
  ],
  "user_stories": [
    {
      "id": "US-001",
      "story": "作为<角色>，我想要<能力>，以便<价值>",
      "related_fr": ["FR-001"],
      "priority": "high|standard|low"
    }
  ],
  "constraints": {
    "platform": "Web",
    "performance": ["P95 < 500ms"],
    "security": ["HTTPS + authentication", "SSRF: reject private IPs and file://"]
  },
  "decisions": {},
  "open_questions": []
}
```

### Markdown（人读）

```
## 项目名称：{title}

## 项目背景
{description}

## 功能需求
### FR-001: {name}
- **描述**: ...
- **优先级**: high
- **验收标准**:
  - AC1: ...

## 用户故事
### US-001: ...

## 决策
- key: value

## 待确认问题
（无）

## 范围
- 平台: Web
- 性能: ...
- 安全: ...

<!-- PRD_READY -->
```

## 反模式

| ❌ 错误 | ✅ 正确 |
|--------|--------|
| 先写「步骤1：分析约束」再写 PRD | 直接输出 JSON/Markdown PRD |
| 用 `**FR-1：**` 粗体当 FR 标题 | 用 `### FR-001: 名称` |
| acceptance_criteria 写「功能正常」 | 「上传后返回 task_id（UUID）」 |
| 不转写 + 语义分析/主题标签 | 声学粗标签（语种/说话人数/情绪倾向） |
| 不转写却单独承诺字/分钟 | 有字幕→字速；无字幕→音节密度 |
| 有 URL 下载却无 SSRF | 拒绝内网 IP 与 file:// |
| 缺 decisions / open_questions 非空就 READY | 边界写入 decisions，open_questions=[] |
| decisions value 写成中文长句 | 只用枚举：`direct_media_url` / `audio_features_only` / `soft_track_only` |
| 把技术实现细节当需求 | 需求只写「做什么」与可测 AC |
| 编造「多语言 / P95<1s / 已加密」等未口述 NFR | 未确认项写入 open_questions 或标「待确认」 |
| 客户说「不上公网」却改成笼统「合规检查」 | constraints.security 保留「照片/附件不得离开内网/不上公网」 |
| 客户说「想打通钉钉但无 API」却写成「已在钉钉应用内完成」 | 集成方式标「待确认」；decision 用 `dingtalk_integration: pending_api` |
| 「里程碑」节只重复开放问题 | 写可执行分期（如「W1–2 试点范围与账号」「W3–4 主路径」「W5–6 看板与复盘」）并标注假设 |
| 文末再用 markdown 代码围栏复读全文 | 只输出一份 Markdown，勿二次包裹 |
