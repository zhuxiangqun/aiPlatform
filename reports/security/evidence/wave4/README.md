# Wave 4 — 外部验证入口

> 工程脚手架 + RFP/IR/SBOM 清单。真人渗透/KVM/仪式仍是 Ops。≠ certification

```bash
python3 scripts/security_wave_ops.py --wave4
```

| 资产 | 说明 |
|---|---|
| [`kvm-guest-probe-card.md`](./kvm-guest-probe-card.md) | 真 GuestChannel；covered 仅人审 |
| [`sbom-ceremony-checklist.md`](./sbom-ceremony-checklist.md) | syft/cosign 或 Ed25519 公钥入库 |
| [`ir-tabletop-scorecard.schema.json`](./ir-tabletop-scorecard.schema.json) | IR 桌面演练记分 schema |
| [`../P2-2-external-pentest-rfp.md`](../../P2-2-external-pentest-rfp.md) | 外部渗透 RFP |
| [`../P1-IR-tabletop-drill.md`](../../P1-IR-tabletop-drill.md) | IR 演练手册 |

D03 在外部报告前保持 G（或 O+外部依赖）；`coverage_ok` 可长期 false，**不得**挡普通 `--release-gate` 以外的工程 CI。
