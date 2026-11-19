"""N09 K32 — platform FDE API GraphIndex tenant (wave 2)."""
from __future__ import annotations

from pathlib import Path

def _repo_root() -> Path:
    """定位工作区根（兼容 CI working-directory=aiPlat-core）。"""
    for p in Path(__file__).resolve().parents:
        if (p / "aiPlat-core").is_dir() and (p / "aiPlat-platform").is_dir():
            return p
    raise RuntimeError("repo root not found from test file")


_FILES = (
    "aiPlat-platform/apps/fde/api/fde.py",
    "aiPlat-platform/apps/fde/api/fde_sessions_v2.py",
    "aiPlat-platform/apps/fde/api/fde_diagnostics_v2.py",
    "aiPlat-platform/apps/fde/api/fde_bootstrap.py",
    "aiPlat-platform/apps/fde/api/fde_validate.py",
    "aiPlat-platform/apps/fde/api/fde_manuals.py",
)


def _assert_no_bare_loads(rel: str) -> None:
    text = (_repo_root() / rel).read_text(encoding="utf-8")
    bare = [
        ln
        for ln in text.splitlines()
        if "GraphIndex.load(" in ln and "tenant_id" not in ln
    ]
    assert bare == [], bare


def test_k32_wave_sources_wire_tenant():
    for rel in _FILES:
        text = (_repo_root() / rel).read_text(encoding="utf-8")
        assert "fde_graph_tenant" in text, rel
        # 允许同模块合并 import（含 fde_graph_domain 等），禁止旁路
        assert "from apps.fde.api.graph_tenant import" in text, rel
        assert "fde_graph_tenant" in text.split("from apps.fde.api.graph_tenant import", 1)[1].split("\n", 1)[0], rel
        _assert_no_bare_loads(rel)


def test_platform_fde_api_no_bare_graphindex_loads():
    """Wave1+wave2: no executable bare GraphIndex.load under apps/fde/api."""
    root = (_repo_root() / "aiPlat-platform/apps/fde/api")
    bare = []
    for py in root.glob("*.py"):
        for i, ln in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if "GraphIndex.load(" in ln and "tenant_id" not in ln:
                bare.append(f"{py}:{i}:{ln.strip()}")
    assert bare == [], bare
