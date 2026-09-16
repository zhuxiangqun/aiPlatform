"""retail-ops demo seed — Phase 2 isomorphic second domain (Path C)."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict

_CLS_SVC = "服务"
_CLS_MW = "中间件"
_CLS_HOST = "主机"
_CLS_ALERT = "告警"

_log = logging.getLogger(__name__)


def _aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def _workspace_yaml() -> Path:
    return Path(__file__).resolve().parents[4] / "workspace_seeds" / "ontologies" / "retail-ops.yaml"


def ensure_retail_ops_ontology(*, force: bool = False) -> Dict[str, Any]:
    src = _workspace_yaml()
    dest_dir = _aiplat_home() / "ontologies"
    dest = dest_dir / "retail-ops.yaml"
    out: Dict[str, Any] = {"src": str(src), "dest": str(dest), "action": "noop"}
    if not src.is_file():
        out["action"] = "missing_seed"
        return out
    need = force or not dest.is_file()
    if not need:
        try:
            text = dest.read_text(encoding="utf-8")
            if "label: 告警" not in text and "label:告警" not in text:
                need = True
        except OSError:
            need = True
    if not need:
        return out
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    out["action"] = "installed"
    # registry fragment
    reg_path = dest_dir / "registry.json"
    try:
        import json

        reg = json.loads(reg_path.read_text(encoding="utf-8")) if reg_path.exists() else {"domains": {}}
        reg.setdefault("domains", {})["retail-ops"] = {
            "name": "零售运营故障诊断",
            "description": "POS/门店告警分诊竖切（Phase 2 同构）",
            "ontology_file": "retail-ops.yaml",
            "collection_id": "retail-ops",
            "namespace": "http://aiplat.local/ontology/retail-ops/",
            "maturity": "seeding",
        }
        reg_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        out["registry"] = "updated"
    except Exception:
        _log.debug("registry update skipped", exc_info=True)
    return out


def seed_retail_ops_demo_graph(
    g: Any,
    *,
    primary_alert_id: str = "ALT-POS-TIMEOUT",
    ensure_ontology: bool = True,
) -> Dict[str, Any]:
    """Minimal call-path: POS-API → payment-gw → Redis @ host + one alert."""
    onto: Dict[str, Any] = {}
    if ensure_ontology:
        onto = ensure_retail_ops_ontology()
        if hasattr(g, "_class_labels_cache"):
            delattr(g, "_class_labels_cache")

    entities = [
        ("SVC-POS-API", "POS下单API", _CLS_SVC),
        ("SVC-PAY", "支付网关", _CLS_SVC),
        ("MW-Redis", "门店Redis", _CLS_MW),
        ("HOST-STORE-1", "门店主机1", _CLS_HOST),
    ]
    for eid, name, cls in entities:
        g.add_entity(eid, name, cls, source_doc_id="retail-demo")
    g.add_relation("SVC-POS-API", "SVC-PAY", "calls", relation_label="calls")
    g.add_relation("SVC-PAY", "MW-Redis", "calls", relation_label="calls")
    g.add_relation("MW-Redis", "HOST-STORE-1", "deployed_on", relation_label="deployed_on")

    g.add_entity(primary_alert_id, "POS超时告警", _CLS_ALERT, source_doc_id="retail-demo")
    g.add_entity_property(primary_alert_id, "state", "open")
    g.add_entity_property(primary_alert_id, "status", "open")
    g.add_entity_property(primary_alert_id, "system_name", "门店POS")

    return {
        "profile": "minimal",
        "primary_alert_id": primary_alert_id,
        "default_root": "MW-Redis",
        "ontology_ensure": onto,
        "alerts": [primary_alert_id],
    }
