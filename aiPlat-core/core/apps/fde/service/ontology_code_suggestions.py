"""Code/ER → ontology proposal drafts (Path A suggestion only).

Never applies YAML or writes GraphIndex. Human must approve → apply.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CLASS_HINT = re.compile(
    r"(?:class|entity|表|实体)\s*[:=]?\s*[`\"']?([A-Za-z_][\w]{2,64}|[\u4e00-\u9fff]{2,32})",
    re.IGNORECASE,
)


def suggest_classes_from_snippets(
    domain_id: str,
    *,
    snippets: Optional[List[str]] = None,
    file_paths: Optional[List[str]] = None,
    author: str = "code-suggest",
    enqueue: bool = False,
) -> Dict[str, Any]:
    """Scan text/code snippets for class-like names → proposal draft.

    When enqueue=True, creates a VersionedOntologyStore draft proposal (not applied).
    """
    did = (domain_id or "").strip() or "default"
    texts: List[str] = list(snippets or [])
    for fp in file_paths or []:
        p = Path(fp)
        if p.is_file() and p.stat().st_size < 512_000:
            try:
                texts.append(p.read_text(encoding="utf-8", errors="ignore")[:80_000])
            except Exception:
                logger.debug("skip unreadable %s", fp, exc_info=True)

    found: List[str] = []
    seen = set()
    for t in texts:
        for m in _CLASS_HINT.finditer(t or ""):
            name = (m.group(1) or "").strip()
            if not name or name.lower() in seen:
                continue
            # skip common noise
            if name.lower() in {"self", "true", "false", "none", "null", "type", "string"}:
                continue
            seen.add(name.lower())
            found.append(name)
            if len(found) >= 12:
                break
        if len(found) >= 12:
            break

    if not found and not texts:
        # deterministic demo suggestions when no input (PLAYBOOK)
        found = ["ServiceEndpoint", "AlertEvent"]

    suggestions = []
    for name in found:
        safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)[:64] or "SuggestedClass"
        suggestions.append(
            {
                "kind": "new_class",
                "name": safe,
                "label": name,
                "tier": "edge",
                "description": f"Suggested from code/doc scan for domain {did}",
                "apply_path": "proposal",
                "auto_apply": False,
            }
        )

    proposal_id: Optional[str] = None
    if enqueue and suggestions:
        try:
            import asyncio

            from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore

            store = VersionedOntologyStore(did)
            first = suggestions[0]
            changes = {
                "add": {
                    "class": {
                        "name": first["name"],
                        "label": first["label"],
                        "tier": "edge",
                        "required_fields": ["name"],
                        "description": first["description"],
                    }
                }
            }

            async def _create() -> str:
                return await store.create_proposal(changes, author=author)

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                # caller should use suggest_classes_from_snippets_async
                proposal_id = None
            else:
                proposal_id = asyncio.run(_create())
        except Exception:
            logger.warning("enqueue code suggestion proposal failed", exc_info=True)

    return {
        "status": "draft",
        "domain_id": did,
        "suggestions": suggestions,
        "proposal_id": proposal_id,
        "authority_note": "仅提案草稿；禁止自动 apply；落图须 Action/confirm",
        "auto_apply": False,
    }


async def suggest_classes_from_snippets_async(
    domain_id: str,
    *,
    snippets: Optional[List[str]] = None,
    file_paths: Optional[List[str]] = None,
    author: str = "code-suggest",
    enqueue: bool = True,
) -> Dict[str, Any]:
    """Async variant that can enqueue a draft proposal."""
    base = suggest_classes_from_snippets(
        domain_id,
        snippets=snippets,
        file_paths=file_paths,
        author=author,
        enqueue=False,
    )
    if not enqueue or not base.get("suggestions"):
        return base
    try:
        from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore

        store = VersionedOntologyStore(domain_id)
        first = base["suggestions"][0]
        proposal_id = await store.create_proposal(
            {
                "add": {
                    "class": {
                        "name": first["name"],
                        "label": first["label"],
                        "tier": "edge",
                        "required_fields": ["name"],
                        "description": first["description"],
                    }
                }
            },
            author=author,
        )
        base["proposal_id"] = proposal_id
        base["enqueue_status"] = "draft"
    except Exception as e:
        logger.warning("async enqueue code suggestion failed", exc_info=True)
        # Still return a local draft id so callers have a review handle (not applied)
        import time

        first = base["suggestions"][0]
        base["proposal_id"] = f"draft_local_{domain_id}_{first['name']}_{int(time.time())}"
        base["enqueue_status"] = "local_draft"
        base["enqueue_error"] = type(e).__name__
    return base


_COL_NOISE = {
    "",
    "id",
    "pk",
    "created_at",
    "updated_at",
    "deleted_at",
    "tenant_id",
}

# Step-② heuristic gloss (suggestion layer only — not claimed completeness %)
_COL_GLOSS = {
    "service_name": "所属服务名称（告警/指标挂载点）",
    "service": "服务标识",
    "severity": "严重级别（如 critical/warning）",
    "state": "生命周期状态",
    "status": "业务状态",
    "host_name": "主机名",
    "hostname": "主机名",
    "cpu_pct": "CPU 使用率（%）",
    "pool_util": "连接池利用率",
    "amount": "金额",
    "order_id": "订单标识",
    "catalog_id": "目录条目标识",
    "asset_name": "数据资产名称",
    "table_name": "物理表名",
    "db_name": "数据库名",
    "schema_name": "库模式/schema",
    "owner": "责任人/归属",
    "lineage": "血缘线索（建议字段）",
}


def enrich_column_meanings(
    columns: List[str],
    sample_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, str]:
    """Heuristic column → business gloss (Xingye step ② shape; not LLM authority)."""
    meanings: Dict[str, str] = {}
    rows = list(sample_rows or [])
    for col in columns:
        key = (col or "").strip()
        if not key:
            continue
        low = key.lower()
        if low in _COL_GLOSS:
            meanings[key] = _COL_GLOSS[low]
            continue
        # sample hint
        sample_vals = []
        for row in rows[:3]:
            if isinstance(row, dict) and key in row and row[key] not in (None, ""):
                sample_vals.append(str(row[key])[:40])
        if re.search(r"[\u4e00-\u9fff]", key):
            meanings[key] = f"业务字段「{key}」" + (
                f"；样例: {', '.join(sample_vals)}" if sample_vals else ""
            )
        elif low.endswith("_id") or low.endswith("id"):
            meanings[key] = f"标识字段；样例: {', '.join(sample_vals)}" if sample_vals else "标识字段"
        elif low.endswith("_at") or "time" in low or "date" in low:
            meanings[key] = "时间戳/日期类字段"
        else:
            meanings[key] = (
                f"待确认业务含义"
                + (f"；样例: {', '.join(sample_vals)}" if sample_vals else "（无样例）")
            )
    return meanings


def _sanitize_ident(raw: str, *, fallback: str = "SuggestedClass") -> str:
    s = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in (raw or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")[:64]
    return s or fallback


def _table_to_class_name(table: str) -> str:
    """alert_events / 告警表 → AlertEvent / 告警表-safe."""
    t = (table or "").strip()
    if not t:
        return "ImportedTable"
    if re.search(r"[\u4e00-\u9fff]", t):
        return _sanitize_ident(t, fallback="ImportedTable")
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", t) if p]
    if not parts:
        return _sanitize_ident(t, fallback="ImportedTable")
    last = parts[-1]
    if len(last) > 3 and last.lower().endswith("s") and not last.lower().endswith("ss"):
        parts[-1] = last[:-1]
    return "".join(p[:1].upper() + p[1:] for p in parts)[:64] or "ImportedTable"


def _normalize_columns(columns: Optional[List[Any]]) -> List[str]:
    out: List[str] = []
    seen = set()
    for c in columns or []:
        name = str(c or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(name)
        if len(out) >= 24:
            break
    return out


def suggest_classes_from_table_schema(
    domain_id: str,
    *,
    table_name: str = "",
    columns: Optional[List[str]] = None,
    csv_text: str = "",
    sample_rows: Optional[List[Dict[str, Any]]] = None,
    author: str = "schema-suggest",
    enqueue: bool = False,
) -> Dict[str, Any]:
    """Table/CSV header → edge-tier class suggestion (Path A draft only).

    Never writes GraphIndex and never auto-applies live YAML.
    Use Path B ``table_map`` ingest separately when you need instances.
    """
    did = (domain_id or "").strip() or "default"
    cols = _normalize_columns(columns)
    rows: List[Dict[str, Any]] = list(sample_rows or [])

    if (csv_text or "").strip():
        try:
            from core.apps.fde.service.abox_connector import parse_csv_text

            parsed = parse_csv_text(csv_text)
            if parsed:
                rows = parsed
                if not cols:
                    cols = _normalize_columns(list(parsed[0].keys()))
        except Exception:
            logger.debug("csv parse for schema suggest failed", exc_info=True)

    if not cols and rows and isinstance(rows[0], dict):
        cols = _normalize_columns(list(rows[0].keys()))

    tname = (table_name or "").strip()
    if not tname and cols:
        tname = "imported_table"
    if not tname and not cols:
        tname = "alert_events"
        cols = ["id", "service_name", "severity", "state"]

    class_name = _table_to_class_name(tname)
    fields = [
        _sanitize_ident(c, fallback=f"field_{i}")
        for i, c in enumerate(cols)
        if c.strip().lower() not in _COL_NOISE
    ][:12]
    if not fields:
        fields = ["name"]

    meanings = enrich_column_meanings(cols, rows)
    meaning_lines = "; ".join(f"{k}={v}" for k, v in list(meanings.items())[:8])
    description = (
        f"Suggested from table/CSV schema '{tname}' for domain {did}; "
        f"AI补齐(启发式): {meaning_lines or '—'}; "
        "Path A proposal only — not GraphIndex ingest"
    )

    suggestion = {
        "kind": "new_class",
        "name": class_name,
        "label": tname or class_name,
        "tier": "edge",
        "required_fields": fields,
        "columns": cols,
        "field_meanings": meanings,
        "table_name": tname,
        "sample_row_count": len(rows),
        "description": description,
        "enrichment": {
            "mode": "heuristic",
            "note": "建议层≠权威元数据补齐；禁止宣称材料补齐率 KPI",
        },
        "apply_path": "proposal",
        "auto_apply": False,
        "authority_note": "表头建议≠数据库建成本体；入轨写图请走 Path B table_map",
    }

    return {
        "status": "draft",
        "domain_id": did,
        "suggestions": [suggestion],
        "proposal_id": None,
        "auto_apply": False,
        "writes_graph": False,
        "step2_enrichment": True,
        "authority_note": (
            "仅提案草稿；禁止自动 apply；禁止把本接口当 Path B 入轨；"
            "落图须 graph/import table_map 或 Action"
        ),
        "author": author,
        "enqueue": bool(enqueue),
    }


async def suggest_classes_from_table_schema_async(
    domain_id: str,
    *,
    table_name: str = "",
    columns: Optional[List[str]] = None,
    csv_text: str = "",
    sample_rows: Optional[List[Dict[str, Any]]] = None,
    author: str = "schema-suggest",
    enqueue: bool = True,
) -> Dict[str, Any]:
    """Async: optional VersionedOntologyStore draft (never apply)."""
    base = suggest_classes_from_table_schema(
        domain_id,
        table_name=table_name,
        columns=columns,
        csv_text=csv_text,
        sample_rows=sample_rows,
        author=author,
        enqueue=False,
    )
    if not enqueue or not base.get("suggestions"):
        return base
    first = base["suggestions"][0]
    try:
        from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore

        store = VersionedOntologyStore(domain_id)
        proposal_id = await store.create_proposal(
            {
                "add": {
                    "class": {
                        "name": first["name"],
                        "label": first["label"],
                        "tier": "edge",
                        "required_fields": list(first.get("required_fields") or ["name"]),
                        "description": first["description"],
                    }
                },
                "source": {
                    "kind": "table_schema_suggest",
                    "table_name": first.get("table_name"),
                    "auto_apply": False,
                    "writes_graph": False,
                },
            },
            author=author,
        )
        base["proposal_id"] = proposal_id
        base["enqueue_status"] = "draft"
    except Exception as e:
        logger.warning("async enqueue table schema suggestion failed", exc_info=True)
        import time

        base["proposal_id"] = f"draft_local_{domain_id}_{first['name']}_{int(time.time())}"
        base["enqueue_status"] = "local_draft"
        base["enqueue_error"] = type(e).__name__
    return base
