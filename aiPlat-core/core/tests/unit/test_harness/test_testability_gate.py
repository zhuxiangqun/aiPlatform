"""P1 testability gate — pure unit tests required for handlers."""

from __future__ import annotations

from datetime import date

from core.harness.meta.testability_gate import (
    evaluate_files,
    is_impure_test,
    resolve_mode,
    veto_reason_from_report,
)


def test_resolve_mode_escalates_after_block_after():
    cfg = {"mode": "warn", "block_after": "2026-11-01"}
    assert resolve_mode(cfg, now=date(2026, 10, 15)) == "warn"
    assert resolve_mode(cfg, now=date(2026, 11, 15)) == "block"


def test_impure_detection():
    assert is_impure_test("import sqlite3\nsqlite3.connect(':memory:')")
    assert is_impure_test("requests.get('https://x')")
    assert not is_impure_test("def test_ok():\n    assert 1 + 1 == 2\n")


def test_missing_pure_test_blocks():
    files = {
        "skills/foo/handler.py": "async def execute(params):\n    return {'ok': True}\n",
    }
    r = evaluate_files(files, mode_override="block")
    assert r.ok is False
    assert any(f.code == "testability_missing_pure_test" for f in r.findings)


def test_pure_test_satisfies():
    files = {
        "skills/foo/handler.py": "async def execute(params):\n    return {'ok': True}\n",
        "tests/test_foo_handler.py": (
            "from skills.foo.handler import execute\n"
            "def test_execute():\n"
            "    assert True\n"
        ),
    }
    r = evaluate_files(files, mode_override="block")
    assert r.ok is True
    assert not r.findings


def test_integration_only_does_not_count():
    files = {
        "skills/foo/handler.py": "def execute(p):\n    return p\n",
        "tests/test_foo_handler.py": (
            "import pytest\n"
            "import requests\n"
            "@pytest.mark.integration\n"
            "def test_live():\n"
            "    assert requests.get('https://example.com').ok\n"
        ),
    }
    r = evaluate_files(files, mode_override="block")
    assert r.ok is False
    assert any(f.code == "testability_integration_only" for f in r.findings)


def test_warn_mode_ok_with_findings():
    files = {"pkg/handler.py": "def execute(p):\n    return 1\n"}
    r = evaluate_files(files, mode_override="warn")
    assert r.ok is True
    assert r.findings
    assert veto_reason_from_report(r) is None


def test_block_veto_reason():
    files = {"pkg/handler.py": "def execute(p):\n    return 1\n"}
    r = evaluate_files(files, mode_override="block")
    reason = veto_reason_from_report(r)
    assert reason and "testability" in reason


def test_impure_unmarked_unit_test():
    files = {
        "pkg/handler.py": "def execute(p):\n    return 1\n",
        "tests/test_handler.py": (
            "import sqlite3\n"
            "def test_db():\n"
            "    sqlite3.connect(':memory:')\n"
            "    assert True\n"
        ),
    }
    r = evaluate_files(files, mode_override="block")
    codes = {f.code for f in r.findings}
    assert "testability_impure_unmarked" in codes or "testability_integration_only" in codes


def test_enrich_loads_disk_test(tmp_path):
    from core.harness.meta.testability_gate import enrich_files_from_workspace

    pkg = tmp_path / "skills" / "foo"
    pkg.mkdir(parents=True)
    (pkg / "handler.py").write_text("def execute(p):\n    return p\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_foo_handler.py").write_text(
        "from skills.foo.handler import execute\n"
        "def test_execute():\n"
        "    assert execute(1) == 1\n",
        encoding="utf-8",
    )
    files = {
        "skills/foo/handler.py": "def execute(p):\n    return p\n",
    }
    enriched = enrich_files_from_workspace(files, tmp_path)
    assert any("test_foo" in k for k in enriched)
    r = evaluate_files(enriched, mode_override="block")
    assert r.ok is True
