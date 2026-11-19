"""W6 deepen：Knowledge SDK Python 写盘安装（allowlist）；非多语言包发布。"""
from __future__ import annotations

from pathlib import Path

from core.harness.knowledge_pipeline.sdk_generator import (
    install_sdk_python,
    resolve_sdk_install_root,
)


def _seed() -> Path:
    p = (
        Path(__file__).resolve().parents[5]
        / "workspace_seeds"
        / "ontologies"
        / "lock-service-object-types.json"
    )
    if p.is_file():
        return p
    return Path("aiPlat-core/workspace_seeds/ontologies/lock-service-object-types.json")


def _fake_knowledge_root(tmp_path: Path) -> Path:
    root = tmp_path / "aiplat-sdk" / "aiplat" / "knowledge"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_resolve_rejects_non_allowlisted_root(tmp_path: Path):
    bad = tmp_path / "elsewhere"
    bad.mkdir()
    out = resolve_sdk_install_root(install_root=bad)
    assert out["status"] == "error"
    assert out["reason"] == "install_root_not_allowlisted"


def test_install_writes_under_allowlist(tmp_path: Path):
    root = _fake_knowledge_root(tmp_path)
    out = install_sdk_python(
        "InstallOrder",
        permissions=["kb:read"],
        bindings_path=_seed(),
        install_root=root,
    )
    assert out["status"] == "ok"
    path = Path(out["path"])
    assert path.is_file()
    assert path.parent == root.resolve()
    assert path.name == "installorder_client.py"
    text = path.read_text(encoding="utf-8")
    assert "from core.api.core_facade import" in text
    assert "class InstallOrderClient" in text
    assert (root / "__init__.py").is_file()
    assert out.get("note") == "python_write_install_only; multi_lang_publish_not_claimed"


def test_install_policy_denied(tmp_path: Path):
    root = _fake_knowledge_root(tmp_path)
    out = install_sdk_python(
        "InstallOrder",
        permissions=["kb:write"],
        bindings_path=_seed(),
        install_root=root,
    )
    assert out["status"] == "policy_denied"
    assert not any(root.glob("*_client.py"))
