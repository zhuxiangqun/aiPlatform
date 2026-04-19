import json
from pathlib import Path


def test_package_manager_install_bundle_and_uninstall(tmp_path, monkeypatch):
    # Redirect HOME to tmp so ~/.aiplat/* is isolated
    monkeypatch.setenv("HOME", str(tmp_path))

    from core.management.package_manager import PackageManager

    mgr = PackageManager(scope="workspace")

    # Build a fake bundle directory
    bundle = tmp_path / "bundle"
    (bundle / "agents" / "a1").mkdir(parents=True)
    (bundle / "agents" / "a1" / "AGENT.md").write_text("hello", encoding="utf-8")

    manifest = {"name": "starter", "version": "0.1.0", "resources": [{"kind": "agent", "id": "a1"}]}
    rec = mgr.install_bundle(pkg_name="starter", pkg_version="0.1.0", manifest=manifest, bundle_dir=bundle, allow_overwrite=True)
    assert rec["package"]["name"] == "starter"
    assert (Path.home() / ".aiplat" / "agents" / "a1" / "AGENT.md").exists()

    res = mgr.uninstall(pkg_name="starter", keep_modified=False)
    assert res["package"]["name"] == "starter"
    assert not (Path.home() / ".aiplat" / "agents" / "a1").exists()

