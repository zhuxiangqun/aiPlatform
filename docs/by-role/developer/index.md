# 👨‍💻 开发者指南

> aiPlatform - 开发指南与最佳实践

---

## 🎯 开发者关注点

作为开发者，您需要了解：
- **如何使用**：如何调用各层服务
- **如何扩展**：如何添加新的实现
- **如何测试**：如何编写单元测试和集成测试
- **最佳实践**：开发中的最佳实践

---

## 🛠️ 开发环境搭建

### 前置条件

| 工具 | 版本要求 | 用途 |
|------|----------|------|
| Python | 3.10+ | 后端开发 |
| Node.js | 18+ | 前端开发 |
| Docker | 20.10+ | 本地服务 |
| Make | 3.81+ | 构建脚本 |
| Git | 2.30+ | 版本控制 |

---

### 本地服务启动

**启动依赖服务**：
```bash
# 启动所有依赖服务（PostgreSQL、Redis、Milvus）
make docker-up

# 等待服务就绪
make docker-wait

# 查看服务状态
make docker-status
```

**初始化数据库**：
```bash
# 运行数据库迁移
make db-migrate

# 初始化种子数据（可选）
make db-seed
```

**配置环境变量**：
```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入必要的配置
# - LLM_API_KEY: LLM提供商的 API 密钥
# - DATABASE_URL: 数据库连接字符串
# - REDIS_URL: Redis 连接字符串
```

---

### 验证环境

**健康检查**：
```bash
make health-check
```

预期输出：所有服务状态为 healthy

**测试服务连接**：
```bash
# 测试数据库连接
make test-db

# 测试 Redis 连接
make test-redis

# 测试 LLM 连接
make test-llm
```

---

### 各层启动方式

| 层 | 启动命令 | 访问端口 | 说明 |
|----|----------|----------|------|
| infra | `make run-infra` | - | 基础服务（通常不需要单独启动） |
| core | `make run-core` | - | 核心服务（通常不需要单独启动） |
| platform | `make run-platform` | 8000 | API 服务 |
| app | `make run-app` | 3000 | Web 应用 |

**开发模式启动**：
```bash
# 启动所有服务（开发模式，热重载）
make dev

# 仅启动后端服务
make dev-backend

# 仅启动前端服务
make dev-frontend
```

---

## 🚀 快速开始

### 5 分钟跑起来

**步骤一：环境准备**
```bash
git clone <repository>
cd aiPlatform
make setup
```

**步骤二：配置**
```bash
cp .env.example .env
# 编辑 .env，设置 LLM_API_KEY
```

**步骤三：启动服务**
```bash
make docker-up
make dev
```

**步骤四：验证**
- 访问 http://localhost:3000 查看 Web 界面
- 访问 http://localhost:8000/docs 查看 API 文档

---

## 📖 各层开发指南

### 基础设施层开发

**详细文档**：[aiPlat-infra/docs/by-role/developer/index.md](../../../aiPlat-infra/docs/by-role/developer/index.md)

**该文档包含**：
- 数据库客户端的使用方法
- LLM客户端的配置和调用
- 向量存储的操作指南
- 配置管理的最佳实践
- 日志和监控的集成方式

**开发任务操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 获取数据库实例 | 调用 `create_database_client()`，传入配置对象 | `infra/factories/database.py` |
| 获取 LLM 客户端 | 调用 `create_llm_client()`，配置 provider 参数 | `infra/factories/llm.py` |
| 获取向量存储 | 调用 `create_vector_store()`，选择后端类型 | `infra/factories/vector.py` |
| 获取 Redis 客户端 | 调用 `create_redis_client()`，传入连接配置 | `infra/factories/cache.py` |
| 加载配置 | 调用 `load_config()`，传入配置文件路径 | `infra/config/loader.py` |

**如何添加新的 LLM 提供商**：

1. **创建实现文件**：在 `infra/llm/providers/` 下新建 `new_provider.py`
2. **实现接口**：实现 `LLMClient` 接口定义的 `chat()` 和 `embed()` 方法
3. **注册工厂**：在工厂函数 `create_llm_client()` 中添加新分支
4. **添加配置**：在配置文件中增加 `new_provider` 类型的配置示例

**相关文件位置**：
- 接口定义：`infra/llm/base.py`
- 工厂函数：`infra/llm/factory.py`
- 配置示例：`config/infra/llm.yaml`
- 测试文件：`tests/unit/infra/test_llm.py`

---

### 核心层开发

**详细文档**：[aiPlat-core/docs/by-role/developer/index.md](../../../aiPlat-core/docs/by-role/developer/index.md)

**该文档包含**：
- Agent的生命周期管理
- Skill 的注册和执行
- 编排引擎的使用方法
- 记忆系统的操作指南
- 知识库的管理方式

**开发任务操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 注册 Agent | 调用 `agent_registry.register()`，传入 Agent 实例 | `core/agents/registry.py` |
| 获取 Agent | 调用 `agent_registry.get()`，传入 Agent 名称 | `core/agents/registry.py` |
| 执行 Agent | 调用 `agent.execute()`，传入上下文对象 | `core/agents/base.py` |
| 注册 Skill | 调用 `skill_registry.register()`，传入 Skill 实例 | `core/skills/registry.py` |
| 编排工作流 | 创建 `Workflow` 对象，添加步骤，调用 `engine.execute()` | `core/orchestration/engine.py` |

**如何添加新的 Agent 类型**：

1. **创建 Agent 文件**：在 `core/agents/implementations/` 下新建 `my_agent.py`
2. **继承基类**：继承 `BaseAgent` 类，实现 `execute()` 方法
3. **注册 Agent**：在应用启动时调用 `agent_registry.register("my_agent", MyAgent())`
4. **添加配置**：在配置文件中添加 Agent 的配置项
5. **编写测试**：在 `tests/unit/core/agents/` 下添加测试文件

**相关文件位置**：
- Agent 基类：`core/agents/base.py`
- 注册表：`core/agents/registry.py`
- 编排引擎：`core/orchestration/engine.py`
- 测试文件：`tests/unit/core/agents/`

---

### 平台层开发

**详细文档**：[aiPlat-platform/docs/by-role/developer/index.md](../../../aiPlat-platform/docs/by-role/developer/index.md)

**该文档包含**：
- API 路由的定义和实现
- 中间件的开发和注册
- 认证授权的集成方式
- 多租户的处理方法
- 限流和熔断的配置

**开发任务操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 添加 API 路由 | 在 `platform/api/routes/` 下创建路由文件 | `platform/api/routes/` |
| 添加中间件 | 在 `platform/middleware/` 下创建中间件，注册到应用 | `platform/middleware/` |
| 访问核心能力 | 通过依赖注入获取 CoreFacade 实例，调用其方法 | `platform/di/`（由 DI 容器注入） |
| 访问基础设施能力 | 通过 CoreFacade 间接访问（内部通过核心层访问） | `core/facades/core_facade.py` |
| 添加认证 | 实现 `AuthMiddleware`，注册到路由 | `platform/middleware/auth.py` |

**如何添加新的 API 端点**：

1. **创建路由文件**：在 `platform/api/routes/` 下创建 `my_route.py`
2. **定义路由**：使用路由装饰器定义端点路径和方法
3. **实现处理器**：实现请求处理逻辑，调用核心层服务
4. **注册路由**：在 `platform/api/__init__.py` 中注册路由
5. **编写测试**：在 `tests/integration/platform/` 下添加测试文件

**相关文件位置**：
- 路由定义：`platform/api/routes/`
- 中间件：`platform/middleware/`
- 门面类：`platform/facades/core_facade.py`
- 测试文件：`tests/integration/platform/`

---

### 应用层开发

**详细文档**：[aiPlat-app/docs/by-role/developer/index.md](../../../aiPlat-app/docs/by-role/developer/index.md)

**该文档包含**：
- 前端项目的启动和配置
- CLI 工具的开发方法
- Gateway 的多渠道适配
- REST API 的使用

**开发任务操作路径**：

| 任务 | 操作路径 | 参考文件位置 |
|------|----------|-------------|
| 调用平台能力 | 调用 REST API 端点 | `aiPlat-platform` 服务 |
| 添加 CLI 命令 | 在 `app/cli/commands/` 下创建命令文件 | `app/cli/commands/` |
| 添加前端页面 | 在 `app/web/pages/` 下创建页面组件 | `app/web/pages/` |
| 添加渠道适配器 | 在 `app/gateway/adapters/` 下创建适配器 | `app/gateway/adapters/` |

**如何添加新的 CLI 命令**：

1. **创建命令文件**：在 `app/cli/commands/` 下创建 `my_command.py`
2. **定义命令**：使用命令装饰器定义命令名称和选项
3. **实现逻辑**：通过 REST API 调用平台能力
4. **注册命令**：在 `app/cli/__init__.py` 中注册命令
5. **编写测试**：在 `tests/unit/app/cli/` 下添加测试文件

**相关文件位置**：
- 客户端 SDK：`app/client/platform_client.py`
- CLI 命令：`app/cli/commands/`
- 前端页面：`app/web/pages/`
- 测试文件：`tests/unit/app/`

---

### 前端开发规范

**系统级 UI 设计规范**：[系统级 UI 设计规范](../../UI_DESIGN.md)

本系统前端开发应遵循统一的 UI 设计规范，主要包括：

| 规范类别 | 说明 |
|----------|------|
| [设计原则](../../UI_DESIGN.md#一设计原则) | 一致性、可用性、性能、可访问性、可维护性 |
| [视觉设计系统](../../UI_DESIGN.md#二视觉设计系统) | 颜色系统、排版、间距、阴影 |
| [组件库规范](../../UI_DESIGN.md#三组件库规范) | 按钮、表单、卡片、表格等组件标准 |
| [交互模式](../../UI_DESIGN.md#四交互模式) | Loading、空状态、确认流程等模式 |
| [响应式设计](../../UI_DESIGN.md#五响应式设计) | 移动端/平板/桌面响应式适配 |
| [动画规范](../../UI_DESIGN.md#六动画规范) | 动画时长、缓动函数、过渡效果 |
| [无障碍标准](../../UI_DESIGN.md#七无障碍标准) | WCAG 2.1 AA 合规、键盘导航 |
| [前端工程规范](../../UI_DESIGN.md#八前端工程规范) | 目录结构、命名规范、技术栈 |

**模块级 UI 设计参考**：

| 模块 | 文档 |
|------|------|
| Dashboard | [系统级 UI 设计规范](../../UI_DESIGN.md) |
| Monitoring | [系统级 UI 设计规范](../../UI_DESIGN.md) |
| Alerting | [系统级 UI 设计规范](../../UI_DESIGN.md) |
| Diagnostics | [系统级 UI 设计规范](../../UI_DESIGN.md) |
| Config | [系统级 UI 设计规范](../../UI_DESIGN.md)

---

## 🧪 测试

### 测试目录结构

```
tests/
├── unit/                    # 单元测试，隔离依赖
│   ├── infra/              # 基础设施层单元测试
│   │   ├── test_database.py
│   │   ├── test_llm.py
│   │   └── test_vector.py
│   ├── core/               # 核心层单元测试
│   │   ├── test_agents.py
│   │   ├── test_skills.py
│   │   └── test_orchestration.py
│   ├── platform/           # 平台层单元测试
│   │   └── test_api.py
│   └── app/                # 应用层单元测试
│       └── test_client.py
├── integration/             # 集成测试，需要真实服务
│   ├── test_agent_execution.py
│   ├── test_api_flow.py
│   └── test_end_to_end.py
├── fixtures/                # 测试数据
│   ├── sample_documents.json
│   └── test_config.yaml
└── conftest.py              # pytest 配置和共享 fixture
```

---

### 运行测试

| 命令 | 用途 | 前置条件 |
|------|------|----------|
| `make test-unit` | 运行单元测试 | 无|
| `make test-integration` | 运行集成测试 | Docker 服务启动 |
| `make test-all` | 运行全部测试 | Docker 服务启动 |
| `make test-coverage` | 生成覆盖率报告 | 无 |
| `make test-watch` | 监听模式运行测试 | 无 |

**测试覆盖率要求**：
- 单元测试覆盖率：≥ 80%
- 核心模块覆盖率：≥ 90%

**核心模块定义**（需要 90% 覆盖率）：

| 模块 | 路径 | 说明 |
|------|------|------|
| Agent 基类 | `core/agents/base.py` | Agent 的核心逻辑 |
| Skill 基类 | `core/skills/base.py` | Skill 的核心逻辑 |
| 编排引擎 | `core/orchestration/engine.py` | 工作流编排 |
| CoreFacade | `core/facades/core_facade.py` | 核心层对外接口 |
| API 认证 | `platform/middleware/auth.py` | 认证逻辑 |

其他模块遵循 80% 覆盖率要求。

---

### 测试编写规范

| 规范 | 说明 |
|------|------|
| 测试文件命名 | `test_<模块名>.py` |
| 测试类命名 | `Test<功能名>` |
| 测试函数命名 | `test_<功能>_<场景>`，如 `test_agent_execute_success` |
| Mock 位置 | 使用 `conftest.py` 提供公共 fixture |
| 集成测试标记 | 使用 `@pytest.mark.integration` 装饰器 |

**测试 fixture 示例**（在 `conftest.py` 中）：
- `mock_database`：模拟数据库客户端
- `mock_llm_client`：模拟 LLM 客户端
- `test_config`：测试配置对象

---

### CI 测试流程

PR 提交后自动执行：

| 阶段 | 内容 | 要求 |
|------|------|------|
| 代码检查 | flake8、mypy、black | 必须通过 |
| 单元测试 | pytest tests/unit | 必须通过 |
| 集成测试 | pytest tests/integration | 必须通过 |
| 覆盖率检查 | coverage ≥ 80% | 必须通过 |
| 依赖检查 | import-linter | 必须通过 |

---

## 📋 最佳实践

### 1. 使用类型注解

**要求**：所有公开函数必须有参数类型和返回值类型注解

**检查方式**：CI 运行 `mypy` 检查，不通过则阻止合并

**正确做法**：
- 函数参数和返回值都标注类型
- 使用 `Optional` 表示可选参数
- 使用 `Union` 表示多种类型

**例外情况**：
- 测试文件中的私有辅助函数可省略
- 回调函数可使用 `Callable` 类型

---

### 2. 使用配置管理

**要求**：不允许任何硬编码值（URL、端口、超时、密钥）

**检查方式**：代码审查时人工检查 + 定期扫描

**正确做法**：
- 所有可变参数从配置对象读取
- 使用环境变量覆盖敏感配置
- 配置文件放在 `config/` 目录

**禁止**：
- 在代码中硬编码 API 密钥
- 在代码中硬编码数据库地址
- 在代码中硬编码超时时间

---

### 3. 使用依赖注入

**要求**：服务实例通过构造函数注入，不在方法内部直接创建

**检查方式**：代码审查时检查

**正确做法**：
- 通过构造函数接收依赖：`__init__(self, db: DatabaseClient)`
- 使用 DI 容器管理依赖生命周期
- 便于测试时 Mock 依赖

**禁止**：
- 在方法内部直接创建实例：`self.db = DatabaseClient()`
- 使用全局变量存储服务实例

---

### 4. 异常处理

**要求**：捕获具体异常，使用预定义的错误类型

**检查方式**：代码审查

**预定义错误类型**：

| 错误类型 | 适用层 | 使用场景 |
|----------|--------|----------|
| `InfraConnectionError` | infra | 数据库/Redis/LLM 连接失败 |
| `InfraTimeoutError` | infra | 外部服务调用超时 |
| `CoreAgentNotFoundError` | core | Agent 不存在 |
| `CoreSkillExecutionError` | core | Skill 执行失败 |
| `PlatformAuthError` | platform | 认证失败（token 无效） |
| `PlatformRateLimitError` | platform | 触发限流 |
| `PlatformPermissionError` | platform | 权限不足 |

**错误处理模式**：

| 场景 | 做法 |
|------|------|
| 捕获底层异常 | 包装为对应的层错误类型后向上抛出 |
| 业务逻辑错误 | 抛出对应的 Core 层错误 |
| API 层错误 | 转换为 HTTP 状态码和错误响应体 |

**正确做法**：
- 捕获具体异常类型
- 使用自定义错误类型
- 提供有意义的错误信息
- 在异常中包含上下文

**禁止**：
- 裸露的 `except:` 语句
- 捕获 `Exception` 后吞掉
- 捕获异常后不记录日志

---

### 5. 异步编程

**要求**：I/O 操作使用异步方法

**检查方式**：代码审查

**适用场景**：
- HTTP 请求
- 数据库查询
- LLM 调用
- 文件读写

**不适用**：
- CPU 密集型计算
- 简单内存操作

**异步编程模式**：

| 场景 | 推荐方式 | 说明 |
|------|----------|------|
| 单个 LLM 调用 | `async/await` | 等待响应，不阻塞 |
| 多个 LLM 调用 | `asyncio.gather()` | 并发执行，提高效率 |
| 长时间运行任务 | 后台任务 + WebSocket | 避免超时，推送进度 |
| 数据库操作 | 使用异步驱动 | `asyncpg`、`aioredis` |

**常用模式示例**：

| 模式 | 适用场景 |
|------|----------|
| 顺序执行 | 有依赖关系的调用，依次 await |
| 并发执行 | 独立的多个调用，使用 `gather()` |
| 超时控制 | 有响应时间要求的调用，使用 `wait_for()` |
| 重试机制 | 可能临时失败的调用，使用 `tenacity` 库 |

---

### 6. 日志规范

**要求**：使用结构化日志，记录关键操作

**检查方式**：代码审查

**日志级别**：
- DEBUG：详细调试信息，仅开发环境
- INFO：关键操作和状态变化
- WARNING：潜在问题，需要关注
- ERROR：错误，需要处理
- CRITICAL：严重错误，需要立即处理

**日志内容**：
- 操作类型
- 操作对象
- 操作结果
- 耗时（可选）

---

## 🐛 调试指南

### 本地调试

| 组件 | 调试方式 | 端口 |
|------|----------|------|
| Python 后端 | VS Code 断点 / pdb | 8000 |
| 前端 | Chrome DevTools | 3000 |

### 日志调试

```bash
# 实时查看日志
make logs

# 按服务过滤
make logs-platform
make logs-core

# 按级别过滤
make logs-error
```

### 常用调试命令

| 命令 | 用途 |
|------|------|
| `make dev` | 开发模式，支持热重载 |
| `make shell` | 进入 Python 交互式环境 |
| `make test-debug` | 运行测试并停在失败处 |
| `make db-console` | 连接数据库控制台 |
| `make redis-cli` | 连接 Redis 控制台 |

### 常见调试场景

| 场景 | 调试方法 |
|------|----------|
| Agent 执行卡住 | 添加日志，检查 LLM 调用是否超时 |
| 依赖注入失败 | 检查 DI 容器注册顺序 |
| 循环导入 | 使用 `python -m` 运行，查看导入顺序 |
| 性能问题 | 使用 `cProfile` 分析，检查热点代码 |

---

## 🔧 常见问题排查

### 环境问题

| 问题 | 可能原因 | 解决步骤 |
|------|----------|----------|
| 数据库连接失败 | 服务未启动或配置错误 | 1. 执行 `make docker-up`<br>2. 检查 `.env` 中的数据库地址<br>3. 执行 `make test-db` |
| Redis 连接失败 | 服务未启动 | 1. 执行 `make docker-up`<br>2. 检查 Redis 端口是否被占用 |
| LLM 调用超时 | API 密钥无效或网络问题 | 1. 检查 `.env` 中的 `LLM_API_KEY`<br>2. 执行 `make test-llm`<br>3. 检查网络代理设置 |
| 向量数据库连接失败 | Milvus 未启动 | 1. 执行 `make docker-up`<br>2. 检查 Milvus 端口 |

### 开发问题

| 问题 | 可能原因 | 解决步骤 |
|------|----------|----------|
| Agent 注册失败 | 注册表未初始化 | 1. 确保在应用启动时调用 `init_registry()`<br>2. 检查 Agent 名称是否已存在 |
| 循环导入错误 | 模块依赖顺序问题 | 1. 检查是否在 `__init__.py` 中过早导入<br>2. 使用延迟导入或TYPE_CHECKING |
| 类型检查失败 | 类型注解不完整或不正确 | 1. 运行 `mypy <file>` 查看详细错误<br>2. 补充缺失的类型注解 |
| 测试失败 | Mock 不正确或依赖未隔离 | 1. 检查 fixture 是否正确 Mock 依赖<br>2. 确保测试不依赖外部服务 |

### 运行问题

| 问题 | 可能原因 | 解决步骤 |
|------|----------|----------|
| 内存不足 | 大模型加载或数据缓存过多 | 1. 检查缓存配置<br>2. 减少 batch size<br>3. 清理不必要的缓存 |
| 响应慢 | 查询未使用索引 | 1. 检查数据库索引<br>2. 检查向量索引<br>3. 添加必要的缓存 |
| 配置不生效 | 配置优先级问题 | 1. 检查配置加载顺序<br>2. 确认环境变量是否正确<br>3. 检查配置文件格式 |

---

## 🔗 相关链接

- [← 返回主文档](../../index.md)
- [架构师指南 →](../architect/index.md)
- [运维指南 →](../ops/index.md)

---

*最后更新: 2026-04-10*
