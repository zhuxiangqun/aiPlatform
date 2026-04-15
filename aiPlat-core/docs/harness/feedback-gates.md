# 反馈闭环增强

> 构建可插拔的质量门禁系统，实现验证驱动的 Agent 执行闭环

---

## 一句话定义

**反馈闭环增强**是在现有 Hooks 机制基础上，构建独立的质量门禁系统——通过可插拔的验证器（QualityGate）、统一的验证结果格式（VerificationResult）、以及命令行接口（/quality-gate, /security-scan），实现验证驱动的 Agent 执行闭环。

---

## 核心概念

### 当前系统已有能力

| 能力 | 实现位置 | 状态 |
|------|---------|------|
| ApprovalManager | harness/infrastructure/approval/ | ✅ 审批门禁 |
| SprintContractManager | harness/contract/ | ✅ 契约验证 |
| EvolutionEngine | harness/feedback_loops/ | ✅ 自动适应 |
| LocalFeedbackLoop | harness/feedback_loops/ | ✅ 运行时反馈 |

### 新增能力

| 能力 | 说明 | 优先级 |
|------|------|--------|
| **QualityGate** | 可插拔验证器基类 | P0 |
| **/quality-gate 命令** | 统一质量验证入口 | P0 |
| **/security-scan 命令** | 统一安全扫描入口 | P0 |
| **VerificationResult** | 统一验证结果格式 | P0 |
| **多检查器组合** | 验证器链式组合 | P1 |
| **新触发器** | VALIDATION_FAILURE 等 | P1 |

---

## 质量门禁设计

### QualityGate 基类

```python
class QualityGate(ABC):
    """质量门禁 - 可插拔验证器"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """验证器名称"""
        
    @property
    @abstractmethod
    def description(self) -> str:
        """验证器描述"""
        
    @abstractmethod
    async def verify(self, context: ExecutionContext) -> VerificationResult:
        """执行验证"""
        
    async def setup(self) -> None:
        """初始化验证器 (可选)"""
        
    async def teardown(self) -> None:
        """清理验证器 (可选)"""
```

### 内置验证器

| 验证器 | 功能 | 触发时机 |
|--------|------|----------|
| **SyntaxCheckGate** | 代码语法检查 | 每次文件写入后 |
| **LintCheckGate** | Lint 检查 | Stop Hook |
| **TestCheckGate** | 测试执行 | Stop Hook |
| **SecurityCheckGate** | 安全扫描 | Stop Hook |
| **ArchitectureCheckGate** | 架构约束验证 | 每次代码变更后 |

---

### 内置验证器实现

#### SyntaxCheckGate

```python
class SyntaxCheckGate(QualityGate):
    """语法检查门禁"""
    
    SUPPORTED_LANGUAGES = {
        "python": ["python", "py"],
        "javascript": ["js", "jsx", "ts", "tsx"],
        "java": ["java"],
    }
    
    async def verify(self, context: ExecutionContext) -> VerificationResult:
        """
        检查文件语法:
        - Python: 使用 ast.parse
        - JavaScript: 使用 esprima
        - Java: 调用 javac -Xdiag
        """
```

#### LintCheckGate

```python
class LintCheckGate(QualityGate):
    """Lint 检查门禁"""
    
    async def verify(self, context: ExecutionContext) -> VerificationResult:
        """
        运行项目配置的 linter:
        - Python: ruff, flake8, pylint
        - JavaScript: eslint, prettier
        - Java: checkstyle
        """
```

#### TestCheckGate

```python
class TestCheckGate(QualityGate):
    """测试执行门禁"""
    
    async def verify(self, context: ExecutionContext) -> VerificationResult:
        """
        执行测试:
        - 运行与变更文件相关的测试
        - 收集覆盖率报告
        - 检查测试通过率
        """
```

#### SecurityCheckGate

```python
class SecurityCheckGate(QualityGate):
    """安全扫描门禁"""
    
    async def verify(self, context: ExecutionContext) -> VerificationResult:
        """
        安全扫描:
        - 依赖漏洞检查 (npm audit, safety)
        - 敏感信息检测 (keys, tokens)
        - 已知漏洞模式匹配
        """
```

---

## 验证结果统一格式

### VerificationResult

```python
@dataclass
class VerificationResult:
    """验证结果统一格式"""
    
    passed: bool
    exit_code: int  # 0=放行, 1=警告, 2=阻断, 3=需人工
    gate_name: str
    checks: List[CheckResult]
    suggestions: List[str]
    metadata: Dict[str, Any]

@dataclass
class CheckResult:
    """单个检查结果"""
    name: str
    passed: bool
    message: str
    severity: str  # "info" | "warning" | "error"
    location: Optional[str]  # 文件路径:行号
```

### Exit Code 语义

| Code | 语义 | Agent 行为 |
|------|------|-----------|
| 0 | 放行 | 继续执行 |
| 1 | 警告 | 显示警告但继续 |
| 2 | **阻断** | 必须修复才能继续 |
| 3 | 需要人工确认 | 暂停等待人类决策 |

---

## 命令行接口

### /quality-gate 命令

```bash
# 运行完整质量门禁
/quality-gate

# 运行特定验证器
/quality-gate --gates syntax,lint,test

# 检查特定文件
/quality-gate --files src/utils.py

# 输出格式
/quality-gate --format json  # JSON 输出
/quality-gate --format text  # 文本输出
```

### /security-scan 命令

```bash
# 运行安全扫描
/security-scan

# 扫描特定目录
/security-scan --path src/

# 只检查依赖漏洞
/security-scan --type dependencies

# 只检查敏感信息
/security-scan --type secrets
```

---

## 验证器链式组合

### GatePipeline

```python
class GatePipeline:
    """验证器流水线 - 链式组合多个验证器"""
    
    def __init__(self):
        self._gates: List[QualityGate] = []
        
    def add_gate(self, gate: QualityGate) -> "GatePipeline":
        """添加验证器"""
        self._gates.append(gate)
        return self
        
    async def execute(self, context: ExecutionContext) -> VerificationResult:
        """执行流水线"""
        all_results = []
        
        for gate in self._gates:
            result = await gate.verify(context)
            all_results.append(result)
            
            # 如果是阻断错误且配置为快速失败，则停止
            if result.exit_code == 2 and self._fast_on_blocking:
                break
                
        return self._aggregate_results(all_results)
```

### 预定义流水线

```python
# 快速验证（仅语法）
QUICK_PIPELINE = GatePipeline()\
    .add_gate(SyntaxCheckGate())

# 标准验证（语法 + Lint）
STANDARD_PIPELINE = GatePipeline()\
    .add_gate(SyntaxCheckGate())\
    .add_gate(LintCheckGate())

# 完整验证（语法 + Lint + 测试 + 安全）
FULL_PIPELINE = GatePipeline()\
    .add_gate(SyntaxCheckGate())\
    .add_gate(LintCheckGate())\
    .add_gate(TestCheckGate())\
    .add_gate(SecurityCheckGate())
```

---

## EvolutionEngine 扩展

### 新增触发器

| 触发器 | 条件 | 动作 |
|--------|------|------|
| **VALIDATION_FAILURE** | 验证失败次数 > 阈值 | REJECT_OUTPUT |
| **RESOURCE_USAGE** | CPU/内存超限 | SCALE_DOWN |
| **COMPLEXITY_THRESHOLD** | 任务复杂度 > 阈值 | SIMPLIFY_TASK |

```python
class EvolutionTriggerType(Enum):
    # 现有
    ERROR_THRESHOLD = "error_threshold"
    LATENCY_THRESHOLD = "latency_threshold"
    QUALITY_SCORE = "quality_score"
    RETRY_COUNT = "retry_count"
    
    # 新增
    VALIDATION_FAILURE = "validation_failure"  # 验证失败
    RESOURCE_USAGE = "resource_usage"          # 资源使用
    COMPLEXITY_THRESHOLD = "complexity_threshold" # 任务复杂度
```

---

## 与现有系统集成

### Stop Hook 集成

```python
# 在 Stop Hook 中调用质量门禁
@hook("Stop")
async def quality_gate_hook(context: ExecutionContext) -> HookResult:
    pipeline = GatePipeline()\
        .add_gate(SyntaxCheckGate())\
        .add_gate(LintCheckGate())\
        .add_gate(TestCheckGate())
        
    result = await pipeline.execute(context)
    
    if result.exit_code == 2:
        return HookResult(
            approved=False,
            message=f"质量门禁未通过: {result.gate_name}",
            details=result.suggestions
        )
    return HookResult(approved=True)
```

### 命令行集成

```python
# 注册命令
@command("/quality-gate")
async def handle_quality_gate(
    args: List[str],
    context: ExecutionContext
) -> CommandResult:
    # 解析参数
    gates = parse_gate_args(args)
    files = parse_file_args(args)
    output_format = parse_format_args(args)
    
    # 执行验证
    pipeline = build_pipeline(gates)
    result = await pipeline.execute(context)
    
    # 输出结果
    return format_result(result, output_format)
```

---

## 配置示例

```yaml
# config/quality-gates.yaml
quality_gates:
  # 默认流水线配置
  pipeline:
    default: "standard"  # quick | standard | full
    
  # 各验证器配置
  gates:
    syntax:
      enabled: true
      languages:
        - python
        - javascript
        - typescript
        
    lint:
      enabled: true
      fail_on_warning: false
      include_rules:
        - "E.*"  # pycodestyle errors
        - "W.*"  # pycodestyle warnings
      exclude_rules:
        - "E501"  # line too long
        
    test:
      enabled: true
      min_coverage: 80
      fail_on_coverage: false
      
    security:
      enabled: true
      scan_dependencies: true
      scan_secrets: true
      severity_threshold: "high"
      
# 快速失败配置
fast_fail:
  enabled: true
  on_blocking: true
  gates:
    - syntax
    - security
    
# 命令行快捷方式
commands:
  quality-gate:
    aliases: ["/qg", "/quality"]
  security-scan:
    aliases: ["/sec", "/scan"]
```

---

## 相关文档

- [反馈循环系统](./feedback-loops.md) - 基础反馈机制
- [Harness 框架](./index.md) - Agent 运行环境
- [Observability](./observability.md) - 可观测性

---

*最后更新: 2026-04-14*