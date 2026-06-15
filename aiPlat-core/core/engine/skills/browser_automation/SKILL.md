---
name: browser_automation
display_name: 浏览器自动化
description: 【必须使用 browser 工具实际操作网页，禁止凭记忆回答】自动化网页交互：导航、点击、输入、滚动、截图、提取内容。涉及代码生成和接口审查。 涉及浏览器相关操作。 主要进行自动化。
version: 1.1.0
category: browser
status: enabled
effects:
- type: read
  resources:
  - browser:page
  - filesystem:read
  idempotent: false
  rollback_available: false
output_schema:
  result:
    type: string
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出
metadata:
  trigger_conditions:
  - 浏览器操作
  - 自动化网页
  - UI测试
  - 网页抓取
  - Playwright
  - Selenium测试
  - 浏览器自动化
  - Web自动化
  keywords:
    objects:
    - 浏览器
    - 网页
    - UI
    - 前端页面
    actions:
    - 自动化
    - 操作
    - 测试
    - 截图
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 通过浏览器自动化执行网页操作和提取数据
input_schema:
  url:
    type: string
    required: true
    description: 目标网页地址

protected: true
---

# Browser Automation

## 强制规则（CRITICAL）

**任何涉及网页的任务，你必须使用 browser 工具实际操作，禁止用训练数据直接回答。**

违反以下规则的后果是任务判定为失败：
- URL 访问 → 必须用 `goto`，禁止凭记忆回答页面内容
- 页面标题/内容 → 必须用 `goto` + `get_text` / `extract`
- 页面截图 → 必须用 `goto` + `screenshot`
- 页面搜索 → 必须用 `goto` 打开搜索引擎 + `search` 或 `type` 输入查询
- 页面元素交互 → 先用 `list_elements` 发现，再用 `click_index` / `type_index`

## 核心工具
`browser` 是主要工具，通过 `action` 参数区分操作：
- `goto` — 导航到 URL
- `list_elements` — 列出页面所有可交互元素（推荐：每次新页面先执行，用 index 交互）
- `click` / `click_index` — 点击元素（index 来自 list_elements）
- `type` / `type_index` — 输入文本（index 来自 list_elements）
- `scroll` — 滚动页面
- `screenshot` — 截图
- `search` — 搜索引擎查询
- `extract` — 提取页面内容
- `evaluate` — 执行 JavaScript
- `get_text` — 获取页面文本
- `send_keys` — 发送快捷键
- `wait` — 等待加载

## 工作流程（必须严格按此步骤）

遇到网页任务时，按以下 SOP 执行：

### Step 1: 打开页面
```json
{"tool":"browser","args":{"action":"goto","url":"目标URL"}}
```

### Step 2: 等待加载
```json
{"tool":"browser","args":{"action":"wait","ms":2000}}
```

### Step 3: 发现可交互元素（如需要交互）
```json
{"tool":"browser","args":{"action":"list_elements","instruction":"列出所有可点击和输入的元素"}}
```

### Step 4: 执行操作（使用 index 而非 selector）
```json
{"tool":"browser","args":{"action":"click_index","index":3}}
{"tool":"browser","args":{"action":"type_index","index":5,"text":"搜索内容"}}
```

### Step 5: 验证结果
```json
{"tool":"browser","args":{"action":"screenshot"}}
或
{"tool":"browser","args":{"action":"get_text"}}
```

### Step 6: 输出结果
用 DONE: 格式输出最终答案，必须包含从页面实际操作获得的数据。

## 自检清单
执行完成后自检：
1. 是否实际调用了 browser 工具？（不是凭记忆回答）
2. 是否到达了目标页面？（goto 返回 status=200）
3. 交互结果是否正确？（检查返回数据）
4. 截图或提取的数据是否真实？

## 目标
通过浏览器自动化执行网页操作和提取数据

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注