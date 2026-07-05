# aiPlat Security Policy

## Supported Versions

| Version | Supported |
|:---|:--:|
| main (latest) | ✅ Active |
| v0.0.x | ✅ Patches backported |

## Vulnerability Disclosure

Report vulnerabilities to: **security@aiplat.dev** (or GitHub Security Advisory)

Response SLA:

| Severity | Acknowledgement | Fix Target | Disclosure |
|:---|:--:|:--:|:--:|
| **Critical** (CVSS ≥ 9.0) | 4 hours | 24 hours | After fix |
| **High** (CVSS 7.0-8.9) | 24 hours | 7 days | After fix |
| **Medium** (CVSS 4.0-6.9) | 48 hours | 30 days | After fix |
| **Low** (CVSS < 4.0) | 1 week | 90 days | After fix |

## Scanning Cadence

| Scan Type | Tool | Frequency | Owner |
|:---|:---|:---|:---|
| SAST | ruff bandit (S-rules) | Every commit | CI |
| Dependency | dependabot | Weekly (Monday) | CI |
| Secret | SecretsManager | Runtime | Core |
| PII Masking | PIIDetector | Runtime | Core |

## Supply Chain

- All dependencies must come from PyPI (no direct GitHub installs)
- Dependabot PRs auto-merge configured for patch updates
- License compliance checked via `pip-licenses` in CI
- Copyleft licenses (GPL/AGPL) explicitly banned

## Runtime Security

| Feature | Status |
|:---|:--:|
| PII auto-masking | ✅ `PIIDetector.mask()` |
| AES-256-GCM secrets | ✅ `SecretsManager` |
| SHA-256 audit chain | ✅ `audit_mixin.py` |
| Injection protection | ✅ `_guard_messages()` |
| Sandbox Gate | ✅ `SandboxGate` |
| Policy Gate (RBAC) | ✅ `PolicyGate` |
| Approval Gate | ✅ `ApprovalGate` |
