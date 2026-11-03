# Compliance / PII v0（最小集）

> Honesty: **`accuracy_claim=false`** · **`certified=false`** · ≠ GDPR/SOC 认证 · ≠ G2b accuracy

## What

| Item | Path |
|------|------|
| Tasks (8) | [`compliance_pii_tasks.v0.json`](./compliance_pii_tasks.v0.json) |
| Rules | `app/scoring/compliance_pii.py`（email / phone / SSN / 身份证 / card 启发式） |
| Schema | `contracts/schemas/eval_compliance_pii.schema.json` |
| Report | `scripts/compliance_pii_v0_report.py` |
| Gate | `scripts/compliance_pii_v0_gate.sh` |

## Gate

```bash
bash packages/aiplat-evaluation/scripts/compliance_pii_v0_gate.sh
# pass_rate ≥ 0.95; accuracy_claim=false; certified=false
```

## Composite role

`pii_clean` / `pii_leak` 在 package engineering composite 中为 **report-only**（不静默改历史权重）。见 [`P1_CANONICAL.md`](./P1_CANONICAL.md)。

## Not claimed

≠ 隐私合规认证 · ≠ 生产 DLP · ≠ authorize · 启发式假阴性可接受；本切片只满足 SCORE_SCOPE 功能维「schema + 规则/报告 + 测试」
