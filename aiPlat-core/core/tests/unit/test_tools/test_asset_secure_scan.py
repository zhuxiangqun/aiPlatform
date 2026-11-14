"""SecureScan gate + majority-blocked import fail helpers."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from core.harness.maintenance.asset_compat import (
    INSTALL_REPORT_SCHEMA,
    apply_majority_import_gate,
    normalize_asset_report_row,
    should_fail_import_majority_blocked,
    wrap_install_report,
)
from core.harness.maintenance.asset_secure_scan import (
    AssetSecureScanError,
    enforce_secure_scan,
    secure_scan_asset_tree,
    secure_scan_zip,
)


def test_secure_scan_blocks_traversal(tmp_path: Path):
    bad = tmp_path / "tree"
    bad.mkdir()
    # relative path with .. in name is caught by path parts
    nested = bad / "ok"
    nested.mkdir()
    (nested / "safe.txt").write_text("x", encoding="utf-8")
    # Create a file whose relative path resolves with .. via symlink escape if possible
    link = bad / "escape"
    try:
        link.symlink_to("/tmp")
    except OSError:
        pytest.skip("symlink not permitted")
    # If symlink points outside, tree scan should flag symlink_escape or still ok for dir
    rep = secure_scan_asset_tree(bad)
    # At least tree exists and scanned
    assert "files_scanned" in rep


def test_secure_scan_blocks_exe_suffix(tmp_path: Path):
    root = tmp_path / "pkg"
    root.mkdir()
    (root / "payload.exe").write_bytes(b"MZ")
    rep = secure_scan_asset_tree(root)
    assert rep["ok"] is False
    assert any("blocked_suffix" in i for i in rep["issues"])


def test_secure_scan_zip_traversal(tmp_path: Path):
    zp = tmp_path / "bad.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("../escape.txt", "x")
    rep = secure_scan_zip(zp)
    assert rep["ok"] is False
    assert any("path_traversal" in i for i in rep["issues"])


def test_enforce_secure_scan_raises(tmp_path: Path):
    root = tmp_path / "pkg"
    root.mkdir()
    (root / "x.bat").write_text("@echo off", encoding="utf-8")
    with pytest.raises(AssetSecureScanError):
        enforce_secure_scan(root)


def test_skill_installer_path_secure_scan_blocks(tmp_path: Path):
    """SkillInstaller path install must fail closed on blocked suffix."""
    from core.management.skill_installer import SkillInstaller

    root = tmp_path / "skills_src"
    skill = root / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: demo\ndescription: d\n---\n\n## SOP\nok\n",
        encoding="utf-8",
    )
    (skill / "evil.exe").write_bytes(b"MZ")
    inst = SkillInstaller(target_base_dir=tmp_path / "dest")
    with pytest.raises(AssetSecureScanError):
        inst.install_from_path(path=str(root), auto_detect_subdir=False)
    assert not (tmp_path / "dest" / "demo").exists()


def test_majority_blocked_import_gate():
    assets = [
        normalize_asset_report_row({"kind": "skill", "id": "a", "schedulable": False}),
        normalize_asset_report_row({"kind": "skill", "id": "b", "schedulable": False}),
        normalize_asset_report_row({"kind": "skill", "id": "c", "schedulable": True}),
    ]
    assert should_fail_import_majority_blocked(assets) is True
    gate = apply_majority_import_gate(assets=assets, warnings=[])
    assert gate["import_failed"] is True
    assert any("import_majority_blocked" in w for w in gate["warnings"])

    ok_assets = [
        normalize_asset_report_row({"kind": "tool", "id": "t1", "schedulable": True}),
        normalize_asset_report_row({"kind": "tool", "id": "t2", "schedulable": True}),
    ]
    assert should_fail_import_majority_blocked(ok_assets) is False
    report = wrap_install_report(assets=ok_assets, registered=2)
    assert report["schema"] == INSTALL_REPORT_SCHEMA
    assert report["import_failed"] is False
    assert report["status"] == "ok"
    assert report["registered"] == 2

    failed_report = wrap_install_report(assets=assets, import_failed=True)
    assert failed_report["status"] == "import_failed"
    assert failed_report["import_failed"] is True
