# Wave 3 — live 文本族 / 跨租户 / judge 标定

> 工程：证据卡 schema + 校验器。Ops：真跑 staging / 标定。≠ certification

```bash
python3 scripts/security_evidence_card.py --validate \
  reports/security/evidence/wave3/text-family-live.card.json
python3 scripts/security_wave_ops.py --wave3
```

| 卡 | 用途 |
|---|---|
| [`text-family-live.card.json`](./text-family-live.card.json) | P1-1 文本族 Subject 锁定 live |
| [`staging-tenant-blackbox.card.json`](./staging-tenant-blackbox.card.json) | staging 跨租户黑盒 |
| [`judge-calibration-starter.md`](./judge-calibration-starter.md) | judge 双盲标定起步 |
