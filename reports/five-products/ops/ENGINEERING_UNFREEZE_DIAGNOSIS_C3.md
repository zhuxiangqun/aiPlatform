# Engineering unfreeze — DIAGNOSIS_V1 C3（D2/D3 本地收口）

- **decided_at**: `2026-11-01`
- **status**: **Closed — C3 PASS**（[`DIAGNOSIS_V1_C3_CLOSEOUT.md`](./DIAGNOSIS_V1_C3_CLOSEOUT.md)）
- **C2**: [`ENGINEERING_UNFREEZE_DIAGNOSIS_C2.md`](./ENGINEERING_UNFREEZE_DIAGNOSIS_C2.md) · closeout [`DIAGNOSIS_V1_C2_CLOSEOUT.md`](./DIAGNOSIS_V1_C2_CLOSEOUT.md) · #516/#517
- **charter**: [`diagnosis-v1-charter.md`](../../../docs/architecture/plans/diagnosis-v1-charter.md) §8 C3
- **freeze**: [`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md)
- **owner**: diagnosis（D1c 之上 D2 cohost ops/security/perf 包）
- **production**: 仍冻结（`staging_ready=false` / `process_split=false` / `cutover=false` / `d3_production=false`）

## 为何选 C3（而非 EVAL G2b）

| 选项 | 阻塞 | 结论 |
|---|---|---|
| **EVAL G2b** | 第二标注者 + κ 未就绪 | 仍暂缓 |
| **DIAGNOSIS C3** | C2 PASS；charter 下一阶段为 D2/D3 本地收口 | **本解冻默认路径** |

## 目标

在 C1/C2 产品能力之上补齐 **D1 Thin + D2 cohost 工程包**（与 ontology/evaluation 同级门禁）：

1. `packages/aiplat-diagnosis`：`d1_*` / `d2_admin_check` / `d2_local_closeout` / `d3_local_acceptance`
2. `security/baseline.yaml` + `docs/{D2_COHOST,SECURITY,PERF_BASELINE}.md` + Chart 骨架（`a3_process_split_authorized=false`）
3. packaging surface 纳入 diagnosis（本地文件门，**不**升 `current_delivery=D2` 为生产宣称）
4. A3 local rehearsal + `a3_split_authorize authorize` **必须 REFUSE**
5. 保持 A0 · `accuracy_claim=false` · 无 remediate · blind fixture 回归

## 允许的代码面

- `packages/aiplat-diagnosis/`（scripts / docs / security / chart / contracts/healthz）
- `scripts/check_five_products_packaging_surface.sh`（+ diagnosis）
- `scripts/check_five_products_perf_baseline.sh`（+ diagnosis contract/doc）
- `core/apps/diagnosis/service/store.py`（healthz 字段与 schema 对齐，最小）
- `STATUS.md` / MODULE / manifest notes / C3 closeout

## 禁止

| 禁止 | 原因 |
|---|---|
| `process_split_authorized=true` / authorize 成功 | 无 live ✅ + ADR Accept |
| staging / `production_signed` / cutover | 生产门仍冻 |
| `POST …/remediate` / `auto_execute=true` | 产品边界 |
| 宣称 accuracy / 外部 gate | 评测权威在 EVAL |
| 静默开 EVAL G2b | 需独立 unfreeze |
| 把 `current_delivery` 写成 D2 生产态 | D2 包 = 工程收口；manifest 保持 D1/cohost |

## C3 出口

| 项 | 门槛 |
|---|---|
| packaging surface | `bash scripts/check_five_products_packaging_surface.sh` 含 diagnosis PASS |
| D2 closeout | `bash packages/aiplat-diagnosis/scripts/d2_local_closeout.sh` PASS |
| split | `a3_split_authorize.sh authorize` REFUSE |
| Autonomy / Delivery | 保持 A0 / D1c；不升 A3 |
| Closeout | `DIAGNOSIS_V1_C3_CLOSEOUT.md` + Outcome |

## 串行规则

- **DIAGNOSIS C3** 独占工程焦点；不并行开 EVAL G2b / C4。
- C3 完成后再评估 EVAL G2b 或 Diagnosis C4（A3）。

## 验证

```bash
test -f reports/five-products/ops/ENGINEERING_UNFREEZE_DIAGNOSIS_C3.md
bash scripts/check_five_products_packaging_surface.sh
bash packages/aiplat-diagnosis/scripts/d2_local_closeout.sh
```
