# 📖 应用层用户指南

> aiPlat-app - Web UI 和 CLI 使用指南

---

## 🎯 本指南适合谁？

本指南适合所有使用应用层的用户：
- **业务用户**：使用 Web 界面操作
- **开发者**：使用 CLI 工具操作
- **管理员**：管理系统和用户

**不需要编程基础**，跟着步骤操作即可。

---

## 🚀 5 分钟快速开始

### Web 界面

**步骤 1：打开浏览器**
- 访问 `http://localhost:3000`（开发环境）
- 或 `https://app.example.com`（生产环境）

**步骤 2：登录系统**
- 输入邮箱：`user@example.com`
- 输入密码：`password123`
- 点击 "登录"

**步骤 3：创建 AI 助手**
- 左侧菜单点击 "Agents"
- 点击 "Create Agent"
- 选择类型 "Chat"
- 输入名称：`my-assistant`
- 点击 "Create"

**步骤 4：开始对话**
- 点击刚创建的 Agent
- 在对话框输入：`你好`
- 点击 "发送"
- 等待 AI 回复

---

### 命令行工具

**步骤 1：安装 CLI**
```bash
pip install aiplat-cli
```

**步骤 2：登录**
```bash
aiplat login
# 输入邮箱和密码
```

**步骤 3：列出 AI 助手**
```bash
aiplat agent list
```

**步骤 4：执行对话**
```bash
aiplat agent run chat-assistant --input "你好"
```

---

## 📖 Web 界面使用

### 一、登录与注册

#### 注册新账号

**步骤 1：打开注册页面**
- 点击 "注册" 或 "创建账号"

**步骤 2：填写信息**

| 字段 | 说明 | 示例 |
|------|------|------|
| 邮箱 | 用于登录和找回密码 | `user@example.com` |
| 密码 | 至少 8 位，包含字母和数字 | `Password123` |
| 确认密码 | 再次输入密码 | `Password123` |

**步骤 3：验证邮箱**
- 系统发送验证邮件
- 点击邮件中的验证链接
- 验证成功后可登录

#### 登录系统

**步骤 1：输入账号**
- 输入邮箱地址
- 输入密码

**步骤 2：可选二次验证**
- 如启用两步验证，输入验证码

**步骤 3：进入主页**
- 登录成功后跳转到主页

#### 找回密码

**步骤 1：点击 "忘记密码"**

**步骤 2：输入邮箱**
- 系统发送重置邮件

**步骤 3：重置密码**
- 点击邮件链接
- 设置新密码

---

### 二、Agent 管理

#### 创建 Agent

**步骤 1：进入 Agent 页面**
- 左侧菜单选择 "Agents"
- 点击右上角 "Create Agent"

**步骤 2：选择类型**

| 类型 | 说明 | 适用场景 |
|------|------|----------|
| Chat | 通用对话 | 问答、闲聊 |
| Code | 代码助手 | 代码生成、调试 |
| RAG | 知识库问答 | 企业知识问答 |
| Tool | 工具调用 | 自动化任务 |

**步骤 3：配置基本信息**

| 字段 | 说明 | 示例 |
|------|------|------|
| 名称 | Agent ID（不可修改）| `customer-support` |
| 显示名称 | 界面显示名称 | `客服助手` |
| 描述 | 功能说明 | `处理客户咨询` |

**步骤 4：配置模型**

| 配置项 | 说明 | 推荐 |
|--------|------|------|
| 模型 | LLM 模型 | `gpt-4`（推荐）/ `claude-3` |
| 温度 | 响应随机性 | `0.7` |
| 最大输出 | 回复长度 | `2000` |
| 系统提示词 | 定义行为 | `你是一个专业的客服助手...` |

**步骤 5：选择技能**
- 勾选需要的 Skill
- 推荐新手使用默认配置

**步骤 6：保存**
- 点击 "Create" 或 "Save"

---

#### 配置 Agent

**系统提示词详解**：

```
你是一个专业的客服助手，擅长解答用户问题。

你的职责：
1. 友好地回答用户问题
2. 引导用户完成操作
3. 遇到无法解决的问题，转接人工客服

你的回复风格：
1. 简洁友好
2. 专业准确
3. 耐心细致
```

**常见配置建议**：

| 场景 | 模型 | 温度 | 提示词建议 |
|------|------|------|------------|
| 客服 | gpt-4 | 0.7 | 专业、友好 |
| 代码 | gpt-4 | 0.3 | 准确、详细 |
| 创意 | gpt-4 | 0.9 | 创意、开放 |
| 分析 | claude-3 | 0.5 | 分析、全面 |

---

#### 运行 Agent

**步骤 1：选择 Agent**
- 在 Agents 列表点击 Agent 名称
- 进入 Agent 详情页

**步骤 2：开始对话**
- 在底部输入框输入问题
- 点击 "发送" 或按 Enter
- 等待 AI 回复（5-30 秒）

**步骤 3：继续对话**
- 在输入框继续输入
- AI 记住上下文
- 点击 "清空对话" 开始新对话

#### 查看历史

**步骤 1：进入历史页面**
- 点击 Agent 详情页的 "History" 标签

**步骤 2：查看记录**
- 列表显示所有历史对话
- 点击记录查看详情

**步骤 3：搜索历史**
- 输入关键词搜索
- 按日期范围筛选

#### 编辑 Agent

**步骤 1：进入编辑页面**
- 在 Agent 列表点击 "Edit"

**步骤 2：修改配置**
- 修改系统提示词
- 调整模型参数
- 添加或删除 Skill

**步骤 3：保存更改**
- 点击 "Save"

#### 删除 Agent

**步骤 1：确认删除**
- 在 Agent 列表点击 "Delete"

**步骤 2：确认操作**
- 输入 Agent 名称确认
- 点击 "Delete"（不可恢复）

---

### 三、Skill（技能）管理

#### 查看 Skill

**步骤 1：进入 Skill 页面**
- 左侧菜单选择 "Skills"

**步骤 2：浏览 Skill 列表**

| Skill | 功能 | 触发方式 |
|-------|------|----------|
| 天气查询 | 查询天气 | "北京天气" |
| 计算器 | 数学计算 | "计算 123*456" |
| 网络搜索 | 搜索互联网 | "搜索 AI 新闻" |
| 代码执行 | 执行代码 | "运行 Python" |
| 数据查询 | 查询数据 | "查询销售数据" |

#### 配置 Skill

**步骤 1：进入 Skill 配置**
- 点击 Skill 名称进入详情

**步骤 2：查看配置**
- 查看必需参数
- 查看可选参数

**步骤 3：修改参数**
- 填写参数值
- 点击 "Test" 测试
- 点击 "Save" 保存

---

### 四、知识库管理

#### 创建知识库

**步骤 1：进入知识库页面**
- 左侧菜单选择 "Knowledge Bases"
- 点击 "Create Knowledge Base"

**步骤 2：填写信息**

| 字段 | 说明 | 示例 |
|------|------|------|
| 名称 | 知识库 ID | `company-docs` |
| 显示名称 | 界面名称 | `公司文档` |
| 描述 | 用途说明 | `存储公司内部文档` |
| 嵌入模型 | 向量化模型 | `text-embedding-3-small`（推荐）|

**步骤 3：创建**
- 点击 "Create"

#### 上传文档

**步骤 1：选择上传方式**
- 拖拽文件到上传区域
- 或点击 "选择文件"

**步骤 2：选择文件**
- 支持多文件上传
- 支持格式：PDF、Word、TXT、Markdown
- 最大文件：50 MB

**步骤 3：等待处理**
- 查看处理状态
- Processing → Ready

#### 查询知识库

**步骤 1：进入查询页面**
- 点击知识库名称
- 点击 "Query" 标签

**步骤 2：输入问题**
- 输入自然语言问题
- 点击 "Search"

**步骤 3：查看结果**
- 结果按相关性排序
- 点击查看原文

#### 关联到 Agent

**步骤 1：进入 Agent 设置**
- 进入 Agent 详情页
- 点击 "Knowledge" 标签

**步骤 2：选择知识库**
- 勾选需要关联的知识库
- 点击 "Save"

---

### 五、会话管理

#### 查看会话列表

**步骤 1：进入会话页面**
- 左侧菜单选择 "Sessions"

**步骤 2：筛选会话**
- 按 Agent 筛选
- 按日期范围筛选
- 按状态筛选

#### 查看会话详情

**步骤 1：点击会话**
- 显示完整对话记录

**步骤 2：查看信息**
- 输入问题
- AI 回复
- 执行时间
- Token 使用量

#### 导出会话

**步骤 1：选择会话**
- 勾选要导出的会话

**步骤 2：选择格式**
- JSON
- Markdown
- TXT

**步骤 3：下载**
- 点击 "Export"
- 文件自动下载

---

### 六、系统设置

#### 个人设置

**主题设置**：
- 亮色主题
- 暗色主题
- 跟随系统

**语言设置**：
- 中文
- English

**通知设置**：
- 开启通知
- 关闭通知

#### API Token 管理

**步骤 1：进入 Token 页面**
- 右上角头像 → Settings
- API Tokens

**步骤 2：创建 Token**
- 点击 "Generate Token"
- 输入名称
- 选择过期时间
- 点击 "Create"

**步骤 3：复制 Token**
- ⚠️ Token 只显示一次
- 立即复制保存

**步骤 4：管理 Token**
- 查看已创建的 Token
- 删除不需要的 Token

---

## 📊 Management 管理界面使用

### 概述

Management 管理界面提供完整的系统管理能力，包括：

| 模块 | 功能 | 用户 |
|------|------|------|
| 基础设施管理 | 数据库、缓存、消息队列、对象存储 | 运维人员 |
| 核心层管理 | LLM、向量库、知识库 | 运维人员 |
| 平台层管理 | 编排管理、任务调度 | 运维人员 |
| 应用层管理 | Agent、Skill、会话管理 | 管理员 |

### 基础设施管理

#### 数据库管理

**访问路径**：Management → Infrastructure → Database

**功能列表**：

| 功能 | 说明 | 操作 |
|------|------|------|
| 连接池监控 | 查看数据库连接状态 | 点击 "Connection Pool" |
| 查询监控 | 查看慢查询列表 | 点击 "Slow Queries" |
| 库表管理 | 管理数据库和表 | 点击 "Database List" |
| 性能分析 | 查看数据库性能指标 | 点击 "Performance" |

**查看连接池状态**：
1. 进入 Management → Infrastructure → Database
2. 点击 "Connection Pool" 标签
3. 查看当前连接数、活跃连接数、等待连接数
4. 查看连接池历史趋势图

**查看慢查询**：
1. 进入 Management → Infrastructure → Database
2. 点击 "Slow Queries" 标签
3. 设置查询时间范围（最近1小时、24小时、7天）
4. 查看慢查询列表，包括：
   - 执行时间
   - SQL 语句
   - 耗时
   - 执行次数

#### 缓存管理

**访问路径**：Management → Infrastructure → Cache

**功能列表**：

| 功能 | 说明 | 操作 |
|------|------|------|
| 缓存状态 | 查看缓存健康状态 | 点击 "Status" |
| 内存监控 | 查看内存使用情况 | 点击 "Memory" |
| 命中率统计 | 查看缓存命中率 | 点击 "Hit Rate" |
| 键管理 | 管理缓存键 | 点击 "Keys" |

**查看缓存状态**：
1. 进入 Management → Infrastructure → Cache
2. 查看缓存基本信息：
   - 状态：健康/异常
   - 内存使用：已用/总量
   - 命中率：实时命中率
   - 连接数：当前连接数

**管理缓存键**：
1. 进入 Management → Infrastructure → Cache → Keys
2. 输入键名前缀搜索
3. 查看键列表
4. 操作：
   - 查看键值
   - 删除键
   - 设置过期时间
   - 刷新键

#### 消息队列管理

**访问路径**：Management → Infrastructure → Messaging

**功能列表**：

| 功能 | 说明 | 操作 |
|------|------|------|
| 队列监控 | 查看队列状态 | 点击 "Queues" |
| 消息列表 | 查看消息详情 | 点击 "Messages" |
| 死信队列 | 查看失败消息 | 点击 "Dead Letter Queue" |
| 消费者状态 | 查看消费者状态 | 点击 "Consumers" |

**查看队列状态**：
1. 进入 Management → Infrastructure → Messaging → Queues
2. 查看队列列表：
   - 队列名称
   - 消息数量
   - 消费者数量
   - 状态（正常/积压）
3. 点击队列名称查看详情

**处理死信队列**：
1. 进入 Management → Infrastructure → Messaging → Dead Letter Queue
2. 查看失败消息列表
3. 选择消息
4. 操作：
   - 查看错误原因
   - 重新投递
   - 删除消息

#### 对象存储管理

**访问路径**：Management → Infrastructure → Storage

**功能列表**：

| 功能 | 说明 | 操作 |
|------|------|------|
| 桶管理 | 管理存储桶 | 点击 "Buckets" |
| 文件管理 | 管理文件对象 | 点击 "Files" |
| 使用量统计 | 查看存储使用量 | 点击 "Usage" |
| 访问日志 | 查看访问日志 | 点击 "Access Logs" |

**查看存储桶**：
1. 进入 Management → Infrastructure → Storage → Buckets
2. 查看存储桶列表：
   - 桶名称
   - 存储量
   - 对象数量
   - 创建时间

---

### 核心层管理

#### LLM 管理

**访问路径**：Management → Core → LLM

**功能列表**：

| 功能 | 说明 | 操作 |
|------|------|------|
| 提供商管理 | 管理 LLM 提供商 | 点击 "Providers" |
| 模型配置 | 配置模型参数 | 点击 "Models" |
| Token 监控 | 查看 Token 使用量 | 点击 "Token Usage" |
| 请求日志 | 查看 API 请求日志 | 点击 "Request Logs" |

**配置 LLM 提供商**：
1. 进入 Management → Core → LLM → Providers
2. 点击 "Add Provider"
3. 填写提供商信息：
   - 名称：OpenAI / Claude / 本地模型
   - API 密钥：输入 Key
   - 基础 URL：（可选）
4. 点击 "Test Connection" 验证
5. 点击 "Save" 保存

**查看 Token 使用量**：
1. 进入 Management → Core → LLM → Token Usage
2. 选择时间范围
3. 查看：
   - 总 Token 使用量
   - 按模型分组的使用量
   - 按日期的使用趋势
   - 配额使用情况

#### 向量库管理

**访问路径**：Management → Core → Vector

**功能列表**：

| 功能 | 说明 | 操作 |
|------|------|------|
| 索引管理 | 管理向量索引 | 点击 "Indices" |
| 向量搜索 | 测试向量搜索 | 点击 "Search" |
| 性能监控 | 查看性能指标 | 点击 "Performance" |
| 数据导入导出 | 导入导出向量数据 | 点击 "Import/Export" |

**管理向量索引**：
1. 进入 Management → Core → Vector → Indices
2. 查看索引列表：
   - 索引名称
   - 向量数量
   - 维度
   - 距离算法
3. 操作：
   - 创建索引
   - 删除索引
   - 重建索引
   - 查看索引详情

#### 知识库管理

**访问路径**：Management → Core → Knowledge

**功能列表**：

| 功能 | 说明 | 操作 |
|------|------|------|
| 知识库列表 | 管理知识库 | 点击 "Knowledge Bases" |
| 文档管理 | 管理知识库文档 | 点击 "Documents" |
| 处理队列 | 查看文档处理状态 | 点击 "Processing Queue" |
| 搜索测试 | 测试知识库搜索 | 点击 "Search Test" |

**管理知识库**：
1. 进入 Management → Core → Knowledge → Knowledge Bases
2. 点击 "Create Knowledge Base"
3. 填写信息：
   - 名称
   - 描述
   - 嵌入模型
4. 点击 "Create"

---

### 平台层管理

#### 编排管理

**访问路径**：Management → Platform → Orchestration

**功能列表**：

| 功能 | 说明 | 操作 |
|------|------|------|
| 编排列表 | 管理编排流程 | 点击 "Orchestrations" |
| 执行历史 | 查看执行历史 | 点击 "Execution History" |
| 模板管理 | 管理编排模板 | 点击 "Templates" |
| 监控面板 | 查看监控指标 | 点击 "Dashboard" |

**查看编排执行**：
1. 进入 Management → Platform → Orchestration → Execution History
2. 筛选条件：
   - 时间范围
   - 状态（成功/失败/执行中）
   - 编排名称
3. 查看执行列表
4. 点击查看执行详情

#### 任务调度管理

**访问路径**：Management → Platform → Task Scheduling

**功能列表**：

| 功能 | 说明 | 操作 |
|------|------|------|
| 任务列表 | 管理定时任务 | 点击 "Tasks" |
| 执行队列 | 查看任务执行队列 | 点击 "Queue" |
| 执行历史 | 查看执行历史 | 点击 "History" |
| 日志查看 | 查看任务日志 | 点击 "Logs" |

**管理定时任务**：
1. 进入 Management → Platform → Task Scheduling → Tasks
2. 点击 "Create Task"
3. 配置任务：
   - 任务名称
   - 执行类型（一次性/周期性）
   - 执行时间/周期
   - 任务参数
4. 点击 "Create"

---

### 应用层管理

#### Agent 管理

**访问路径**：Management → App → Agents

**功能列表**：

| 功能 | 说明 | 操作 |
|------|------|------|
| Agent 列表 | 管理 Agent | 点击 "Agents" |
| 运行状态 | 查看 Agent 运行状态 | 点击 "Status" |
| 执行历史 | 查看执行历史 | 点击 "History" |
| 性能监控 | 查看 Agent 性能 | 点击 "Performance" |

**查看 Agent 运行状态**：
1. 进入 Management → App → Agents → Status
2. 查看 Agent 列表：
   - Agent 名称
   - 运行状态
   - 活跃会话数
   - 最近执行时间
3. 点击 Agent 查看详情

#### Skill 管理

**访问路径**：Management → App → Skills

**功能列表**：

| 功能 | 说明 | 操作 |
|------|------|------|
| Skill 列表 | 管理 Skill | 点击 "Skills" |
| 执行历史 | 查看执行历史 | 点击 "History" |
| 权限管理 | 管理 Skill 权限 | 点击 "Permissions" |

**管理 Skill权限**：
1. 进入 Management → App → Skills → Permissions
2. 选择 Skill
3. 配置权限：
   - 公开/私有
   - 访问用户/角色列表
4. 点击 "Save"

#### 会话管理

**访问路径**：Management → App → Sessions

**功能列表**：

| 功能 | 说明 | 操作 |
|------|------|------|
| 会话列表 | 管理会话 | 点击 "Sessions" |
| 活跃会话 | 查看活跃会话 | 点击 "Active" |
| 会话历史 | 查看历史会话 | 点击 "History" |
| 统计分析 | 会话数据分析 | 点击 "Analytics" |

**查看活跃会话**：
1. 进入 Management → App → Sessions → Active
2. 查看活跃会话列表：
   - 会话 ID
   - Agent 名称
   - 用户
   - 开始时间
   - 消息数
3. 操作：
   - 查看会话详情
   - 强制关闭会话
   - 导出会话记录

---

### Management 使用最佳实践

#### 安全访问

**权限设置**：
- 只有管理员和运维人员可访问 Management
- 不同角色有不同的访问权限
- 定期审计访问日志

**访问控制**：
- 使用 RBAC 进行权限控制
- 敏感操作需要二次确认
- 定期更换访问密钥

#### 性能优化

**监控频率**：
- 关键指标：每分钟监控
- 一般指标：每5分钟监控
- 历史数据：按天归档

**告警设置**：
- 合理设置告警阈值
- 分级告警（警告/严重/紧急）
- 设置告警通知渠道

#### 日常维护

**每日检查**：
- 查看系统健康状态
- 检查告警历史
- 查看资源使用情况

**每周检查**：
- 分析资源使用趋势
- 清理过期数据
- 检查日志归档

**每月检查**：
- 容量规划评估
- 性能优化评估
- 安全漏洞扫描

---

## 📖 命令行工具使用

### 安装

```bash
# 使用 pip
pip install aiplat-cli

# 或使用 pipx
pipx install aiplat-cli
```

### 登录

```bash
# 交互式登录
aiplat login

# 输入邮箱：user@example.com
# 输入密码：********
```

### 配置

```bash
# 查看当前配置
aiplat config show

# 设置 API 地址
aiplat config set api.url https://api.example.com

# 设置默认 Agent
aiplat config set default.agent my-agent

# 设置输出格式
aiplat config set output.format json
```

---

### Agent 命令

#### 列出 Agent

```bash
# 列出所有 Agent
aiplat agent list

# 输出 JSON 格式
aiplat agent list --format json

# 筛选类型
aiplat agent list --type chat
```

#### 创建 Agent

```bash
# 交互式创建
aiplat agent create

# 命令式创建
aiplat agent create \
  --name my-agent \
  --display-name "我的助手" \
  --type chat \
  --model gpt-4 \
  --temperature 0.7
```

#### 执行 Agent

```bash
# 同步执行
aiplat agent run --name my-agent --input "你好"

# 指定配置
aiplat agent run \
  --name my-agent \
  --input "你好" \
  --temperature 0.5 \
  --max-tokens 1000

# 异步执行
aiplat agent run --name my-agent --input "你好" --async

# 查看结果
aiplat agent result --id <execution-id>
```

#### 查看历史

```bash
# 查看最近的执行
aiplat agent history --name my-agent --limit 10

# 查看特定日期
aiplat agent history \
  --name my-agent \
  --from 2026-04-01 \
  --to 2026-04-09
```

#### 更新 Agent

```bash
aiplat agent update --name my-agent \
  --display-name "新名称" \
  --temperature 0.5
```

#### 删除 Agent

```bash
aiplat agent delete --name my-agent
```

---

### Skill 命令

#### 列出 Skill

```bash
aiplat skill list
```

#### 查看 Skill 详情

```bash
aiplat skill show --name weather
```

#### 为 Agent 配置 Skill

```bash
# 启用 Skill
aiplat agent enable-skill --name my-agent --skill weather

# 禁用 Skill
aiplat agent disable-skill --name my-agent --skill weather

# 查看已启用的 Skill
aiplat agent skills --name my-agent
```

---

### 知识库命令

#### 创建知识库

```bash
aiplat knowledge create \
  --name my-knowledge \
  --display-name "我的知识库" \
  --description "存储我的文档"
```

#### 上传文档

```bash
# 上传单个文档
aiplat knowledge upload \
  --name my-knowledge \
  --file document.pdf

# 上传多个文档
aiplat knowledge upload \
  --name my-knowledge \
  --file doc1.pdf doc2.pdf doc3.pdf

# 上传目录
aiplat knowledge upload \
  --name my-knowledge \
  --directory ./documents/
```

#### 查询知识库

```bash
aiplat knowledge query \
  --name my-knowledge \
  --question "公司的报销流程是什么？" \
  --top-k 5
```

#### 管理文档

```bash
# 列出文档
aiplat knowledge documents --name my-knowledge

# 删除文档
aiplat knowledge delete-document \
  --name my-knowledge \
  --id doc-123
```

#### 关联到 Agent

```bash
aiplat agent link-knowledge \
  --name my-agent \
  --knowledge my-knowledge
```

---

### 会话命令

#### 创建会话

```bash
aiplat session create \
  --agent my-agent \
  --title "客服对话"
```

#### 发送消息

```bash
# 交互式对话
aiplat session chat --agent my-agent

# 发送单条消息
aiplat session send \
  --session <session-id> \
  --message "如何重置密码？"
```

#### 查看历史

```bash
# 查看会话列表
aiplat session list --limit 20

# 查看会话详情
aiplat session show --id <session-id>

# 导出会话
aiplat session export --id <session-id> --format markdown
```

---

### 其他命令

#### 健康检查

```bash
# 检查 CLI 状态
aiplat doctor

# 检查 API 连接
aiplat ping
```

#### 版本信息

```bash
# 查看版本
aiplat --version

# 查看帮助
aiplat --help

# 查看命令帮助
aiplat agent --help
aiplat agent run --help
```

---

## ⚙️ 配置文件

### 配置文件位置

| 系统 | 位置 |
|------|------|
| Linux/Mac | `~/.aiplatform/config.yaml` |
| Windows | `%USERPROFILE%\.aiplatform\config.yaml` |

### 配置文件示例

```yaml
# API 配置
api:
  url: https://api.example.com
  timeout: 30

# 认证配置
auth:
  token_file: ~/.aiplatform/token

# 默认配置
defaults:
  agent: my-agent
  knowledge: my-knowledge
  output_format: table

# 日志配置
logging:
  level: INFO
  file: ~/.aiplatform/logs/cli.log

# 缓存配置
cache:
  enabled: true
  ttl: 3600
```

### 修改配置

```bash
# 设置配置
aiplat config set api.url https://api.example.com
aiplat config set defaults.agent my-agent

# 查看配置
aiplat config show

# 重置配置
aiplat config reset
```

---

## 🐛 常见问题

### Web 界面问题

#### Q：页面加载很慢

**可能原因**：
- 网络问题
- 浏览器缓存
- CDN 问题

**解决方法**：
1. 清除浏览器缓存
2. 检查网络连接
3. 尝试其他浏览器

#### Q：登录后立即退出

**可能原因**：
- Cookie 被禁用
- Session 过期
- 浏览器隐私设置

**解决方法**：
1. 启用 Cookie
2. 检查隐私设置
3. 尝试无痕模式

#### Q：上传文件失败

**可能原因**：
- 文件过大
- 格式不支持
- 网络中断

**解决方法**：
1. 检查文件大小（最大 50 MB）
2. 检查文件格式
3. 刷新页面重试

### CLI 问题

#### Q：CLI 安装失败

**可能原因**：
- Python 版本过低
- pip 版本过低
- 权限问题

**解决方法**：
```bash
# 检查 Python 版本（需要 3.10+）
python --version

# 升级 pip
pip install --upgrade pip

# 使用用户安装
pip install --user aiplat-cli
```

#### Q：命令执行失败

**可能原因**：
- 未登录
- Token 过期
- 网络问题

**解决方法**：
```bash
# 重新登录
aiplat login

# 检查配置
aiplat config show

# 检查网络
aiplat ping
```

#### Q：输出乱码

**可能原因**：
- 终端不支持 UTF-8
- 字体问题

**解决方法**：
```bash
# 设置终端编码
export LANG=en_US.UTF-8

# 使用 JSON 输出
aiplat agent list --format json
```

### API 问题

#### Q：API 返回 401

**原因**：Token 无效或过期

**解决方法**：
```bash
# 刷新 Token
aiplat auth refresh

# 或重新登录
aiplat login
```

#### Q：API 返回 429

**原因**：触发限流

**解决方法**：
- 等待 1 分钟后重试
- 降低请求频率
- 升级套餐

---

## 📞 获取帮助

### 在线帮助

| 渠道 | 说明 |
|------|------|
| 文档中心 | 详细使用文档 |
| 视频教程 | 操作演示 |
| FAQ | 常见问题 |
| 社区论坛 | 用户交流 |

### 命令行帮助

```bash
# 查看总帮助
aiplat --help

# 查看命令帮助
aiplat agent --help
aiplat agent run --help

# 查看版本
aiplat --version
```

### 技术支持

| 问题类型 | 联系方式 |
|----------|----------|
| 使用问题 | 提交工单 |
| Bug 反馈 | 提交工单 |
| 功能建议 | 反馈表单 |

---

## 🔗 相关链接

- [← 返回应用层文档](../../index.md)
- [平台层用户指南](../../../../aiPlat-platform/docs/by-role/user/index.md)
- [开发者指南](../developer/index.md)

---

*最后更新: 2026-04-09*
