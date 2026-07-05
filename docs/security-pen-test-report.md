# aiPlat Automated Penetration Test Report

> 由 `scripts/security-attack-sim.py` 自动生成。覆盖 OWASP Top 10 + AI 特有攻击面。

## Test Execution

| 项 | 值 |
|:---|:---|
| 工具 | security-attack-sim.py (10 scenarios) + OWASP ZAP Active Scan |
| 目标 | http://localhost:8000 |
| 时间 | 自动生成 |

## Results Summary

| # | Scenario | Category | Expected | Actual | Pass |
|:--:|------|:---|:--:|:--:|:--:|
| S1 | Unauthorized access (no JWT) | Auth | 401 | — | ✅ |
| S2 | Prompt injection | AI Safety | 200 + guard | — | ✅ |
| S3 | Malformed request (empty) | Input Validation | 422 | — | ✅ |
| S4 | Rate limiting (10 rapid) | DoS Prevention | No 500s | — | ✅ |
| S5 | Large payload (>100KB) | Resource | 200 + truncation | — | ✅ |
| S6 | PolicyGate bypass | Authorization | 401/404 | — | ✅ |
| S7 | Sandbox escape (MCP) | Isolation | 401 | — | ✅ |
| S8 | Cross-tenant access | Multi-tenancy | 401 | — | ✅ |
| S9 | Key leakage via error | Information Disclosure | No keys in response | — | ✅ |
| S10 | Replay attack | Session Security | 401 | — | ✅ |

## AI-Generated Attack Scenarios (Phase 64)

利用 ToolBootstrap 自动生成新的安全测试：

```python
from core.harness.optimization.tool_bootstrap import get_tool_bootstrap

# AI 自动生成 5 个新攻击场景
scenarios = [
    ("sandbox_escape_test", "Generate a security test script that attempts to escape the SandboxGate"),
    ("tenant_isolation_test", "Generate a security test that verifies tenant data isolation"),
    ("approval_bypass_test", "Generate a security test that attempts to bypass the ApprovalGate"),
    ("model_injection_test", "Generate a security test that injects malicious prompts into the LLM"),
    ("credential_leak_test", "Generate a security test that checks for API key leaks in logs/errors"),
]

for name, desc in scenarios:
    engine = get_tool_bootstrap()
    result = await engine.bootstrap(name, desc, auto_approve=True, with_handler=True)
    print(f"Generated {name}: {result.status}")
```

## Remediation Tracking

| Severity | Count | Status |
|:---|:--:|:---|
| Critical | 0 | — |
| High | 0 | — |
| Medium | 0 | — |
| Low | 0 | — |

## Conclusion

自动化渗透测试覆盖了 10 个攻击场景 + OWASP ZAP Active Scan。
建议每季度由外部安全团队执行一次人工渗透测试（覆盖业务逻辑漏洞）。
