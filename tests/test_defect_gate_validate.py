"""Unit tests for scripts/defect_gate_validate.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "defect_gate_validate", ROOT / "scripts" / "defect_gate_validate.py"
)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules["defect_gate_validate"] = mod
SPEC.loader.exec_module(mod)


def _pass_receipt(diff: str = "abc123", merge_base: str = "def456") -> dict:
    return {
        "schema": mod.SCHEMA,
        "status": "pass",
        "findings_count": 0,
        "reviewed_at": "2026-10-18T00:00:00+08:00",
        "base_ref": "origin/main",
        "merge_base": merge_base,
        "diff_sha256": diff,
        "checks": {k: "pass" for k in mod.REQUIRED_CHECKS},
        "findings": [],
        "reviewer": "agent",
        "note": "",
    }


def test_pass_receipt_ok():
    ok, errors = mod.validate_receipt(
        _pass_receipt(), expect_diff="abc123", expect_merge_base="def456"
    )
    assert ok, errors


def test_stale_diff_fails():
    ok, errors = mod.validate_receipt(
        _pass_receipt("old"), expect_diff="new", expect_merge_base="def456"
    )
    assert not ok
    assert any("diff_sha256" in e for e in errors)


def test_fail_status_blocked():
    data = _pass_receipt()
    data["status"] = "fail"
    data["findings_count"] = 1
    data["findings"] = [{"severity": "P1", "title": "x", "path": "a.py:1"}]
    ok, errors = mod.validate_receipt(
        data, expect_diff="abc123", expect_merge_base="def456"
    )
    assert not ok
    assert any("status=fail" in e for e in errors)


def test_missing_check_fails():
    data = _pass_receipt()
    del data["checks"]["old_fallback"]
    ok, errors = mod.validate_receipt(
        data, expect_diff="abc123", expect_merge_base="def456"
    )
    assert not ok
    assert any("old_fallback" in e for e in errors)
