"""Ontology API v0 — public exchange envelope for entity/relation/graph/wiki/asset.

SSOT: reports/five-products/modules/ontology/contracts/schemas/ontology_api.schema.json
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, MutableMapping, Optional


SCHEMA_VERSION = "ontology.api.v0"
_KINDS = frozenset({"entity", "relation", "graph", "wiki", "asset", "query_result"})


def to_ontology_api_v0(
    *,
    kind: str,
    payload: Optional[Mapping[str, Any]] = None,
    domain_id: str = "",
    refs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    k = str(kind or "query_result").strip().lower()
    if k not in _KINDS:
        k = "query_result"
    out: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": k,
        "payload": dict(payload) if isinstance(payload, Mapping) else {},
    }
    if domain_id:
        out["domain_id"] = str(domain_id)
    if refs:
        out["refs"] = [str(x) for x in refs if x is not None]
    return out


def from_structured_query(result: Mapping[str, Any], *, domain_id: str = "") -> Dict[str, Any]:
    """Wrap wiki structured_query dict as ontology.api.v0 query_result."""
    res = dict(result) if isinstance(result, Mapping) else {}
    refs: List[str] = []
    for key in ("page", "title", "source", "wiki_path"):
        if res.get(key):
            refs.append(str(res[key]))
    nested = res.get("result")
    if isinstance(nested, Mapping):
        for key in ("title", "page", "id"):
            if nested.get(key):
                refs.append(str(nested[key]))
    return to_ontology_api_v0(
        kind="query_result",
        payload=res,
        domain_id=domain_id,
        refs=refs or None,
    )


def from_wiki_pages(
    pages: List[Mapping[str, Any]],
    *,
    query: str = "",
    collection_id: str = "default",
) -> Dict[str, Any]:
    items = [dict(p) for p in (pages or []) if isinstance(p, Mapping)]
    refs = []
    for p in items[:20]:
        for key in ("title", "path", "id"):
            if p.get(key):
                refs.append(str(p[key]))
                break
    return to_ontology_api_v0(
        kind="wiki",
        payload={"query": query, "collection_id": collection_id, "items": items, "total": len(items)},
        domain_id=collection_id if collection_id and collection_id != "default" else "",
        refs=refs or None,
    )


def from_graph_health(health: Mapping[str, Any], *, domain_id: str = "") -> Dict[str, Any]:
    h = dict(health) if isinstance(health, Mapping) else {}
    did = str(domain_id or h.get("domain") or "")
    return to_ontology_api_v0(
        kind="graph",
        payload=h,
        domain_id=did,
        refs=[did] if did else None,
    )


def attach_ontology_api(
    response: MutableMapping[str, Any],
    envelope: Mapping[str, Any],
) -> MutableMapping[str, Any]:
    """Attach envelope under `ontology_api` without removing legacy fields."""
    response["ontology_api"] = dict(envelope)
    return response


def to_ontology_healthz(
    *,
    status: str = "ok",
    version: str = "0.0.0",
    domains: int = 0,
    mode: str = "read_only",
) -> Dict[str, Any]:
    """Ontology capability healthz (A1/D1 co-hosted on Central)."""
    st = str(status or "ok").strip().lower()
    if st in {"healthy", "up", "pass", "passed", "success"}:
        st = "ok"
    elif st not in {"ok", "degraded", "fail"}:
        st = "degraded"
    md = str(mode or "read_only").strip().lower()
    if md not in {"read_only", "read_write"}:
        md = "read_only"
    return {
        "status": st,
        "version": str(version or "0.0.0"),
        "product_id": "ontology",
        "capability_id": "ontology",
        "deploy_unit": "central",
        "domains": max(0, int(domains or 0)),
        "mode": md,
    }
