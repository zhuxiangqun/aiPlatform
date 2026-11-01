# Engineering unfreeze — EVAL_V1 E6 评测中心 UI v1

- **decided_at**: `2026-11-01`
- **status**: **Closed — E6 PASS**（[`EVAL_V1_E6_CLOSEOUT.md`](./EVAL_V1_E6_CLOSEOUT.md)）
- **parent**: [`ENGINEERING_UNFREEZE_EVAL_V1.md`](./ENGINEERING_UNFREEZE_EVAL_V1.md) · preview [`ENGINEERING_UNFREEZE_EVAL_V1_UI_PREVIEW.md`](./ENGINEERING_UNFREEZE_EVAL_V1_UI_PREVIEW.md)
- **freeze**: [`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md)
- **charter**: [`eval-v1-charter.md`](../../../docs/architecture/plans/eval-v1-charter.md) §8 / G3
- **trigger**: G2a locked + `/eval` preview 已落地；DIAGNOSIS C3 PASS（#518）；**G2b 仍阻塞**（第二标注者）

## 为何选 E6（而非 G2b / Diagnosis C4）

| 选项 | 阻塞 | 结论 |
|---|---|---|
| **EVAL G2b** | 100 条 + 第二标注者 + κ | 暂缓 |
| **Diagnosis C4** | A3 ADR Accept + staging / live | 生产门仍冻 |
| **EVAL E6** | G2a 已锁；preview 已开；charter 下一 UI 阶段 | **本解冻默认路径** |

## 目标

把 `/eval` 从 preview 升为 **评测中心 v1**（仍 **不宣称 accuracy**）：

1. Charter §8.1 多 tab：总览 / 评测集 / 复核 / 门禁 / 报告 + 旧能力入口（agents/knowledge/prompts/code-review）
2. 旧页 **软跳转** 到 `/eval?tab=…`（G3）
3. 只读/canonical 走 `/api/platform/apps/eval`；诚实横幅：`accuracy_claim=false` · κ=null · local gate ≠ 外部
4. 菜单文案「评测中心」（去掉 Preview 后缀）

## 允许的代码面

- `aiPlat-management/frontend/src/pages/Eval/`
- `App.tsx` / `pageManifest.ts`（路由与菜单）
- `STATUS.md` / freeze / charter 状态行 / CAPABILITIES 备注
- 既有 store API 只读消费（不新开 accuracy / 外部 gate）

## 禁止

| 禁止 | 原因 |
|---|---|
| `accuracy_claim=true` / κ 文案 / 外部 gate | 需 G2b |
| staging / authorize / A3 拆分 | 生产门仍冻 |
| 静默开 G2b | 需独立 unfreeze + 第二标注者 |
| 删除旧页能力而无 tab 承接 | G3：redirect，不丢功能 |

## E6 出口

| 项 | 门槛 |
|---|---|
| `/eval` | 多 tab 可导航；诚实横幅可见 |
| Redirect | `/diagnostics/eval` → `/eval?tab=agents`（可 `?legacy=1` 回旧页） |
| API | 总览/集/复核/门禁读 canonical store |
| Accuracy | UI 仍禁止宣称 |
| Closeout | `EVAL_V1_E6_CLOSEOUT.md` + Outcome |

## 验证

```bash
test -f reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_E6.md
grep -q "path: 'eval'" aiPlat-management/frontend/src/App.tsx
cd aiPlat-management/frontend && npx tsc --noEmit
```
