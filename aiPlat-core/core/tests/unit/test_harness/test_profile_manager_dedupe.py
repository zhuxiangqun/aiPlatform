"""ProfileManager：name≠namespace 时 list 不得出现重复客户。"""

from __future__ import annotations

from pathlib import Path

from core.harness.kernel.profile import ProfileManager


def test_create_name_differs_from_namespace_lists_once(tmp_path: Path):
    pm = ProfileManager(home_dir=str(tmp_path))
    cfg = pm.create(
        name="MTW-syu",
        namespace="mtw-syu",
        description="dup-guard",
        industry="software",
    )
    assert cfg.namespace == "mtw-syu"
    assert cfg.name == "MTW-syu"
    listed = [c for c in pm.list_all() if c.profile_type != "template"]
    ns_hits = [c for c in listed if c.namespace == "mtw-syu"]
    assert len(ns_hits) == 1
    assert pm.get("mtw-syu") is not None
    assert pm.get("MTW-syu") is not None  # 仍可按展示名查找
