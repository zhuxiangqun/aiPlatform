# Diagnosis `rep-2551f299acf5`

- status: **ok**
- run_id: `pi-live-20261023T155206Z`
- bundle: `20261023-840e3fbd7cf1`
- source: live pi -e

```json
{
  "ok": true,
  "report_id": "rep-2551f299acf5",
  "scenario_id": "fp-internal-bundle-pi-diag-001",
  "status": "ok",
  "run_id": "pi-live-20261023T155206Z",
  "trace_id": "",
  "bundle_version": "20261023-840e3fbd7cf1",
  "runtime_version": "pi-thin-live",
  "evidence_refs": [
    {
      "kind": "pi_run",
      "id": "pi-live-20261023T155206Z"
    },
    {
      "kind": "bundle_version",
      "id": "20261023-840e3fbd7cf1"
    },
    {
      "kind": "ingest",
      "id": "ing-6e1b01b10ea8"
    }
  ],
  "freshness": "fresh",
  "asset_versions": {
    "bundle_version": "20261023-840e3fbd7cf1"
  },
  "event_count": 1,
  "created_at": "2026-10-23T15:52:06.254731+00:00",
  "rule": "Missing Pi run/events or bundle/asset version → unknown/fail; aiPlat unreachable with otherwise complete evidence → stale; never default to healthy/success.",
  "diagnosis_ok": true,
  "path": "/Users/apple/workdata/person/zy/aiPlatform/reports/five-products/.aiplat_home/five_products_slice/evidence/rep-2551f299acf5.json"
}
```
