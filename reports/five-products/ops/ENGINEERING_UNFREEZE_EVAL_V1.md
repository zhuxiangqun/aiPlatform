# Engineering unfreeze — EVAL_V1（评测准确性 + 唯一入口 + gate）

- **decided_at**: `2026-11-01`
- **status**: **Active**（E0–E5 + G2a locked；UI preview 见子解冻）
- **charter**: [`eval-v1-charter.md`](../../../docs/architecture/plans/eval-v1-charter.md)
- **freeze**: [`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md)
- **owner**: evaluation（local engineering）
- **production**: 仍冻结（`staging_ready=false` / `process_split=false` / `cutover=false` / `d3_production=false`）

## 解冻范围

| 允许（E0–E5） | 禁止 |
|---|---|
| E0 charter / 决策 / 指标 | 完整 E6 评测中心（仅 preview，见 UI 子解冻） |
| E1 canonical API `/api/platform/apps/eval` + shim | A3 进程/DB 拆分 |
| E2 数据模型 / store | staging / production_signed |
| E3 gold set：≥15 启动，30 锁 v0；单人复核 | 任何 `*_authorize` 成功路径 |
| E4 judge 校准 / 偏差 / k=3 | 改 checklist 🟨→✅ |
| E5 eval gate（PR/nightly/release） | 用 local 证据推动 authorize |

**一句话**：解冻“评测准确性 + 唯一入口 + gate”；G2a 锁后 `/eval` preview 见 [`ENGINEERING_UNFREEZE_EVAL_V1_UI_PREVIEW.md`](./ENGINEERING_UNFREEZE_EVAL_V1_UI_PREVIEW.md)；A3/生产仍冻。

## 允许的代码面

- `aiPlat-platform/apps/eval/api/`（canonical API）
- `aiPlat-core/core/apps/eval/service/`（业务逻辑）
- `aiPlat-core/core/harness/evaluation/`（仅通用评分/执行）
- `packages/aiplat-evaluation/contracts/`（schema/协议）
- `aiPlat-platform/registry/apps.yaml`（如需注册/路由）
- 对应测试/文档

**不允许**：完整 E6 评测中心冒充交付（preview 另见 [`ENGINEERING_UNFREEZE_EVAL_V1_UI_PREVIEW.md`](./ENGINEERING_UNFREEZE_EVAL_V1_UI_PREVIEW.md)）；`packages/aiplat-evaluation` 独立进程入口（A3）。

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
- **E2**（2026-11-01）：`EvalStore` SQLite（charter §5.3）+ `eval_store.schema.json` + `POST …/store/migrate/code-review-gold`；测试 `test_eval_v1_e2_store.py`。
- **E3**（2026-11-01）：`bootstrap_e3_gold` ≥15 可跑 + [`EVAL_V1_E3_GOLD_SOURCES.md`](./EVAL_V1_E3_GOLD_SOURCES.md) + solo 复核队列；测试 `test_eval_v1_e3_gold.py`（v0 锁见下方 G2a human lock）。
- **E4**（2026-11-01）：`judge.deterministic.code_review_gold.v1` + k=3/ECE/bias 校准报告（`eval.calibration.v0`）；`POST …/store/calibrate-e4`；**accuracy_claim=false**；测试 `test_eval_v1_e4_judge.py`。
- **E5**（2026-11-01）：failure taxonomy + local gate（pr/nightly/release）；`POST …/store/gate-e5` + schema `eval_gate.schema.json`；**gate_claim=false / accuracy_claim=false**（未达 G2a）；测试 `test_eval_v1_e5_gate.py`。
- **G2a machinery**（2026-11-01）：`g2a.py` + `POST …/store/{review-queue,labels/*/adjudicate,lock-v0,gate-g2a}`；测试 `test_eval_v1_g2a.py`。
- **G2a human lock**（2026-11-01）：本机 tenant `eval-v1` — 30 条 solo（用户授权采信 AI preannotate）→ `lock-v0` → `gate-g2a`（`gate_claim=true`，`rpt_c12dfe23ba70`）；**accuracy_claim=false**；κ=null。
- **UI preview unfreeze**（2026-11-01）：[`ENGINEERING_UNFREEZE_EVAL_V1_UI_PREVIEW.md`](./ENGINEERING_UNFREEZE_EVAL_V1_UI_PREVIEW.md) + `/eval` preview 页。
- **E6**（2026-11-01）：**PASS** — [`EVAL_V1_E6_CLOSEOUT.md`](./EVAL_V1_E6_CLOSEOUT.md)（评测中心 UI；accuracy 仍禁）。
- G2b accuracy / 外部 gate：`_pending_`
