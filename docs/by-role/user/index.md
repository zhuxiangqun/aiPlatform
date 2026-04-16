# 📖 用户指南

> aiPlatform - 从零开始使用 AI 中台

---

## 🎯 本指南适合谁？

本指南适合所有想要使用 aiPlatform 的用户：
- **产品经理**：创建和管理 AI 助手
- **业务人员**：使用 AI 助手处理业务问题
- **开发者**：通过 API 调用 AI 能力
- **运维人员**：了解用户操作流程

**不需要编程基础**，跟着步骤操作即可。

---

## 🚀 5 分钟快速体验

### 方式一：Web 界面（推荐新手）

**步骤 1：打开浏览器**
- 访问 `http://localhost:3000`（开发环境）
- 或访问 `https://app.example.com`（生产环境）

**步骤 2：登录系统**
- 默认账号：`admin@aiplatform.com`
- 默认密码：`admin123`
- 点击 "登录"

**⚠️ 重要提示**：
- **首次登录后请立即修改密码**
- 默认密码仅用于初始登录，不安全

**修改密码步骤**：
1. 登录后，点击右上角用户头像
2. 选择 "Settings"
3. 点击 "Change Password"
4. 输入新密码（至少 8 位，包含大小写字母和数字）
5. 点击 "Save"

**步骤 3：创建 AI 助手**
- 左侧菜单选择 "Agents"
- 点击 "Create Agent"
- 选择类型 "Chat Assistant"
- 填写名称：`my-first-agent`
- 点击 "Create"

**步骤 4：开始对话**
- 在对话框输入：`你好，请介绍一下你自己`
- 点击 "发送" 或按 Enter
- 等待 AI 回复

---

### 方式二：命令行工具（适合开发者）

**步骤 1：安装 CLI**

**从 PyPI 安装**（推荐）：
```bash
pip install aiplat-cli
```

**从源码安装**（开发版）：
```bash
git clone <repository>
cd aiPlatform/cli
pip install -e .
```

**验证安装**：
```bash
aiplat --version
# 预期输出：aiplat-cli 1.0.0
```

**步骤 2：配置 CLI**
```bash
# 初始化配置
aiplat config init

# 设置 API 地址
aiplat config set api.url http://localhost:8000

# 登录
aiplat auth login --username admin@aiplatform.com --password admin123
```

**步骤 3：列出可用的 AI 助手**
```bash
aiplat agent list
```

**步骤 4：执行对话**
```bash
aiplat agent run --name chat-assistant --input "你好，请介绍一下你自己"
```

**步骤 5：查看执行结果**
```bash
# 查看最近的执行记录
aiplat agent history --limit 5

# 查看特定执行的详情
aiplat agent show --id <execution-id>
```

---

### 方式三：API 调用（适合应用集成）

**步骤 1：获取访问令牌**
```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin@aiplatform.com",
    "password": "admin123"
  }'
```

返回：
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**步骤 2：调用 AI 助手**
```bash
curl -X POST http://localhost:8000/api/v1/agents/chat-assistant/execute \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..." \
  -H "Content-Type: application/json" \
  -d '{
    "input": "你好，请介绍一下你自己"
  }'
```

返回：
```json
{
  "execution_id": "exec-123",
  "status": "completed",
  "output": "你好！我是 AI 助手...",
  "duration_ms": 1250
}
```

**错误响应示例**：

**401 Unauthorized**（Token 无效）：
```json
{
  "error": "unauthorized",
  "message": "Invalid or expired token",
  "status_code": 401
}
```

**429 Too Many Requests**（触发限流）：
```json
{
  "error": "rate_limit_exceeded",
  "message": "Request limit exceeded. Please try again in 60 seconds.",
  "status_code": 429,
  "retry_after": 60
}
```

**500 Internal Server Error**（服务内部错误）：
```json
{
  "error": "internal_server_error",
  "message": "An unexpected error occurred",
  "status_code": 500,
  "request_id": "req-abc-123"
}
```

---

## 📖 核心功能详解

### 一、Agent（AI 助手）管理

#### 什么是 Agent？

Agent 是 AI 助手的执行单元，每个 Agent 有特定的能力：

| 类型 | 说明 | 适用场景 |
|------|------|----------|
| **Chat Assistant** | 通用对话助手 | 问答、闲聊、信息查询 |
| **Code Assistant** | 代码助手 | 代码生成、解释、重构 |
| **Data Analyst** | 数据分析师 | 数据查询、分析、可视化 |
| **RAG Agent** | 知识库助手 | 基于私有知识回答问题 |
| **Tool Agent** | 工具助手 | 调用外部工具完成任务 |

---

#### 创建 Agent

**通过 Web UI**：

**步骤 1：进入创建页面**
- 左侧菜单选择 "Agents"
- 点击右上角 "Create Agent" 按钮

**步骤 2：填写基本信息**

| 字段 | 说明 | 示例 | 必填 |
|------|------|------|------|
| 名称 | Agent 唯一标识 | `customer-support` | 是 |
| 显示名称 | 友好显示名称 | `客服助手` | 否 |
| 类型 | Agent 类型 | 从下拉列表选择 | 是 |
| 描述 | 功能说明 | `处理客户咨询` | 否 |

**步骤 3：配置 Agent**

| 配置项 | 说明 | 推荐 |
|--------|------|------|
| **模型** | 使用的 LLM | `gpt-4`（推荐）/ `gpt-3.5-turbo`（快速）/ `claude-3`（擅长推理）|
| **系统提示词** | 定义 Agent 行为 | `你是一个专业的客服助手，擅长解答用户问题...` |
| **温度** | 响应随机性 | `0.7`（推荐）/ `0.0`（确定性）/ `1.0`（创意性）|
| **最大输出** | 回复最大长度 | `2000`（默认）|

**步骤 4：选择技能（可选）**
- 勾选需要的 Skill
- 推荐新手使用默认配置

**步骤 5：保存**
- 点击 "Create" 或 "Save"

**通过 CLI**：

```bash
aiplat agent create \
  --name customer-support \
  --display-name "客服助手" \
  --type chat \
  --model gpt-4 \
  --prompt "你是一个专业的客服助手，擅长解答用户问题。请用简洁友好的语言回答。" \
  --temperature 0.7 \
  --max-tokens 2000
```

---

#### 执行 Agent

**通过 Web UI**：

**步骤 1：选择 Agent**
- 在 Agents 列表点击 Agent 名称
- 进入 Agent 详情页

**步骤 2：开始对话**
- 在底部对话框输入问题
- 点击 "发送" 或按 Enter
- 等待 AI 回复（通常 5-30 秒）

**步骤 3：继续对话**
- 在对话框继续输入
- AI 会记住上下文
- 可以点击 "Clear" 清空对话

**通过 CLI**：

```bash
# 单次对话
aiplat agent run --name customer-support --input "如何重置密码？"

# 查看执行状态
aiplat agent status --id <execution-id>

# 查看执行结果
aiplat agent result --id <execution-id>
```

**通过 API**：

```bash
# 执行 Agent
curl -X POST http://localhost:8000/api/v1/agents/customer-support/execute \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"input": "如何重置密码？"}'

# 查询执行状态
curl -X GET http://localhost:8000/api/v1/executions/<execution-id> \
  -H "Authorization: Bearer <token>"
```

---

#### 查看执行历史

**通过 Web UI**：
- 进入 Agent 详情页
- 点击 "History" 标签
- 查看所有历史对话
- 点击任意记录查看详情

**通过 CLI**：
```bash
# 查看最近的执行记录
aiplat agent history --name customer-support --limit 10

# 查看特定日期的记录
aiplat agent history --name customer-support --from 2026-04-01 --to 2026-04-09
```

---

#### 更新 Agent 配置

**通过 Web UI**：
- 在 Agents 列表找到目标 Agent
- 点击 "Edit" 按钮
- 修改配置项
- 点击 "Save"

**通过 CLI**：
```bash
aiplat agent update --name customer-support \
  --prompt "新的提示词内容" \
  --temperature 0.5
```

---

#### 删除 Agent

**通过 Web UI**：
- 在 Agents 列表找到目标 Agent
- 点击 "Delete" 按钮
- 确认删除（注意：此操作不可恢复）

**通过 CLI**：
```bash
aiplat agent delete --name customer-support
```

---

### 二、Skill（技能）管理

#### 什么是 Skill？

Skill 是 Agent 可以调用的能力，扩展 Agent 的功能：

| Skill 名称 | 功能 | 触发示例 |
|------------|------|----------|
| `weather` | 查询天气 | "北京今天天气怎么样？" |
| `calculator` | 数学计算 | "计算 123 × 456" |
| `web_search` | 网络搜索 | "搜索最新的 AI 新闻" |
| `code_execute` | 执行代码 | "写一个 Python 脚本计算斐波那契数列" |
| `database_query` | 数据库查询 | "查询上月销售额前10的产品" |
| `document_analysis` | 文档分析 | "分析这个PDF文档的主要内容" |

---

#### 查看可用 Skill

**通过 Web UI**：
- 左侧菜单选择 "Skills"
- 查看 Skill 列表
- 点击 Skill 名称查看详情

**通过 CLI**：
```bash
# 列出所有 Skill
aiplat skill list

# 查看 Skill 详情
aiplat skill show --name weather
```

---

#### 为 Agent 启用 Skill

**通过 Web UI**：
- 进入 Agent 详情页
- 点击 "Skills" 标签
- 勾选需要启用的 Skill
- 点击 "Save"

**通过 CLI**：
```bash
# 启用 Skill
aiplat agent enable-skill --name customer-support --skill weather

# 禁用 Skill
aiplat agent disable-skill --name customer-support --skill weather

# 查看已启用的 Skill
aiplat agent skills --name customer-support
```

---

#### Skill 参数说明

部分 Skill 需要额外配置：

| Skill | 必填参数 | 可选参数 |
|-------|----------|----------|
| `weather` | 无 | `city`（默认城市）|
| `calculator` | 无 | `precision`（精度）|
| `web_search` | 无 | `max_results`（结果数量）|
| `database_query` | `connection_string` | `timeout`（超时时间）|

**配置示例**（Web UI）：
1. 进入 Skill 配置页
2. 填写参数值
3. 点击 "Test" 测试
4. 点击 "Save"

---

### 三、知识库管理

#### 什么是知识库？

知识库用于存储您的**私有数据**，让 AI 助手能够回答基于您自己数据的问题。

**典型应用场景**：
- 企业内部知识问答
- 产品文档问答
- 客户服务知识库
- 技术文档检索

---

#### 支持的文件格式

| 格式 | 文件大小限制 | 说明 |
|------|--------------|------|
| `.txt` | 10 MB | 纯文本文件 |
| `.pdf` | 50 MB | PDF 文档 |
| `.docx` | 20 MB | Word 文档 |
| `.md` | 10 MB | Markdown 文件 |
| `.csv` | 50 MB | 表格数据 |
| `.xlsx` | 50 MB | Excel 表格 |
| `.pptx` | 50 MB | PowerPoint |

---

#### 创建知识库

**通过 Web UI**：

**步骤 1：进入创建页面**
- 左侧菜单选择 "Knowledge Bases"
- 点击 "Create Knowledge Base"

**步骤 2：填写基本信息**

| 字段 | 说明 | 示例 |
|------|------|------|
| 名称 | 知识库唯一标识 | `company-docs` |
| 显示名称 | 友好显示名称 | `公司文档` |
| 描述 | 知识库用途说明 | `存储公司内部文档` |

**步骤 3：选择嵌入模型**

| 模型 | 说明 | 推荐 |
|------|------|------|
| `text-embedding-3-small` | OpenAI 小模型 | ✅ 推荐（性价比高）|
| `text-embedding-3-large` | OpenAI 大模型 | 高精度场景 |
| `text-embedding-ada-002` | OpenAI 旧版模型 | 兼容旧系统 |

**步骤 4：创建**
- 点击 "Create"
- 等待知识库初始化完成

**通过 CLI**：
```bash
aiplat knowledge create \
  --name company-docs \
  --display-name "公司文档" \
  --description "存储公司内部文档" \
  --embedding-model text-embedding-3-small
```

---

#### 上传文档

**通过 Web UI**：

**步骤 1：进入知识库**
- 点击知识库名称进入详情页

**步骤 2：上传文档**
- 点击 "Upload Documents"
- 拖拽文件或点击选择文件
- 支持同时上传多个文件

**步骤 3：等待处理**
- 系统自动解析文档
- 提取文本、分块、向量化
- 状态从 "Processing" 变为 "Ready"

**处理时间参考**：
| 文件大小 | 预计时间 |
|----------|----------|
| < 1 MB | 10-30 秒 |
| 1-10 MB | 30秒-2分钟 |
| 10-50 MB | 2-5 分钟 |
| > 50 MB | 5-15 分钟（建议拆分文件）|

**通过 CLI**：
```bash
# 上传单个文档
aiplat knowledge upload --name company-docs --file ./document.pdf

# 上传多个文档
aiplat knowledge upload --name company-docs --file ./doc1.pdf ./doc2.pdf ./doc3.docx

# 上传目录下的所有文档
aiplat knowledge upload --name company-docs --directory ./documents/
```

---

#### 查询知识库

**通过 Web UI**：

**步骤 1：进入查询页面**
- 进入知识库详情页
- 点击 "Query" 标签

**步骤 2：输入问题**
- 在搜索框输入问题
- 点击 "Search"

**步骤 3：查看结果**
- 结果列表按相关性排序
- 点击结果查看原文

**通过 CLI**：
```bash
# 查询知识库
aiplat knowledge query --name company-docs --question "公司的报销流程是什么？"

# 指定返回结果数量
aiplat knowledge query --name company-docs --question "年假政策" --top-k 5
```

---

#### 管理文档

**查看文档列表**：
- Web UI：进入知识库详情页，点击 "Documents" 标签
- CLI：`aiplat knowledge documents --name company-docs`

**删除文档**：
- Web UI：点击文档右侧 "Delete" 按钮
- CLI：`aiplat knowledge delete-document --name company-docs --id <doc-id>`

**更新文档**：
- 先删除旧文档
- 重新上传新文档

---

#### 关联知识库到 Agent

**通过 Web UI**：
- 进入 Agent 详情页
- 点击 "Knowledge" 标签
- 勾选要关联的知识库
- 点击 "Save"

**通过 CLI**：
```bash
aiplat agent link-knowledge \
  --name customer-support \
  --knowledge company-docs
```

---

### 四、对话管理

#### 查看对话历史

**通过 Web UI**：
- 左侧菜单选择 "Sessions"
- 查看所有对话记录
- 点击记录查看详情

**通过 CLI**：
```bash
# 查看最近的对话
aiplat session list --limit 20

# 查看特定 Agent 的对话
aiplat session list --agent customer-support

# 查看对话详情
aiplat session show --id <session-id>
```

---

#### 导出对话记录

**通过 Web UI**：
- 点击对话记录右上角 "Export" 按钮
- 选择导出格式（JSON/Markdown/TXT）
- 下载文件

**通过 CLI**：
```bash
# 导出为 JSON
aiplat session export --id <session-id> --format json

# 导出为 Markdown
aiplat session export --id <session-id> --format markdown
```

---

#### 删除对话记录

**通过 Web UI**：
- 点击对话记录右侧 "Delete" 按钮
- 确认删除

**通过 CLI**：
```bash
aiplat session delete --id <session-id>
```

---

## ⚙️ 配置说明

### Web UI 配置

**访问配置页面**：
- 点击右上角用户头像
- 选择 "Settings"

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| 主题 | 亮色/暗色/跟随系统 | 跟随系统 |
| 语言 | 界面语言 | 中文 |
| 每页条数 | 列表每页显示数量 | 20 |
| 通知 | 开启/关闭通知 | 开启 |

---

### CLI 配置

**配置文件位置**：`~/.aiplatform/config.yaml`

**查看当前配置**：
```bash
aiplat config show
```

**配置文件示例**：
```yaml
# ~/.aiplatform/config.yaml
api:
  url: http://localhost:8000
  timeout: 30
  
auth:
  token_file: ~/.aiplatform/token
  
defaults:
  agent: chat-assistant
  knowledge: company-docs
  
output:
  format: table  # table, json, yaml
  color: true
```

**修改配置**：
```bash
# 设置 API 地址
aiplat config set api.url https://api.example.com

# 设置默认 Agent
aiplat config set defaults.agent customer-support

# 设置输出格式
aiplat config set output.format json
```

---

### API 认证

**所有 API 请求都需要认证**。

**获取 Token**：

方式一：用户名密码
```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin@aiplatform.com",
    "password": "admin123"
  }'
```

方式二：Web UI 生成
- 登录 Web UI
- 进入 "Settings" → "API Tokens"
- 点击 "Generate Token"
- 复制 Token

**使用 Token**：
```bash
# 在请求头中携带 Token
curl -X GET http://localhost:8000/api/v1/agents \
  -H "Authorization: Bearer <your-token>"
```

**Token 有效期**：
- 默认 24 小时
- 可在 "Settings" → "API Tokens" 刷新

---

## 💡 使用技巧与最佳实践

### 提示词编写技巧

| 技巧 | 说明 | 示例 |
|------|------|------|
| **明确角色** | 告诉 Agent 它是什么角色 | `你是一名专业的客服助手，擅长解答用户问题` |
| **提供示例** | 给出输入输出示例 | `例如：用户问"退货流程"，你回答"请按以下步骤..."` |
| **设定边界** | 明确能做什么、不能做什么 | `只回答与公司业务相关的问题，拒绝其他话题` |
| **格式化输出** | 指定输出格式 | `用 Markdown 列表形式回答，每个要点一行` |

**好的提示词示例**：
```
你是一名专业的客服助手，负责解答用户关于公司产品的问题。

你的职责：
- 回答产品相关问题
- 处理客户投诉
- 提供使用指导

你的边界：
- 不讨论竞争对手产品
- 不承诺具体优惠或赔偿

回答格式：
- 简洁明了，300 字以内
- 使用 Markdown 列表
- 语气友好专业
```

---

### 知识库优化建议

| 问题 | 建议 | 操作 |
|------|------|------|
| 检索效果差 | 文档分段要合理 | 每段聚焦一个主题，避免过长段落 |
| 处理时间长 | 大文件拆分为多个小文件 | 单文件建议 < 50 MB |
| 回答不准确 | 检查文档质量 | 确保内容清晰无歧义，避免扫描件 |
| 检索不相关 | 检查问题表达 | 尝试不同的提问方式 |
| 多语言问题 | 检查语言一致性 | 文档语言与问题语言保持一致 |

---

### 常见误区

| 误区 | 正确做法 |
|------|----------|
| Agent 类型选错 | Chat Assistant 适合通用对话，RAG Agent 适合知识问答，Tool Agent 适合调用外部工具 |
| 提示词过于复杂 | 提示词应简洁明确，300 字以内最佳，避免过于复杂的指令 |
| 一次上传过多文档 | 分批上传，每批不超过 10 个文件，观察处理状态 |
| 忘记保存配置 | 修改配置后记得点击 "Save"，否则不会生效 |
| 忽略错误信息 | 错误信息包含问题原因，仔细阅读可快速定位问题 |
| Token 过期未刷新 | Token 默认 24 小时过期，过期前刷新或重新登录 |

---

### 性能优化建议

| 场景 | 优化建议 |
|------|----------|
| Agent 响应慢 | 缩短提示词、降低温度、使用更快的模型（如 gpt-3.5-turbo）|
| 知识库检索慢 | 优化文档分段、减少单文档大小、使用更快的嵌入模型 |
| API 调用频繁失败 | 降低并发数、添加重试机制、检查限流配置 |
| 内存占用高 | 清理历史对话、删除无用文档、调整缓存配置 |

---

## 📌 版本信息

### 当前文档适用版本

| 组件 | 版本 |
|------|------|
| aiPlatform | 1.0.0 |
| API | v1 |
| CLI | 1.0.0 |

### 查看版本

**Web UI**：
- 页面底部显示版本号

**CLI**：
```bash
aiplat --version
# 输出：aiplat-cli 1.0.0
```

**API**：
```bash
curl http://localhost:8000/api/v1/version
# 输出：{"version": "1.0.0", "api_version": "v1"}
```

### 版本兼容性

- API v1 将在 1.x 版本中保持稳定
- 新功能会以向后兼容的方式添加
- 破坏性变更会提前 30 天通知并发布迁移指南
- CLI 版本需与 API 版本匹配（主版本号一致）

---

## 🐛 常见问题

### Agent 执行问题

#### Q：Agent 响应很慢或超时

**原因**：
- LLM 服务繁忙（高峰期）
- 输入内容过长
- 网络问题

**解决方法**：
1. 等待 30 秒后再试
2. 缩短问题长度
3. 检查系统状态页面
4. 切换其他模型

---

#### Q：Agent 回复不相关或错误

**原因**：
- 提示词不清晰
- 问题过于模糊
- 缺少上下文

**解决方法**：
1. 优化系统提示词
2. 提供更具体的问题
3. 提供必要的背景信息
4. 启用相关 Skill

---

#### Q：Agent 不使用我启用的 Skill

**原因**：
- Skill 触发词不匹配
- 问题表达方式不对
- Skill 配置问题

**解决方法**：
1. 明确提示需要使用 Skill（如"使用计算器计算..."）
2. 查看 Skill 的触发词说明
3. 检查 Skill 配置参数

---

### 知识库问题

#### Q：上传文档后状态一直是 "Processing"

**原因**：
- 文档较大，处理时间长
- 系统负载高
- 文档格式问题

**解决方法**：
1. 等待 5-10 分钟
2. 刷新页面查看状态
3. 尝试重新上传文档
4. 联系管理员查看后台日志

---

#### Q：知识库检索不到相关内容

**原因**：
- 文档还在处理中
- 问题与文档内容不相关
- 文档语言与问题语言不一致
- 文档质量问题（扫描件、乱码）

**解决方法**：
1. 确认文档状态为 "Ready"
2. 检查文档内容是否包含答案
3. 尝试不同的提问方式
4. 检查文档质量，必要时重新上传

---

#### Q：文档处理失败

**原因**：
- 文件格式不支持
- 文件损坏
- 文件过大

**解决方法**：
1. 检查文件格式是否支持
2. 尝试重新生成文件
3. 压缩大文件或分块上传
4. 查看错误日志

---

### 认证问题

#### Q：登录后 Token 很快过期

**原因**：
- Token 有效期配置较短
- 系统时间不同步

**解决方法**：
1. 在 Settings 中刷新 Token
2. 检查系统时间是否正确
3. 联系管理员延长 Token 有效期

---

#### Q：API 返回 401 Unauthorized

**原因**：
- Token 过期或无效
- Token 格式错误

**解决方法**：
1. 重新获取 Token
2. 检查 Authorization 头格式（应为 "Bearer <token>"）
3. 确认 Token 未过期

---

### 性能问题

#### Q：页面加载慢

**原因**：
- 网络延迟
- 浏览器缓存
- CDN 问题

**解决方法**：
1. 清除浏览器缓存
2. 检查网络连接
3. 尝试其他浏览器
4. 联系管理员检查 CDN 状态

---

#### Q：API 返回 429 Too Many Requests

**原因**：
- 触发了限流（请求过于频繁）
- 配额用尽

**解决方法**：
1. 降低请求频率
2. 查看配额使用情况
3. 联系管理员提高配额
4. 升级到更高级套餐

---

## 📞 获取帮助

### 在线帮助

| 渠道 | 说明 |
|------|------|
| 文档中心 | 查看详细使用文档 |
| 视频教程 | 视频演示操作流程 |
| FAQ | 常见问题解答 |
| 社区论坛 | 用户交流讨论 |

### 技术支持

| 问题类型 | 联系方式 | 响应时间 |
|----------|----------|----------|
| 使用问题 | 提交工单 | 24小时内 |
| Bug 反馈 | 提交工单 | 48小时内 |
| 功能建议 | 反馈表单 | - |
| 紧急问题 | 电话支持 | 立即 |

### 提交工单

**步骤**：
1. 登录系统
2. 点击右上角 "? Help"
3. 选择 "Submit Ticket"
4. 填写问题描述
5. 提交等待回复

**提供以下信息可加快处理**：
- 问题描述
- 复现步骤
- 截图或日志
- 使用的 Agent/Skill 名称
- 执行 ID（如有）

---

## 🔗 相关链接

- [← 返回主文档](../../index.md)
- [开发者指南](../developer/index.md) - API 详细文档
- [架构师指南](../architect/index.md) - 系统架构说明

---

*最后更新: 2026-04-10*
