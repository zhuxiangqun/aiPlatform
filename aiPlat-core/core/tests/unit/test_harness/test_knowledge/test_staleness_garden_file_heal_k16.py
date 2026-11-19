"""N09 K16 — garden / sys_file / self_heal use per-tenant staleness scans."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")



def test_file_source_wires_tenant_scan():
    text = (_repo_root() / "aiPlat-core/core/harness/syscalls/file.py").read_text(encoding="utf-8")
    assert "list_kb_tenant_ids" in text
    assert "StalenessMonitor(tenant_id=t)" in text
    assert "StalenessMonitor().scan_all_collections()" not in text
    assert "trace_context=trace_context" in text


def test_garden_source_wires_tenant_scan():
    text = (_repo_root() / "aiPlat-core/core/harness/knowledge/auto_garden.py").read_text(encoding="utf-8")
    assert "_scan_staleness_tenants" in text
    assert "list_kb_tenant_ids" in text
    assert "StalenessMonitor(tenant_id=tid)" in text
    # bare ctor only allowed inside explanatory comments, not as a call site
    assert "monitor = StalenessMonitor()" not in text
    assert "StalenessMonitor().scan" not in text


def test_self_heal_source_wires_tenant_scan():
    text = (_repo_root() / "aiPlat-core/core/harness/evaluation/self_heal_gate.py").read_text(
        encoding="utf-8"
    )
    assert "list_kb_tenant_ids" in text
    assert "StalenessMonitor(tenant_id=t)" in text
    assert "monitor = StalenessMonitor()" not in text


def test_garden_scan_uses_explicit_tenant(monkeypatch, tmp_path):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    from core.harness.knowledge import auto_garden as ag
    from core.harness.knowledge import staleness_monitor as sm

    seen = []

    class _FakeMon:
        def __init__(self, *, tenant_id="default"):
            seen.append(tenant_id)

        def scan_all_collections(self):
            return []

    monkeypatch.setattr(sm, "StalenessMonitor", _FakeMon)
    monkeypatch.setattr(sm, "list_kb_tenant_ids", lambda: ["should-not-run"])
    # avoid wiki IO
    monkeypatch.setattr(ag.AutoGarden, "_list_collections", lambda self, specific: [])
    monkeypatch.setattr(ag.AutoGarden, "_write_report", lambda self, result, cid: "")

    r = ag.AutoGarden().run(tenant_id="n09-t16")
    assert seen == ["n09-t16"]
    assert r.total_checked == 0
