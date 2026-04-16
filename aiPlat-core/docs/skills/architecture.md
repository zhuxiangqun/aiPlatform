# Skill 架构设计（设计真值：以代码事实为准）

> ⚠️ **实现状态提示（As-Is vs To-Be）**：本文档以 **当前代码事实（As-Is）** 为准，并对“进化引擎/市场化”类能力标注为 **To-Be**。  
> 完整实现状态参见 [架构实现状态](../ARCHITECTURE_STATUS.md)。
>
> - ✅ 已实现：SkillManager CRUD、SkillExecutor inline/fork 模式、Manager↔Registry 桥接、Discovery→Registry 注册、SkillContext.tools 注入
> - ✅ 已实现：版本查询 API（/skills/{id}/versions/{version} 返回真实 config）
> - ✅ 已实现：版本回滚语义闭环（回滚会影响后续执行配置；`/active-version` 可查询；rollback API 校验与返回 active_version/active_config）
> - ✅ 已实现：PermissionManager 已接入执行入口，且具备默认 seed 策略与授权 API 闭环
> - ❌ 未实现：Skill 进化引擎（CAPTURED/FIX/DERIVED 等）

> Skill 的核心架构设计，包括注册发现、执行模型、版本管理与Agent Skill模式改进

本文档是 [Skill 概述](./index.md) 的扩展，聚焦于架构层面的设计决策。

---

## 一、核心定位

Skill 是智能体可复用的能力单元，是 Agent 完成任务的具体手段。

**与 Agent 的关系**：
- Agent 是任务执行的主体
- Skill 是 Agent 可调用的能力
- 一个 Agent 可以绑定多个 Skill

**核心职责**：
- 能力定义与标准化
- 执行调度与监控
- 版本管理与演进

---

## 二、架构演进：从基础到 Agent Skill 模式

### 2.1 基础架构

当前系统的基本架构：

```
SkillRegistry (注册表)
    │
    ├── register()     # 手动注册
    ├── get()          # 按名获取
    ├── list_skills()  # 列表查询
    └── execute()      # 执行调用
```

**特点**：
- 所有 Skill 在 `base.py` 中定义
- 手动注册到全局 Registry
- 基础元数据（name, description, version, category, tags）

### 2.2 Agent Skill 模式

> 借鉴行业实践的改进方案

```
my-skill/                      # Skill 目录
├── SKILL.md                   # 元数据定义（核心）
├── handler.py                 # Skill 实现
├── scripts/                   # 确定性脚本（可选）
│   ├── fetch_data.py         # curl 抓取、文件处理等
│   └── transform.py          # 数据转换脚本
└── references/                # 按需加载知识（可选）
    ├── api_docs.md           # 详细 API 文档
    └── examples.md           # 使用示例
```

**各目录职责**：

| 目录 | 说明 | 加载策略 |
|------|------|---------|
| `SKILL.md` | 元数据 + 核心指令，始终加载 | 常驻 |
| `handler.py` | Skill 主体逻辑 | 执行时加载 |
| `scripts/` | 确定性操作（curl、文件处理等），不占上下文，执行更可靠 | 触发时执行 |
| `references/` | 详细知识，按需加载 | 按需检索 |

**改进点**：

| 方面 | 基础架构 | Agent Skill 模式 |
|------|----------|------------------|
| **结构** | 所有 Skill 在 base.py | 每个 Skill 独立目录 |
| **发现** | 手动 register() | 自动扫描目录 |
| **元数据** | 基础字段 | 丰富（examples, capabilities, requirements） |
| **知识存储** | 代码内嵌 | references/ 按需加载 |
| **脚本支持** | 无 | scripts/ 确定性脚本 |
| **版本** | Registry-based | Git-based 或语义版本 |

---

## 三、核心组件

### 3.1 SkillRegistry

> 代码位置: `core/apps/skills/registry.py`

```python
class SkillRegistry:
    """Skill 注册表 - 管理所有可用 Skill"""
    
    def register(self, skill: BaseSkill) -> None:
        """注册 Skill"""
        
    def get(self, name: str) -> Optional[BaseSkill]:
        """按名获取 Skill"""
        
    def get_versions(self, name: str) -> List[SkillVersion]:
        """获取所有版本"""
        
    def rollback_version(self, name: str, version: str) -> bool:
        """回滚到指定版本"""
        
    def enable(self, name: str) -> bool:
        """启用 Skill"""
        
    def disable(self, name: str) -> bool:
        """禁用 Skill"""
        
    def bind_agent(self, skill_name: str, agent_id: str) -> None:
        """绑定到 Agent"""
        
    def get_binding_stats(self, name: str) -> SkillBindingStats:
        """获取绑定统计"""
```

---

## 证据索引（Evidence Index｜抽样）

- Registry 版本/回滚语义：`core/apps/skills/registry.py`（`rollback_version()` / `get_active_version()`）
- API：`core/server.py`（`/skills/{id}/active-version`、rollback endpoint 返回 active_version/active_config）
- 单测：`core/tests/unit/test_skills/test_skill_rollback_semantics.py`

---

## 设计补全（Round2）：版本与回滚语义（必须可验收）

> 目标：避免“回滚 API 成功但行为不变”的误导性实现，保证审计与回滚具备工程意义。

### 1) 核心语义定义

**术语**：
- `SkillVersion`：版本条目（version + SkillConfig + created_at）
- `active_version`：当前生效版本（用于后续执行）

**最低语义（必须满足）**：
1. 回滚后，`GET /skills/{id}/versions/{version}` 返回的 config 与创建时一致（已实现）
2. 回滚后，系统必须能明确回答“当前 active_version 是谁”（建议新增 `GET /skills/{id}/active-version` 或在 skill info 中返回）
3. 回滚后，**下一次执行**必须使用目标版本对应的配置/行为（必要时重建 skill 实例或刷新其 config）

### 2) 推荐实现策略（两种择一）

| 策略 | 描述 | 优点 | 风险 |
|---|---|---|---|
| A. 单实例切配置 | skill 实例保持单例，回滚时更新其 config 并触发 reload | 简单、资源少 | 需要保证 skill 对 config 变更可重入 |
| B. 按版本多实例 | registry 内维护 name→(version→instance)，active 指针切换 | 语义最清晰 | 占用更多资源、需管理生命周期 |

### 3) API 契约要求

`POST /skills/{id}/rollback`（或现有 endpoint）必须：
- 若 version 不存在：返回 404
- 若 rollback 成功：返回 `active_version` 与 `active_config` 摘要

### 4) 验收标准（必须有集成测试）

最小闭环用例：
1. 创建 v1（description=A）与 v2（description=B）
2. 执行 skill，记录其读取的 description（或通过 config 查询）
3. rollback 到 v1
4. 再执行 skill，必须观察到 config/行为回到 v1


### 3.2 SkillExecutor

> 代码位置: `core/apps/skills/executor.py`

```python
class SkillExecutor:
    """Skill 执行器 - 负责 Skill 的具体执行"""
    
    def __init__(self, registry: SkillRegistry, default_timeout: float = 60.0):
        self._registry = registry
        self._default_timeout = default_timeout
        
    async def execute(
        self,
        skill_name: str,
        params: Dict[str, Any],
        context: Optional[SkillContext] = None,
        timeout: Optional[float] = None
    ) -> SkillResult:
        """执行 Skill（带超时控制）"""
        
    def get_execution(self, execution_id: str) -> Optional[ExecutionRecord]:
        """获取执行记录"""
        
    def list_executions(self, skill_name: Optional[str], limit: int, offset: int):
        """列出执行历史"""
```

### 3.3 自动发现机制

> 未来改进方向：从手动注册到自动扫描

```python
class SkillDiscovery:
    """自动发现系统 - 扫描目录，自动加载 Skill"""
    
    def __init__(self, base_path: str):
        self.base_path = base_path
        
    async def discover(self) -> Dict[str, BaseSkill]:
        """扫描目录，自动发现 Skill"""
        skills = {}
        
        for item in Path(self.base_path).iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                skill = await self._load_skill(item)
                skills[skill.name] = skill
                
        return skills
    
    async def _load_skill(self, skill_dir: Path) -> BaseSkill:
        """加载单个 Skill"""
        # 读取 SKILL.md 解析元数据
        # 加载 handler.py
        # 加载 references/（按需）
        pass
```

**发现流程**：
```
skill_dir/
    └── SKILL.md (必须有)
         ↓
    解析元数据 (name, description, version)
         ↓
    加载 handler.py (可选)
         ↓
    注册到 SkillRegistry
```

---

## 四、元数据设计

### 4.1 基础元数据（现有）

```python
@dataclass
class SkillMetadata:
    name: str
    description: str
    version: str = "1.0.0"
    category: str = "general"
    tags: List[str] = field(default_factory=list)
```

### 4.2 SKILL.md 格式（Agent Skill 模式）

```yaml
# SKILL.md - Skill 元数据定义
name: text-generation
display_name: 文本生成
description: 根据提示生成各类文本内容
version: 1.0.0

category: generation
tags: [text, gpt, llm]

# 能力定义
capabilities:
  - 生成营销文案
  - 写邮件
  - 内容润色

# 触发场景（给 AI 看的"路由表"）
trigger_conditions:
  - "用户要求生成文本内容"
  - "需要撰写文档或文案"
  - "内容润色或改写需求"

# 输入输出
input_schema:
  prompt:
    type: string
    required: true
    description: 生成提示
  max_tokens:
    type: integer
    default: 1000
    description: 最大长度
  temperature:
    type: number
    default: 0.7
    description: 采样温度

output_schema:
  text:
    type: string
    description: 生成的文本
  tokens:
    type: integer
    description: 消耗的 token 数

# 示例
examples:
  - input:
      prompt: 写一篇关于AI的文章
      max_tokens: 2000
    output:
      text: "AI正在改变..."
      tokens: 1500

# 依赖
requirements:
  - name: openai
    version: ">=1.0.0"
  - name: langchain
    version: ">=0.1.0"

# 权限
permissions:
  - network_access
  - file_read
```

**设计原则**：

1. **简洁是王道**：`description` 字段是给 AI 看的"路由表"，要精准描述触发场景
2. **脚本优先**：确定性逻辑（如 `curl` 抓取、文件处理）写成脚本，不占上下文，执行更可靠
3. **渐进式披露**：元数据 → 核心指令 → 详细知识 → 脚本资源，逐层加载
4. **不要创建无关文档**：Skill 目录里不要放 `README.md`，会造成混淆

---

## 五、执行模型

### 5.1 同步 vs 异步

所有 Skill 执行都是 **异步** 的：

```python
# 调用方式
result = await skill_executor.execute(
    skill_name="text_generation",
    params={"prompt": "Hello", "max_tokens": 100},
    context=SkillContext(session_id="sess-001"),
    timeout=30.0  # 可选超时
)
```

### 5.2 超时控制

| 阶段 | 处理 |
|------|------|
| 参数验证 | 同步，返回 bool |
| 执行 | 异步，可设置超时 |
| 超时 | 返回超时错误，记录日志 |

### 5.3 执行状态

```
pending → running → success / failed / timeout
```

### 5.4 执行记录

```python
@dataclass
class ExecutionRecord:
    execution_id: str       # 执行ID
    skill_name: str        # Skill 名称
    status: str            # pending/running/success/failed/timeout
    input_params: Dict     # 输入参数
    output: Any            # 输出结果
    error: Optional[str]   # 错误信息
    start_time: float      # 开始时间
    end_time: float        # 结束时间
    latency: float         # 耗时（毫秒）
```

---

## 六、版本管理

### 6.1 版本策略

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| **语义版本** | x.y.z 格式 | 稳定发布 |
| **时间版本** | yymmdd-hhmmss | 快速迭代 |
| **Git commit** | commit hash | 追溯源码 |

### 6.2 版本操作

```python
# 获取版本列表
GET /api/core/skills/{skill_id}/versions

# 获取指定版本
GET /api/core/skills/{skill_id}/versions/{version}

# 回滚
POST /api/core/skills/{skill_id}/versions/{version}/rollback
```

---

## 七、权限控制

> 代码位置: `core/apps/tools/permission.py`

### 7.1 权限模型

| 权限 | 说明 |
|------|------|
| `network_access` | 网络访问 |
| `file_read` | 读取文件 |
| `file_write` | 写入文件 |
| `execute_command` | 执行命令 |
| `http_request` | HTTP 请求 |

### 7.2 权限检查

```python
class PermissionManager:
    async def check_permission(self, skill_name: str, operation: str) -> bool:
        """检查权限"""
        
    async def grant(self, skill_name: str, permission: str) -> None:
        """授予权限"""
        
    async def revoke(self, skill_name: str, permission: str) -> None:
        """撤销权限"""
```

---

## 八、与模块的关系

| 模块 | 关系 | 引用 |
|------|------|------|
| **Harness** | 使用执行循环 | [Harness 框架](./harness/index.md) |
| **Tools** | Skill 可调用工具 | [工具系统](./tools/index.md) |
| **Models** | Skill 使用模型 | [LLM 适配器](./adapters/llm.md) |
| **Memory** | 使用上下文 | [记忆系统](./memory/index.md) |
| **Agent** | Agent 调用 Skill | [Agent 架构](./agents/architecture.md) |

---

## 九、相关文档

- [Skill 概述](./index.md) - Skill 模块定位与类型
- [Skill 生命周期](./lifecycle.md) - Skill 进化机制 (CAPTURED/FIX/DERIVED)
- [Agent 架构](./agents/architecture.md) - Agent 架构设计
- [工具系统](./tools/index.md) - 工具定义与权限
- [Harness 框架](./harness/index.md) - 基础设施层

---

*最后更新: 2026-04-14*
*版本: v1.0*
