# Engineering unfreeze — DIAGNOSIS_V1（C0 only）

- **decided_at**: `2026-11-01`
- **status**: **Active — C0 only**
- **charter**: [`diagnosis-v1-charter.md`](../../../docs/architecture/plans/diagnosis-v1-charter.md)
- **freeze**: [`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md)
- **owner**: diagnosis（product design / local engineering）
- **production**: 仍冻结（`staging_ready=false` / `process_split=false` / `cutover=false` / `d3_production=false`）

## 解冻范围（C0）

| 允许 | 禁止 |
|---|---|
| 产品 charter / 边界 / 指标 | 业务代码 / API / UI |
| 证据模型 / schema 设计 | manifest 实际修改（C0 出口再确认） |
| 20–30 个 seed case 清单 + 根因标签 | A3 进程/DB 拆分 |
| `/api/platform/apps/diagnosis` + `/diagnosis` UI 设计稿 | staging / production_signed |
| 只读盘点现有 Diagnostics 端点/页面 | 任何 `*_authorize` 成功路径 |
| manifest/module/apps.yaml 更新**提案** | 用 local 证据推动 authorize |

**一句话**：C0 只做产品定义/证据模型/seed case/设计；C1 才写代码。

## 允许的文档面

- `docs/architecture/plans/diagnosis-v1-charter.md`
- `reports/five-products/ops/ENGINEERING_UNFREEZE_DIAGNOSIS_V1.md`
- seed case / evidence schema / API/UI 设计文档
- 只读盘点记录（不修改代码）

**不允许**：`aiPlat-platform/apps/diagnosis/`、`aiPlat-core/core/apps/diagnosis/`、`aiPlat-management/.../Diagnosis/` 的实际代码/页面；`capabilities.manifest` 实际条目（C0 出口提案）。

## C0 出口条件

- [x] 20–30 个 seed case + 根因标签 → [`DIAGNOSIS_V1_C0_SEED_CASES.md`](./DIAGNOSIS_V1_C0_SEED_CASES.md)（25）
- [x] Evidence schema v0 → [`../modules/diagnosis/contracts/schemas/diagnosis_evidence.schema.json`](../modules/diagnosis/contracts/schemas/diagnosis_evidence.schema.json)
- [x] API/UI 设计稿 → [`DIAGNOSIS_V1_C0_API_UI_DESIGN.md`](./DIAGNOSIS_V1_C0_API_UI_DESIGN.md)
- [x] manifest/module/apps.yaml 更新提案 → [`DIAGNOSIS_V1_C0_MANIFEST_PROPOSAL.md`](./DIAGNOSIS_V1_C0_MANIFEST_PROPOSAL.md) + [`../modules/diagnosis/MODULE.md`](../modules/diagnosis/MODULE.md)
- [ ] 与 EVAL_V1 排期确认（串行，不并行开两条重轨）— **待你确认**
- [ ] 你确认进入 C1。

## C1 启动条件

- C0 出口全部满足；
- 新的 `ENGINEERING_UNFREEZE_DIAGNOSIS_C1`（或本文件扩展）明确允许代码/API/UI；
- 生产门仍冻结。

## 验证

```bash
python3 scripts/check_five_products_status_sync.py
bash scripts/ops_engineering_freeze_check.sh
```

## 变更控制

- 范围变化 → 新 unfreeze 文档，不静默扩大。
- 任何 staging/authorize 动作 → 不在本解冻内。
- 完成/中止 → 在本文件追加 Outcome，并更新 `ENGINEERING_FREEZE.md` 解冻史。

## Outcome

- **2026-11-01**：Charter Accepted for C0；本解冻生效。
- **2026-11-01**：Seed 25 + evidence schema v0 + API/UI 设计 + manifest 提案已落文档；**未改业务代码 / 未改 capabilities.manifest**。
- 待确认：与 EVAL_V1 串行排期 + 是否进入 C1。
