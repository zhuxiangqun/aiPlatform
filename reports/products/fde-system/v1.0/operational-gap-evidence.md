---
doc_type: Report
doc_id: FDE_SYS_V10_OPS_GAP
status: measurement
authority: evidence
created: 2026-11-26
last_reviewed: 2026-11-26
purpose: FDE 系统 v1.0 Operational（F10–F11）测量；不扩大 ADR-09 E4
---

# FDE 系统 v1.0 — Operational 差距证据（测量）

| ID | 状态 | 证据 |
|---|---|---|
| F10 生产独立进程 authorize | **exists** + **authorized=true** | `evaluate_fde_production_process_authorize`；`AIPLAT_FDE_OPTIONAL_SPLIT` 不够 |
| F11 compose 长驻 | **exists** + **authorized=true** | `evaluate_fde_compose_long_running_authorize`；批准 + `adr_ref` |

**当前 F10+F11 authorized=true** → bundle **`operational_ready=true`**（朱莹非作者批准  
`operational-approval-record.approved.json`；`adr_ref` =  
`docs/decisions/products/five-products/ADR-FDE-COMPOSE-LONG-RUNNING.md` · **Accepted**）。  
≠ `certified`；≠ 强制生产默认；≠ E4。compose 文件/烟测仍按 ADR 落地序另 PR。

```bash
python3 -c "
from core.apps.fde.service.operational_contracts import evaluate_fde_operational_bundle
p='reports/products/fde-system/v1.0/operational-approval-record.approved.json'
b=evaluate_fde_operational_bundle(approval_record_path=p)
assert b['operational_ready'] and b['F11']['authorized']
print('ok', b['F11']['adr_ref'])
"
pytest aiPlat-core/core/tests/unit/test_apps/test_fde_operational_f10_f11.py -q
```
