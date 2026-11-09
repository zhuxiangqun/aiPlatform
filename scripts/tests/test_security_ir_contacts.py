"""IR contacts SoT validator."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "scripts" / "security_ir_contacts.py"


def _load():
    spec = importlib.util.spec_from_file_location("security_ir_contacts_ut", MOD)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ir():
    return _load()


def test_example_template_not_filled(ir):
    example = ROOT / "security" / "ir" / "contacts.example.yaml"
    data = ir._try_yaml_load(example.read_text(encoding="utf-8"))
    out = ir.validate_contacts(data, path=example)
    assert out["filled"] is False
    assert any("blank_or_tbd" in e for e in out["errors"])


def test_filled_contacts_pass(ir, tmp_path: Path):
    # Use the committed example-with-names file content pattern
    text = (ROOT / "security" / "ir" / "contacts.local.yaml.example").read_text(
        encoding="utf-8"
    )
    p = tmp_path / "contacts.local.yaml"
    p.write_text(text, encoding="utf-8")
    out = ir.load_contacts(path=p)
    assert out["filled"] is True
    assert out["ok"] is True
    assert out["security_certification"] is False
