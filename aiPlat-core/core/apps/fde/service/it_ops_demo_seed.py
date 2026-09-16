"""it-ops demo GraphIndex seeds (AcceptTab / tests) — 路径 C：已有说明书 → 写入真实层。

本体不「生成」实例；本模块按固定场景模板写入，类/边必须 ∈ 故障诊断版 it-ops.yaml。
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

# class labels must match workspace_seeds/ontologies/it-ops.yaml Chinese labels
_CLS_SVC = "服务"
_CLS_MW = "中间件"
_CLS_HOST = "主机"
_CLS_ALERT = "告警"

_log = logging.getLogger(__name__)


def _aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def _workspace_fault_it_ops_yaml() -> Path:
    # .../aiPlat-core/core/apps/fde/service/this.py → aiPlat-core/
    return Path(__file__).resolve().parents[4] / "workspace_seeds" / "ontologies" / "it-ops.yaml"


def ensure_it_ops_fault_ontology(*, force: bool = False) -> Dict[str, Any]:
    """Install fault-diagnosis it-ops.yaml into AIPLAT_HOME if Alert class missing.

    Local `~/.aiplat/ontologies/it-ops.yaml` may be a different「IT运维知识」本体
    (基础设施/配置项…). Path C demo needs 告警/服务/中间件/主机.
    """
    src = _workspace_fault_it_ops_yaml()
    dest_dir = _aiplat_home() / "ontologies"
    dest = dest_dir / "it-ops.yaml"
    out: Dict[str, Any] = {"src": str(src), "dest": str(dest), "action": "noop"}

    if not src.is_file():
        out["action"] = "missing_seed"
        _log.warning("it-ops fault ontology seed missing: %s", src)
        return out

    need_install = force or not dest.is_file()
    if not need_install:
        try:
            text = dest.read_text(encoding="utf-8")
            # fault seed has label 告警 under Alert; knowledge ontology does not
            if "label: 告警" not in text and "label:告警" not in text:
                need_install = True
                out["reason"] = "installed_yaml_missing_alert_class"
        except OSError as e:
            need_install = True
            out["reason"] = str(e)

    if not need_install:
        return out

    dest_dir.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        bak = dest_dir / "it-ops.knowledge-bak.yaml"
        shutil.copy2(dest, bak)
        out["backup"] = str(bak)
    shutil.copy2(src, dest)
    out["action"] = "installed"
    _log.info("installed fault-diagnosis it-ops ontology → %s (backup=%s)", dest, out.get("backup"))
    return out


def seed_it_ops_demo_graph(
    g: Any,
    *,
    profile: str = "minimal",
    primary_alert_id: str,
    primary_alert_name: str = "积分系统告警（演示）",
    primary_state: str = "open",
    source_doc_id: str = "ui-demo",
    ensure_ontology: bool = True,
) -> Dict[str, Any]:
    """Write call-path (+ optional complex flood) into GraphIndex ``g``.

    Profiles:
      - minimal: cast-query → cast-action → redis @ host + one alert
      - complex: B3.2 teaching topology (multi-alert, fork, noise) aligned to docs
    """
    onto_meta: Dict[str, Any] = {}
    if ensure_ontology:
        onto_meta = ensure_it_ops_fault_ontology()
        # drop class-label cache so GraphIndex re-reads YAML after install
        if hasattr(g, "_class_labels_cache"):
            delattr(g, "_class_labels_cache")

    profile = (profile or "minimal").strip().lower()
    if profile not in ("minimal", "complex"):
        raise ValueError(f"unsupported it-ops demo profile: {profile}")

    if profile == "minimal":
        meta = _seed_minimal(
            g,
            primary_alert_id=primary_alert_id,
            primary_alert_name=primary_alert_name,
            primary_state=primary_state,
            source_doc_id=source_doc_id,
        )
    else:
        meta = _seed_complex(
            g,
            primary_alert_id=primary_alert_id,
            primary_alert_name=primary_alert_name,
            primary_state=primary_state,
            source_doc_id=source_doc_id,
        )
    meta["ontology_ensure"] = onto_meta
    return meta


def _ensure_entity(g: Any, eid: str, name: str, cls: str, source_doc_id: str) -> None:
    if eid not in g._nodes:
        g.add_entity(eid, name, cls, source_doc_id=source_doc_id)


def _seed_minimal(
    g: Any,
    *,
    primary_alert_id: str,
    primary_alert_name: str,
    primary_state: str,
    source_doc_id: str,
) -> Dict[str, Any]:
    topo: List[Tuple[str, str, str]] = [
        ("SVC-CAST-QUERY", "cast-query", _CLS_SVC),
        ("SVC-CAST-ACTION", "cast-action", _CLS_SVC),
        ("MW-REDIS-1", "redis-1", _CLS_MW),
        ("HOST-1", "10.0.0.8", _CLS_HOST),
    ]
    for tid, tname, tcls in topo:
        _ensure_entity(g, tid, tname, tcls, source_doc_id)
    g.add_relation("SVC-CAST-QUERY", "SVC-CAST-ACTION", "calls", relation_label="调用")
    g.add_relation("SVC-CAST-ACTION", "MW-REDIS-1", "calls", relation_label="调用")
    g.add_relation("MW-REDIS-1", "HOST-1", "deployed_on", relation_label="部署于")

    g.add_entity(primary_alert_id, primary_alert_name, _CLS_ALERT, source_doc_id=source_doc_id)
    g.add_entity_property(primary_alert_id, "state", primary_state)
    g.add_entity_property(primary_alert_id, "status", primary_state)
    g.add_entity_property(primary_alert_id, "system_name", "积分系统")
    g.add_entity_property(primary_alert_id, "service_name", "SVC-CAST-QUERY")

    return {
        "profile": "minimal",
        "topology": [t[0] for t in topo],
        "alerts": [primary_alert_id],
        "default_root": "MW-REDIS-1",
        "primary_alert_id": primary_alert_id,
    }


def _seed_complex(
    g: Any,
    *,
    primary_alert_id: str,
    primary_alert_name: str,
    primary_state: str,
    source_doc_id: str,
) -> Dict[str, Any]:
    """Teaching topology ≈ ONTOLOGY_PPT_SCENARIOS B3.2 (path C template)."""
    entities: List[Tuple[str, str, str]] = [
        ("SVC-网关", "gateway", _CLS_SVC),
        ("SVC-查询", "cast-query", _CLS_SVC),
        ("SVC-动作", "cast-action", _CLS_SVC),
        ("SVC-通知", "notify", _CLS_SVC),
        ("MW-Redis主", "redis-primary", _CLS_MW),
        ("MW-Redis从", "redis-replica", _CLS_MW),
        ("MW-MySQL", "mysql-orders", _CLS_MW),
        ("HOST-8", "10.0.0.8", _CLS_HOST),
        ("HOST-9", "10.0.0.9", _CLS_HOST),
        ("HOST-批处理", "10.0.0.20", _CLS_HOST),
    ]
    for tid, tname, tcls in entities:
        _ensure_entity(g, tid, tname, tcls, source_doc_id)

    edges = [
        ("SVC-网关", "SVC-查询", "calls", "调用"),
        ("SVC-查询", "SVC-动作", "calls", "调用"),
        ("SVC-查询", "SVC-通知", "calls", "调用"),
        ("SVC-动作", "MW-Redis主", "calls", "调用"),
        ("SVC-动作", "MW-MySQL", "calls", "调用"),
        ("SVC-通知", "MW-Redis从", "calls", "调用"),
        ("MW-Redis主", "HOST-8", "deployed_on", "部署于"),
        ("MW-MySQL", "HOST-9", "deployed_on", "部署于"),
    ]
    for src, dst, rel, label in edges:
        g.add_relation(src, dst, rel, relation_label=label)

    g.add_entity_property("MW-Redis主", "pool_util", "98")
    g.add_entity_property("MW-Redis从", "healthy", "true")

    alerts_meta = [
        (primary_alert_id, primary_alert_name or "ALT-主·查询超时", "SVC-查询"),
        (f"{primary_alert_id}-ERR", "ALT-错误率", "SVC-查询"),
        (f"{primary_alert_id}-LAT", "ALT-延迟", "SVC-动作"),
        (f"{primary_alert_id}-SQL", "ALT-慢SQL", "MW-MySQL"),
        (f"{primary_alert_id}-DISK", "ALT-磁盘", "HOST-批处理"),
    ]
    alert_ids: List[str] = []
    for aid, aname, svc in alerts_meta:
        g.add_entity(aid, aname, _CLS_ALERT, source_doc_id=source_doc_id)
        st = primary_state if aid == primary_alert_id else "open"
        g.add_entity_property(aid, "state", st)
        g.add_entity_property(aid, "status", st)
        g.add_entity_property(aid, "system_name", "积分系统")
        g.add_entity_property(aid, "service_name", svc)
        alert_ids.append(aid)

    return {
        "profile": "complex",
        "topology": [e[0] for e in entities],
        "alerts": alert_ids,
        "default_root": "MW-Redis主",
        "primary_alert_id": primary_alert_id,
    }


_ALLOWED_CLASSES = {_CLS_SVC, _CLS_MW, _CLS_HOST, _CLS_ALERT}
_ALLOWED_RELS = {"calls", "deployed_on", "suspects", "rooted_at"}


def load_it_ops_import_sample() -> Dict[str, Any]:
    """Load bundled monitor-style JSON sample (path B fixture)."""
    import json

    path = Path(__file__).resolve().parent / "fixtures" / "it_ops_alert_import_sample.json"
    return json.loads(path.read_text(encoding="utf-8"))


def import_it_ops_alert_payload(
    g: Any,
    payload: Dict[str, Any],
    *,
    source_doc_id: str = "monitor-import",
    ensure_ontology: bool = True,
) -> Dict[str, Any]:
    """Path B: write monitor/JSON payload into GraphIndex with class/rel checks.

    Delegates to domain-configurable ``import_abox_payload`` (connector allowlists).
    Expected payload shape (see fixtures/it_ops_alert_import_sample.json):
      entities: [{id, name, class, state?, props?}, ...]
      relations: [{from, to, rel, label?}, ...]
      primary_alert_id?, default_root?
    """
    from core.apps.fde.service.abox_connector import import_abox_payload

    onto_meta: Dict[str, Any] = {}
    if ensure_ontology:
        onto_meta = ensure_it_ops_fault_ontology()
        if hasattr(g, "_class_labels_cache"):
            delattr(g, "_class_labels_cache")

    meta = import_abox_payload(
        g,
        payload,
        allowed_classes=_ALLOWED_CLASSES,
        allowed_relations=_ALLOWED_RELS,
        source_doc_id=source_doc_id,
        primary_class=_CLS_ALERT,
    )
    meta["ontology_ensure"] = onto_meta
    return meta
