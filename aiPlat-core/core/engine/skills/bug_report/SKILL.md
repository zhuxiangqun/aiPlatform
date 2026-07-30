---
name: bug_report
display_name: Bug信息整理
description: >
  将残缺的Bug描述补全为可提审的标准化Bug报告，
  自动推断环境、步骤、预期结果、实际结果、优先级和严重程度。
  适用场景：收到模糊的问题描述后，补充缺失字段形成完整Bug单。
category: analysis
version: 1.0.0
status: enabled
execution_type: prompt
tags:
  - 测试
  - bug
  - 缺陷管理
  - 质量
triggers:
  - 报错
  - bug
  - 缺陷
  - 异常
  - 问题
  - 帮我提单
  - 整理bug
  - bug报告
permissions:
  - file:read
  - kb:read
effects:
  - type: read
    resources: ["kb:default"]
    idempotent: true
    rollback_available: false
input_schema:
  description:
    type: string
    required: true
    description: 原始Bug描述（可残缺）
  environment:
    type: string
    required: false
    description: 已知环境信息（如不提供则自动推断）
  screenshots:
    type: array
    items:
      type: string
    required: false
    description: 截图/日志文件路径
output_schema:
  bug_report:
    type: object
    required: true
    description: 完整Bug报告
  markdown:
    type: string
    required: true
    description: 格式化Bug单（Markdown）
trigger_conditions:
  - 用户消息包含报错/缺陷/bug/异常等关键词
  - 描述模糊需要补全信息
---
# Bug 信息整理

## 触发条件

当用户提交残缺的 Bug 描述时调用。描述可以是："登录报错了""那个页面打不开""昨天晚上接口超时"等非常模糊的信息。

## SOP

### Step 1: 解析原始描述
- 从用户消息中提取已知信息：现象、时间、操作、错误提示（如有）
- 标注信息缺失点——哪些必填字段还没有覆盖

### Step 2: 推断补全
按以下优先级推断缺失字段：
1. **环境**：从错误特征推断（500→服务端，404→客户端，CORS→浏览器，timeout→网络或服务器）
2. **步骤**：基于现象反推操作路径（"登录报错"→可能是第3步密码验证）
3. **预期结果**：根据功能语义推断（"应正常登录""应返回200"）
4. **实际结果**：就是用户描述的现象
5. **优先级**：P0(核心流程阻塞)/P1(主要功能异常)/P2(次要功能)/P3(体验问题)
6. **严重程度**：Blocker/Critical/Major/Minor/Trivial

### Step 3: 追问缺失
- 如果超过 3 个必填字段无法推断 → 返回追问列表，列出需要用户补充的信息
- 如果可以推断大部分 → 生成完整 Bug 报告，标注推断字段为 [AI推断]

### Step 4: 输出 Bug 报告
- 按标准模板格式输出
- 推断字段前加 🤖 标记
- 确认字段前加 ✅ 标记

## 输出格式

```markdown
## Bug 报告

| 字段 | 内容 | 来源 |
|------|------|:---:|
| **标题** | {标题} | 🤖 |
| **环境** | {环境} | 🤖 |
| **严重程度** | {Blocker/Critical/Major/Minor/Trivial} | 🤖 |
| **优先级** | {P0/P1/P2/P3} | 🤖 |
| **模块** | {模块} | 🤖 |

### 复现步骤
1. {步骤1}
2. {步骤2}
3. {步骤3}

### 预期结果
{预期结果}

### 实际结果
{实际结果}

### 附加信息
- 截图: {如有}
- 日志: {如有}
```

## 反模式 (Anti-patterns)

| ❌ 错误做法 | ✅ 正确做法 |
|---------|---------|
| 完全不推断，所有字段都追问用户 | 先推断再追问，仅在无法推断时追问 |
| 编造不存在的环境/步骤 | 标注 [AI推断]，让用户有审核机会 |
| 所有 Bug 都标 P0 | 按核心流程阻塞→主要功能→次要→体验分级 |
| 输出纯文本无结构 | 使用表格和章节结构输出 |

## 严重程度 × 优先级矩阵

参见 `references/severity-matrix.md`
