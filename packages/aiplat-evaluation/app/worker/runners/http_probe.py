"""http_probe — B3-L local_stub only (no network I/O).

Honesty: validates payload shape; does **not** fetch URLs; accuracy_claim=false.
"""
from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlparse

from app.sandbox.policy import sandbox_admits, sandbox_backend
from app.worker.runners._common import runner_result


def run_http_probe(job: Dict[str, Any]) -> Dict[str, Any]:
    rid = "http_probe"
    job_id = str(job.get("job_id") or "")
    if not sandbox_admits(rid):
        raise ValueError(f"sandbox_required:{rid}")

    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    url = str(payload.get("url") or payload.get("target") or "").strip()
    method = str(payload.get("method") or "GET").upper()

    parsed_ok = False
    scheme = ""
    if url:
        try:
            p = urlparse(url)
            scheme = (p.scheme or "").lower()
            parsed_ok = scheme in ("http", "https") and bool(p.netloc)
        except Exception:
            parsed_ok = False

    ok = parsed_ok and method in ("GET", "HEAD", "POST")
    return runner_result(
        runner_id=rid,
        job_id=job_id,
        ok=ok,
        metrics={"parsed": 1.0 if parsed_ok else 0.0, "fetched": 0.0},
        evidence={
            "url_present": bool(url),
            "scheme": scheme,
            "method": method,
            "network_io": False,
            "sandbox_backend": sandbox_backend(),
        },
        detail="" if ok else "invalid url/method for local_stub http_probe",
        mode="local_stub",
    )
