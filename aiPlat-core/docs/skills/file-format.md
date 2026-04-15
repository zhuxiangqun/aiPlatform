# Skill 文件格式演进设计

> 基于 OpenClaw/Claude Code 实践，增强 Skill 系统能力

本文档描述如何将现有 Skill 系统演进为 OpenClaw 兼容格式，添加 trigger_keywords、Category 分类、Script 执行器等能力。

---

## 一、现状分析

### 1.1 已实现功能

| 组件 | 位置 | 状态 |
|------|------|------|
| SKILL.md 解析 | `discovery.py:SKILLMD_parser` | ✅ 已实现 |
| YAML frontmatter | `FRONT_MATTER_PATTERN` | ✅ 已实现 |
| references/ 加载 | `SkillLoader.load_reference` | ✅ 已实现 |
| scripts/ 加载 | `SkillLoader.load_script` | ✅ 已实现 |
| 目录发现 | `server.py:lifespan` | ✅ 已实现 |

### 1.2 缺失功能

| 优先级 | 功能 | 当前状态 |
|--------|------|----------|
| P0 | trigger_keywords | ❌ 缺失 |
| P1 | Category 分类 | 只有 `general` |
| P1 | Script 执行 | 仅读取，未运行 |
| P2 | 执行模式 (inline/fork) | ❌ 缺失 |
| P2 | SkillManifest 数据结构 | ❌ 缺失 |

---

## 二、目标设计

### 2.1 SKILL.md 完整格式

```yaml
---
name: code-review
description: 代码审查技能，检测代码质量问题
trigger_keywords:
  - "代码审查"
  - "review 代码"
  - "检查代码"
category: code_review
version: 1.0.0
author: aiplat-team

# 扩展字段
capabilities:
  - 语法检查
  - 风格检查
  - 安全扫描

# 执行模式
execution_mode: inline  # inline | fork

# 输入输出
input_schema:
  code:
    type: string
    description: 待审查代码
  language:
    type: string
    description: 编程语言

output_schema:
  issues:
    type: array
    description: 发现的问题列表
  score:
    type: number
    description: 代码质量评分

# 示例
examples:
  - input:
      code: "def foo():\n    pass"
      language: python
    output:
      issues: []
      score: 100

# 依赖
requirements:
  - name: ruff
    version: ">=0.1.0"

# 权限
permissions:
  - file_read
  - execute_command
---
# Skill 正文内容

## 功能说明

此 Skill 用于代码审查...

## 使用方法

使用方式：@skill code-review [代码路径]

## 注意事项

- 需要安装 ruff
- 仅支持 Python/JS/TS
```

### 2.2 Category 分类 (9 类)

| Category | 说明 | 示例触发词 |
|----------|------|-----------|
| `code_review` | 代码审查 | "审查代码", "代码检查" |
| `ci_cd` | CI/CD 部署 | "部署", "发布", "CI" |
| `data_analysis` | 数据分析 | "分析数据", "生成报表" |
| `documentation` | 文档生成 | "写文档", "生成报告" |
| `runbook` | 运维手册 | "故障排查", "运维" |
| `testing` | 测试验证 | "写测试", "测试用例" |
| `frontend` | 前端开发 | "前端", "UI", "组件" |
| `api_design` | API 设计 | "设计 API", "接口" |
| `general` | 通用 | 其他 |

### 2.3 目录结构

```
skills/
├── SKILL.md              # 索引文件（可选）
├── code-review/          # Skill A
│   ├── SKILL.md          # 元数据
│   ├── handler.py        # Python 处理器（可选）
│   ├── references/       # 参考文档
│   │   ├── patterns.md   # 模式参考
│   │   └── api-docs.md   # API 文档
│   └── scripts/          # 确定性脚本
│       ├── lint.sh       # lint 脚本
│       └── format.py     # 格式化脚本
├── ci-cd/
│   └── ...
└── data-analysis/
    └── ...
```

---

## 三、演进计划

### Phase 1: trigger_keywords 元数据增强 (P0)

#### 目标
添加用户意图匹配能力，通过关键词触发 Skill。

#### 修改文件
- `core/apps/skills/discovery.py` - DiscoveredSkill 添加字段
- `core/apps/skills/types.py` - 新增 SkillManifest 类型

#### 实现方式

**1. 更新 DiscoveredSkill**

```python
@dataclass
class DiscoveredSkill:
    # ... 现有字段 ...
    trigger_keywords: List[str] = field(default_factory=list)  # 新增
    execution_mode: str = "inline"  # 新增
```

**2. 解析 trigger_keywords**

```python
# SKILLMD_parser.parse() 中添加
trigger_keywords = data.get('trigger_keywords', [])
execution_mode = data.get('execution_mode', 'inline')
```

**3. 匹配逻辑**

```python
class SkillMatcher:
    """根据用户输入匹配 Skill"""
    
    def match(self, user_input: str, skills: List[DiscoveredSkill]) -> List[DiscoveredSkill]:
        """匹配相关 Skill"""
        results = []
        input_lower = user_input.lower()
        
        for skill in skills:
            for keyword in skill.trigger_keywords:
                if keyword.lower() in input_lower:
                    results.append(skill)
                    break
        
        return results
```

### Phase 2: Category 分类扩展 (P1)

#### 目标
支持 Anthropic 9 类 Category，实现按类别筛选。

#### 修改文件
- `core/apps/skills/types.py` - 新增 SkillCategory 枚举
- `core/apps/skills/discovery.py` - 更新 DiscoveredSkill

#### 实现方式

```python
# core/apps/skills/types.py

from enum import Enum

class SkillCategory(Enum):
    """Skill Category - 9 类分类"""
    CODE_REVIEW = "code_review"
    CI_CD = "ci_cd"
    DATA_ANALYSIS = "data_analysis"
    DOCUMENTATION = "documentation"
    RUNBOOK = "runbook"
    TESTING = "testing"
    FRONTEND = "frontend"
    API_DESIGN = "api_design"
    GENERAL = "general"
    
    @classmethod
    def from_string(cls, value: str) -> "SkillCategory":
        """从字符串转换"""
        try:
            return cls(value)
        except ValueError:
            return cls.GENERAL
```

### Phase 3: Script 执行器 (P1)

#### 目标
实际执行 scripts/ 目录下的脚本，实现确定性操作。

#### 新增文件
- `core/apps/skills/script_runner.py` - ScriptRunner 类

#### 设计要点

**1. 沙箱限制**

```python
class SandboxConfig:
    """沙箱配置"""
    allowed_extensions: List[str] = [".sh", ".py", ".js"]  # 允许的脚本类型
    max_execution_time: float = 30.0  # 最大执行时间 (秒)
    max_memory_mb: int = 512  # 最大内存
    allowed_env_vars: List[str] = ["PATH", "HOME"]  # 允许的环境变量
    blocked_commands: List[str] = ["rm -rf", "sudo", "kill"]  # 禁止的命令
```

**2. 执行器**

```python
@dataclass
class ScriptResult:
    """脚本执行结果"""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float


class ScriptRunner:
    """确定性脚本执行器"""
    
    def __init__(self, config: SandboxConfig):
        self._config = config
    
    async def execute(
        self,
        script_path: str,
        args: List[str] = None,
        env: Dict[str, str] = None
    ) -> ScriptResult:
        """执行脚本"""
        # 1. 检查脚本扩展名
        # 2. 检查危险命令
        # 3. 设置超时
        # 4. 执行并捕获输出
        # 5. 清理资源
```

**3. 支持的脚本类型**

| 类型 | 执行方式 | 场景 |
|------|----------|------|
| `.sh` | `subprocess.run()` | Shell 脚本 |
| `.py` | `subprocess.run(['python', ...])` | Python 脚本 |
| `.js` | `subprocess.run(['node', ...])` | Node.js 脚本 |

### Phase 4: 执行模式支持 (P2)

#### 目标
支持 inline/fork 两种执行模式。

#### 修改文件
- `core/apps/skills/executor.py` - 添加 mode 参数

#### 实现方式

```python
class SkillExecutor:
    async def execute(
        self,
        skill_name: str,
        params: Dict[str, Any],
        context: Optional[SkillContext] = None,
        mode: str = "inline",  # 新增: inline | fork
        timeout: Optional[float] = None
    ) -> SkillResult:
        """执行 Skill"""
        
        if mode == "fork":
            # 启动子 Agent 执行
            return await self._execute_fork(skill_name, params, context)
        else:
            # 当前行为：inline
            return await self._execute_inline(skill_name, params, context)
    
    async def _execute_fork(
        self,
        skill_name: str,
        params: Dict,
        context: SkillContext
    ) -> SkillResult:
        """Fork 模式：启动子 Agent"""
        # 1. 获取 Skill 内容
        # 2. 创建子 Agent
        # 3. 传递 Skill 指令
        # 4. 返回结果
```

---

## 四、向后兼容性

### 4.1 两种定义方式共存

```python
class SkillExecutor:
    async def execute(self, skill_name, params, mode="inline"):
        # 1. 优先查找 Python class (BaseSkill)
        skill = self._registry.get(skill_name)
        if skill:
            return await self._execute_skill(skill, params)
        
        # 2. 回退到文件加载 (DiscoveredSkill)
        discovered = self._discovery.get(skill_name)
        if discovered:
            return await self._execute_file_skill(discovered, params, mode)
        
        return SkillResult(success=False, error="Skill not found")
```

### 4.2 默认值兼容

| 字段 | 缺失时的默认值 |
|------|----------------|
| `trigger_keywords` | `[]` (不触发) |
| `category` | `general` |
| `execution_mode` | `inline` |
| `version` | `1.0.0` |

---

## 五、安全策略

### 5.1 沙箱配置

```python
DEFAULT_SANDBOX_CONFIG = SandboxConfig(
    allowed_extensions=[".sh", ".py", ".js"],
    max_execution_time=30.0,
    max_memory_mb=512,
    allowed_env_vars=["PATH", "HOME", "USER"],
    blocked_commands=[
        "rm -rf /",
        "sudo",
        "kill -9",
        "curl | sh",
        "wget | sh"
    ]
)
```

### 5.2 权限检查

```python
class ScriptPermissionChecker:
    """脚本权限检查器"""
    
    def check(self, script_path: str) -> bool:
        """检查脚本是否安全"""
        # 1. 扩展名检查
        # 2. 路径遍历检查
        # 3. 命令黑名单检查
        # 4. 文件大小限制
```

---

## 六、实施顺序

| 阶段 | 任务 | 文件变更 |
|------|------|----------|
| **P0** | trigger_keywords | `discovery.py` |
| **P0** | SkillMatcher | `types.py` (新) |
| **P1** | SkillCategory 枚举 | `types.py` (新) |
| **P1** | ScriptRunner | `script_runner.py` (新) |
| **P2** | 执行模式支持 | `executor.py` |

---

## 七、相关文档

- [Skill 架构](./architecture.md) - 现有架构设计
- [Skill 概述](./index.md) - Skill 模块定位
- [Skill 生命周期](./lifecycle.md) - Skill 进化机制

---

*最后更新: 2026-04-14*
*版本: v1.0*