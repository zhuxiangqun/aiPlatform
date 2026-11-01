# Engineering unfreeze — EVAL_V1（评测准确性 + 唯一入口 + gate）

- **decided_at**: `2026-11-01`
- **status**: **Active**（仅 E0–E5）
- **charter**: [`eval-v1-charter.md`](../../../docs/architecture/plans/eval-v1-charter.md)
- **freeze**: [`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md)
- **owner**: evaluation（local engineering）
- **production**: 仍冻结（`staging_ready=false` / `process_split=false` / `cutover=false` / `d3_production=false`）

## 解冻范围

| 允许（E0–E5） | 禁止 |
|---|---|
| E0 charter / 决策 / 指标 | UI `/eval`（G2a 后 preview 另批） |
| E1 canonical API `/api/platform/apps/eval` + shim | A3 进程/DB 拆分 |
| E2 数据模型 / store | staging / production_signed |
| E3 gold set：≥15 启动，30 锁 v0；单人复核 | 任何 `*_authorize` 成功路径 |
| E4 judge 校准 / 偏差 / k=3 | 改 checklist 🟨→✅ |
| E5 eval gate（PR/nightly/release） | 用 local 证据推动 authorize |

**一句话**：只解冻“评测准确性 + 唯一入口 + gate”，不解冻“UI/A3/生产”。

## 允许的代码面

- `aiPlat-platform/apps/eval/api/`（canonical API）
- `aiPlat-core/core/apps/eval/service/`（业务逻辑）
- `aiPlat-core/core/harness/evaluation/`（仅通用评分/执行）
- `packages/aiplat-evaluation/contracts/`（schema/协议）
- `aiPlat-platform/registry/apps.yaml`（如需注册/路由）
- 对应测试/文档

**不允许**：`aiPlat-management` UI 页面（G2a 后 preview 另批）；`packages/aiplat-evaluation` 独立进程入口（A3）。

## 退出条件

| 结果 | 动作 |
|---|---|
| **G2a**（30 条 + 单人复核） | 可接 local gate / UI preview；**不宣称 accuracy** |
| **G2b**（100 条 + 第二标注者 + κ） | 才可宣称 accuracy / 外部 gate |
| 30 条未满 | 不锁 v0、不做 G2/gate 宣称；E1 可继续 |
| 预算/范围超限 | 缩小 gold set；不降标准 |

**D5 accepted**：v0 由你一人复核；不报 κ；只做 engineering calibration；第二标注者仅在 v1 需要。  
**E3 启动**：≥15 条可跑 + 来源清单；满 30 锁 v0；<30 不挡 E1，只挡 G2/gate 宣称。

## 验证

```bash
python3 reports/five-products/modules/evaluation/contracts/validate_sample.py
python3 -m pytest aiPlat-core/core/tests/unit/test_eval_protocol_v0.py -q
bash scripts/ops_engineering_freeze_check.sh
python3 scripts/check_five_products_status_sync.py
```

## 变更控制

- 范围变化 → 新 unfreeze 文档，不静默扩大。
- 任何 staging/authorize 动作 → 不在本解冻内，按 `STAGING_READY.md` / `OPS_HANDOFF.md`。
- 完成/中止 → 在本文件追加 Outcome，并更新 `ENGINEERING_FREEZE.md` 解冻史。

## Outcome

- **E0**：charter + unfreeze 已合入（`cb6d4b18`）。
- **E1**（2026-11-01）：canonical `/api/platform/apps/eval` dual-mount + `EvalLegacyDeprecationMiddleware`；core `/kb-eval` shim；inventory [`EVAL_V1_E1_INVENTORY.md`](./EVAL_V1_E1_INVENTORY.md)；契约测试 `test_eval_v1_e1_canonical.py`。
- G2a/G2b accuracy claim：`_pending_`
