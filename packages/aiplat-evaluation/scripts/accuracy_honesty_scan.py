#!/usr/bin/env python3
"""Scan eval honesty fields (scheme A).

Product-level ``accuracy_claim`` must not be true in package evidence/scorecard.
G2b scoped claim must use ``scoped_accuracy_claim`` when accepted.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"not object: {path}")
    return data


def main() -> int:
    errors: List[str] = []
    # 1–3: scorecard / manifest / aggregate
    card = _load(ROOT / "docs/a3/scorecard_v1.json")
    if card.get("accuracy_claim") is not False:
        errors.append("scorecard_v1.json: product accuracy_claim must be false")

    manifest = _load(ROOT / "docs/a3/evidence/evidence_manifest.v1.json")
    if manifest.get("accuracy_claim") is not False:
        errors.append("evidence_manifest: product accuracy_claim must be false")

    agg = _load(ROOT / "docs/a3/evidence/g2b_accuracy_aggregate.v1.json")
    if agg.get("accuracy_claim") is not False:
        errors.append("g2b_accuracy_aggregate: product accuracy_claim must be false")
    if agg.get("scoped_accuracy_claim") is not True:
        errors.append("g2b_accuracy_aggregate: scoped_accuracy_claim expected true after owner accept")
    if agg.get("not_accuracy_certification") is not True:
        errors.append("g2b_accuracy_aggregate: not_accuracy_certification must be true")
    if not agg.get("claim_refuse_reason"):
        errors.append("g2b_accuracy_aggregate: claim_refuse_reason must be non-empty")

    # 4: attestation remains scoped accept (not product certification)
    att = _load(ROOT / "docs/a3/evidence/g2b_accuracy_claim_attestation.v1.json")
    ack = att.get("acknowledgements") if isinstance(att.get("acknowledgements"), dict) else {}
    if ack.get("scoped_g2b_accuracy_claim_only") is not True:
        errors.append("attestation: scoped_g2b_accuracy_claim_only must be true")
    if ack.get("not_production_accuracy_certification") is not True:
        errors.append("attestation: not_production_accuracy_certification must be true")

    # Sweep: no product-level accuracy_claim:true under docs/a3 evidence+scorecard JSON
    for path in (ROOT / "docs/a3").rglob("*.json"):
        if "_archive" in path.parts:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if '"accuracy_claim": true' in raw or '"accuracy_claim":true' in raw:
            # allow attestation accept_accuracy_claim / nested text only if top-level product field
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("accuracy_claim") is True:
                errors.append(f"product accuracy_claim=true forbidden: {path.relative_to(ROOT)}")

    if errors:
        print(json.dumps({"gate": "fail", "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    print(
        json.dumps(
            {
                "gate": "ok",
                "accuracy_claim": False,
                "scoped_accuracy_claim": True,
                "not_accuracy_certification": True,
                "scheme": "A",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
