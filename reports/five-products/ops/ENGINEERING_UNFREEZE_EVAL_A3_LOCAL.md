# Engineering unfreeze — EVAL_A3_LOCAL（独立进程/DB 本地验证）

- **decided_at**: `2026-11-02`
- **status**: **Active — A-local only**（A1 landed · A2 store/migrations in flight）
- **plan**: [`eval-a3-independent-service.md`](../../../docs/architecture/plans/eval-a3-independent-service.md)
- **A3 ADR**: [`ADR-EVALUATION-A3.md`](../ADR-EVALUATION-A3.md)（Accepted 有条件）
- **checklist**: [`SPLIT_CHECKLIST.md`](../../../packages/aiplat-evaluation/docs/a3/SPLIT_CHECKLIST.md)
- **freeze**: [`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md)
- **production**: 仍冻结（`process_split_authorized=false` / `staging_ready=false` / 任何 authorize=false）

## 解冻范围（A0–A5）

| 允许 | 禁止 |
|---|---|
| A0 方案/API/DB 设计 | `process_split_authorized=true` |
| A1 独立 FastAPI 入口 `:8010` | staging / production_signed / authorize |
| A2 eval DB/schema/migrations | 生产数据迁移/切流 |
| A3 canonical API 独立宿主 + Central 代理 | A3 生产 Chart/HA 宣称 |
| A4 本地双进程独立性测试 | 新开 EVAL 功能 / accuracy 宣称 |
| A5 回滚/备份/本地收口 | 把 local 标成 staging |

**一句话**：只解冻“本地证明能独立”，不解冻“生产独立”。

## 允许的代码面

- `packages/aiplat-evaluation/app/`（新入口/API/service/store）
- `packages/aiplat-evaluation/migrations/`
- `packages/aiplat-evaluation/scripts/run_local.sh` / `independence_check.sh`
- `aiPlat-platform/apps/eval/api/`（代理/兼容）
- `aiPlat-core/core/apps/eval/service/`（如复用，不得新增 core 私有耦合）
- 对应 tests/docs

**不允许**：`aiPlat-management` 新 UI 功能；`process_split` 开关；A3 chart 生产化。

## 退出条件

| 结果 | 动作 |
|---|---|
| A-local 9 项验收全 PASS | A3 local closeout；不自动进 B |
| Central 停掉 eval 不能读 | A4 失败；不宣称独立 |
| 仍依赖 core 私有 import | 停在 A1/A2；先解耦 |
| 数据对账不一致 | 停切换；回 cohost |
| 范围到 staging/authorize | 停；另开 B 解冻 |

## 验证

```bash
# 独立启动
bash packages/aiplat-evaluation/scripts/run_local.sh
curl -fsS http://127.0.0.1:8010/healthz

# 独立性（Central 停止后）
bash packages/aiplat-evaluation/scripts/independence_check.sh

# 契约/回滚
python3 reports/five-products/modules/evaluation/contracts/validate_sample.py
bash scripts/ops_engineering_freeze_check.sh
```

## 变更控制

- 范围变化 → 新 unfreeze，不静默扩大。
- A-local 完成 ≠ A3 生产授权；B 需要 staging + checklist + signed live。
- 完成/中止 → 追加 Outcome，并更新 `ENGINEERING_FREEZE.md` 解冻史（#521 合并后）。

## Outcome

- `_pending_`（A-local 出口填写）
