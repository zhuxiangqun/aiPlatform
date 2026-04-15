# 应用层开发规范

> 继承系统级开发规范，针对应用层的特定要求

---

## 继承规范

本文档继承 [系统级开发规范](../../docs/guides/DEVELOPMENT.md)，所有系统级规范在本层必须遵守。

---

## 特定规范

### 层级定位

应用层（Layer 3）面向用户的最终应用，依赖平台层：

```
aiPlat-app (Layer 3)
    ↓ 依赖
    aiPlat-platform（通过 REST/GraphQL API）
    ↑
    用户（通过 Web UI / CLI / Gateway）
```

**允许的依赖**：
- ✅ `aiPlat_platform`（通过 REST/GraphQL API）
- ✅ Python 标准库
- ✅ 第三方库（React, Vue, Click 等）

**禁止的依赖**：
- ❌ `aiPlat_core`（应通过 platform 层访问）
- ❌ `aiPlat_infra`（应通过 platform 层访问）

---

## 应用类型

### Web UI 开发规范

```typescript
// 前端代码规范遵循 TypeScript + React 最佳实践
// - 使用 TypeScript
// - 使用函数组件 + Hooks
// - 使用状态管理（Redux / Zustand）
// - 使用 Tailwind CSS + 自定义组件库
```

### CLI 开发规范

```python
# app/cli/main.py
import click

@click.group()
def cli():
    """AI Platform CLI"""
    pass

@cli.command()
@click.option('--name', '-n', required=True, help='Agent name')
def create_agent(name: str):
    """Create a new agent"""
    # 调用 platform API
    ...

@cli.command()
@click.argument('agent_id')
def execute_agent(agent_id: str):
    """Execute an agent"""
    # 调用 platform API
    ...

if __name__ == '__main__':
    cli()
```

### Gateway 开发规范

```python
# app/gateway/telegram.py
from aiPlat_platform import APIClient

class TelegramGateway:
    """Telegram 消息网关"""
    
    def __init__(self, api_client: APIClient):
        self.api_client = api_client
    
    async def handle_message(self, message: dict):
        """处理 Telegram 消息"""
        # 1. 解析消息
        user_input = self.parse_message(message)
        
        # 2. 调用 platform API
        response = await self.api_client.execute_agent(
            agent_id=self.get_agent_id(message),
            input=user_input
        )
        
        # 3. 返回响应
        await self.send_response(message['chat']['id'], response)
```

---

## 开发检查清单

### Web UI

- [ ] 使用 TypeScript
- [ ] 使用函数组件
- [ ] 状态管理规范
- [ ] API 调用错误处理
- [ ] 响应式设计
- [ ] 无障碍支持

### CLI

- [ ] 命令命名规范（动词_名词）
- [ ] 参数验证
- [ ] 错误处理
- [ ] 帮助文档
- [ ] 进度显示
- [ ] 日志输出

### Gateway

- [ ] 消息格式转换
- [ ] 协议转换
- [ ] 错误处理
- [ ] 重试机制
- [ ] 日志记录

---

## 测试规范

详细测试规范见：[系统级测试指南](../../docs/TESTING_GUIDE.md)

| 测试类型 | 覆盖率要求 |
|----------|-----------|
| 单元测试 | ≥ 60% |
| 集成测试 | ≥ 60% |

---

## 相关链接

- [系统级开发规范](../../docs/guides/DEVELOPMENT.md)
- [系统级测试指南](../../docs/TESTING_GUIDE.md)
- [app层部署指南](./DEPLOYMENT.md)

---

*最后更新: 2026-04-11*