"""Unit tests for scripts/defect_gate_validate.py and independence check."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mod = _load("defect_gate_validate", "scripts/defect_gate_validate.py")
indep = _load("defect_gate_independence", "scripts/defect_gate_independence.py")


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


def test_command_needs_gate_push_and_pr():
    assert mod.command_needs_gate("git push origin HEAD")
    assert mod.command_needs_gate("gh pr create --title x")
    assert not mod.command_needs_gate("echo git push")
    assert not mod.command_needs_gate(
        "git commit -m \"$(cat <<'EOF'\nmention git push\nEOF\n)\""
    )


def test_dirty_without_allow_dirty_fails(monkeypatch):
    monkeypatch.setattr(mod, "dirty_paths_outside_receipt", lambda: ["foo.py"])
    monkeypatch.setattr(mod, "merge_base_with", lambda _base: "m" * 40)
    monkeypatch.setattr(mod, "reviewed_diff_sha", lambda *_a, **_k: "d" * 64)
    monkeypatch.setattr(mod, "_repo_root", lambda: ROOT)
    monkeypatch.setattr(os, "chdir", lambda _p: None)
    # Ensure bypass off
    monkeypatch.delenv("AIPLAT_DEFECT_GATE", raising=False)
    rc = mod.main([])
    assert rc == 1


def test_print_template_works_under_bypass(monkeypatch=None):
    env = os.environ.copy()
    env["AIPLAT_DEFECT_GATE"] = "0"
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "defect_gate_validate.py"), "--print-template"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["schema"] == mod.SCHEMA
    assert data["diff_sha256"]


def test_non_author_approval_pass():
    reviews = [
        {"user": {"login": "alice"}, "state": "APPROVED"},
        {"user": {"login": "bob"}, "state": "COMMENTED"},
    ]
    ok, msg = indep.check_independence(author="bob", reviews=reviews)
    assert ok, msg
    assert "alice" in msg


def test_author_self_approve_ignored():
    reviews = [{"user": {"login": "bob"}, "state": "APPROVED"}]
    ok, msg = indep.check_independence(author="bob", reviews=reviews)
    assert not ok
    assert "bob" in msg


def test_dismissed_latest_state_blocks():
    # Newest-first: CHANGES_REQUESTED then older APPROVED for same user
    reviews = [
        {"user": {"login": "alice"}, "state": "CHANGES_REQUESTED"},
        {"user": {"login": "alice"}, "state": "APPROVED"},
    ]
    ok, _ = indep.check_independence(author="bob", reviews=reviews)
    assert not ok


def test_independence_cli_offline():
    reviews = [{"user": {"login": "alice"}, "state": "APPROVED"}]
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "reviews.json"
        path.write_text(json.dumps(reviews), encoding="utf-8")
        r = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "defect_gate_independence.py"),
                "--reviews-json",
                str(path),
                "--author",
                "bob",
            ],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, r.stderr
