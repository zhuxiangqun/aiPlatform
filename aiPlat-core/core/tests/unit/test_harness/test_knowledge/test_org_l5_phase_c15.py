"""Phase C1.5 — Interface YAML authority; connector.live is read-only fallback."""

from __future__ import annotations

from core.apps.fde.service.abox_connector import _workspace_connector_seed
from core.apps.org.service.org_interface import (
    get_interface_spec,
    materialize_interface_yaml,
)


def test_seed_yaml_is_authority():
    pack = get_interface_spec("it-ops")
    assert pack["authority_source"] == "interfaces.yaml"
    assert pack["compat_live"] is False
    assert "interfaces" in pack["authority_path"]
    assert pack["spec"]["interface_ref"] == "it-ops.monitor.fetch"
    assert pack["spec"]["enabled"] is False


def test_home_yaml_overrides_without_merging_live(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    dest = tmp_path / "interfaces"
    dest.mkdir()
    (dest / "it-ops.home.yaml").write_text(
        "\n".join(
            [
                "interface_ref: it-ops.home.only",
                "domain_id: it-ops",
                "version: 9.9.9",
                "adapter: http_json",
                "enabled: false",
                "allowed_hosts: []",
                "timeout_sec: 11",
                "bound_action_ids: [only_home]",
                "auth:",
                "  type: none",
                "",
            ]
        ),
        encoding="utf-8",
    )
    pack = get_interface_spec("it-ops")
    spec = pack["spec"]
    assert pack["authority_source"] == "interfaces.yaml"
    assert pack["compat_live"] is False
    assert spec["interface_ref"] == "it-ops.home.only"
    assert spec["timeout_sec"] == 11
    assert spec["bound_action_ids"] == ["only_home"]
    assert "triage_alert" not in spec["bound_action_ids"]


def test_connector_live_fallback_when_no_yaml(tmp_path, monkeypatch):
    import core.apps.org.service.org_interface as iface

    empty = tmp_path / "none"
    empty.mkdir()
    monkeypatch.setattr(iface, "_home_interface_dir", lambda: empty / "home")
    monkeypatch.setattr(iface, "_seed_interface_dir", lambda: empty / "seed")
    pack = get_interface_spec("it-ops")
    assert pack["authority_source"] == "connector.live"
    assert pack["compat_live"] is True
    assert pack["spec"]["interface_ref"] == "it-ops.monitor.fetch"


def test_materialize_writes_home_yaml_only(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    connector = _workspace_connector_seed("it-ops")
    before = connector.read_bytes()
    first = materialize_interface_yaml("it-ops")
    assert first["wrote"] is True
    assert first["copied_from"] == "interfaces.yaml"
    assert connector.read_bytes() == before
    second = materialize_interface_yaml("it-ops")
    assert second["wrote"] is False
    assert connector.read_bytes() == before
    pack = get_interface_spec("it-ops")
    assert str(tmp_path) in pack["authority_path"]
    assert pack["compat_live"] is False
