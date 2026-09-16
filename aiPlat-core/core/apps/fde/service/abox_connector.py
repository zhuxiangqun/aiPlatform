"""Path B ABox connector — domain-configurable GraphIndex import + webhook ingest.

Harness-agnostic: class/rel allowlists come from connector.json per domain,
not hardcoded domain_id branches in core/harness.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

_DEFAULT_IT_OPS = {
    "source_id": "monitor-alerts",
    "domain_id": "it-ops",
    "allowed_classes": ["服务", "中间件", "主机", "告警"],
    "allowed_relations": ["calls", "deployed_on", "suspects", "rooted_at"],
    "primary_class": "告警",
    "auth": {"type": "shared_secret_env", "env": "AIPLAT_ABOX_WEBHOOK_SECRET"},
}


def _aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def _workspace_connector_seed(domain_id: str) -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "connectors"
        / f"{domain_id}.json"
    )


def connector_path(domain_id: str) -> Path:
    return _aiplat_home() / "ontologies" / domain_id / "connector.json"


def ensure_connector_config(domain_id: str, *, force: bool = False) -> Dict[str, Any]:
    """Install workspace seed connector.json into AIPLAT_HOME when missing."""
    dest = connector_path(domain_id)
    src = _workspace_connector_seed(domain_id)
    out: Dict[str, Any] = {"domain_id": domain_id, "dest": str(dest), "action": "noop"}
    if dest.is_file() and not force:
        return {**out, **load_connector_config(domain_id)}
    if src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        out["action"] = "installed"
        out["src"] = str(src)
    elif domain_id == "it-ops":
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(_DEFAULT_IT_OPS, ensure_ascii=False, indent=2), encoding="utf-8")
        out["action"] = "default_it_ops"
    else:
        out["action"] = "missing"
        return out
    return {**out, **load_connector_config(domain_id)}


def load_connector_config(domain_id: str) -> Dict[str, Any]:
    path = connector_path(domain_id)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8")) or {}
            data.setdefault("domain_id", domain_id)
            return data
        except Exception:
            logger.warning("load_connector_config failed for %s", domain_id, exc_info=True)
    seed = _workspace_connector_seed(domain_id)
    if seed.is_file():
        try:
            data = json.loads(seed.read_text(encoding="utf-8")) or {}
            data.setdefault("domain_id", domain_id)
            return data
        except Exception:
            logger.warning("load seed connector failed for %s", domain_id, exc_info=True)
    if domain_id == "it-ops":
        return dict(_DEFAULT_IT_OPS)
    return {
        "source_id": f"{domain_id}-ingest",
        "domain_id": domain_id,
        "allowed_classes": [],
        "allowed_relations": [],
        "primary_class": "",
    }


def find_domain_for_source(source_id: str) -> Optional[str]:
    """Resolve source_id → domain_id via installed connector.json files."""
    sid = (source_id or "").strip()
    if not sid:
        return None
    root = _aiplat_home() / "ontologies"
    if root.is_dir():
        for child in root.iterdir():
            if not child.is_dir():
                continue
            cfg_path = child / "connector.json"
            if not cfg_path.is_file():
                continue
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if str(cfg.get("source_id") or "").strip() == sid:
                return child.name
            aliases = cfg.get("source_aliases") or []
            if sid in [str(a).strip() for a in aliases]:
                return child.name
    # fallback: workspace seeds
    seeds = Path(__file__).resolve().parents[4] / "workspace_seeds" / "connectors"
    if seeds.is_dir():
        for p in seeds.glob("*.json"):
            try:
                cfg = json.loads(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if str(cfg.get("source_id") or "").strip() == sid:
                return str(cfg.get("domain_id") or p.stem)
    if sid in ("monitor-alerts", "it-ops-monitor"):
        return "it-ops"
    return None


def verify_webhook_secret(cfg: Dict[str, Any], provided: Optional[str]) -> bool:
    """Return True if secret check passes (or auth disabled / unset env)."""
    auth = cfg.get("auth") or {}
    if not auth or str(auth.get("type") or "") in ("", "none"):
        return True
    if str(auth.get("type")) == "shared_secret_env":
        env_name = str(auth.get("env") or "AIPLAT_ABOX_WEBHOOK_SECRET")
        expected = (os.getenv(env_name) or "").strip()
        if not expected:
            # Dev-friendly: unset secret → allow (document in PLAYBOOK)
            return True
        return (provided or "").strip() == expected
    return True


def import_abox_payload(
    g: Any,
    payload: Dict[str, Any],
    *,
    allowed_classes: Set[str],
    allowed_relations: Set[str],
    source_doc_id: str = "abox-import",
    primary_class: str = "",
) -> Dict[str, Any]:
    """Generic Path B writer. Receipt: created_entities / relations / skipped / primary_id."""
    created: List[str] = []
    skipped: List[Dict[str, str]] = []
    relations_ok: List[str] = []
    allow_cls = {str(c).strip() for c in allowed_classes if str(c).strip()}
    allow_rel = {str(r).strip() for r in allowed_relations if str(r).strip()}

    for raw in payload.get("entities") or []:
        if not isinstance(raw, dict):
            skipped.append({"id": "?", "reason": "entity_not_object"})
            continue
        eid = str(raw.get("id") or "").strip()
        cls = str(raw.get("class") or "").strip()
        name = str(raw.get("name") or eid).strip()
        if not eid or not cls:
            skipped.append({"id": eid or "?", "reason": "missing_id_or_class"})
            continue
        if allow_cls and cls not in allow_cls:
            skipped.append({"id": eid, "reason": f"class_not_allowed:{cls}"})
            continue
        if eid not in g._nodes:
            g.add_entity(eid, name, cls, source_doc_id=source_doc_id)
            created.append(eid)
        else:
            created.append(eid)
        state = str(raw.get("state") or "").strip()
        if state:
            g.add_entity_property(eid, "state", state)
            g.add_entity_property(eid, "status", state)
        props = raw.get("props") if isinstance(raw.get("props"), dict) else {}
        for pk, pv in props.items():
            g.add_entity_property(eid, str(pk), str(pv))
        sys_name = str(payload.get("system_name") or "").strip()
        if sys_name and (not primary_class or cls == primary_class):
            g.add_entity_property(eid, "system_name", sys_name)

    for raw in payload.get("relations") or []:
        if not isinstance(raw, dict):
            skipped.append({"id": "rel", "reason": "relation_not_object"})
            continue
        src = str(raw.get("from") or "").strip()
        dst = str(raw.get("to") or "").strip()
        rel = str(raw.get("rel") or "").strip()
        label = str(raw.get("label") or rel).strip()
        if not src or not dst or not rel:
            skipped.append({"id": f"{src}->{dst}", "reason": "incomplete_relation"})
            continue
        if allow_rel and rel not in allow_rel:
            skipped.append({"id": f"{src}->{dst}", "reason": f"rel_not_allowed:{rel}"})
            continue
        if src not in g._nodes or dst not in g._nodes:
            skipped.append({"id": f"{src}->{dst}", "reason": "endpoint_missing"})
            continue
        g.add_relation(src, dst, rel, relation_label=label)
        relations_ok.append(f"{src}-{rel}->{dst}")

    primary = str(
        payload.get("primary_alert_id")
        or payload.get("primary_id")
        or ""
    ).strip()
    if not primary and primary_class:
        for eid in created:
            node = g._nodes.get(eid)
            if node and node.class_name == primary_class:
                primary = eid
                break
    if not primary and created:
        primary = created[0]

    return {
        "profile": "import",
        "source": str(payload.get("source") or source_doc_id),
        "created_entities": sorted(set(created)),
        "relations": relations_ok,
        "skipped": skipped,
        "primary_id": primary,
        "primary_alert_id": primary,  # backward compat for it-ops UI
        "default_root": str(payload.get("default_root") or ""),
        "alerts": [
            eid
            for eid in sorted(set(created))
            if primary_class
            and g._nodes.get(eid)
            and g._nodes[eid].class_name == primary_class
        ],
    }


def parse_csv_text(csv_text: str) -> List[Dict[str, str]]:
    """Parse CSV text into list of row dicts (header required)."""
    import csv
    import io

    text = (csv_text or "").strip()
    if not text:
        return []
    reader = csv.DictReader(io.StringIO(text))
    rows: List[Dict[str, str]] = []
    for raw in reader:
        if not isinstance(raw, dict):
            continue
        rows.append({str(k).strip(): str(v).strip() if v is not None else "" for k, v in raw.items() if k})
    return rows


def map_table_rows_to_payload(
    rows: List[Dict[str, Any]],
    *,
    table_map: Optional[Dict[str, Any]] = None,
    relation_rows: Optional[List[Dict[str, Any]]] = None,
    source: str = "table-map",
) -> Dict[str, Any]:
    """Map tabular rows → Path B payload using connector ``table_map`` config.

    table_map keys (all optional with defaults):
      id_column, name_column, class_column, state_column
      class_default — used when class column empty
      prop_columns — list of column names → entity props
      relation_from / relation_to / relation_rel — for relation_rows column names
    """
    tm = dict(table_map or {})
    id_col = str(tm.get("id_column") or "id").strip() or "id"
    name_col = str(tm.get("name_column") or "name").strip() or "name"
    class_col = str(tm.get("class_column") or "class").strip() or "class"
    state_col = str(tm.get("state_column") or "state").strip() or "state"
    class_default = str(tm.get("class_default") or "").strip()
    prop_cols = [str(c).strip() for c in (tm.get("prop_columns") or []) if str(c).strip()]

    entities: List[Dict[str, Any]] = []
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        eid = str(raw.get(id_col) or raw.get("id") or "").strip()
        if not eid:
            continue
        cls = str(raw.get(class_col) or raw.get("class") or class_default or "").strip()
        name = str(raw.get(name_col) or raw.get("name") or eid).strip()
        ent: Dict[str, Any] = {"id": eid, "name": name, "class": cls}
        state = str(raw.get(state_col) or raw.get("state") or "").strip()
        if state:
            ent["state"] = state
        props: Dict[str, str] = {}
        for pc in prop_cols:
            if pc in raw and str(raw.get(pc) or "").strip():
                props[pc] = str(raw.get(pc)).strip()
        # pass through unknown scalar columns as props (except reserved)
        reserved = {id_col, name_col, class_col, state_col, "id", "name", "class", "state"}
        for k, v in raw.items():
            ks = str(k).strip()
            if ks in reserved or ks in props:
                continue
            if v is None or str(v).strip() == "":
                continue
            if ks not in prop_cols:
                continue  # only explicit prop_columns (avoid leaking noise)
        if props:
            ent["props"] = props
        entities.append(ent)

    relations: List[Dict[str, Any]] = []
    rel_from = str(tm.get("relation_from") or "from").strip() or "from"
    rel_to = str(tm.get("relation_to") or "to").strip() or "to"
    rel_rel = str(tm.get("relation_rel") or "rel").strip() or "rel"
    for raw in relation_rows or []:
        if not isinstance(raw, dict):
            continue
        src = str(raw.get(rel_from) or raw.get("from") or "").strip()
        dst = str(raw.get(rel_to) or raw.get("to") or "").strip()
        rel = str(raw.get(rel_rel) or raw.get("rel") or "").strip()
        if src and dst and rel:
            relations.append({"from": src, "to": dst, "rel": rel})

    return {
        "source": source,
        "entities": entities,
        "relations": relations,
    }


def load_table_map_sample(domain_id: str = "it-ops") -> Dict[str, Any]:
    """Bundled CSV + relation sample for demos (it-ops)."""
    fixture = (
        Path(__file__).resolve().parent
        / "fixtures"
        / f"{domain_id.replace('-', '_')}_table_map_sample.csv"
    )
    rel_fixture = (
        Path(__file__).resolve().parent
        / "fixtures"
        / f"{domain_id.replace('-', '_')}_table_map_relations.json"
    )
    csv_text = ""
    if fixture.is_file():
        csv_text = fixture.read_text(encoding="utf-8")
    else:
        # minimal inline fallback for it-ops
        csv_text = (
            "id,name,class,state\n"
            "SVC-TMAP-1,query-api,服务,\n"
            "MW-TMAP-1,redis-cache,中间件,\n"
            "ALT-TMAP-1,latency-spike,告警,open\n"
        )
    rows = parse_csv_text(csv_text)
    relation_rows: List[Dict[str, Any]] = []
    if rel_fixture.is_file():
        try:
            data = json.loads(rel_fixture.read_text(encoding="utf-8")) or {}
            relation_rows = list(data.get("relations") or data.get("relation_rows") or [])
        except Exception:
            logger.warning("load relation sample failed", exc_info=True)
    else:
        relation_rows = [
            {"from": "ALT-TMAP-1", "to": "SVC-TMAP-1", "rel": "suspects"},
            {"from": "SVC-TMAP-1", "to": "MW-TMAP-1", "rel": "calls"},
        ]
    return {"rows": rows, "relation_rows": relation_rows, "csv_text": csv_text}


def import_table_map_payload(
    g: Any,
    *,
    domain_id: str,
    rows: Optional[List[Dict[str, Any]]] = None,
    csv_text: Optional[str] = None,
    relation_rows: Optional[List[Dict[str, Any]]] = None,
    use_sample: bool = False,
    source_doc_id: str = "table-map",
) -> Dict[str, Any]:
    """Path B table/CSV → GraphIndex via connector allowlist + table_map."""
    ensure_connector_config(domain_id)
    cfg = load_connector_config(domain_id)
    table_map = cfg.get("table_map") if isinstance(cfg.get("table_map"), dict) else {}

    if use_sample and (not rows) and not (csv_text or "").strip():
        sample = load_table_map_sample(domain_id)
        rows = sample["rows"]
        relation_rows = relation_rows or sample["relation_rows"]

    if csv_text and not rows:
        rows = parse_csv_text(csv_text)

    if not rows:
        return {
            "profile": "table_map",
            "created_entities": [],
            "relations": [],
            "skipped": [{"id": "?", "reason": "empty_rows"}],
            "primary_id": "",
            "primary_alert_id": "",
        }

    payload = map_table_rows_to_payload(
        rows,
        table_map=table_map,
        relation_rows=relation_rows,
        source=source_doc_id,
    )
    allow_cls = set(cfg.get("allowed_classes") or [])
    allow_rel = set(cfg.get("allowed_relations") or [])
    meta = import_abox_payload(
        g,
        payload,
        allowed_classes=allow_cls,
        allowed_relations=allow_rel,
        source_doc_id=source_doc_id,
        primary_class=str(cfg.get("primary_class") or ""),
    )
    meta["profile"] = "table_map"
    meta["source_type"] = "table_map"
    return meta


def ingest_webhook_payload(
    source_id: str,
    payload: Dict[str, Any],
    *,
    secret: Optional[str] = None,
    domain_id: Optional[str] = None,
    graph_factory: Any = None,
) -> Dict[str, Any]:
    """Production Path B entry: resolve connector → write GraphIndex → receipt."""
    did = (domain_id or find_domain_for_source(source_id) or "").strip()
    if not did:
        return {
            "status": "rejected",
            "reason": f"unknown source_id={source_id}",
            "created_entities": [],
            "relations": [],
            "skipped": [],
            "primary_id": "",
        }

    ensure_connector_config(did)
    cfg = load_connector_config(did)
    if not verify_webhook_secret(cfg, secret):
        return {
            "status": "unauthorized",
            "reason": "webhook_secret_mismatch",
            "domain_id": did,
            "created_entities": [],
            "relations": [],
            "skipped": [],
            "primary_id": "",
        }

    # Optional it-ops ontology ensure (domain-specific helper, not harness)
    if did == "it-ops":
        try:
            from core.apps.fde.service.it_ops_demo_seed import ensure_it_ops_fault_ontology

            ensure_it_ops_fault_ontology()
        except Exception:
            logger.debug("ensure_it_ops_fault_ontology skipped", exc_info=True)

    if graph_factory is None:
        from core.harness.ontology_engine.graph_index import GraphIndex

        GraphIndex._loaded_instances.clear()
        g = GraphIndex.load(did)
    else:
        g = graph_factory(did)

    allow_cls = set(cfg.get("allowed_classes") or [])
    allow_rel = set(cfg.get("allowed_relations") or [])
    primary_class = str(cfg.get("primary_class") or "")
    meta = import_abox_payload(
        g,
        payload,
        allowed_classes=allow_cls,
        allowed_relations=allow_rel,
        source_doc_id=str(payload.get("source") or source_id or "webhook"),
        primary_class=primary_class,
    )
    if hasattr(g, "save"):
        g.save()
    return {
        "status": "imported",
        "path": "B",
        "source_id": source_id,
        "domain_id": did,
        **meta,
    }
