"""data-gov demo GraphIndex seeds — B4 治理教学真实层（路径 C）+ ACL 种子."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List

_log = logging.getLogger(__name__)

_CLS_ASSET = "数据资产"
_CLS_TBL = "物理表"
_CLS_CAT = "目录条目"
_CLS_DRAFT = "抽取草稿"


def _aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def _workspace_data_gov_yaml() -> Path:
    return Path(__file__).resolve().parents[4] / "workspace_seeds" / "ontologies" / "data-gov.yaml"


def ensure_data_gov_ontology(*, force: bool = False) -> Dict[str, Any]:
    src = _workspace_data_gov_yaml()
    dest_dir = _aiplat_home() / "ontologies"
    dest = dest_dir / "data-gov.yaml"
    out: Dict[str, Any] = {"src": str(src), "dest": str(dest), "action": "noop"}
    if not src.is_file():
        out["action"] = "missing_seed"
        return out
    need = force or not dest.is_file()
    if not need:
        try:
            text = dest.read_text(encoding="utf-8")
            if "label: 数据资产" not in text:
                need = True
        except Exception:
            need = True
    if need:
        dest_dir.mkdir(parents=True, exist_ok=True)
        if dest.is_file():
            bak = dest_dir / "data-gov.bak.yaml"
            shutil.copy2(dest, bak)
            out["backup"] = str(bak)
        shutil.copy2(src, dest)
        out["action"] = "installed"
    return out


def seed_data_gov_demo_graph(
    g: Any,
    *,
    source_doc_id: str = "data-gov-demo",
    ensure_ontology: bool = True,
    seed_acl: bool = True,
) -> Dict[str, Any]:
    """B4.3 teaching subset: mainline asset + ghost + wrong catalog + draft."""
    onto_meta: Dict[str, Any] = {}
    if ensure_ontology:
        onto_meta = ensure_data_gov_ontology()
        if hasattr(g, "_class_labels_cache"):
            delattr(g, "_class_labels_cache")

    entities: List[tuple] = [
        ("DA-账户", "账户资产", _CLS_ASSET),
        ("DA-积分流水", "积分流水", _CLS_ASSET),
        ("TBL-积分审计", "积分审计表", _CLS_TBL),
        ("TBL-tmp_export", "临时导出幽灵", _CLS_TBL),
        ("CAT-积分流水", "积分流水目录", _CLS_CAT),
        ("CAT-流水旧版", "流水旧版错挂", _CLS_CAT),
        ("DRAFT-流水抽取", "流水抽取草稿", _CLS_DRAFT),
    ]
    for eid, name, cls in entities:
        if eid not in g._nodes:
            g.add_entity(eid, name, cls, source_doc_id=source_doc_id)

    g.add_entity_property("DA-账户", "state", "cataloged")
    g.add_entity_property("DA-账户", "status", "cataloged")
    g.add_entity_property("DA-积分流水", "state", "meta_ready")
    g.add_entity_property("DA-积分流水", "status", "meta_ready")
    g.add_entity_property("DA-积分流水", "owner_contact", "ops@example.com")
    g.add_entity_property("TBL-积分审计", "state", "raw")
    g.add_entity_property("TBL-tmp_export", "state", "raw")
    g.add_entity_property("TBL-tmp_export", "ghost", "true")
    g.add_entity_property("CAT-流水旧版", "wrong_mount", "true")
    g.add_entity_property("DRAFT-流水抽取", "state", "pending")

    g.add_relation("DA-账户", "DA-积分流水", "feeds", relation_label="业务供给")
    g.add_relation("DA-积分流水", "TBL-积分审计", "feeds", relation_label="业务供给")
    g.add_relation("DA-账户", "DA-积分流水", "lineage", relation_label="血缘")
    g.add_relation("DRAFT-流水抽取", "DA-积分流水", "describes", relation_label="描述")
    # wrong mount as soft edge for teaching (still mounts relation)
    g.add_relation("DA-积分流水", "CAT-流水旧版", "mounts", relation_label="错挂")

    acl_meta: Dict[str, Any] = {}
    if seed_acl:
        from core.policy.graph_abox_acl import seed_demo_data_gov_acl

        acl_meta = seed_demo_data_gov_acl("data-gov")

    return {
        "profile": "data-gov-b4",
        "primary_asset_id": "DA-积分流水",
        "ghost_id": "TBL-tmp_export",
        "catalog_id": "CAT-积分流水",
        "topology": [e[0] for e in entities],
        "ontology_ensure": onto_meta,
        "acl_seeded": bool(acl_meta.get("entities")),
    }
