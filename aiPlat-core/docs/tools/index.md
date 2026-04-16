# 工具系统模块（设计真值：以代码事实为准）

> 本文档以 **As-Is（当前实现）** 为准，并对“增强/规划项”明确标注为 **To-Be**。  
> 状态口径与可追溯规则参见：[架构实现状态](../ARCHITECTURE_STATUS.md)。

## 实现状态提示（As-Is）

- ✅ 已具备统一工具执行封装（校验/权限/超时/统计/可选 tracing）与最小线程安全（stats + registry 加锁）
- ⚠️ 部分工具类型在文档中出现但仅为占位/桩实现；以 `core/server.py` 启动时实际注册的 tools 为准

> 提供外部工具的注册、发现、调用和统计能力，支持编排追踪、调用统计、权限校验等特性

---

## 模块定位

工具系统负责管理 Agent 可调用的外部工具，提供：
- 工具注册与发现
- 编排追踪集成
- 工具调用统计
- 权限校验
- 超时控制

**代码位置**：`core/apps/tools/`

---

## 模块结构

```
apps/tools/
├── __init__.py              # 模块入口
├── base.py                  # Tool 基类 + 内置工具 + ToolRegistry
│   # - BaseTool (工具基类)
│   # - CalculatorTool (计算器)
│   # - SearchTool (搜索)
│   # - FileOperationsTool (文件操作)
│   # - ToolRegistry (工具注册表)
│   # - create_tool() (工厂函数)
├── permission.py            # 权限管理器
│   # - Permission (权限枚举: read/write/execute)
│   # - PermissionEntry (权限条目)
│   # - PermissionManager (权限管理器)
└── recaller.py              # TokMem 混合召回系统
    # - TokenRecaller (基于关键词的召回)
    # - RAGRecaller (基于语义的召回)
    # - NeuralEnhancer (神经网络特征增强)
    # - ToolRecaller (混合召回器)
```

---

## 核心接口

### Tool 基类

**位置**：`core/apps/tools/base.py`

**Tool 基类**

核心组件：

- **ToolSchema**：工具模式定义
  - name：工具名称
  - description：工具描述
  - parameters：参数定义（JSON Schema）
  - required：必需参数
  - returns：返回值定义

- **ToolResult**：工具执行结果
  - success：是否成功
  - result：执行结果
  - error：错误信息
  - latency：执行延迟
  - metadata：元数据

- **Tool**：工具基类
  - 工具调用统计：call_count / success_count / error_count / avg_latency
  - 线程安全：使用锁保护共享状态
  - 编排追踪器：自动注入执行追踪
  - 权限管理器：自动注入权限校验
  - 带追踪的执行：自动注入追踪、权限、超时、错误捕获

---

### ToolRegistry 工具注册表

**位置**：`core/apps/tools/base.py`

**ToolRegistry 工具注册表**

核心能力：

- **单例模式**：全局唯一实例，线程安全
- **工具注册**：注册工具并自动注入编排追踪器和权限管理器
- **工具注销**：注销指定工具
- **工具获取**：按名称获取工具实例
- **类别管理**：按类别组织工具
- **统计获取**：获取所有工具的调用统计
- **编排追踪器设置**：设置后自动注入到所有已注册工具
- **权限管理器设置**：设置后自动注入到所有已注册工具

---

## ⚙️ 关键设计

### 1. 编排追踪器自动注入

**问题**：需要追踪工具调用链路，但手动注入繁琐且容易遗漏

**解决方案**：工具注册时自动注入编排追踪器

**自动注入效果**：
- 工具注册时自动注入编排追踪器
- 工具调用时自动追踪开始/结束
- 错误时自动记录错误信息
- 统计信息自动记录

---

### 2. 工具调用统计（Automatic Call Statistics）

**问题**：需要统计工具使用情况，但手动统计遗漏多

**解决方案**：工具基类自动统计调用次数、成功率、延迟

**统计指标**：
- **调用次数**：总调用次数
- **成功次数**：成功执行的次数
- **失败次数**：执行失败的次数
- **平均延迟**：平均执行时间

**使用方式**：使用 `_call_with_tracking()` 方法会自动统计，可通过 `get_stats()` 获取统计信息。

---

### 3. TokMem 混合召回系统

**问题**：工具召回精度低，Token消耗大

**解决方案**：结合 Token 和 RAG 的混合召回

**核心组件**：

- **RecallResult**：召回结果（`core/apps/tools/recaller.py`）
  - tool_name：工具名称
  - score：召回分数
  - source：召回来源（token/rag/mixed）
  - metadata：元数据

- **TokenRecaller**：基于 Token 的召回（`core/apps/tools/recaller.py`）
  - 关键词索引构建
  - 分词和匹配
  - Jaccard 相似度分数计算

- **RAGRecaller**：基于 RAG 的召回（`core/apps/tools/recaller.py`）
  - 工具描述向量化（TF-IDF 模拟）
  - 余弦相似度计算
  - 语义检索

- **NeuralEnhancer**：神经网络特征增强（`core/apps/tools/recaller.py`）
  - 组合特征：乘积、和、差、平方和、几何平均
  - 加权混合输出

- **ToolRecaller**：混合召回器（`core/apps/tools/recaller.py`）
  - Token 权重：0.4
  - RAG 权重：0.6
  - 可选 NeuralEnhancer 增强

**使用方式**：创建 ToolRecaller 实例，调用 `recall_tools()` 方法传入查询和 top_k 参数。

**输出示例**：
```
工具: calculator, 分数: 0.8500, 来源: mixed
  Token分数: 0.7000, RAG分数: 0.9500
工具: geometry_helper, 分数: 0.7200, 来源: mixed
  Token分数: 0.8000, RAG分数: 0.6600
```

---

### 4. 神经网络特征增强

**问题**：简单的关键词匹配和向量相似度不够准确

**解决方案**：结合神经网络进行特征增强

**NeuralEnhancer**（`core/apps/tools/recaller.py`）

核心能力：

- **特征提取**：将 Token 分数和 RAG 分数扩展为特征向量
- **特征组合**：乘积、和、差、平方和、几何平均
- **加权输出**：支持可配置的 Token/RAG 权重

---

### 5. 权限管理集成

**问题**：需要控制工具的访问权限

**解决方案**：工具级别权限管理

**PermissionManager**（`core/apps/tools/permission.py`）

核心能力：

- **授予权限**：`grant_permission(user_id, tool_name, permission)`
- **检查权限**：`check_permission(user_id, tool_name, permission)`
- **撤销权限**：`revoke_permission(user_id, tool_name)` - 支持撤销单个权限或全部
- **查询权限**：`get_user_tools(user_id)`, `get_tool_users(tool_name)`

**权限级别**：Permission 枚举 - `READ` / `WRITE` / `EXECUTE`

**集成方式**：权限管理器通过 ToolRegistry 自动注入到工具基类，在工具调用前执行权限检查。

---

## 🚀 使用示例

### 注册和调用工具

**使用方式**：

1. 定义工具：继承 BaseTool 基类，实现 execute 方法，使用 _call_with_tracking 包装
2. 注册工具：使用 tool_registry.register()
3. 调用工具：调用 execute 方法，自动追踪和统计
4. 查看统计：使用 get_stats() 获取调用次数、成功率、平均延迟

---

## 设计补全（Round2）：权限闭环与默认策略（必须落地）

> 背景：仅有 `check_permission()` 不足以构成可用的权限体系；需要补齐“默认策略 + 授权入口 + 审计/验收”闭环。

### 1) 默认策略（Default Policy）

为保证平台**开箱可用**且可控，统一默认策略如下：

- `user_id=system`（或 `admin`）拥有对 **seed agent/skill/tool** 的 `EXECUTE` 最小权限集
- 其他用户默认拒绝（deny-by-default），必须通过授权接口授予

> 说明：如果产品定位要求“严格默认拒绝”，也必须提供初始化脚本或管理 API，否则执行端点会出现“开箱即 403”。

### 2) 授权管理 API（闭环入口）

必须提供（或等价能力）：

| API | 方法 | 说明 |
|---|---|---|
| `/permissions/grant` | POST | 授予 user 对 tool/skill/agent 的某权限 |
| `/permissions/revoke` | POST | 撤销权限（单个或全部） |
| `/permissions/users/{user_id}` | GET | 查询用户的授权集合 |
| `/permissions/tools/{tool_name}` | GET | 查询拥有该工具权限的用户列表 |

数据模型建议统一为：`subject_id` + `resource_type(agent/skill/tool)` + `resource_id` + `permission(READ/WRITE/EXECUTE)`

### 3) 权限检查位置（Single Source of Truth）

为了避免重复/遗漏，推荐优先级：

1. **入口层（server.py）**：对外执行 API 必须校验（Agent/Skill 执行）
2. **执行封装层（可选）**：BaseTool/BaseSkill/BaseAgent 的统一 wrapper 可进行二次校验（防止内部绕过）

### 4) 验收标准（必须有测试）

最小验收用例（集成测试或可执行命令）：

---

## 证据索引（Evidence Index｜抽样）

- Tool 基类封装与 stats 加锁：`core/apps/tools/base.py: BaseTool._call_with_tracking()` / `_update_stats()`
- ToolRegistry 加锁与注入：`core/apps/tools/base.py: ToolRegistry.register()/get_all_stats()`
- 权限管理：`core/apps/tools/permission.py`
- 默认权限 seed + 授权 API：`core/server.py`（`_seed_default_permissions` 与 `/permissions/*` endpoints）

1. `system` 调用任意 seed skill/agent/tool **不应返回 403**
2. 普通用户默认调用返回 403
3. 调用 `/permissions/grant` 后普通用户可执行，并能通过查询接口看到授权
4. 撤销后再次执行应返回 403


### 使用混合召回

**使用方式**：

```python
from core.apps.tools import ToolRecaller

# 创建召回器
recaller = ToolRecaller(weight_token=0.4, weight_rag=0.6)

# 索引工具
recaller.index_tool("calculator", "Perform mathematical calculations", keywords=["math", "calc", "compute"])
recaller.index_tool("search", "Search the web for information", keywords=["search", "find", "query"])

# 召回工具
results = recaller.recall("compute math expression", top_k=3)
for r in results:
    print(f"工具: {r.tool_name}, 分数: {r.score:.4f}, 来源: {r.source.value}")
```

### 使用权限管理

**使用方式**：

```python
from core.apps.tools import PermissionManager, Permission

# 创建权限管理器
pm = PermissionManager()

# 授予权限
pm.grant_permission("user-001", "calculator", Permission.EXECUTE)
pm.grant_permission("user-001", "search", Permission.READ, granted_by="admin")

# 检查权限
has_perm = pm.check_permission("user-001", "calculator", Permission.EXECUTE)  # True

# 撤销权限
pm.revoke_permission("user-001", "search", Permission.READ)
```

---

## 📁 文件结构

```
core/apps/tools/
├── __init__.py              # 模块入口
├── base.py                  # Tool 基类 + 内置工具 + ToolRegistry
│   # - BaseTool (工具基类)
│   # - CalculatorTool (计算器)
│   # - SearchTool (搜索)
│   # - FileOperationsTool (文件操作)
│   # - ToolRegistry (工具注册表)
│   # - create_tool() (工厂函数)
├── permission.py            # 权限管理器
│   # - Permission (权限枚举)
│   # - PermissionEntry (权限条目)
│   # - PermissionManager (权限管理器)
└── recaller.py              # TokMem 混合召回系统
    # - TokenRecaller (Token召回)
    # - RAGRecaller (RAG召回)
    # - NeuralEnhancer (神经网络增强)
    # - ToolRecaller (混合召回器)
```

---

## 🔗 相关文档

- [Harness框架](../harness/index.md) - Agent框架和生命周期
- [工具系统](./index.md) - 工具注册和调用

---

*最后更新: 2026-04-14*
