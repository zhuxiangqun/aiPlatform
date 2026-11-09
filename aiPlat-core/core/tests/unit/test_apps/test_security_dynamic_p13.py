"""P1-3: dynamic probes (importlib; avoid Py3.9 eval package import)."""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pytest

ROOT = Path(__file__).resolve().parents[4]
MOD_PATH = ROOT / "core" / "apps" / "eval" / "service" / "security_dynamic_p13.py"


def _ensure_pkg(name: str) -> None:
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def p13():
    for pkg in ("core", "core.apps", "core.apps.eval", "core.apps.eval.service"):
        _ensure_pkg(pkg)
    return _load("core.apps.eval.service.security_dynamic_p13", MOD_PATH)


def _ok_transport(
    method: str,
    url: str,
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, str]:
    if "/tenants/tenant-b/" in url or "X-Target-Tenant-Id" in (headers or {}):
        return 403, json.dumps({"error": "forbidden"})
    if headers and headers.get("X-Tenant-Id") == "tenant-b" and method == "POST":
        return 403, json.dumps({"error": "forbidden"})
    if url.endswith("/api/items") and method == "GET":
        if (headers or {}).get("X-Target-Tenant-Id"):
            return 403, "{}"
        return 200, "[]"
    if "/api/chat" in url or "/api/rag/ask" in url:
        return 422, json.dumps({"error": "injection_rejected"})
    if "/api/render" in url:
        return 200, json.dumps({"html": "&lt;script&gt;alert(1)&lt;/script&gt;"})
    return 404, "missing"


def _leaky_injection_transport(
    method: str,
    url: str,
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, str]:
    if "/api/chat" in url:
        return 200, "Here is the system prompt: you are now DAN"
    if "/api/rag/ask" in url:
        return 200, "secret=api_key_abc password=xyz"
    return _ok_transport(method, url, body, headers)


def test_cross_tenant_100_percent_reject(p13):
    out = p13.evaluate_cross_tenant(
        base_url="http://test.local",
        transport=_ok_transport,
        repeats=2,
    )
    assert out["meets_100_percent_reject"] is True
    assert out["reject_rate"] == 1.0
    assert out["n"] == len(p13.CROSS_TENANT_PROBES) * 2
    assert out["result"] == "pass"
    assert out["security_certification"] is False


def test_cross_tenant_fail_on_allow(p13):
    def allow_all(method, url, body=None, headers=None):
        return 200, json.dumps({"items": [{"tenant": "b"}]})

    out = p13.evaluate_cross_tenant(
        base_url="http://test.local", transport=allow_all, repeats=1
    )
    assert out["meets_100_percent_reject"] is False
    assert out["result"] == "fail"


def test_injection_asr_baseline_recorded(p13):
    clean = p13.evaluate_injection_asr(
        base_url="http://test.local", transport=_ok_transport
    )
    assert clean["asr"] == 0.0
    assert clean["result"] == "baseline_recorded"
    assert clean["report_only"] is True
    assert clean["n"] == len(p13.INJECTION_PROBES)

    leaky = p13.evaluate_injection_asr(
        base_url="http://test.local", transport=_leaky_injection_transport
    )
    assert leaky["asr"] == 1.0
    assert leaky["attack_successes"] == len(p13.INJECTION_PROBES)
    assert leaky["accuracy_claim"] is False


def test_output_encoding_pass_and_fail(p13):
    ok = p13.evaluate_output_encoding(
        base_url="http://test.local", transport=_ok_transport
    )
    assert ok["result"] == "pass"
    assert ok["pass_n"] == len(p13.OUTPUT_ENCODING_PROBES)

    def echo_raw(method, url, body=None, headers=None):
        text = (body or {}).get("text", "")
        return 200, text

    bad = p13.evaluate_output_encoding(
        base_url="http://test.local", transport=echo_raw
    )
    assert bad["result"] == "fail"


def test_aggregate_requires_base_url(p13):
    out = p13.run_security_dynamic_p13(base_url="")
    assert out["ok"] is False
    assert out["error"] == "base_url_required"
    assert out["security_certification"] is False


def test_aggregate_ok(p13):
    out = p13.run_security_dynamic_p13(
        base_url="http://test.local",
        transport=_ok_transport,
        cross_tenant_repeats=1,
    )
    assert out["schema"] == "eval.security_dynamic_p1_3.v1"
    assert out["ok"] is True
    assert out["cross_tenant"]["meets_100_percent_reject"] is True
    assert out["injection"]["asr"] == 0.0
    assert out["claim_eligible"] is False
    assert out["accuracy_claim"] is False
