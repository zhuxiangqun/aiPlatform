# 👨‍💻 应用层开发者指南

> aiPlat-app - 开发指南与最佳实践

---

## 🎯 开发者关注点

作为应用层开发者，您需要了解：
- **如何使用**：如何调用 REST API、开发前端界面和 CLI 工具
- **如何扩展**：如何添加新的渠道适配器、CLI 命令、UI 组件
- **如何测试**：如何编写单元测试、集成测试和端到端测试
- **最佳实践**：开发中的最佳实践

---

## 🛠️ 开发环境搭建

### 前置条件

| 工具 | 版本要求 | 用途 |
|------|----------|------|
| Node.js | 18+ | 前端开发（React） |
| Python | 3.10+ | CLI 开发 |
| pnpm / npm | 8+ / 9+ | 包管理 |
| Docker | 20.10+ | 本地服务 |

### 技术栈

| 层次 | 技术 | 版本 |
|------|------|------|
| 前端框架 | **React** | 18+ |
| 状态管理 | **Redux Toolkit** | 2+ |
| 样式框架 | **Tailwind CSS** | 3+ |
| 动画库 | **Framer Motion** | 11+ |
| 图标库 | **Lucide React** | 最新 |
| 构建工具 | **Vite** | 5+ |
| 类型系统 | **TypeScript** | 5+ |

### React + Redux 开发规范

**项目结构**：
```
src/
├── components/          # 可复用组件
│   ├── common/         # 通用组件
│   └── business/       # 业务组件
├── pages/              # 页面组件
│   ├── Dashboard/      # 仪表盘
│   ├── Agents/         # Agent 管理
│   ├── Skills/         # Skill 管理
│   └── Knowledge/      # 知识库管理
├── store/              # Redux 状态管理
│   ├── index.ts        # Store 配置
│   ├── slices/         # ReduxSlices
│   │   ├── agents.ts   # Agent 状态
│   │   ├── skills.ts   # Skill 状态
│   │   └── knowledge.ts# 知识库状态
│   └── hooks.ts        # Redux Hooks
├── services/           # API 服务
│   ├── agent.ts        # Agent API
│   ├── skill.ts        # Skill API
│   └── knowledge.ts    # Knowledge API
├── hooks/               # 自定义 Hooks
├── utils/               # 工具函数
└── types/               # 类型定义
```

**Redux Slice 示例**：
```typescript
// store/slices/agents.ts
import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { agentService } from '@/services/agent';

export const fetchAgents = createAsyncThunk(
  'agents/fetchAgents',
  async () => {
    const response = await agentService.listAgents();
    return response.data;
  }
);

const agentsSlice = createSlice({
  name: 'agents',
  initialState: {
    items: [],
    loading: false,
    error: null,
  },
  reducers: {
    clearError: (state) => {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchAgents.pending, (state) => {
        state.loading = true;
      })
      .addCase(fetchAgents.fulfilled, (state, action) => {
        state.loading = false;
        state.items = action.payload;
      })
      .addCase(fetchAgents.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message;
      });
  },
});

export const { clearError } = agentsSlice.actions;
export default agentsSlice.reducer;
```

**组件最佳实践**：
```typescript
// pages/Agents/AgentList.tsx
import React, { useEffect } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import { Table, Button, Alert } from '@/components/ui';
import { fetchAgents } from '@/store/slices/agents';

const AgentList: React.FC = () => {
  const dispatch = useDispatch();
  const { items, loading, error } = useSelector((state) => state.agents);

  useEffect(() => {
    dispatch(fetchAgents());
  }, [dispatch]);

  if (loading) return <div className="flex justify-center p-8"><Spinner /></div>;
  if (error) return <Alert type="error" message={error} />;

  return (
    <div className="p-6">
      <Table
        data={items}
        columns={[
          { title: '名称', dataIndex: 'name', key: 'name' },
          { title: '类型', dataIndex: 'type', key: 'type' },
          { title: '状态', dataIndex: 'status', key: 'status' },
        ]}
        rowKey="id"
      />
    </div>
  );
};

export default AgentList;
```

---

### 前端环境

**安装依赖**：
```bash
cd aiPlat-app/web
pnpm install
```

**配置环境**：
```bash
# 复制配置模板
cp .env.example .env

# 编辑配置文件
vi .env

# 配置 API 地址
VITE_API_URL=http://localhost:8000
```

**启动开发服务器**：
```bash
pnpm dev
# 访问 http://localhost:3000
```

### CLI 环境

**安装依赖**：
```bash
cd aiPlat-app/cli
pip install -e .
```

**配置环境**：
```bash
# 复制配置模板
cp config/app/cli.yaml.example config/app/cli.yaml

# 编辑配置文件
vi config/app/cli.yaml
```

**验证安装**：
```bash
aiplat --version
aiplat --help
```

### 验证环境

**前端测试**：
```bash
# 运行前端单元测试
make test-web-unit

# 运行前端端到端测试
make test-web-e2e
```

**CLI 测试**：
```bash
# 运行 CLI 单元测试
make test-cli-unit

# 运行 CLI 集成测试
make test-cli-integration
```

---

## 🚀 快速开始

### 5 分钟跑起来（前端）

**步骤一：安装依赖**
```bash
cd aiPlat-app/web
pnpm install
```

**步骤二：配置环境**
```bash
cp .env.example .env
# 编辑 .env 设置 API 地址
```

**步骤三：启动开发服务器**
```bash
pnpm dev
```

**步骤四：访问应用**
```
打开浏览器访问 http://localhost:3000
```

### 5 分钟跑起来（CLI）

**步骤一：安装依赖**
```bash
cd aiPlat-app/cli
pip install -e .
```

**步骤二：配置环境**
```bash
aiplat config init
# 编辑配置文件设置 API地址
```

**步骤三：测试命令**
```bash
aiplat agent list
aiplat skill list
```

---

## 📖 核心模块使用

### channels - 消息通道

**详细文档**：[channels 模块文档](../../channels/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 添加渠道适配 | 在 `app/channels/adapters/` 下创建适配器 | `app/channels/adapters/` |
| 添加消息处理器 | 在 `app/channels/handlers/` 下创建处理器 | `app/channels/handlers/` |

**如何添加新的渠道适配**：

1. **创建适配器文件**：在 `app/channels/adapters/` 下创建 `MyChannelAdapter.ts`
2. **实现适配器接口**：实现 ChannelAdapter 接口
3. **注册适配器**：在通道配置中注册
4. **测试**：添加单元测试

---

### cli - 命令行工具

**详细文档**：[cli 模块文档](../../cli/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 定义命令 | 在 `app/cli/commands/` 下创建命令文件 | `app/cli/commands/` |
| 定义选项 | 使用 `@click.option()` 装饰器 | `app/cli/commands/` |
| 定义参数 | 使用 `@click.argument()` 装饰器 | `app/cli/commands/` |
| 注册命令 | 在 `app/cli/__init__.py` 中注册 | `app/cli/__init__.py` |

**如何添加新的命令**：

1. **创建命令文件**：在 `app/cli/commands/` 下创建 `my_command.py`
2. **定义命令组**：使用 `@click.group()` 创建命令组
3. **定义子命令**：使用 `@click.command()` 创建子命令
4. **实现逻辑**：通过 REST API 调用平台能力
5. **注册命令**：在 `app/cli/__init__.py` 中导入并注册
6. **编写测试**：在 `tests/unit/app/cli/` 下添加测试文件

**命令结构**：
```
aiplat
├── agent
│   ├── list
│   ├── create
│   ├── run
│   └── delete
├── skill
│   ├── list
│   ├── register
│   └── execute
└── config
    ├── init
    ├── set
    └── get
```

**相关文件位置**：
- 命令目录：`app/cli/commands/`
- 配置管理：`app/cli/config.py`
- REST API：`app/client/platform_client.py`

---

### workbench - 工作台

**详细文档**：[workbench 模块文档](../../workbench/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 创建页面 | 在 `app/workbench/pages/` 下创建页面文件 | `app/workbench/pages/` |
| 创建组件 | 在 `app/workbench/components/` 下创建组件文件 | `app/workbench/components/` |
| 管理状态 | 在 `app/workbench/store/` 下创建状态文件 | `app/workbench/store/` |
| 定义动作 | 在 `app/workbench/actions/` 下创建动作文件 | `app/workbench/actions/` |

**如何添加新的页面**：

1. **创建页面文件**：在 `app/workbench/pages/` 下创建 `MyPage.tsx`
2. **实现页面组件**：实现页面 UI 和逻辑
3. **添加路由**：在路由配置中添加页面路由
4. **添加权限**：配置页面访问权限
5. **编写测试**：添加页面测试

**页面类型**：
- **仪表盘**：系统概览、使用统计、快捷入口
- **列表页**：数据列表、搜索、筛选
- **详情页**：详细信息、操作按钮
- **表单页**：数据录入、验证

**相关文件位置**：
- 页面目录：`app/workbench/pages/`
- 组件目录：`app/workbench/components/`
- 状态管理：`app/workbench/store/`
- API 服务：`app/workbench/services/`

---

### services - 应用服务

**详细文档**：[services 模块文档](../../services/index.md)

**操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 调用 Agent API | 使用 `AgentService.xxx()` | `app/workbench/services/agent.ts` |
| 调用 Skill API | 使用 `SkillService.xxx()` | `app/workbench/services/skill.ts` |
| 调用知识库 API | 使用 `KnowledgeService.xxx()` | `app/workbench/services/knowledge.ts` |
| 调用工具 API | 使用 `ToolService.xxx()` | `app/workbench/services/tool.ts` |

**服务层结构**：
```
services/
├── agent.ts          # Agent 服务
├── skill.ts          # Skill 服务
├── knowledge.ts      # 知识库服务
├── tool.ts           # 工具服务
├── auth.ts           # 认证服务
└── http.ts           # HTTP 客户端
```

**调用平台 API**：
1. 创建 REST API 实例
2. 调用对应的服务方法
3. 处理响应和错误

**相关文件位置**：
- 服务目录：`app/workbench/services/`
- HTTP 客户端：`app/workbench/services/http.ts`
- 类型定义：`app/workbench/types/`

---

### client - REST API SDK（说明）

当前仓库未提供独立的 app 层 Python SDK（`app/client/*`）实现。

建议：
- Web UI/工作台：通过 `services`（前端 API 层）调用 platform API
- CLI/脚本：直接通过 HTTP（或后续从 OpenAPI 生成客户端）调用 platform API

---

## 🔧 如何扩展

### 添加新的前端页面

**步骤**：

1. **创建页面文件**：在 `app/workbench/pages/` 下创建页面
2. **实现页面组件**：实现页面 UI 和逻辑
3. **添加 API 服务**：如果需要，在 `app/workbench/services/` 下添加服务
4. **添加路由**：在路由配置中添加页面路由
5. **添加权限**：配置页面访问权限
6. **编写测试**：添加页面测试

### 添加新的 CLI 命令

**步骤**：

1. **创建命令文件**：在 `app/cli/commands/` 下创建命令
2. **定义命令组**：使用 `@click.group()` 创建命令组
3. **定义子命令**：使用 `@click.command()` 创建子命令
4. **实现命令逻辑**：通过 REST API 调用平台能力
5. **注册命令**：在 `app/cli/__init__.py` 中注册
6. **编写测试**：添加命令测试

### 添加新的渠道适配器

**步骤**：

1. **创建适配器文件**：在 `app/channels/adapters/` 下创建适配器
2. **实现适配器接口**：实现适配器接口的方法
3. **注册适配器**：在适配器配置中注册
4. **配置渠道**：配置渠道连接参数
5. **编写测试**：添加适配器测试

---

## 🧪 测试

### 测试目录结构

```
tests/
├── unit/app/               # 单元测试
│   ├── cli/
│   │   └── test_commands.py
│   └── client/
│       └── test_client.py
├── integration/app/        # 集成测试
│   └── test_cli_integration.py
├── e2e/                    # 端到端测试
│   ├── pages/
│   │   └── myPage.spec.ts
│   └── features/
│       └── login.spec.ts
└── fixtures/               # 测试数据
    └── app/
        ├── sample_agents.json
        └── sample_skills.json
```

### 运行测试

| 命令 | 用途 | 前置条件 |
|------|------|----------|
| `make test-web-unit` | 运行前端单元测试 | 无 |
| `make test-web-e2e` | 运行前端端到端测试 | 后端服务启动 |
| `make test-cli-unit` | 运行 CLI 单元测试 | 无 |
| `make test-cli-integration` | 运行 CLI 集成测试 | 后端服务启动 |
| `make test-app-all` | 运行应用层所有测试 | 后端服务启动 |

### 测试编写规范

**前端测试**：

| 规范 | 说明 |
|------|------|
| 单元测试 | 测试组件渲染和交互 |
| 集成测试 | 测试组件组合和 API 调用 |
| 端到端测试 | 测试用户流程 |
| 测试文件命名 | `*.spec.ts` 或 `*.test.ts` |

**CLI 测试**：

| 规范 | 说明 |
|------|------|
| 单元测试 | 测试命令解析和选项处理 |
| 集成测试 | 测试命令执行和参数验证 |
| 测试文件命名 | `test_*.py` |

### Mock 示例

**前端 Mock**（在 `setup.ts` 中定义）：
- `mockApi`：模拟 API 响应
- `mockRouter`：模拟路由
- `mockStore`：模拟状态管理

**CLI Mock**（在 `conftest.py` 中定义）：
- `mock_client`：模拟 REST API
- `mock_config`：模拟配置
- `mock_console`：模拟控制台输出

---

## 📋 最佳实践

### 前端开发

| 要求 | 说明 |
|------|------|
| 组件单一职责 | 每个组件应该只负责一个功能 |
| 类型定义完整 | 所有组件 Props 应该有完整类型定义 |
| 状态管理分离 | 全局状态和组件状态分离 |
| 样式一致性 | 使用统一的样式规范 |

### CLI 开发

| 要求 | 说明 |
|------|------|
| 命令命名清晰 | 命令名使用 kebab-case，如 `agent-list` |
| 帮助信息完整 | 每个命令应该有详细的帮助信息 |
| 错误信息友好 | 错误信息应该清晰易懂 |
| 输出格式化 | 输出应该美观、易读 |

### API 调用

| 要求 | 说明 |
|------|------|
| 错误处理完整 | 所有 API 调用应该有错误处理 |
| 加载状态显示 | 长时间操作应该显示加载状态 |
| 缓存策略合理 | 合理使用缓存减少 API 调用 |
| 请求取消支持 | 支持取消正在进行的请求 |

---

## 🔧 常见问题排查

### 前端问题

| 问题 | 可能原因 | 解决步骤 |
|------|----------|----------|
| 页面加载失败 | 路由配置错误或组件错误 | 1. 检查路由配置<br>2. 检查控制台错误 |
| API 调用失败 | CORS 或认证问题 | 1. 检查 API 地址配置<br>2. 检查认证令牌 |
| 状态不更新 | 状态管理配置错误 | 1. 检查状态定义<br>2. 检查状态更新方式 |
| 组件渲染错误 | Props 类型错误 | 1. 检查 Props 类型定义<br>2. 检查必填Props |

### CLI 问题

| 问题 | 可能原因 | 解决步骤 |
|------|----------|----------|
| 命令找不到 | 命令未注册或名称错误 | 1. 检查命令注册<br>2. 检查命令名称 |
| 连接失败 | API 地址错误或网络问题 | 1. 检查 API 配置<br>2. 检查网络连接 |
| 权限不足 | 认证令牌无效或权限不足 | 1. 检查认证令牌<br>2. 检查用户权限 |
| 输出乱码 | 终端编码问题 | 1. 设置终端编码<br>2. 使用支持的终端 |

---

## 📖 相关链接

- [← 返回应用层文档](../../index.md)
- [架构师指南 →](../architect/index.md)
- [运维指南 →](../ops/index.md)

---

*最后更新: 2026-04-09*
