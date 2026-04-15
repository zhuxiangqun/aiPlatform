# 反馈闭环增强设计

## 概述

本文档描述如何增强 aiPlat-core 的反馈闭环系统，实现质量门禁、安全扫描和自动验证机制。

## 目标

1. **质量门禁** - 代码/输出质量自动检查
2. **安全扫描** - 敏感信息检测和漏洞扫描
3. **验证机制** - 执行结果验证和确认

## 现有组件

### FeedbackCollector (已实现)

位置: `core/harness/execution/feedback.py`

功能:
- 收集反馈条目 (SUCCESS, ERROR, WARNING, RETRY, TIMEOUT, QUALITY, PERFORMANCE)
- 按类型、严重级别、来源聚合统计
- 支持自定义处理器

### ApprovalSystem (已实现)

位置: `core/harness/infrastructure/approval/`

功能:
- 人工审批工作流
- 规则引擎 (金额阈值、敏感操作、批量操作、首次操作)
- 请求生命周期管理

## 设计方案

### 1. 质量门禁 (Quality Gate)

**目的**: 在关键节点自动检查输出质量，不满足则阻止继续

**触发点**:
- Agent 执行完成后
- 工具调用返回后
- 任务完成时

**检查项**:

| 检查项 | 描述 | 阈值 |
|--------|------|------|
| 代码语法 | Python/JS 语法检查 | 0 错误 |
| 代码复杂度 | Cyclomatic complexity | < 15 |
| 错误率 | 错误反馈占比 | < 5% |
| 延迟 | 执行延迟 | < 阈值 |
| 质量分数 | 自定义评分 | >= 80 |

**接口设计**:

```python
@dataclass
class QualityGateResult:
    passed: bool
    score: float
    checks: Dict[str, CheckResult]
    suggestions: List[str]

@dataclass
class CheckResult:
    name: str
    passed: bool
    value: Any
    threshold: Any
    message: str

class QualityGate:
    async def check(self, context: ExecutionContext) -> QualityGateResult:
        """执行质量检查"""
        pass
```

### 2. 安全扫描 (Security Scan)

**目的**: 检测敏感信息和潜在安全风险

**扫描类型**:

| 类型 | 检测内容 | 示例 |
|------|----------|------|
| 密钥检测 | API Key, Token, Password | "sk-xxxx", "password=xxx" |
| 凭证检测 | AWS, GitHub, 数据库凭证 | AKIAIOSFODNN7EXAMPLE |
| 路径遍历 | 路径注入攻击 | ../../../etc/passwd |
| SQL 注入 | SQL 注入风险 | ' OR '1'='1 |
| 命令注入 | Shell 命令注入 | ; cat /etc/passwd |

**接口设计**:

```python
@dataclass
class SecurityScanResult:
    passed: bool
    vulnerabilities: List[Vulnerability]
    
@dataclass
class Vulnerability:
    severity: str  # critical, high, medium, low
    type: str
    location: str
    description: str
    suggestion: str

class SecurityScanner:
    async def scan(self, content: str, context: Dict) -> SecurityScanResult:
        """执行安全扫描"""
        pass
```

### 3. 验证机制 (Verification)

**目的**: 验证执行结果符合预期

**验证类型**:

| 类型 | 描述 |
|------|------|
| 断言验证 | 基于用户定义的断言 |
| 模式验证 | JSON/Schema 验证 |
| 回归验证 | 与历史输出对比 |
| 阈值验证 | 数值范围验证 |

**接口设计**:

```python
class ResultVerifier:
    async def verify(
        self,
        result: Any,
        spec: VerificationSpec
    ) -> VerificationResult:
        """验证执行结果"""
        pass

@dataclass
class VerificationSpec:
    type: str  # assertion, schema, regression, threshold
    spec: Dict  # 具体验证规范
    
@dataclass  
class VerificationResult:
    passed: bool
    message: str
    details: Dict
```

### 4. 命令集成

通过命令方式触发质量门禁和安全扫描:

```bash
/quality-gate --strict          # 严格模式
/quality-gate --checks=syntax,complexity  # 指定检查项
/security-scan --full           # 完整扫描
/security-scan --types=keys,sql  # 指定扫描类型
/verify --spec=schema.json      # 验证输出
```

## 模块结构

```
core/apps/quality/
├── __init__.py
├── gates.py           # QualityGate
├── scanner.py         # SecurityScanner  
├── verifier.py        # ResultVerifier
├── checks/            # 各类检查器
│   ├── __init__.py
│   ├── syntax.py     # 语法检查
│   ├── complexity.py # 复杂度检查
│   └── security.py   # 安全扫描
└── types.py          # 数据类型
```

## 集成方式

### 与 FeedbackLoop 集成

质量门禁结果发送到反馈系统:

```python
feedback = ExecutionFeedback.get_instance()
result = await quality_gate.check(context)

feedback.collector.add(
    FeedbackType.QUALITY,
    FeedbackSeverity.HIGH if not result.passed else FeedbackSeverity.LOW,
    "quality_gate",
    f"Quality gate {'passed' if result.passed else 'failed'}",
    context=result.to_dict()
)
```

### 与 Approval 集成

安全扫描失败触发审批:

```python
if not scan_result.passed:
    approval_manager.request_approval(
        context=ApprovalContext(
            operation="security_scan_failed",
            details=f"Found {len(scan_result.vulnerabilities)} issues"
        )
    )
```

## 配置

```python
# 质量门禁配置
quality_gate_config = {
    "enabled": True,
    "checks": ["syntax", "complexity", "error_rate"],
    "thresholds": {
        "error_rate": 0.05,
        "max_complexity": 15,
        "min_quality_score": 80
    }
}

# 安全扫描配置
security_scan_config = {
    "enabled": True,
    "scan_types": ["keys", "credentials", "injection"],
    "severity_threshold": "high"
}
```

## 实施计划

1. **Phase 1**: 实现基础 QualityGate 框架
2. **Phase 2**: 实现语法和复杂度检查
3. **Phase 3**: 实现 SecurityScanner
4. **Phase 4**: 实现 ResultVerifier
5. **Phase 5**: 命令行集成

## 待实现

- [ ] core/apps/quality/ 模块
- [ ] 语法检查器
- [ ] 复杂度检查器
- [ ] 安全扫描器
- [ ] 结果验证器
- [ ] 命令行接口

---

## Agent 评估体系

基于 Anthropic 的 Agent 评估实践，解决"Agent 是否真的有用"的量化问题。

### 1. 评估维度

| 维度 | 描述 | 指标 |
|------|------|------|
| **任务成功率** | 端到端是否解决了用户问题 | Pass@k |
| **工具使用准确性** | 是否调用了正确的工具和参数 | Tool Accuracy |
| **安全性与护栏** | 是否拒绝了不安全指令 | Safety Rate |
| **Token 效率** | 完成任务的 Token 消耗 | Token/Task |
| **响应延迟** | 从请求到响应的时间 | Latency |

### 2. Pass@k vs Pass^k

这是两个不同的概念：

| 指标 | 含义 | 用途 |
|------|------|------|
| **Pass@k** | 尝试 k 次后至少成功一次的概率 | 验证能力边界 |
| **Pass^k** | 连续 k 次请求都成功的概率 | 保证上线质量 |

```
Pass@1 = 首次成功率
Pass@3 = 3 次内至少成功一次
Pass^k >= 95% = 上线质量标准
```

### 3. 评估数据收集

#### 轨迹记录

每次 Agent 执行需要记录：

```python
@dataclass
class AgentTrace:
    session_id: str
    task_id: str
    prompt: str
    tool_calls: List[ToolCall]
    tool_results: List[ToolResult]
    final_response: str
    success: bool
    latency_ms: int
    tokens_used: int
    
    # 评分字段
    quality_score: float
    safety_score: float
    tool_accuracy: float
```

#### 自动评分（LLM-as-Judge）

使用 LLM 对执行结果进行评分：

```python
# 判断任务是否成功完成
judge_prompt = """
任务：{task_description}
Agent 响应：{response}
是否成功完成任务？是/否，原因："""
```

### 4. 基准测试

#### 内置基准

| 基准 | 描述 | 任务数 |
|------|------|--------|
| `code-review` | 代码审查任务 | 20 |
| `bug-fix` | Bug 修复任务 | 30 |
| `refactor` | 代码重构任务 | 15 |
| `test-write` | 测试编写任务 | 25 |
| `doc-gen` | 文档生成任务 | 20 |

#### 自定义基准

```python
# 创建自定义基准
benchmark = Benchmark(
    name="my-tasks",
    tasks=[
        Task(
            id="task-1",
            prompt="分析这个 PR 的安全性",
            expected_tools=["Read", "Grep"],
            success_criteria="找出 3 个安全漏洞"
        )
    ]
)

# 运行基准
results = await benchmark.run(agent=my_agent)

# 输出报告
print(results.summary())
# {
#   "pass_at_1": 0.75,
#   "pass_at_3": 0.92,
#   "avg_tokens": 4500,
#   "avg_latency": 2.3s
# }
```

### 5. 回归检测

每次代码变更后自动运行基准测试：

```python
# 检测是否性能下降
def check_regression(current: Result, baseline: Result) -> bool:
    return (
        current.pass_at_1 < baseline.pass_at_1 - 0.05 or  # 成功率下降 > 5%
        current.avg_tokens > baseline.avg_tokens * 1.2   # Token 增加 > 20%
    )
```

### 6. 轨迹自动分级

使用 LLM 对轨迹进行质量分级：

```python
# 轨迹分级
GRADE_A = "完美执行，无需任何修正"
GRADE_B = "有轻微问题，自行修正后成功"
GRADE_C = "需要人工介入才能完成"
GRADE_D = "执行失败，无法完成任务"

# 分析轨迹
grade = await grader.grade(trace)
```

### 7. 模块结构

```
core/apps/evaluation/
├── __init__.py
├── benchmarks/          # 基准定义
│   ├── __init__.py
│   ├── base.py        # 基准基类
│   └── builtin.py     # 内置基准
├── grader.py          # LLM 评分器
├── tracker.py         # 轨迹追踪
├── regression.py      # 回归检测
├── reporter.py        # 报告生成
└── cli.py             # CLI 接口
```

### 8. CLI 命令

```bash
# 运行内置基准
aiplat eval run --benchmark=code-review

# 运行自定义基准
aiplat eval run --benchmark=path/to/benchmark.yaml

# 查看历史结果
aiplat eval history --days=30

# 检测回归
aiplat eval regression --compare=last-release

# 轨迹分析
aiplat eval trace session-123 --format=json
```

### 9. 与 Quality Gate 集成

评估结果可触发质量门禁：

```python
# 评估结果不满足要求时阻止部署
if results.pass_at_1 < 0.70:
    raise DeploymentError(
        f"Agent 成功率不达标: {results.pass_at_1} < 0.70"
    )
```

### 10. 与 Skill 进化集成

评估结果用于触发 Skill 进化：

```python
# 成功率下降触发 Skill 修复
if task_category == "bug-fix" and results.pass_at_1 < 0.60:
    await evolution_engine.trigger_evolution(
        skill_id="bug-fix",
        trigger_type=TriggerType.METRIC,
        context={"metric": "pass_rate", "value": results.pass_at_1}
    )
```

## 待实现（补充）

- [ ] core/apps/evaluation/ 模块
- [ ] 内置基准定义
- [ ] LLM-as-Judge 评分器
- [ ] 轨迹记录和存储
- [ ] 回归检测
- [ ] CLI 命令集成
- [ ] 与 Skill 进化集成