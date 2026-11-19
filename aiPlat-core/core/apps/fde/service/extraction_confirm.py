"""抽取 confirm 编排（G2 收口）：K1 信号 + Graph/Fact 副作用。

职责：把原先 HTTP 路由内联的 confirm 副作用收敛为可复用编排，供
ActionRegistry handler 与薄路由共同调用。

非目标：不写活 YAML；不替代 PendingExtractionStore 存储；不实现 Wiki 只读。
"""
from __future__ import annotations

from core.harness.knowledge.domain_router import DomainRouter

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _parse_list(raw: Any) -> list:
    """解析 entities/relations JSON 列为 list。"""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            val = json.loads(raw)
            return val if isinstance(val, list) else []
        except Exception:
            return []
    return []


async def run_confirm_extraction(
    extraction_id: str,
    *,
    actor: str = "",
    store: Optional[Any] = None,
) -> Dict[str, Any]:
    """执行抽取确认编排（K1 + Graph + Fact→投影）。

    Args:
        extraction_id: pending extraction 标识。
        actor: 操作者身份（写入 K1 审计）。
        store: PendingExtractionStore；缺省时新建并 initialize。

    Returns:
        与原 HTTP confirm 响应同形的 dict；失败时含 ``ok=False`` 或 ``status`` 非 confirmed。
    """
    from core.api.core_facade import (
        PendingExtractionStore,
        fact_ledger_project_to_graph,
        k1_confirm_extraction,
        record_extraction_as_claim,
        write_extraction_to_graph_index,
    )

    eid = (extraction_id or "").strip()
    if not eid:
        return {"ok": False, "status": "invalid", "reason": "need_extraction_id"}

    if store is None:
        store = PendingExtractionStore()
        await store.initialize()

    receipt = await k1_confirm_extraction(eid, actor=actor)
    if not receipt.get("ok"):
        return {
            "ok": False,
            "status": "failed",
            "reason": receipt.get("reason") or "confirm failed",
            "extraction_id": eid,
        }

    proposal_id = None
    graph_write = None
    fact_ledger = None
    try:
        await store.initialize()
        row = await store.get_row(eid)
        if row:
            proposal_id = await store._enqueue_ontology_proposal(row)
            ents = _parse_list(row.get("entities_json"))
            rels = _parse_list(row.get("relations_json"))
            domain_id = str(row.get("domain_id") or receipt.get("domain_id") or DomainRouter.default_graph_domain())
            tenant_id = str(
                row.get("tenant_id")
                or receipt.get("tenant_id")
                or DomainRouter.default_tenant()
            ).strip() or DomainRouter.default_tenant()
            if ents:
                try:
                    # 为什么：N09 K6 — confirm 写图必须带租户，与 Fact 投影一致
                    graph_write = write_extraction_to_graph_index(
                        domain_id,
                        ents,
                        rels,
                        source_doc_id=f"extract:{eid}",
                        tenant_id=tenant_id,
                    )
                except Exception:
                    logger.warning(
                        "confirm: GraphIndex write failed for %s",
                        eid,
                        exc_info=True,
                    )
                    graph_write = {"error": "graph_write_failed"}
            _ot_seed = Path(
                f"aiPlat-core/workspace_seeds/ontologies/{domain_id}-object-types.json"
            )
            if _ot_seed.is_file():
                try:
                    summary = f"confirmed extraction {eid} ({len(ents)} entities)"
                    fact_ledger = await record_extraction_as_claim(
                        tenant_id=tenant_id,
                        domain_id=domain_id,
                        extraction_id=eid,
                        source_doc=str(row.get("source_doc") or ""),
                        text=summary,
                        evidence_quote=summary,
                    )
                    try:
                        fact_ledger["projection"] = await fact_ledger_project_to_graph(
                            tenant_id=tenant_id,
                            domain_id=domain_id,
                            clear_projected=False,
                        )
                    except Exception:
                        logger.warning(
                            "confirm: fact projection failed for %s",
                            eid,
                            exc_info=True,
                        )
                        fact_ledger["projection"] = {"error": "projection_failed"}
                except Exception:
                    logger.warning(
                        "confirm: fact_ledger write failed for %s",
                        eid,
                        exc_info=True,
                    )
                    fact_ledger = {"error": "fact_ledger_failed"}
    except Exception:
        logger.warning("confirm: proposal/graph failed for %s", eid, exc_info=True)
        fact_ledger = None

    return {
        "ok": True,
        "status": "confirmed",
        "path": "K1+graph+action",
        "extraction_id": eid,
        "domain_id": receipt.get("domain_id"),
        "signal_id": receipt.get("signal_id"),
        "trace_id": receipt.get("trace_id"),
        "trace_origin": receipt.get("trace_origin"),
        "extract_actor": receipt.get("extract_actor"),
        "entity_ids": receipt.get("entity_ids")
        or (graph_write or {}).get("created_entities")
        or [],
        "yaml_unchanged": True,
        "wrote_live_yaml": False,
        "wrote_cross_domain_edge": False,
        "idempotent": bool(receipt.get("idempotent")),
        "fact_ledger": fact_ledger,
        "proposal_id": proposal_id,
        "graph_write": graph_write,
    }
