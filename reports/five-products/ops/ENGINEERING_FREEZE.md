# Engineering freeze（本地工程轨）

- frozen_at: `2026-11-01`（初冻）
- **re_frozen_at**: `2026-11-01`（D3/E2E 关闭 + D2++ SOC + ADR v2 文档后）
- scope: five-products **local** packaging / D1–D3 local / Option B / E2E local
- `staging_ready`: **false**
- hard gates: **all false**（cutover / process_split / d3_production）

## Frozen means

本地工程增量已闭合（安装面、D2 pack、D3 本地验收、跨能力 E2E、compat/security、perf、packaging）。  
再改须有明确缺陷、**已列 Still open**、或复审驱动；禁止用本地证据推动 authorize。  

### 解冻史

| 时点 | 动作 |
|------|------|
| 初冻 | D1/D2 / packaging / Option B 收口 |
| [`ENGINEERING_UNFREEZE_D3_E2E.md`](./ENGINEERING_UNFREEZE_D3_E2E.md) | 解冻 D3 本地验收 + 跨能力 E2E |
| **本再冻结** | 上述两项已 PASS；Pi D2++ SOC schema 硬核；Field compose ADR → **v2 草案** |

- ❌ **仍不解冻**：staging_ready / production_signed / 任何 authorize 成功  
- 计划同步：工程方案 **V2.2**

## Verify

```bash
bash scripts/ops_engineering_freeze_check.sh
bash scripts/five_products_gate.sh   # 需本机 listen（非沙箱）
```

## Still open（非本 freeze）

| 项 | 说明 |
|----|------|
| 真实预发 | 11-08/11-15 → **continue_defer**；下次 [`STAGING_REVIEW_2026-11-22.md`](./STAGING_REVIEW_2026-11-22.md) · 供给包备查 [`STAGING_PROVISIONING.md`](./STAGING_PROVISIONING.md)（不实施直至有主机） |
| live → sign → authorize | [`OPS_HANDOFF.md`](../OPS_HANDOFF.md) |
| Field compose 长驻 | 草案 **v2** → **继续 Draft**（[`ADR-DRAFT-fde-field-compose.md`](../ADR-DRAFT-fde-field-compose.md) · 不实施） |
| D2++ deeper SOC | ✅ 本地 schema 硬核已闭合；真实 SIEM/webhook 仍须 staging |
| 11-22 复审预填 | [`STAGING_REVIEW_2026-11-22.md`](./STAGING_REVIEW_2026-11-22.md)（无主机 → 预期续 defer） |

## Evidence index

见 [`ENGINEERING_LOCAL_CLOSEOUT.md`](./ENGINEERING_LOCAL_CLOSEOUT.md) · [`G0_CLOSEOUT.md`](../G0_CLOSEOUT.md) · [`OPTION_B_LOCAL_VM.md`](./OPTION_B_LOCAL_VM.md) · [`OPTION_B_LAST_RUN.md`](./OPTION_B_LAST_RUN.md)
