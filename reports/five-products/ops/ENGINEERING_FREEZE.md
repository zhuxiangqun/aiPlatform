# Engineering freeze（本地工程轨）

- frozen_at: `2026-11-01`（初冻）
- **re_frozen_at**: `2026-11-01`（D3/E2E 关闭 + D2++ SOC + ADR v2 文档后）
- scope: five-products **local** packaging / D1–D3 local / Option B / E2E local
- `staging_ready`: **false**
- hard gates: **all false**（cutover / process_split / d3_production）

## Frozen means

本地工程增量已闭合（安装面、D2 pack、D3 本地验收、跨能力 E2E、compat/security、perf、packaging）。  
**本地五产品工程轨无必须任务；EVAL_V1 仍为显式解冻；DIAGNOSIS C1/C2 已出口 PASS。**  
再改须有明确缺陷、**已列 Still open**、复审驱动、或**显式解冻新范围**（C3 / EVAL G2b）；禁止用本地证据推动 authorize。  

### 解冻史

| 时点 | 动作 |
|------|------|
| 初冻 | D1/D2 / packaging / Option B 收口 |
| [`ENGINEERING_UNFREEZE_D3_E2E.md`](./ENGINEERING_UNFREEZE_D3_E2E.md) | 解冻 D3 本地验收 + 跨能力 E2E |
| **本再冻结** | 上述两项已 PASS；Pi D2++ SOC schema 硬核；Field compose ADR → **v2 草案** |
| [`EVAL_V1`](./ENGINEERING_UNFREEZE_EVAL_V1.md) | 解冻评测 **E0–E5**（唯一 API/准确性/gate）；A3/生产仍冻 |
| [`EVAL_V1 UI preview`](./ENGINEERING_UNFREEZE_EVAL_V1_UI_PREVIEW.md) | G2a locked 后解冻 `/eval` **local preview**（accuracy 仍禁） |
| [`DIAGNOSIS_V1 C0`](./ENGINEERING_UNFREEZE_DIAGNOSIS_V1.md) | 解冻诊断 **C0**（产品定义/seed case/设计）；C1 代码另批；A3/生产冻 |
| [`DIAGNOSIS_V1 C1`](./ENGINEERING_UNFREEZE_DIAGNOSIS_C1.md) | 解冻诊断 **C1**（D1c MVP）；无自动修复；A3/生产冻 |
| [`DIAGNOSIS_V1 C1 closeout`](./DIAGNOSIS_V1_C1_CLOSEOUT.md) | **C1 PASS**（#513/#514）；盲测 fixture 出口 |
| [`DIAGNOSIS_V1 C2`](./ENGINEERING_UNFREEZE_DIAGNOSIS_C2.md) | 解冻诊断 **C2**（Eval/Ontology 加深 + 置信度/unknown·stale；无自动修复）；G2b 仍冻 |
| [`DIAGNOSIS_V1 C2 closeout`](./DIAGNOSIS_V1_C2_CLOSEOUT.md) | **C2 PASS**（#516）；report.v1；保持 A0；下一决策 C3 或 EVAL G2b |

- ❌ **仍不解冻**：staging_ready / production_signed / 任何 authorize 成功 / accuracy 宣称 / 自动修复 / A3 / EVAL G2b  
- 计划同步：工程方案 **V2.2** + [`eval-v1-charter.md`](../../../docs/architecture/plans/eval-v1-charter.md) + [`diagnosis-v1-charter.md`](../../../docs/architecture/plans/diagnosis-v1-charter.md)

### Active unfreeze

| 范围 | 文档 | 允许 | 禁止 |
|---|---|---|---|
| EVAL_V1 | [`ENGINEERING_UNFREEZE_EVAL_V1.md`](./ENGINEERING_UNFREEZE_EVAL_V1.md) | E0–E5 + G2a local gate | A3 / staging / authorize / accuracy |
| EVAL_V1 UI preview | [`ENGINEERING_UNFREEZE_EVAL_V1_UI_PREVIEW.md`](./ENGINEERING_UNFREEZE_EVAL_V1_UI_PREVIEW.md) | `/eval` local preview | 完整 E6 / accuracy / 外部 gate |
| DIAGNOSIS_V1 C1 | [`ENGINEERING_UNFREEZE_DIAGNOSIS_C1.md`](./ENGINEERING_UNFREEZE_DIAGNOSIS_C1.md) | **Closed PASS** — 见 [`DIAGNOSIS_V1_C1_CLOSEOUT.md`](./DIAGNOSIS_V1_C1_CLOSEOUT.md) | 自动修复 / A3 / staging / authorize |
| DIAGNOSIS_V1 C2 | [`ENGINEERING_UNFREEZE_DIAGNOSIS_C2.md`](./ENGINEERING_UNFREEZE_DIAGNOSIS_C2.md) | **Closed PASS** — 见 [`DIAGNOSIS_V1_C2_CLOSEOUT.md`](./DIAGNOSIS_V1_C2_CLOSEOUT.md) | 自动修复 / A3 / staging / authorize / G2b accuracy / 静默开 C3 |

## Verify

```bash
bash scripts/ops_engineering_freeze_check.sh
bash scripts/five_products_gate.sh   # 需本机 listen（非沙箱）
```

## Still open（非本 freeze）

| 项 | 说明 |
|----|------|
| 真实预发 | 11-08/15/22 → continue_defer；复审改为 **事件驱动** [`STAGING_REVIEW_EVENT_DRIVEN.md`](./STAGING_REVIEW_EVENT_DRIVEN.md)；11-29 **cancelled** |
| live → sign → authorize | [`OPS_HANDOFF.md`](../OPS_HANDOFF.md) |
| Field compose 长驻 | 草案 **v2** → **继续 Draft**（[`ADR-DRAFT-fde-field-compose.md`](../ADR-DRAFT-fde-field-compose.md) · 不实施） |
| D2++ deeper SOC | ✅ 本地 schema 硬核已闭合；真实 SIEM/webhook 仍须 staging |
| 日历复审 | **停止空转**；有主机再审 |

## Evidence index

见 [`ENGINEERING_LOCAL_CLOSEOUT.md`](./ENGINEERING_LOCAL_CLOSEOUT.md) · [`G0_CLOSEOUT.md`](../G0_CLOSEOUT.md) · [`OPTION_B_LOCAL_VM.md`](./OPTION_B_LOCAL_VM.md) · [`OPTION_B_LAST_RUN.md`](./OPTION_B_LAST_RUN.md)
