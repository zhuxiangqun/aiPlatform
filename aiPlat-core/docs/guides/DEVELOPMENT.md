# 核心层开发规范（设计真值：以代码事实为准）

> 说明：本文档用于约束 core 层的工程实践。涉及“已实现/已接线”的描述，以代码事实为准，并遵循 [`ARCHITECTURE_STATUS.md`](../ARCHITECTURE_STATUS.md) 的可追溯断言规则。

> 继承系统级开发规范，针对核心层的特定要求

---

## 继承规范

本文档继承系统级开发规范（若存在上层仓库/平台仓库），所有系统级规范在本层必须遵守。

---

## 特定规范

### 层级定位

核心层（Layer 1）封装 AI 核心能力和业务逻辑，依赖基础设施层，被平台层调用：

```
aiPlat-core (Layer 1)
    ↓ 依赖
    aiPlat-infra（通过工厂接口）
    ↑ 被依赖
    aiPlat-platform（通过 CoreFacade）
```

**允许的依赖**：
- ✅ `aiPlat_infra`（通过工厂接口）
- ✅ Python 标准库
- ✅ 第三方库（LangChain, LangGraph 等）

**禁止的依赖**：
- ❌ `aiPlat_platform`
- ❌ `aiPlat_app`

---

## 核心接口

### CoreFacade（唯一对外入口｜To-Be）

```python
# To-Be：平台层通常会以 Facade 方式暴露 core 能力
from typing import Any

class CoreFacade:
    """核心层唯一对外入口"""
    
    async def execute_agent(
        self,
        agent_id: str,
        input: dict[str, Any],
        context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """执行 Agent"""
        ...
    
    async def create_agent(
        self,
        name: str,
        config: dict[str, Any]
    ) -> str:
        """创建 Agent"""
        ...
    
    async def get_agent(self, agent_id: str) -> Agent | None:
        """获取 Agent"""
        ...
    
    async def execute_skill(
        self,
        skill_id: str,
        params: dict[str, Any]
    ) -> dict[str, Any]:
        """执行 Skill"""
        ...
```

> As-Is：当前仓库的 HTTP/API 入口主要在 `core/server.py`，并未以 CoreFacade 形式对外提供。

---

## 证据索引（Evidence Index｜抽样）

- API/启动入口：`core/server.py`
- 依赖边界（core 不依赖 platform/app）：可通过 import-linter（To-Be）或代码 review 约束

---

## 开发检查清单

- [ ] 不直接暴露内部实现类
- [ ] 通过 CoreFacade 提供服务
- [ ] 使用依赖注入管理服务
- [ ] 定义清晰的 Agent 接口
- [ ] 编写单元测试（覆盖率 ≥ 90%）
- [ ] 编写集成测试（使用 Mock 基础设施）

---

## 依赖检查

### 检查工具

使用 `import-linter` 检查模块依赖规则，防止循环依赖和跨层依赖。

### 配置文件

在项目根目录创建 `.importlinter` 文件：

```toml
[settings]
name = "aiPlat-core"

[[layers]]
    name = "harness"
    modules = ["harness.*"]

[[layers]]
    name = "orchestration"
    modules = ["orchestration.*"]
    dependencies = ["harness", "agents", "skills", "tools"]

[[layers]]
    name = "agents"
    modules = ["agents.*"]
    dependencies = ["harness", "memory", "knowledge", "tools", "models"]

# ... 其他模块配置
```

### CI 集成

在 `.github/workflows/dependency-check.yml` 中配置：

```yaml
name: Dependency Check

on:
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run import-linter
        run: pip install import-linter && import-linter
```

**检查规则**：
- PR 提交时自动运行依赖检查
- 检查不通过则阻止合并
- 特殊情况需架构师审批豁免

---

## 测试规范

详细测试规范见：[系统级测试指南](../../../docs/TESTING_GUIDE.md)

| 测试类型 | 覆盖率要求 |
|----------|-----------|
| 单元测试 | ≥ 90% |
| 集成测试 | ≥ 60% |

---

## 相关链接

- [系统级开发规范](../../../docs/guides/DEVELOPMENT.md)
- [系统级测试指南](../../../docs/TESTING_GUIDE.md)
- [core层部署指南](./DEPLOYMENT.md)

---

*最后更新: 2026-04-14*
