# Ontology A3 prep（Accepted 有条件 · 未授权拆分）

> ADR: [`ADR-ONTOLOGY-A3.md`](../../../../reports/five-products/ADR-ONTOLOGY-A3.md) — **Accepted（有条件）**  
> 默认仍为 Central **共宿 D1**。

| Doc | Purpose |
|-----|---------|
| [`SPLIT_CHECKLIST.md`](./SPLIT_CHECKLIST.md) | 进程拆分硬门 |
| [`PREP_STATUS.json`](./PREP_STATUS.json) | 自动检查结果 |
| [`LIVE_DRILL_EVIDENCE.md`](./LIVE_DRILL_EVIDENCE.md) | 生产 live 证据模板 |

```bash
bash packages/aiplat-ontology/scripts/a3_local_rehearsal.sh  # #3/#5 → 🟨
bash packages/aiplat-ontology/scripts/a3_prep_check.sh
# process_split_authorized 恒 false 直至 checklist 全 ✅
bash packages/aiplat-ontology/scripts/a3_split_authorize.sh status
bash packages/aiplat-ontology/scripts/a3_split_authorize.sh authorize  # 未全 ✅ → REFUSE
```
