# Agent 安全审计（设计真值：以代码事实为准）

> 本文档区分 **As-Is（当前实现）** 与 **To-Be（目标演进）**。  
> 统一口径与可追溯规则参见：[架构实现状态](../ARCHITECTURE_STATUS.md)。

## 实现状态提示（As-Is vs To-Be）

- **As-Is（当前实现）**：Harness 默认在 `pre_approval_check` 阶段启用最小安全扫描（`SecurityScanHook`），并支持用环境变量配置扫描工具白/黑名单；扫描结果会写入 `state.context.audit_events[]`。
- **To-Be（目标演进）**：接入更完整的“部署前/CI 安全扫描”（如 agent-audit/规则集/策略门禁），并将扫描/审批/策略决策统一事件化并可回放。

---

## 一、安全挑战

### 1.1 Agent 特有的安全风险

| 风险类型 | 说明 | 危害 |
|----------|------|------|
| **工具滥用** | Agent 可执行任意 Shell 命令 | 系统破坏、数据泄露 |
| **Prompt 注入** | 恶意指令欺骗 Agent | 绕过安全控制 |
| **凭证暴露** | API Keys 留在代码中 | 账户被盗用 |
| **MCP 过度授权** | 工具权限过大 | 权限滥用 |
| **数据流污染** | 用户输入未过滤进入命令 | 命令注入 |

### 1.2 传统安全工具的盲区

通用 SAST 工具（如 SonarQube、Semgrep）无法检测：
- Tool Functions 中的不安全模式
- MCP 配置中的过度授权
- Agent 特有的 Prompt 注入向量

---

## 二、Agent Audit 体系

### 2.1 核心问题

> "部署前应该检查什么？——模型、工具代码、还是部署配置？"

**答案**：三者都需要检查

### 2.2 检测维度

| 维度 | 检测内容 | 示例 |
|------|---------|------|
| **数据流分析** | 用户输入传播路径 | 拼接命令注入检测 |
| **凭证检测** | 硬编码密钥和 Token | API Keys 暴露 |
| **配置解析** | MCP 配置文件审计 | 过度授权 |
| **权限风险** | 工具调用权限评估 | 不必要的全读写 |

---

## 三、漏洞分类 (OWASP Agentic Top 10 对齐)

### 3.1 规则体系

| 类别 | 规则 ID | 说明 |
|------|---------|------|
| **Prompt Injection** | AGENT-010 | System Prompt 注入向量 |
| **Sensitive Data Exposure** | AGENT-031 | MCP 敏感环境变量暴露 |
| **Tool Harmfulness** | AGENT-001 | 命令注入 |
| **Unbounded Consumption** | - | 速率限制缺失 |
| **Overprivileged Tool** | - | MCP 工具过度授权 |
| **MCP Misconfiguration** | - | MCP 服务器配置错误 |

### 3.2 漏洞级别

| 级别 | 置信度 | 处置方式 |
|------|--------|----------|
| **BLOCK** | ≥ 90% | 立即阻止合并 |
| **WARN** | 70-89% | 警告，需人工审查 |
| **INFO** | < 70% | 信息性提示 |

---

## 四、检测规则详解

### 4.1 命令注入 (AGENT-001)

```python
# 不安全模式
command = f"ls {user_input}"  # 用户输入直接拼接
subprocess.run(command, shell=True)
```

```yaml
检测规则:
  pattern: "shell=True.*user_input"
  修复建议: "使用参数化执行，避免 shell=True"
```

### 4.2 SQL 注入 (AGENT-041)

```python
# 不安全模式
query = f"SELECT * FROM users WHERE name = '{user_input}'"
cursor.execute(query)
```

### 4.3 凭证暴露 (AGENT-031)

```json
// MCP 配置中的敏感信息
{
  "env": {
    "API_KEY": "sk-proj-xxxxx"  // 真实密钥残留
  }
}
```

### 4.4 MCP 过度授权

```json
// 过度宽松的 MCP 配置
{
  "servers": [{
    "name": "filesystem",
    "permissions": ["read_write_all"]  // 不必要的全权限
  }]
}
```

---

## 五、扫描工具集成（To-Be 为主）

### 5.1 快速开始

```bash
# 安装
pip install agent-audit

# 扫描项目
agent-audit scan ./your-agent-project

# 仅显示高危漏洞
agent-audit scan . --severity high

# CI 集成
agent-audit scan . --fail-on high
```

> 说明：以上属于 To-Be 的 CI/部署前扫描集成示例，当前仓库运行时默认实现以 `SecurityScanHook`（审批前扫描）为主。

---

## 证据索引（Evidence Index｜抽样）

- 默认 hook 注册与 pre_approval_check 扫描：`core/harness/infrastructure/hooks/hook_manager.py`
- SecurityScanHook 规则实现：`core/harness/infrastructure/hooks/builtin.py`
- 扫描配置项与审计事件写入：`core/harness/infrastructure/hooks/hook_manager.py`
- 单测：`core/tests/unit/test_harness/test_hooks/test_security_scan_config.py`

### 5.2 CI/CD 集成示例

```yaml
# GitHub Actions
- name: Agent Security Scan
  run: |
    pip install agent-audit
    agent-audit scan . --fail-on high --format sarif --output agent-audit.sarif
```

### 5.3 输出格式

| 格式 | 用途 |
|------|------|
| Terminal | 本地开发查看 |
| JSON | CI/CD 集成 |
| SARIF | GitHub Security 导入 |

---

## 六、安全设计模式

### 6.1 五层防御体系

```
┌─────────────────────────────────────────┐
│         Prompt-Level Guardrails        │
│         (System Prompt 安全规则)          │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│       Schema-Level Tool Restrictions    │
│       (Tool Schema 权限过滤)            │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│         Runtime Approval System         │
│         (运行时审批三级机制)             │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│          Tool-Level Validation          │
│          (工具级实时验证)                │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│            Lifecycle Hooks              │
│            (自定义安全钩子)              │
└─────────────────────────────────────────┘
```

### 6.2 审批级别

| 级别 | 风险 | 审批方式 |
|------|------|----------|
| **Auto** | 低风险 | 自动通过 |
| **Semi-Auto** | 中风险 | 安全检查后自动通过 |
| **Manual** | 高风险 | 必须人工确认 |

### 6.3 危险命令黑名单

```yaml
# 永远不允许的记忆命令
blocked_commands:
  - "rm -rf /"
  - "rm -rf *"
  - "sudo"
  - "npm publish"
  - "git push --force"
  - "DROP TABLE"
```

---

## 设计补全（Round2）：运行时治理闭环（Hook/审批/合约/范围）

> 背景：安全文档不仅要描述“有哪些 HookPhase”，还必须定义它们在执行主路径中的触发点、是否可阻断、以及验收方式，否则属于“承诺但不可验证”。

### 1) 必触发 HookPhase（最低集）

| HookPhase | 触发位置（建议） | 是否可阻断 | 说明 |
|---|---|---|---|
| SESSION_START / SESSION_END | BaseLoop.run() 开始/结束 | 否 | 会话级追踪与审计边界 |
| PRE_APPROVAL_CHECK / POST_APPROVAL_CHECK | PRE_TOOL_USE 之前/之后 | 是 | HITL/审批策略的统一入口 |
| PRE_CONTRACT_CHECK / POST_CONTRACT_CHECK | 每轮 step 前后 | 是 | Sprint Contract/范围合约校验 |
| SCOPE_REVIEW | 合约失败或超范围时触发 | 是 | 触发降级/请求确认/停止 |
| STOP | 达到停止条件（max_steps、异常、循环） | 是 | 强制最终验证/审计封存 |

### 2) Hook 输出契约（阻断语义）

建议 Hook 的执行结果具备统一结构：
- `allow: bool`（是否允许继续）
- `action: Optional[str]`（deny/pause/compact/require_manual 等）
- `reason: str`（阻断原因/建议）
- `metadata: dict`（审计证据）

并规定：
- 一旦某 Hook 返回 `allow=False`，Loop 必须立即停止并返回可解释错误（同时触发 STOP/SESSION_END）。

### 3) 默认启用策略（最小安全基线）

默认启用（建议）：
- TokenLimitHook（资源耗尽保护）
- SecurityScanHook（基本危险模式扫描）
- ApprovalManager（对高风险工具触发人工审批）

默认关闭（需显式配置开启）：
- 深度静态扫描、外部 agent-audit 集成（取决于 CI 环境与依赖）

### 3.1) 安全扫描的可配置范围（实现落地）

默认的 `pre_approval_check` 会对工具输入进行敏感信息扫描，并支持通过环境变量调整“扫描哪些工具”：

- `AIPLAT_SECURITY_SCAN_TOOLS`：默认扫描工具集合（逗号分隔，默认 `write,edit`）
- `AIPLAT_SECURITY_SCAN_TOOL_ALLOWLIST`：扫描白名单（非空时仅扫描白名单内工具）
- `AIPLAT_SECURITY_SCAN_TOOL_DENYLIST`：扫描黑名单（从默认/白名单中排除）

同时会在执行上下文中追加审计事件：
- `state.context.audit_events[]`：记录 `security_scan` 事件（是否扫描、是否阻断、findings）

### 4) 验收标准（必须可自动化）

最小验收用例（单测/集成测试）：
1. 触发一次工具调用：必须出现 PRE_APPROVAL_CHECK → PRE_TOOL_USE → POST_TOOL_USE → POST_APPROVAL_CHECK 的 trace（或事件记录）
2. 合约失败（例如 scope 超出）：必须触发 SCOPE_REVIEW 并阻断执行
3. 达到 max_steps：必须触发 STOP 并返回明确的停止原因


---

## 七、相关文档

- [Agent 设计模式](../framework/patterns.md) - 6种核心模式
- [Skill 生命周期](../skills/lifecycle.md) - Skill 进化机制
- [Context 管理](./context.md) - 上下文与记忆

---

## 八、参考资料

- [Agent Audit](https://github.com/HeadyZhang/agent-audit) - 安全扫描工具
- [OWASP Agentic Top 10](https://genai.owasp.org/) - Agent 安全标准

---

*最后更新: 2026-04-14*
