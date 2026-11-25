"""N02 seed authority 产品面 slice-2：migrate/rollback；certified / complete 恒 false。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from core.api.core_facade import (
    apply_published_seed_authority_product,
    backup_knowledge_seed_authority_snapshot,
    evaluate_seed_authority_product_gate,
    list_knowledge_object_type_seed_catalog,
    list_knowledge_seed_authority_backups,
    restore_knowledge_seed_authority_snapshot,
    run_seed_authority_product_suite,
)
from core.harness.knowledge_pipeline.object_type_publish import (
    apply_published_seed_authority,
    backup_seed_authority_snapshot,
    evaluate_seed_authority_product_gate as _gate,
    list_object_type_seed_catalog,
    list_seed_authority_backups,
    restore_seed_authority_snapshot,
    run_seed_authority_product_suite as _suite,
)

ROOT = Path(__file__).resolve().parents[6]


def test_product_suite_and_gate_honesty():
    suite = _suite()
    assert suite["ok"] is True
    assert suite["passed"] == 6
    assert suite["certified"] is False
    assert suite["seed_replacement_complete"] is False
    assert suite["seed_product_surface"] is True
    assert suite["seed_migrate_rollback"] is True
    assert suite["workspace_seeds_mutated"] is False
    ids = {c["id"] for c in suite["cases"] if c.get("ok")}
    assert "seed_authority_product_catalog" in ids
    assert "seed_authority_product_apply" in ids
    assert "seed_migrate_backup" in ids
    assert "seed_migrate_write" in ids
    assert "seed_migrate_restore" in ids
    assert "honesty_product_certified_false" in ids
    gate = _gate(suite)
    assert gate["ok"] is True
    assert gate["seed_migrate_rollback"] is True
    bad = dict(suite)
    bad["certified"] = True
    honesty = _gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]
    bad2 = dict(suite)
    bad2["seed_migrate_rollback"] = False
    honesty2 = _gate(bad2)
    assert honesty2["ok"] is False
    assert "product_seed_migrate_rollback_required" in honesty2["issues"]
    bad3 = dict(suite)
    bad3["workspace_seeds_mutated"] = True
    honesty3 = _gate(bad3)
    assert honesty3["ok"] is False
    assert "honesty_workspace_seeds_mutated_forbidden" in honesty3["issues"]


def test_facade_product_suite():
    suite = run_seed_authority_product_suite()
    assert suite["ok"] is True
    gate = evaluate_seed_authority_product_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False
    assert gate["seed_product_surface"] is True
    assert gate["seed_migrate_rollback"] is True


def test_product_without_residual_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    os.environ.pop("AIPLAT_KNOWLEDGE_OBJECT_TYPE_SEED_REPLACE", None)
    catalog = list_object_type_seed_catalog()
    assert catalog["status"] == "ok"
    assert catalog["seed_product_surface"] is True
    assert catalog["seed_migrate_rollback"] is True
    assert (catalog.get("items") or []), "expected workspace_seeds *-object-types.json"
    residual = apply_published_seed_authority(
        tenant_id="t-seed-product",
        seed_path=str(catalog["items"][0]["path"]),
        write=False,
    )
    assert residual["status"] == "seed_replacement_unavailable"
    applied = apply_published_seed_authority_product(
        tenant_id="t-seed-product",
        seed_path=str(catalog["items"][0]["name"]),
        write=False,
    )
    assert applied["status"] == "ok"
    assert applied["via"] == "product"
    assert applied["workspace_seeds_mutated"] is False
    assert applied["seed_replacement_complete"] is False
    assert applied["seed_migrate_rollback"] is True
    fr = list_knowledge_object_type_seed_catalog()
    assert fr["status"] == "ok"


def test_migrate_backup_write_restore_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / "home"))
    os.environ.pop("AIPLAT_KNOWLEDGE_OBJECT_TYPE_SEED_REPLACE", None)
    catalog = list_object_type_seed_catalog()
    seed_name = str(catalog["items"][0]["name"])
    first = apply_published_seed_authority_product(
        tenant_id="t-migrate",
        seed_path=seed_name,
        write=True,
    )
    assert first["status"] == "ok"
    assert first["wrote"] is True
    assert "current" in Path(str(first["output_path"])).parts
    assert first["seed_migrate_rollback"] is True

    bak = backup_seed_authority_snapshot(tenant_id="t-migrate")
    assert bak["status"] == "ok"
    assert bak["backed_up"] is True
    bid = str(bak["backup_id"])
    listed = list_seed_authority_backups(tenant_id="t-migrate")
    assert listed["status"] == "ok"
    assert any(i.get("backup_id") == bid for i in (listed.get("items") or []))

    second = apply_published_seed_authority_product(
        tenant_id="t-migrate",
        seed_path=seed_name,
        write=True,
    )
    assert second["status"] == "ok"
    assert second.get("backup_id")
    current = Path(str(second["output_path"]))
    current.write_text(
        json.dumps({"tampered": True}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    restored = restore_seed_authority_snapshot(
        tenant_id="t-migrate",
        backup_id=bid,
    )
    assert restored["status"] == "ok"
    assert restored["restored"] is True
    body = json.loads(Path(str(restored["output_path"])).read_text(encoding="utf-8"))
    assert body.get("tampered") is not True
    assert isinstance(body.get("object_types"), list)

    # Facade 别名
    fb = backup_knowledge_seed_authority_snapshot(tenant_id="t-migrate")
    assert fb["status"] == "ok"
    fl = list_knowledge_seed_authority_backups(tenant_id="t-migrate")
    assert fl["status"] == "ok"
    fr = restore_knowledge_seed_authority_snapshot(
        tenant_id="t-migrate",
        backup_id=bid,
    )
    assert fr["status"] == "ok"


def test_docs_and_wiring_state():
    mod = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge_pipeline"
        / "object_type_publish.py"
    )
    text = mod.read_text(encoding="utf-8")
    assert "apply_published_seed_authority_product" in text
    assert "backup_seed_authority_snapshot" in text
    assert "restore_seed_authority_snapshot" in text
    assert "seed_migrate_rollback" in text
    assert "seed_migrate_backup" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    facade_text = facade.read_text(encoding="utf-8")
    assert "backup_knowledge_seed_authority_snapshot" in facade_text
    assert "restore_knowledge_seed_authority_snapshot" in facade_text
    routes = (
        ROOT
        / "aiPlat-platform"
        / "apps"
        / "fde"
        / "api"
        / "object_type_publish_routes.py"
    )
    routes_text = routes.read_text(encoding="utf-8")
    assert "object-types/product/seed-authority/backup" in routes_text
    assert "object-types/product/seed-authority/restore" in routes_text
    panel = (
        ROOT
        / "aiPlat-management"
        / "frontend"
        / "src"
        / "pages"
        / "KnowledgeFactory"
        / "ObjectTypePublishPanel.tsx"
    )
    panel_text = panel.read_text(encoding="utf-8")
    assert "object-types/product/seed-files" in panel_text
    assert "seed-authority/backup" in panel_text or "Backup" in panel_text
    evidence = (
        ROOT
        / "reports"
        / "products"
        / "knowledge-system"
        / "v4.3.1"
        / "phase2-n02-seed-authority-product-slice2-evidence.md"
    )
    assert evidence.is_file()
    ev = evidence.read_text(encoding="utf-8")
    assert "seed_migrate_rollback" in ev
    assert "seed_migrate_restore" in ev
