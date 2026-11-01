# Engineering freeze（本地工程轨）

- frozen_at: `2026-11-01`
- scope: five-products **local** packaging / D1–D2 packs / Option B
- `staging_ready`: **false**
- hard gates: **all false**（cutover / process_split / d3_production）

## Frozen means

本地工程增量（安装面、D2 pack、compat/security、perf baseline、packaging surface）已闭合。  
再改须有明确缺陷、**已列 Still open**、或复审驱动；禁止用本地证据推动 authorize。  
**未**解冻：D3 本地验收 harness（除 Pi 已有）/ 跨能力 E2E / 计划 V2.2（需显式决策）。

## Verify

```bash
bash scripts/ops_engineering_freeze_check.sh
```

## Still open（非本 freeze）

| 项 | 说明 |
|----|------|
| 真实预发 | 11-08 → continue_defer；下次 [`STAGING_REVIEW_2026-11-15.md`](./STAGING_REVIEW_2026-11-15.md) · 供给包 [`STAGING_PROVISIONING.md`](./STAGING_PROVISIONING.md) |
| live → sign → authorize | [`OPS_HANDOFF.md`](../OPS_HANDOFF.md) |
| Field compose 长驻 | 草案 [`ADR-DRAFT-fde-field-compose.md`](../ADR-DRAFT-fde-field-compose.md)（未 Accepted） |
| D2++ deeper SOC | [`packages/aiplat-pi-runtime/docs/D2_PLUS_SOC.md`](../../packages/aiplat-pi-runtime/docs/D2_PLUS_SOC.md) · `d2_soc_deeper_check.sh` |

## Evidence index

见 [`ENGINEERING_LOCAL_CLOSEOUT.md`](./ENGINEERING_LOCAL_CLOSEOUT.md) · [`LOCAL_DEFER.md`](./LOCAL_DEFER.md) · [`OPTION_B_LOCAL_VM.md`](./OPTION_B_LOCAL_VM.md)
