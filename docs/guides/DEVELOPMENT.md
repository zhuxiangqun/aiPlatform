# AI Platform 开发规范

> 系统级开发规范 - 各层必须遵循

---

## 📋 目录

- [代码规范](#代码规范)
- [提交规范](#提交规范)
- [分支策略](#分支策略)
- [PR 流程](#pr-流程)
- [代码审查](#代码审查)
- [测试规范](#测试规范)
- [文档规范](#文档规范)
- [发布规范](#发布规范)

---

## 代码规范

### Python 代码规范

**工具配置**：

```toml
# pyproject.toml
[tool.ruff]
line-length = 120
target-version = "py311"

select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # pyflakes
    "I",      # isort
    "B",      # flake8-bugbear
    "C4",     # flake8-comprehensions
    "UP",     # pyupgrade
    "ARG",    # flake8-unused-arguments
    "SIM",    # flake8-simplify
]

[tool.ruff.isort]
known-first-party = ["aiPlat_infra", "aiPlat_core", "aiPlat_platform", "aiPlat_app"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_ignores = true
```

**命名规范**：

| 类型 | 规范 | 示例 |
|------|------|------|
| 模块 | snake_case | `database_client.py` |
| 类 | PascalCase | `class PostgresClient` |
| 函数 | snake_case | `def get_connection()` |
| 变量 | snake_case | `user_name` |
| 常量 | UPPER_SNAKE_CASE | `MAX_CONNECTIONS` |
| 私有属性 | _snake_case | `self._connection` |
| 保护属性 | __snake_case | `self.__private` |

**类型注解**：

```python
# 必须使用类型注解
def get_user(user_id: int) -> User | None:
    ...

async def query(sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    ...

# 使用 typing.NewType 为 ID 类型
UserId = NewType("UserId", int)
AgentId = NewType("AgentId", str)
```

**导入顺序**：

```python
# 1. 标准库
import os
from typing import Any

# 2. 第三方库
import pytest
from pydantic import BaseModel

# 3. 本项目内部模块（按层级）
from infra.database import DatabaseClient
from core.apps.agents.base import BaseAgent

# 4. 平台层 API 框架（当前仓库内以 FastAPI 示例为准）
from fastapi import APIRouter
```

**禁止的模式**：

```python
# ❌ 禁止
from module import *

# ❌ 禁止
def foo(x):  # 缺少类型注解
    ...

# ❌ 禁止
global_var = 1  # 模块级全局变量

# ✅ 正确
class Config:
    var: int = 1  # 类属性
```

---

### TypeScript 代码规范

**工具配置**：

```json
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "strict": true,
    "noImplicitAny": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true
  }
}
```

**命名规范**：

| 类型 | 规范 | 示例 |
|------|------|------|
| 文件 | kebab-case | `user-service.ts` |
| 类 | PascalCase | `class UserService` |
| 接口 | PascalCase | `interface User` |
| 函数 | camelCase | `function getUser()` |
| 变量 | camelCase | `userName` |
| 常量 | UPPER_SNAKE_CASE | `MAX_RETRIES` |
| 枚举 | PascalCase | `enum Status` |

---

## 提交规范

### Commit Message 格式

```
<type>(<scope>): <summary>

<body>

<footer>
```

**Type 类型**：

| Type | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(database): add MySQL support` |
| `fix` | Bug 修复 | `fix(core): fix agent memory leak` |
| `refactor` | 重构 | `refactor(platform): simplify auth logic` |
| `docs` | 文档 | `docs: update API documentation` |
| `test` | 测试 | `test(infra): add PostgreSQL integration tests` |
| `chore` | 杂项 | `chore: update dependencies` |
| `perf` | 性能优化 | `perf(core): optimize vector search` |
| `style` | 代码风格 | `style: format code` |
| `ci` | CI 配置 | `ci: add GitHub Actions workflow` |

**Scope 范围**：

| 层级 | Scope 示例 |
|------|-----------|
| infra | `database`, `llm`, `vector`, `messaging`, `config` |
| core | `agent`, `skill`, `orchestration`, `memory`, `knowledge` |
| platform | `api`, `auth`, `tenant`, `billing` |
| app | `webui`, `cli`, `gateway` |

**示例**：

```bash
# 功能开发
feat(database): add PostgreSQL connection pool support

- Implement connection pool with configurable size
- Add health check for idle connections
- Support connection timeout and retry

Closes #123

# Bug 修复
fix(core): fix agent memory leak in long conversations

The agent was not clearing old messages from memory, causing
memory exhaustion after long conversations.

Fixes #456

# 重构
refactor(platform): simplify authentication middleware

Extract JWT validation into separate function for better
testability and reusability.
```

---

## 分支策略

### Git Flow 模型

```
main          ──→ 生产环境
  │
  ├── develop ──→ 开发环境
  │     │
  │     ├── feature/xxx  ──→ 功能开发
  │     ├── bugfix/xxx    ──→ Bug 修复
  │     └── refactor/xxx  ──→ 重构
  │
  ├── release/x.x ──→ 发布准备
  │
  └── hotfix/xxx   ──→ 紧急修复
```

### 分支命名规范

| 分支类型 | 命名规范 | 示例 |
|----------|----------|------|
| 功能分支 | `feature/<feature-name>` | `feature/add-mysql-support` |
| Bug 修复 | `bugfix/<bug-name>` | `bugfix/fix-connection-leak` |
| 重构分支 | `refactor/<refactor-name>` | `refactor/simplify-auth` |
| 发布分支 | `release/<version>` | `release/1.2.0` |
| 热修复分支 | `hotfix/<hotfix-name>` | `hotfix/fix-critical-bug` |

### 分支规则

**必须遵守**：

1. **功能分支从 develop 创建**
   ```bash
   git checkout develop
   git pull
   git checkout -b feature/add-mysql-support
   ```

2. **一个功能一个分支**
   - 每个分支只做一件事
   - 分支粒度适中，不过大也不过小

3. **保持分支更新**
   ```bash
   # 定期同步 develop
   git checkout develop
   git pull
   git checkout feature/add-mysql-support
   git rebase develop
   ```

4. **禁止直接提交到 main**
   - main 只接受 merge request
   - main 代表生产环境代码

---

## PR 流程

### 创建 PR

**PR 标题格式**：

```
<type>(<scope>): <summary>
```

**PR 描述模板**：

```markdown
## 变更说明

<!-- 简要描述本次变更 -->

## 变更类型

- [ ] 新功能（feature）
- [ ] Bug 修复（fix）
- [ ] 重构（refactor）
- [ ] 文档（docs）
- [ ] 测试（test）
- [ ] 其他（chore）

## 影响范围

<!-- 描述影响哪些层和模块 -->

- 层级：[ ] infra / [ ] core / [ ] platform / [ ] app
- 模块：

## 测试

- [ ] 已添加单元测试
- [ ] 已添加集成测试
- [ ] 所有测试通过

## 检查清单

- [ ] 代码风格检查通过（ruff / eslint）
- [ ] 类型检查通过（mypy / tsc）
- [ ] 文档已更新
- [ ] CHANGELOG 已更新

## 关联 Issue

Closes #xxx
```

### PR 审查流程

```
┌─────────────┐
│ 创建 PR     │
└─────┬───────┘
      │
      ▼
┌─────────────┐
│ 自动检查    │ ← CI: lint, test, type-check
└─────┬───────┘
      │
      ├── 失败 → 修复代码
      │
      ▼
┌─────────────┐
│ 代码审查    │ ← 至少 1 人审查
└─────┬───────┘
      │
      ├── 修改请求 → 修改代码
      │
      ▼
┌─────────────┐
│ 合并到      │
│ develop     │
└─────────────┘
```

### 合并规则

**必须满足**：

- ✅ CI 检查通过
- ✅ 至少 1 人审查通过
- ✅ 无冲突
- ✅ 文档已更新（如果需要）
- ✅ CHANGELOG 已更新（如果需要）

**合并方式**：

| 场景 | 合并方式 |
|------|----------|
| 功能分支 → develop | Squash and merge |
| develop → release | Merge commit |
| release → main | Merge commit |
| hotfix → main | Merge commit |

---

## 代码审查

### 审查重点

**必须审查**：

| 审查项 | 说明 |
|--------|------|
| **代码正确性** | 逻辑是否正确，边界条件是否处理 |
| **代码风格** | 是否符合规范（ruff / eslint） |
| **类型注解** | 是否有类型注解，类型是否正确 |
| **测试覆盖** | 是否有测试，测试是否充分 |
| **文档** | 重要变更是否有文档 |
| **性能** | 是否有性能问题（N+1 查询、大循环） |
| **安全** | 是否有安全问题（SQL 注入、XSS、敏感信息泄露） |

### 审查制度

| 变更类型 | 审查人数 | 审查范围 |
|----------|----------|----------|
| 小修复（< 50 行） | 1 人 | 代码正确性 |
| 功能开发（< 500 行） | 1 人 | 代码 + 测试 + 文档 |
| 大功能（> 500 行） | 2 人 | 代码 + 测试 + 文档 + 架构 |
| 架构变更 | 2+ 人（含架构师） | 全部 |

### 审查响应时间

| 优先级 | 响应时间 |
|--------|----------|
| 紧急（hotfix） | 4 小时内 |
| 高（功能开发） | 1 天内 |
| 中（重构、文档） | 2 天内 |
| 低（优化） | 3 天内 |

---

## 测试规范

### 测试层级

遵循测试金字塔：

```
        ┌─────────┐
        │   E2E   │  5-10%
        └─────────┘
      ┌─────────────┐
      │ Integration │  15-25%
      └─────────────┘
    ┌───────────────────┐
    │    Unit Tests     │  70-80%
    └───────────────────┘
```

### 测试要求

| 层级 | 单元测试 | 集成测试 | 总覆盖率 |
|------|----------|----------|----------|
| **infra** | ≥ 80% | ≥ 70% | ≥ 85% |
| **core** | ≥ 90% | ≥ 60% | ≥ 90% |
| **platform** | ≥ 70% | ≥ 70% | ≥ 85% |
| **app** | ≥ 60% | ≥ 60% | ≥ 70% |

### 测试命名规范

```python
# 格式：test_<功能>_<场景>_<预期结果>
def test_agent_execute_with_valid_input_returns_result():
    ...

def test_agent_execute_with_invalid_input_raises_error():
    ...

def test_database_insert_with_duplicate_key_fails():
    ...
```

### 测试组织

```
tests/
├── unit/              # 单元测试
│   ├── infra/
│   ├── core/
│   ├── platform/
│   └── app/
├── integration/        # 集成测试
│   ├── infra/
│   ├── core/
│   ├── platform/
│   └── app/
└── e2e/               # 端到端测试
    └── scenarios/
```

详细测试规范参见：[系统测试指南](../TESTING_GUIDE.md)

---

## 文档规范

### 文档结构

```
aiPlatform/
├── README.md              # 项目说明
├── docs/
│   ├── index.md           # 文档索引
│   ├── TESTING_GUIDE.md   # 系统测试指南
│   └── guides/
│       ├── DEVELOPMENT.md # 开发规范（本文档）
│       └── DEPLOYMENT.md  # 部署指南
│
├── aiPlat-infra/
│   ├── README.md          # 层说明
│   └── docs/
│       ├── index.md       # 层文档索引
│       └── testing/       # 层测试文档
│
├── aiPlat-core/           # 同样结构
├── aiPlat-platform/       # 同样结构
└── aiPlat-app/            # 同样结构
```

### 文档类型

| 文档类型 | 内容 | 更新频率 |
|----------|------|----------|
| **README.md** | 项目/模块简介、快速开始 | 功能变更时 |
| **index.md** | 文档索引、导航 | 新增文档时 |
| **开发规范** | 代码规范、提交流程 | 规范变更时 |
| **部署指南** | 部署流程、运维手册 | 部署变更时 |
| **测试文档** | 测试策略、测试报告 | 测试完成时 |
| **API 文档** | 接口定义、使用示例 | 接口变更时 |

### Markdown 格式

**标题层级**：

```markdown
# 一级标题（文档标题）

## 二级标题（章节）

### 三级标题（小节）

#### 四级标题（细节）
```

**代码块**：

````markdown
```python
# Python 代码
def hello():
    print("Hello, World!")
```

```bash
# Shell 命令
make test
```

```typescript
// TypeScript 代码
const user: User = { name: "test" };
```
````

**表格**：

```markdown
| 列1 | 列2 | 列3 |
|-----|-----|-----|
| 值1 | 值2 | 值3 |
```

---

## 发布规范

### 版本号规范

遵循语义化版本：

```
MAJOR.MINOR.PATCH

MAJOR: 不兼容的 API 变更
MINOR: 向后兼容的功能新增
PATCH: 向后兼容的问题修正
```

### CHANGELOG 格式

```markdown
# CHANGELOG

## [1.2.0] - 2026-04-11

### Added
- feat(database): add MySQL support
- feat(vector): add Milvus integration

### Changed
- refactor(core): optimize agent memory management

### Fixed
- fix(platform): fix authentication token expiration

### Deprecated
- deprecate(infra): old config format, use new format instead

### Removed
- remove(core): legacy skill executor

### Security
- fix(auth): patch JWT validation vulnerability
```

### 发布流程

```
┌─────────────────┐
│ develop 分支     │
│ 功能开发完成     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 创建 release 分支│
│ release/1.2.0   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 测试和修复      │
│ 集成测试        │
│ E2E 测试        │
│ 性能测试        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 合并到 main     │
│ 打 tag          │
│ v1.2.0          │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 发布到生产      │
│ 更新文档        │
│ 发布 CHANGELOG  │
└─────────────────┘
```

---

## 各层开发规范

各层在遵循系统级开发规范的基础上，需遵循各自的特定规范：

| 层级 | 额外规范 | 文档 |
|------|----------|------|
| **infra** | 接口设计规范、配置驱动 | [infra 开发规范](../../aiPlat-infra/docs/guides/DEVELOPMENT.md) |
| **core** | Agent 设计规范、Skill 开发规范 | [core 开发规范](../../aiPlat-core/docs/guides/DEVELOPMENT.md) |
| **platform** | API 设计规范、认证规范 | [platform 开发规范](../../aiPlat-platform/docs/guides/DEVELOPMENT.md) |
| **app** | UI 组件规范、CLI 命令规范 | [app 开发规范](../../aiPlat-app/docs/guides/DEVELOPMENT.md) |

### 前端开发规范

所有层的前端开发应遵循系统级 UI 设计规范：

- [系统级 UI 设计规范](../UI_DESIGN.md) - 统一的颜色、排版、组件、交互模式
- [系统级 UI 设计规范](../UI_DESIGN.md) - UI 规范与组件风格约定

---

## 📌 检查清单

### 提交前检查

```bash
# 代码风格检查
make lint

# 类型检查
make type-check

# 测试
make test

# 文档检查
make docs-check
```

### PR 检查

- [ ] 代码风格检查通过
- [ ] 类型检查通过
- [ ] 所有测试通过
- [ ] 新增代码有测试
- [ ] 文档已更新（如果需要）
- [ ] CHANGELOG 已更新（如果需要）
- [ ] 提交信息符合规范

---

*最后更新: 2026-04-11*
