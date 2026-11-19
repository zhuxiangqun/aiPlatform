"""N07/N22 deepen：H.1 masked_properties + 只读 H.1 投影；非完整策略编辑器 / 非 certified。"""
from __future__ import annotations

from pathlib import Path

from core.policy.graph_abox_acl import (
    entity_acl_to_h1,
    list_masked_properties,
    load_abox_acl,
    preview_abox_acl,
    redact_entity_fields,
    set_entity_acl,
)


ROOT = Path(__file__).resolve().parents[6]


def test_masked_properties_syncs_field_acl(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-mask"
    set_entity_acl(
        domain,
        "e1",
        deny_roles={"viewer": ["read"]},
        masked_properties=["ssn", "customer_phone"],
    )
    assert list_masked_properties(domain, "e1") == ["ssn", "customer_phone"]
    fields = load_abox_acl(domain).get("fields") or {}
    assert fields["e1.ssn"]["visibility"] == "none"
    assert fields["e1.customer_phone"]["visibility"] == "none"
    red = redact_entity_fields(
        domain, "e1", {"ssn": "1", "customer_phone": "2", "name": "ok"}, "viewer"
    )
    assert red["ssn"] == "[REDACTED]"
    assert red["customer_phone"] == "[REDACTED]"
    assert red["name"] == "ok"
    # 更新列表：移除 ssn、保留 phone、新增 email
    set_entity_acl(domain, "e1", masked_properties=["customer_phone", "email"])
    fields2 = load_abox_acl(domain).get("fields") or {}
    assert "e1.ssn" not in fields2
    assert fields2["e1.customer_phone"]["visibility"] == "none"
    assert fields2["e1.email"]["visibility"] == "none"
    # 空列表清除
    set_entity_acl(domain, "e1", masked_properties=[])
    assert list_masked_properties(domain, "e1") == []
    assert "e1.customer_phone" not in (load_abox_acl(domain).get("fields") or {})


def test_entity_acl_to_h1_and_preview(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    domain = "lock-service-acl-h1"
    set_entity_acl(
        domain,
        "Ticket-1",
        deny_roles={"viewer": ["read", "update"]},
        condition={"status": "open"},
        masked_properties=["ssn"],
    )
    h1 = entity_acl_to_h1(domain, "Ticket-1")
    assert h1["resource"] == "Ticket-1"
    assert h1["effect"] == "deny"
    assert h1["principals"] == ["role:viewer"]
    assert h1["condition"] == {"status": "open"}
    assert h1["masked_properties"] == ["ssn"]
    assert "read" in h1["actions"]
    assert h1["certified"] is False
    prev = preview_abox_acl(
        domain, "Ticket-1", {"ssn": "x", "status": "open"}, role="viewer"
    )
    assert prev["masked_properties"] == ["ssn"]
    assert prev["h1_policy"]["masked_properties"] == ["ssn"]
    assert prev["certified"] is False


def test_abox_panel_documents_masked_properties():
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "AboxAclPanel.tsx"
    )
    text = panel.read_text(encoding="utf-8")
    assert "masked_properties" in text
    assert "非完整策略编辑器" in text
