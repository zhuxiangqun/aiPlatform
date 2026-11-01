# DIAGNOSIS_V1 C3.5 closeout — adversarial fixture hardening

- **closed_at**: `2026-11-02`
- **status**: **PASS**（工程轨；非准确率认证）
- **unfreeze**: [`ENGINEERING_UNFREEZE_DIAGNOSIS_C35_FIXTURE_HARDENING.md`](./ENGINEERING_UNFREEZE_DIAGNOSIS_C35_FIXTURE_HARDENING.md)
- **parent**: [`DIAGNOSIS_V1_C3_CLOSEOUT.md`](./DIAGNOSIS_V1_C3_CLOSEOUT.md)

## Delivered

| 项 | 证据 |
|---|---|
| ≥6 `dx.adv.*` fixtures | `packages/aiplat-diagnosis/fixtures/dx.adv.*`（6） |
| metrics subset | `fixture_metrics(subset=core\|adversarial\|all)` |
| API | `GET /api/platform/apps/diagnosis/metrics/fixtures?subset=` |
| honesty | `accuracy_claim=false`；adversarial note 明示 holdout 可 <1.00 |
| tests | `core/tests/unit/test_diagnosis_v1_c35.py` |

## Honesty

- Core Top-1 仍是工程指标，**不是**诊断准确率。
- Adversarial 故意含误导信号；分报 core / adversarial，禁止用 core 1.00 对外宣称。
- 无 remediate / 无 A3 / 无 staging（C4 仍需独立解冻）。

## Verify

```bash
PYTHONPATH=aiPlat-core python3 -c "
from core.apps.diagnosis.service.metrics import fixture_metrics
c=fixture_metrics(subset='core',limit=10,blind=True)
a=fixture_metrics(subset='adversarial',limit=30,blind=True)
assert c['accuracy_claim'] is False and a['n']>=6
print('core', c['top1_rate'], 'adv', a['top1_rate'], a['n'])
"
pytest aiPlat-core/core/tests/unit/test_diagnosis_v1_c35.py -q
```
