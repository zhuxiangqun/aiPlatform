#!/usr/bin/env python3
"""Live smoke: delivery SKU endpoints on a running platform (default :8003).

Usage:
  AIPLAT_PLATFORM_URL=http://127.0.0.1:8003 \\
  AIPLAT_TENANT_TOKEN=apl_dev_telemetry \\
    python3 scripts/smoke_delivery_sku_live.py

Exit 0 when cost / kb-health / monthly-ops / l3-duty all return HTTP 200 + ok.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Tuple
from urllib.parse import urljoin


def _base() -> str:
    raw = (
        os.environ.get("AIPLAT_PLATFORM_URL")
        or os.environ.get("AIPLAT_API_BASE")
        or "http://127.0.0.1:8003"
    ).strip().rstrip("/")
    # Avoid /api on :8003 (would 404)
    if raw.endswith(":8003/api"):
        raw = raw[: -len("/api")]
    return raw


def _get(path: str) -> Tuple[int, Dict[str, Any]]:
    url = urljoin(_base() + "/", path.lstrip("/"))
    token = (
        os.environ.get("AIPLAT_TENANT_TOKEN")
        or os.environ.get("AIPLAT_API_KEY")
        or "apl_dev_telemetry"
    )
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            code = int(resp.status)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        code = int(e.code)
    except Exception as e:
        return 0, {"error": str(e)}
    try:
        data = json.loads(body) if body else {}
    except json.JSONDecodeError:
        data = {"raw": body[:200]}
    if not isinstance(data, dict):
        data = {"value": data}
    return code, data


def main() -> int:
    checks: List[Tuple[str, str]] = [
        ("cost-report", "/platform/delivery/cost-report?window_hours=24"),
        ("kb-health", "/platform/delivery/kb-health?window_hours=24"),
        ("monthly-ops", "/platform/delivery/monthly-ops-report?window_hours=24"),
        ("l3-duty", "/platform/delivery/l3-duty-desk?window_hours=24"),
    ]
    failed = 0
    for name, path in checks:
        code, data = _get(path)
        ok = code == 200 and (data.get("ok") is True or data.get("status") == "ok")
        detail = ""
        if name == "cost-report":
            mr = data.get("model_routing") or {}
            detail = f" share={mr.get('usage_share_source')}"
        elif name == "l3-duty":
            detail = f" sku={data.get('sku')} contact={((data.get('duty_contact') or {}).get('available'))}"
        elif name == "monthly-ops":
            detail = f" period={data.get('period')}"
        print(f"{'OK' if ok else 'FAIL'} {name} http={code}{detail}")
        if not ok:
            failed += 1
            if data.get("detail") or data.get("error"):
                print(f"  {data.get('detail') or data.get('error')}")
    if failed:
        print(f"FAILED {failed}/{len(checks)} — restart platform if routes 404 after merge")
        return 1
    print(f"PASS {len(checks)}/{len(checks)} delivery SKU endpoints")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
