---
doc_type: Index
---

# Wave 1 Ops 证据目录

> 工程可自动归档项 vs Ops 真人项。≠ `security_certification`

| ID | 项 | 证据 | 状态 |
|---|---|---|---|
| W1-0 | attack-sim 不可达必须非 0 | [`attack-sim-unreachable-127.0.0.1-9.json`](./attack-sim-unreachable-127.0.0.1-9.json) | **工程已归档** |
| W1-1 | staging fail-closed 故障注入 | 填 [`staging-fail-closed-card.md`](./staging-fail-closed-card.md) | Ops |
| W1-2 | 生产 profile 只读审计 | 填 [`prod-profile-audit-card.md`](./prod-profile-audit-card.md)；干跑矩阵见 [`profile-matrix-dry-run.json`](./profile-matrix-dry-run.json)（≠生产切流） | Ops + 工程干跑已归档 |
| W1-3 | IR `contacts.local.yaml` | `.gitignore` 已忽略 `*.local.yaml`；落盘后 **chmod 0600**；CI 只用 example；真人不上报/入库 | 工程约束已落地 |
| W1-4 | staging 可达 attack-sim | 填 [`staging-attack-sim-card.md`](./staging-attack-sim-card.md)；须含 pass/fail/unknown | Ops |
| W1-5 | 发布门 | `scripts/security_publish_gates.py --mode ledger\|release\|claim`；CI 默认 ledger | **工程已接线** |

```bash
python3 scripts/security_wave_ops.py --wave1
python3 scripts/security_ops_audit.py --profile-matrix
python3 scripts/security_publish_gates.py --mode release   # ordinary publish
python3 scripts/security_publish_gates.py --mode claim     # external claim only
```
