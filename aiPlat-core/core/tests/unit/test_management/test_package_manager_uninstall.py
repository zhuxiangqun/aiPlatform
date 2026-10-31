import json
from pathlib import Path


def test_package_manager_install_bundle_and_uninstall(tmp_path, monkeypatch):
    # Workspace installs go through get_aiplat_data_dir (AIPLAT_HOME SSOT)
    home = tmp_path / "aiplat_home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))

    from core.management.package_manager import PackageManager
    from core.utils.paths import get_aiplat_data_dir

    mgr = PackageManager(scope="workspace")

    # Build a fake bundle directory
    bundle = tmp_path / "bundle"
    (bundle / "agents" / "a1").mkdir(parents=True)
    (bundle / "agents" / "a1" / "AGENT.md").write_text("hello", encoding="utf-8")

    manifest = {"name": "starter", "version": "0.1.0", "resources": [{"kind": "agent", "id": "a1"}]}
    rec = mgr.install_bundle(pkg_name="starter", pkg_version="0.1.0", manifest=manifest, bundle_dir=bundle, allow_overwrite=True)
    assert rec["package"]["name"] == "starter"
    agent_md = Path(get_aiplat_data_dir("agents")) / "a1" / "AGENT.md"
    assert agent_md.exists()

    res = mgr.uninstall(pkg_name="starter", keep_modified=False)
    assert res["package"]["name"] == "starter"
    assert not agent_md.exists()

