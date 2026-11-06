# Engineering unfreeze — EVAL_V1 `/eval` UI preview（G2a 后）

- **decided_at**: `2026-11-01`
- **status**: **Active**（仅 local preview）
- **parent**: [`ENGINEERING_UNFREEZE_EVAL_V1.md`](./ENGINEERING_UNFREEZE_EVAL_V1.md)
- **freeze**: [`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md)
- **charter**: [`eval-v1-charter.md`](../../../docs/architecture/plans/eval-v1-charter.md) §8 / D8
- **trigger**: G2a human lock（≥30 solo adjudicated → `lock-v0` → local `gate_claim`）

## 解冻范围

| 允许 | 禁止 |
|---|---|
| 管理端 `/eval` **preview**（G2a 状态、诚实横幅、链到 canonical API） | 宣称 accuracy / κ / 外部 gate |
| 旧页软链到 `/eval`（不强制全量 redirect） | staging / authorize / A3 进程拆分 |
| 只读展示 `g2a-status` / 进度 | 把 local `gate_claim` 当成生产签核 |
| 标注队列只读预览（写操作仍走 API / 对话流程） | 完整 E6 评测中心（多 tab 全量）冒充已交付 |

**一句话**：G2a 锁后可开 `/eval` local preview；**accuracy 仍禁**；E6 全量 UI 另批。

## 允许的代码面

- `aiPlat-management/frontend/src/pages/Eval/`（preview 页）
- `App.tsx` 路由 `/eval` + `pageManifest` 菜单项
- 对应 freeze check / STATUS / charter 同步

## 退出条件

| 结果 | 动作 |
|---|---|
| Preview 可用 + 诚实横幅可见 | STATUS 标注 G2a locked + UI preview unfrozen |
| G2b（100 + 第二标注 + κ） | 才可 accuracy / 外部 gate 文案 |
| 范围扩大到全量 E6 | 新 unfreeze 文档，不静默扩大 |

## Outcome

- **2026-11-01**：G2a 本机 `eval-v1` — 30 条 solo（用户授权采信 AI preannotate）→ `v0_locked` → `gate_claim=true`（`rpt_c12dfe23ba70`）；`accuracy_claim=false`；κ=null。
- **2026-11-01**：本文件生效；`/eval` preview 页落地。
