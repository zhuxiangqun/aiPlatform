# Pi D3 prep（Accepted 有条件 · 未授权生产宣称）

> ADR: [`ADR-PI-D3.md`](../../../../reports/five-products/ADR-PI-D3.md) — **Accepted（有条件）**  
> 默认交付仍为 **D1 Thin + D2 admin**；D3 为批准路径。

| Doc | Purpose |
|-----|---------|
| [`D3_CHECKLIST.md`](./D3_CHECKLIST.md) | 生产宣称硬门 |
| [`PREP_STATUS.json`](./PREP_STATUS.json) | 自动检查结果 |
| [`BUNDLE_INTEGRITY.md`](./BUNDLE_INTEGRITY.md) | Bundle 校验策略（骨架） |
| [`OPS_SURFACE.md`](./OPS_SURFACE.md) | 运维面约定（骨架） |
| [`LIVE_DRILL_EVIDENCE.md`](./LIVE_DRILL_EVIDENCE.md) | 生产 live 证据模板 |

```bash
# 一键本地收口（推荐 · Option B）
bash packages/aiplat-pi-runtime/scripts/d3_local_closeout.sh
# → reports/five-products/ops/PI_D3_LOCAL_CLOSEOUT.md

# 拆步
bash packages/aiplat-pi-runtime/scripts/d3_local_rehearsal.sh      # #3/#4 → 🟨
bash packages/aiplat-pi-runtime/scripts/d3_soc_local_rehearsal.sh  # #5 → 🟨
bash packages/aiplat-pi-runtime/scripts/d3_n1_local_rehearsal.sh   # #6 N-1 → 🟨
bash packages/aiplat-pi-runtime/scripts/d3_prep_check.sh
bash packages/aiplat-pi-runtime/scripts/d3_authorize.sh status
bash packages/aiplat-pi-runtime/scripts/d3_authorize.sh authorize  # 未全 ✅ → REFUSE
```
