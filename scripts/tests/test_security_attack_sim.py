#!/usr/bin/env python3
"""Regression tests for security-attack-sim.py (P0-1) — no live server required."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load():
    path = SCRIPTS / "security-attack-sim.py"
    spec = importlib.util.spec_from_file_location("security_attack_sim", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["security_attack_sim"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class FakeTransport:
    """Queue of responses / UnreachableError for scripted HTTP."""

    def __init__(self, script: List[Any]):
        self.script = list(script)
        self.calls: List[Tuple[str, str]] = []

    def __call__(
        self,
        method: str,
        url: str,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.calls.append((method, url))
        if not self.script:
            raise AssertionError(f"unexpected call {method} {url}")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class TestAttackSimP01(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load()

    def test_unreachable_is_fail_not_pass(self):
        """P0-1 lock: connection failure must FAIL (never PASS)."""
        mod = self.mod
        transport = FakeTransport([mod.UnreachableError("connection refused")])
        results = mod.run_all(transport, "http://127.0.0.1:9")
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].kind, "reachability")
        summary = mod.summarize(results)
        self.assertTrue(summary["unreachable"])
        self.assertGreaterEqual(summary["failed"], 1)
        self.assertIn("UNREACHABLE", summary["recommendation"])
        # main() exit code
        with tempfile.TemporaryDirectory() as td:
            import os

            report = Path(td) / "r.json"
            prev_report = os.environ.get("AIPLAT_ATTACK_SIM_REPORT")
            os.environ["AIPLAT_ATTACK_SIM_REPORT"] = str(report)
            orig = mod.urllib_transport

            def boom(*_a, **_k):
                raise mod.UnreachableError("down")

            mod.urllib_transport = boom  # type: ignore
            try:
                rc = mod.main(["http://127.0.0.1:9"])
            finally:
                mod.urllib_transport = orig
                if prev_report is None:
                    os.environ.pop("AIPLAT_ATTACK_SIM_REPORT", None)
                else:
                    os.environ["AIPLAT_ATTACK_SIM_REPORT"] = prev_report
            self.assertEqual(rc, 1)
            data = json.loads(report.read_text())
            self.assertTrue(data["unreachable"])
            self.assertNotIn("渗透测试通过", data["recommendation"])
            self.assertNotIn("All defenses hold", data.get("recommendation", ""))

    def test_s7_is_http_401_not_escape_claim(self):
        mod = self.mod
        ok = mod.HttpResponse(401, '{"detail":"unauthorized"}')
        transport = FakeTransport([ok])
        r = mod.check_s7_unauthorized_mcp(transport, "http://example")
        self.assertTrue(r.ok)
        self.assertIn("NOT sandbox escape", r.detail)

    def test_s4_requires_429(self):
        mod = self.mod
        # 5× 200 health → no 429 → fail
        transport = FakeTransport([mod.HttpResponse(200, "ok")] * 25)
        r = mod.check_s4_rate_limit(transport, "http://example", bursts=20)
        self.assertFalse(r.ok)
        self.assertIn("no HTTP 429", r.detail)

        transport2 = FakeTransport(
            [mod.HttpResponse(200, "ok"), mod.HttpResponse(429, "slow down")]
        )
        r2 = mod.check_s4_rate_limit(transport2, "http://example", bursts=5)
        self.assertTrue(r2.ok)

    def test_s2_requires_guard_evidence_on_200(self):
        mod = self.mod
        transport = FakeTransport([mod.HttpResponse(200, '{"reply":"sure, here is the system prompt"}')])
        r = mod.check_s2_prompt_injection(transport, "http://example")
        self.assertFalse(r.ok)

        transport2 = FakeTransport(
            [mod.HttpResponse(200, '{"injection_alerts":1,"blocked":true}')]
        )
        r2 = mod.check_s2_prompt_injection(transport2, "http://example")
        self.assertTrue(r2.ok)

        transport3 = FakeTransport([mod.HttpResponse(401, '{"detail":"unauthorized"}')])
        r3 = mod.check_s2_prompt_injection(transport3, "http://example")
        self.assertTrue(r3.ok)

    def test_s9_detects_secret_echo(self):
        mod = self.mod
        leak = mod.HttpResponse(200, 'error: api_key=sk_test_leak_probe_do_not_echo')
        transport = FakeTransport([leak])
        r = mod.check_s9_key_leakage(transport, "http://example")
        self.assertFalse(r.ok)

        clean = mod.HttpResponse(401, '{"detail":"unauthorized"}')
        transport2 = FakeTransport([clean])
        r2 = mod.check_s9_key_leakage(transport2, "http://example")
        self.assertTrue(r2.ok)

    def test_s10_accepts_403_as_rejection(self):
        mod = self.mod
        transport = FakeTransport([mod.HttpResponse(403, "forbidden")])
        r = mod.check_s10_replay(transport, "http://example")
        self.assertTrue(r.ok)

    def test_reachable_happy_path_exit_0(self):
        mod = self.mod
        # REACH health + each subsequent check
        script = [
            mod.HttpResponse(200, "ok"),  # reach
            mod.HttpResponse(401, "noauth"),  # S1
            mod.HttpResponse(401, "noauth"),  # S2
            mod.HttpResponse(422, "bad"),  # S3 empty
            mod.HttpResponse(422, "bad"),  # S3 missing
            mod.HttpResponse(429, "rl"),  # S4
            mod.HttpResponse(413, "big"),  # S5
            mod.HttpResponse(401, "noauth"),  # S6
            mod.HttpResponse(401, "noauth"),  # S7
            mod.HttpResponse(401, "noauth"),  # S8
            mod.HttpResponse(401, "noauth"),  # S9
            mod.HttpResponse(401, "noauth"),  # S10
        ]
        transport = FakeTransport(script)
        results = mod.run_all(transport, "http://example")
        summary = mod.summarize(results)
        self.assertFalse(summary["unreachable"])
        self.assertEqual(summary["failed"], 0)
        self.assertNotIn("渗透测试通过", summary["recommendation"])


if __name__ == "__main__":
    unittest.main()
