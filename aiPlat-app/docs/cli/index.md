# CLI 模块

> CLI 模块是 AI Platform 应用层的命令行接口，提供终端交互能力，用于本地开发、调试和运维。

---

## 一、模块定位

### 1.1 核心职责

CLI 模块在整个 AI Platform 架构中承担以下核心职责：

| 职责 | 说明 |
|------|------|
| **命令入口** | 提供命令行工具入口 |
| **交互式对话** | 支持终端 AI 对话 |
| **调试工具** | 提供调试和测试命令 |
| **运维管理** | 服务启动、停止、状态查询 |

### 1.2 与相邻模块的关系

```
┌─────────────────────────────────────────────────────────────┐
│                   Terminal/Console                       │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    CLI Commands                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Chat      │  │  Serve     │  │  Manage             │  │
│  │  (对话)    │  │  (服务)    │  │  (管理)             │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    Gateway / Runtime                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、命令结构

### 2.1 CLI 主命令

```bash
# 主命令
aiplat --help

# 子命令
aiplat chat       # 交互式对话
aiplat serve     # 启动服务
aiplat status    # 查看状态
aiplat config    # 配置管理
aiplat test      # 测试工具
```

### 2.2 Chat 命令

```bash
# 交互式对话
aiplat chat [OPTIONS]

# 选项
--model MODEL      # 指定模型 (default: deepseek-chat)
--temp TEMP       # 温度参数 (default: 0.7)
--stream         # 流式输出
--system SYSTEM  # 系统提示
```

### 2.3 Serve 命令

```bash
# 启动服务
aiplat serve [OPTIONS]

# 选项
--host HOST      # 主机 (default: 0.0.0.0)
--port PORT      # 端口 (default: 8080)
--workers WORKERS  # 工作进程数
--reload         # 开发模式热重载
```

---

## 三、配置结构

### 3.1 CLI 配置

```yaml
# aiPlat-app/cli/config.yaml

cli:
  # ==================== 默认配置 ====================
  defaults:
    model: "deepseek-chat"
    temperature: 0.7
    max_tokens: 4096
    
  # ==================== 服务配置 ====================
  serve:
    host: "0.0.0.0"
    port: 8080
    workers: 4
    reload: false
    
  # ==================== 输出配置 ====================
  output:
    color: true
    rich: true
    stream: false
```

---

## 四、核心接口定义

### 4.1 CLI 基类

```python
class CLICommand:
    """CLI 命令基类"""
    
    name: str           # 命令名
    help: str          # 帮助文本
    options: list      # 选项定义
    
    async def execute(self, **kwargs):
        """执行命令"""
        pass
```

### 4.2 命令列表

| 命令 | 说明 |
|------|------|
| `chat` | 交互式对话 |
| `serve` | 启动服务 |
| `status` | 查看状态 |
| `config` | 配置管理 |
| `test` | 测试工具 |
| `init` | 初始化项目 |

---

## 五、使用示例

### 5.1 交互式对话

```bash
# 启动交互式对话
aiplat chat

# 指定模型
aiplat chat --model gpt-4

# 流式输出
aiplat chat --stream

# 带系统提示
aiplat chat --system "你是一个有帮助的助手"
```

### 5.2 启动服务

```bash
# 启动 API 服务
aiplat serve

# 指定端口
aiplat serve --port 9000

# 开发模式
aiplat serve --reload

# 多进程
aiplat serve --workers 8
```

### 5.3 状态查询

```bash
# 查看服务状态
aiplat status

# 详细输出
aiplat status -v

# JSON 格式
aiplat status --json
```

### 5.4 配置管理

```bash
# 查看配置
aiplat config show

# 设置配置
aiplat config set model gpt-4

# 重置配置
aiplat config reset
```

---

## 六、设计原则

### 6.1 核心设计原则

1. **用户友好**：清晰的帮助文本和错误提示
2. **交互式**：支持实时对话交互
3. **可脚本化**：支持非交互模式
4. **配置优先**：优先使用配置文件

### 6.2 输出设计

1. **彩色输出**：使用 ANSI 颜色
2. **进度指示**：显示处理进度
3. **错误提示**：清晰的错误信息

---

## 七、与旧系统差异

### 7.1 架构差异

| 方面 | 旧系统 (RANGEN) | 新系统 (aiPlat-app) |
|------|----------------|-------------------|
| 命令风格 | 自定义 | Click/Typer |
| 交互模式 | 基础 | 富文本 |

---

## 八、相关文档

- [management 管理平面 - Layer 3 应用层](../../../aiPlat-management/docs/app/index.md)
- [runtime 运行时文档](../runtime/index.md)
- [management 管理平面 - Layer 3 应用层](../../../aiPlat-management/docs/app/index.md)
