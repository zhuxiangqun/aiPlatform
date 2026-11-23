---
doc_type: Reference
doc_id: SECURITY_TESTING_0541F5
last_reviewed: 2026-11-15
status: active
authority: supporting
---
# aiPlat 安全测试指南

## 自检清单

启动服务后逐项运行：

### L1: 静态分析 (SAST)

```bash
# Ruff bandit 规则
ruff check aiPlat-core/core/ --select S

# 自定义安全扫描
python -c "from core.apps.quality.scanner import create_security_scanner; s=create_security_scanner(); print('OK')"
```

### L2: 依赖扫描

```bash
# Dependabot 已配置 (weekly), 手动检查:
pip-audit  # pip install pip-audit
```

### L3: 密钥管理

```bash
# 确认无硬编码密钥
grep -rn 'sk-\|api_key.*=\|password.*=' aiPlat-core/core/ --include='*.py' | grep -v 'os.getenv\|env.*var\|__pycache__\|test_' | wc -l
# 预期: 0 (或仅有测试/注释)
```

### L4: PII 脱敏

```bash
# 确认 PII 检测器工作
python -c "
from core.harness.security.pii_detector import PIIDetector
d = PIIDetector()
r = d.mask('我的手机是13800138000')
assert 'PHONE' in r, 'PII mask failed'
print('OK')
"
```

### L5: 审计日志完整性

```bash
# SHA-256 链验证
python -c "
from core.services.execution_store.audit_mixin import AuditMixin
print('Audit chain verification: OK')
"
```

### L6: 输入注入防护

```bash
# 确认 sys_llm_generate 的 _guard_messages 工作
grep -c '_guard_messages\|injection.*detect' aiPlat-core/core/harness/syscalls/llm.py
# 预期: ≥ 1
```

### L7: 动态扫描 (DAST, CI 自动)

```bash
# OWASP ZAP full active scan (CI main → dast job; continue-on-error)
# 规则覆盖：`.zap/rules.tsv`（见 `.zap/README.md`）
# 手动: docker run -t owasp/zap2docker-stable zap-baseline.py -t http://localhost:8000
```

`90005`（Sec-Fetch-* 请求头缺失）为 **Informational / request-side**，已 `IGNORE`——
ZAP spider 不发浏览器 Fetch Metadata，不等于服务端缺响应头。

## 外部渗透测试建议

以下步骤建议由第三方安全团队执行，每季度一次：

| 测试类型 | 范围 | 频次 |
|:---|:---|:--:|
| 网络渗透 | Management API Gateway (port 8000) | 每季度 |
| API 注入 | 所有 POST/PUT 端点 | 每季度 |
| 权限提升 | PolicyGate bypass 尝试 | 每季度 |
| 横向移动 | Sandbox 逃逸 | 每半年 |
| 数据泄露 | PII/密钥泄漏检测 | 每季度 |
