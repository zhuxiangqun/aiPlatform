# DIAGNOSIS_V1 C2 Local Closeout（深度接入 + 置信度）

- recorded_at: `20261101T143228Z`
- result: **PASS**
- merge: PR #516 → `29c00960`
- unfreeze: [`ENGINEERING_UNFREEZE_DIAGNOSIS_C2.md`](./ENGINEERING_UNFREEZE_DIAGNOSIS_C2.md)
- `process_split_authorized`: **false**
- `current_autonomy`: **A0**（未升 A2 — 新场景 fixture 子集未开；仅加深 adapters + report.v1）
- `accuracy_claim`: **false**
- `auto_execute`: **false**

## Exit gate

| 项 | 门槛 | 实测 |
|---|---|---|
| Eval adapter | 生产只读 + 非测试 caller | ✅ `read_evaluation_refs` ← `collect_live_stubs` ← `diagnosis_collect` / `cases.py` |
| Ontology adapter | 同上 | ✅ `read_ontology_refs` 同路径 |
| Report | confidence + reason_codes | ✅ `diagnosis.report.v1` · `top_confidence` · `uncertainty.reason_codes` |
| UI | `/diagnosis` 置信度/不确定态 | ✅ reason_codes / support / counter |
| C1 回归（blind n=10） | Top-1≥70% · Top-3≥85% · bare=0 | **1.00 / 1.00 / 0** |
| unknown/stale | ≥90% | **1.00 / 1.00** |
| 新场景（可选） | 每场景 ≥2 fixture | **未开**（本轮不宣称） |
| 自动修复 | 无 | ✅ |
| A2 升格 | 评估 | **保持 A0** |

## Verify

```bash
pytest aiPlat-core/core/tests/unit/test_diagnosis_v1_c1.py aiPlat-core/core/tests/unit/test_diagnosis_v1_c2.py -q
PYTHONPATH=aiPlat-core python3 -c "from core.apps.diagnosis.service.metrics import fixture_metrics; print(fixture_metrics(limit=10,blind=True)['top1_rate'])"
python3 reports/five-products/modules/diagnosis/contracts/validate_sample.py
python3 scripts/check_five_products_status_sync.py
bash scripts/ops_engineering_freeze_check.sh
```

## Honesty

- Engineering fixture metrics only — **not** accuracy certification.
- Live Evaluation/Ontology refs are read-only snapshots; never invent root cause from healthz alone.
- Production gates remain frozen.

## Next（需新 unfreeze）

1. **DIAGNOSIS C3** — D2/D3 本地收口 / 文档安全性能  
2. **EVAL G2b** — 第二标注者 + κ（仍阻塞）  
3. 可选：C2 中期新场景（知识/RAG、部署、安全）各 ≥2 real fixture 后再评估 A2
