# 工具系统增强设计

## 概述

本文档描述如何增强 aiPlat-core 的工具系统，新增多种工具类型并实现权限控制。

## 目标

1. **新增工具类型** - HTTP、Browser、Database、CodeExecution、WebFetch
2. **增强权限系统** - 基于角色的访问控制 (RBAC)
3. **统一工具接口** - 所有工具实现 ITool 接口

## 架构设计

### 现有工具

| 工具 | 状态 | 说明 |
|------|------|------|
| FileTool | 存在 | 文件操作 |
| BashTool | 存在 | Shell 命令 |
| RecallerTool | 存在 | 记忆检索 |
| WebFetchTool | 新增 | 网页抓取 |

### 新增工具

```
core/apps/tools/
├── http.py         # HTTP 客户端工具
├── browser.py      # 浏览器自动化工具
├── database.py     # 数据库工具
├── code.py         # 代码执行工具
└── webfetch.py    # 网页抓取工具
```

## 工具详情

### 1. HTTPClientTool

**功能**: 发起 HTTP 请求

**参数**:
- `url` (必填): 目标 URL
- `method`: HTTP 方法 (GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS)
- `headers`: 请求头
- `body`: 请求体 (JSON)
- `timeout`: 超时时间 (ms)

**安全特性**:
- URL 白名单验证
- 仅支持 http/https
- 响应大小限制 (10MB)

**代码示例**:
```python
tool = HTTPClientTool(whitelist=["api.example.com", "github.com"])
result = await tool.execute({
    "url": "https://api.example.com/data",
    "method": "GET",
    "headers": {"Authorization": "Bearer token"}
})
```

### 2. BrowserTool

**功能**: 浏览器自动化 (Playwright/Selenium)

**参数**:
- `action`: 操作类型 (navigate, click, type, screenshot, evaluate)
- `selector`: CSS 选择器
- `url`: 导航 URL
- `script`: JavaScript 代码

**安全特性**:
- 沙盒环境运行
- 禁止访问敏感 API

### 3. DatabaseTool

**功能**: 数据库查询和操作

**参数**:
- `operation`: 操作类型 (query, execute, connect)
- `connection_string`: 数据库连接串
- `query`: SQL 查询
- `params`: 查询参数

**安全特性**:
- 连接串加密存储
- SQL 注入防护
- 只读模式支持

### 4. CodeExecutionTool

**功能**: 沙盒代码执行

**参数**:
- `language`: 编程语言 (python, javascript)
- `code`: 代码内容
- `timeout`: 执行超时 (ms)

**安全特性**:
- 资源限制 (CPU, Memory)
- 网络隔离
- 临时文件系统

**支持语言**:
- Python
- JavaScript

### 5. WebFetchTool

**功能**: 网页内容抓取

**参数**:
- `url`: 目标 URL
- `format`: 输出格式 (text, html, markdown)
- `max_length`: 最大长度

## 权限系统增强

### 模块结构

```
core/apps/tools/permission.py
```

### 核心组件

#### PermissionManager

基于用户-工具的细粒度权限管理。

```python
from core.apps.tools.permission import PermissionManager, Permission

manager = PermissionManager()
manager.grant_permission("user1", "http", Permission.EXECUTE)
has_perm = manager.check_permission("user1", "http", Permission.EXECUTE)
```

#### RBAC (RoleBasedAccess)

基于角色的访问控制。

```python
from core.apps.tools.permission import RoleBasedAccess, Role, ResourcePermission, Permission

rbac = RoleBasedAccess()
rbac.assign_role("user1", "developer")

# 检查权限
can_access = rbac.check_permission(
    "user1",
    "file",
    "/workspace/src/main.py",
    Permission.READ
)
```

### 内置角色

| 角色 | 权限 |
|------|------|
| developer | 读取 /workspace/*, 写入 /workspace/src/*, 读取 API |
| analyst | 读取 /workspace/data/*, 读取 analytics_* 数据库 |
| admin | 所有文件/数据库/API 全部权限 |

### 资源权限类型

- `file`: 文件系统路径
- `api`: API URL
- `database`: 数据库名
- `command`: 命令名称

## 工具基类

所有工具继承 `BaseTool`:

```python
from core.apps.tools.base import BaseTool, ToolConfig

class MyTool(BaseTool):
    async def execute(self, params: Dict) -> ToolResult:
        # 实现
        pass
```

## 安全最佳实践

1. **最小权限** - 默认拒绝，仅授予必要权限
2. **资源限制** - 设置超时、内存、CPU 限制
3. **输入验证** - 验证所有用户输入
4. **审计日志** - 记录工具调用历史
5. **网络隔离** - 限制网络访问

---

## Hook 机制

基于 Claude Code 的事件驱动自动化机制，在工具执行过程中注入自定义逻辑。

### 1. 事件类型

| 事件 | 触发时机 | 能否阻止执行 | 典型用途 |
|------|----------|--------------|----------|
| `PreToolUse` | 工具执行前 | ✅ 是 | 验证参数、修改输入 |
| `PostToolUse` | 工具执行后 | ❌ 否 | 日志记录、结果格式化 |
| `UserPromptSubmit` | 用户提交提示词时 | ✅ 是 | 输入校验、安全检查 |
| `Stop` | Agent 完成回复时 | ✅ 是 | 完成检查、结果验证 |
| `SessionStart` | 会话开始时 | ❌ 否 | 环境初始化 |
| `Notification` | 通知发送时 | ❌ 否 | 自定义通知 |

### 2. Hook 配置

```yaml
# hook.yaml
name: security-scan
description: 文件写入后自动扫描敏感信息

# 触发事件
event: PostToolUse

# 触发条件（仅当工具为 Write 或 Edit 时触发）
condition:
  tool_name: ["Write", "Edit"]

# 执行脚本
script: scripts/security-scan.py

# 优先级（数字越小越先执行）
priority: 100
```

### 3. Hook 脚本接口

Hook 通过 stdin 接收 JSON 事件，退出码控制流程：

```json
{
  "session_id": "abc123",
  "hook_event_name": "PostToolUse",
  "tool_name": "Write",
  "tool_input": {
    "path": "/workspace/src/config.py",
    "content": "API_KEY = 'sk-xxx'"
  },
  "tool_result": {
    "success": true
  }
}
```

**退出码含义**：
- `0`: 继续执行，不做干预
- `1`: 记录日志（信息）
- `2`: 阻止执行，显示 stderr 原因

### 4. 内置 Hook 示例

#### auto-adapt-mode（权限自适应学习）

用户手动批准工具操作后，自动泛化为权限规则：

```
批准: git push origin main
↓ 自动泛化
规则: Bash(git push:*)  ← 匹配所有 git push 变体

批准: npm run build
↓ 自动泛化
规则: Bash(npm run:*)   ← 匹配所有 npm run 子命令
```

**硬底线** - 以下命令永远不会被记忆：
- `rm -rf` 系列
- `sudo` 系列
- `npm publish`
- `git push --force`
- `DROP TABLE`

#### context-tracker（Token 追踪）

精确追踪每次请求的 Token 消耗：

```python
# 通过 PreToolUse 记录起点
# 通过 Stop 记录终点
# 计算差值 = 本次请求消耗
```

#### pre-commit（提交前检查）

检测到 git commit 时自动运行测试：

```bash
# 自动识别项目语言
Node.js → npm test
Python → pytest
Go → go test
```

#### security-scan（安全扫描）

文件写入后扫描硬编码密钥：

```python
# 检测模式
- "AKIA[0-9A-Z]{16}"           # AWS Key
- "sk-[a-zA-Z0-9]{20,}"        # OpenAI Key
- "ghp_[a-zA-Z0-9]{36,}"      # GitHub Token
```

#### format-code（自动格式化）

文件写入后自动格式化：

```
JS/TS → prettier
Python → black
Go → gofmt
```

### 5. 模块结构

```
core/apps/tools/
├── hooks/
│   ├── __init__.py
│   ├── registry.py      # Hook 注册表
│   ├── executor.py      # Hook 执行器
│   ├── builtin/         # 内置 Hook
│   │   ├── __init__.py
│   │   ├── auto_adapt.py
│   │   ├── context_tracker.py
│   │   ├── pre_commit.py
│   │   ├── security_scan.py
│   │   └── format_code.py
│   └── types.py         # Hook 类型定义
```

### 6. 核心组件

#### HookRegistry

```python
class HookRegistry:
    """Hook 注册表"""
    
    def register(self, hook: HookConfig):
        """注册 Hook"""
        pass
    
    def get_hooks(self, event: str) -> List[Hook]:
        """获取指定事件的所有 Hook"""
        pass
    
    def unregister(self, name: str):
        """注销 Hook"""
        pass
```

#### HookExecutor

```python
class HookExecutor:
    """Hook 执行器"""
    
    async def execute_pre(self, tool: Tool, params: Dict) -> Optional[Dict]:
        """PreToolUse - 可修改参数或阻止执行"""
        pass
    
    async def execute_post(self, tool: Tool, result: ToolResult):
        """PostToolUse - 记录日志、后处理"""
        pass
    
    async def execute_stop(self, response: AgentResponse):
        """Stop - 最终检查"""
        pass
```

### 7. 与 Skill 系统集成

Hook 可调用 Skill：

```python
# PreToolUse 中调用安全审查 Skill
async def pre_tool_use(tool, params):
    if tool.name == "Write":
        # 调用安全审查 Skill
        result = await skill_executor.execute(
            "security-review",
            {"file": params["path"], "content": params["content"]}
        )
        if not result.success:
            return {"block": True, "reason": result.error}
```

### 8. 与 Subagent 集成

Subagent 可配置专属 Hook：

```python
subagent_config = SubagentConfig(
    name="debugger",
    hooks=["debug-logger", "error-tracker"]  # 专属 Hook
)
```

## 使用方式

### 1. 注册 Hook

```python
from core.apps.tools.hooks import HookRegistry, HookConfig

registry = HookRegistry()

config = HookConfig(
    name="my-hook",
    event="PostToolUse",
    condition={"tool_name": ["Bash"]},
    script="scripts/my-hook.py",
    priority=50
)
registry.register(config)
```

### 2. 启用内置 Hook

```python
from core.apps.tools.hooks.builtin import enable_all_builtin_hooks

# 启用所有内置 Hook
await enable_all_builtin_hooks()

# 或只启用特定 Hook
await enable_builtin_hook("security-scan")
```

### 3. 查看 Hook 状态

```bash
# 查看所有已注册 Hook
aiplat hooks list

# 查看 Hook 执行日志
aiplat hooks logs --event=PostToolUse
```

## 待实现

- [ ] core/apps/tools/hooks/ 模块实现
- [ ] HookRegistry 实现
- [ ] HookExecutor 实现
- [ ] 内置 Hook 实现
- [ ] 与 ToolExecutor 集成
- [ ] 与 Skill 系统集成