# Agent 安全审计

> 基于 Agent Audit 实践的部署前安全扫描机制

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

## 五、扫描工具集成

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