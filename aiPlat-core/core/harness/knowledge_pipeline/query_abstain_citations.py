"""查询统一 abstain+citations（附录 N N21 deepen / 防假绿）。

职责：
  - 统一校验/归一化查询响应：abstain 无 citations/answer；有命中须 citations（可选强制）
  - 覆盖 Fact Gateway + object_set + Wiki/KB 查询形 + MaterialsChat RAG 出口
    + 非 RAG 捷径（time/math/greeting）+ cache_hit + GraphRAG 信封
    + list 命中挂 ``n21_query`` 信封（不改 list 主结构）
  - 套件/门槛门：``certified`` / ``n21_full`` 恒 false

非目标：
  - 不改写 ``sys_wiki_retrieve`` / ``sys_kb_retrieve`` list 主返回类型
  - 不并入 N13 校准封顶宣称
  - 不宣称 N21 certified
"""
from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

_SUITE_CASES = (
    "abstain_clears_citations",
    "abstain_clears_answer",
    "hit_requires_citations",
    "fact_gateway_path",
    "object_set_path",
    "wiki_path",
    "kb_path",
    "materials_path",
    "materials_shortcut_path",
    "materials_cache_hit_path",
    "list_query_shape_path",
    "graphrag_path",
    "honesty_certified_false",
)

_TRIVIAL_STRATEGIES = frozenset({"trivial_bypass"})
_TRIVIAL_INTENTS = frozenset({"trivial"})
_TRIVIAL_QUALITIES = frozenset({"trivial"})
_CACHE_HIT_STRATEGIES = frozenset({"cache_hit"})
_CACHE_HIT_QUALITIES = frozenset({"cached"})
_CACHE_HIT_MODES = frozenset({"cache"})


class QueryAbstainCitationsError(ValueError):
    """查询 abstain+citations 契约错误。"""


def validate_abstain_citations(
    response: Dict[str, Any],
    *,
    require_citations_on_hit: bool = True,
) -> Dict[str, Any]:
    """校验查询响应的 abstain/citations 防假绿规则。

    Args:
        response: 查询响应 dict。
        require_citations_on_hit: 未 abstain 时是否要求非空 citations。
    """
    if not isinstance(response, dict):
        raise QueryAbstainCitationsError("response_must_be_dict")
    errors: List[str] = []
    abstained = response.get("abstained") is True
    citations = response.get("citations") or []
    answer = str(response.get("answer") or "").strip()
    if abstained:
        if citations:
            errors.append("abstained_must_not_have_citations")
        if answer:
            errors.append("abstained_must_not_have_answer")
    elif require_citations_on_hit:
        if not isinstance(citations, list) or not citations:
            errors.append("hit_requires_citations")
    if response.get("certified") is True or response.get("n21_full_conformance") is True:
        # 为什么：响应体自签认证 = 假绿
        errors.append("honesty_certified_flag_forbidden")
    return {
        "ok": not errors,
        "errors": errors,
        "abstained": abstained,
        "certified": False,
        "n21_full_conformance": False,
    }


def enforce_abstain_citations(
    response: Dict[str, Any],
    *,
    require_citations_on_hit: bool = True,
) -> Dict[str, Any]:
    """归一化查询响应以符合 abstain+citations 规则。

    Args:
        response: 原始响应。
        require_citations_on_hit: 未 abstain 时强制 citations。
    """
    if not isinstance(response, dict):
        raise QueryAbstainCitationsError("response_must_be_dict")
    out = dict(response)
    abstained = out.get("abstained") is True
    citations = list(out.get("citations") or []) if isinstance(out.get("citations"), list) else []
    if abstained:
        # 为什么：拒答时清空引用与答案，防止假绿
        out["citations"] = []
        out["answer"] = ""
    elif require_citations_on_hit and not citations:
        # 为什么：无引用却宣称命中 → 降级为 abstain（防假绿）
        out["abstained"] = True
        out["citations"] = []
        out["answer"] = ""
        out["route_reason"] = str(out.get("route_reason") or "") + ";n21:abstain_missing_citations"
    out["certified"] = False
    out["n21_full_conformance"] = False
    out["n21_enforced"] = True
    return out


def pack_retrieve_hits_as_query_response(
    hits: Optional[List[Dict[str, Any]]],
    *,
    channel: str,
    query: str = "",
) -> Dict[str, Any]:
    """将 Wiki/KB list 命中打包为查询形响应（供 abstain 门消费）。

    Args:
        hits: ``sys_wiki_retrieve`` / ``sys_kb_retrieve`` 风格命中列表。
        channel: ``wiki`` / ``kb``（写入 route_reason）。
        query: 原始查询（用于拼接短 answer）。
    """
    ch = (channel or "").strip().lower() or "retrieve"
    items = [h for h in (hits or []) if isinstance(h, dict)]
    citations: List[Dict[str, str]] = []
    for h in items:
        sid = str(
            h.get("source")
            or h.get("title")
            or h.get("doc_id")
            or h.get("page_id")
            or h.get("element_id")
            or ""
        ).strip()
        if not sid:
            # 为什么：无 source 标识的命中不可引用 → 跳过，避免假绿 citations
            continue
        citations.append(
            {
                "source_id": sid,
                "locator": str(h.get("title") or h.get("element_id") or ""),
                "quote": str(h.get("text") or h.get("summary") or "")[:200],
            }
        )
    abstained = not citations
    answer = ""
    if not abstained:
        parts = [
            str(h.get("text") or h.get("summary") or h.get("title") or "").strip()[:120]
            for h in items[:3]
        ]
        answer = " | ".join(p for p in parts if p) or (query or "").strip()
    return {
        "answer": "" if abstained else answer,
        "citations": citations,
        "abstained": abstained,
        "channel": ch,
        "route_reason": f"n21:{ch}",
        "hits_count": len(items),
        "certified": False,
        "n21_full_conformance": False,
    }


def attach_list_retrieve_n21_envelope(
    hits: Optional[Union[List[Dict[str, Any]], Dict[str, Any]]],
    *,
    channel: str,
    query: str = "",
    require_citations_on_hit: bool = True,
    tenant_id: str = "",
) -> Dict[str, Any]:
    """给 Wiki/KB list 命中附加 ``n21_query`` 信封（不改 list 主结构）。

    Args:
        hits: list 命中，或含 ``results`` 的上下文 dict（如 sys_wiki_context）。
        channel: ``wiki`` / ``kb`` / ``wiki_context``。
        query: 原始查询。
        require_citations_on_hit: 无引用则 abstain。
        tenant_id: 非空时落 N19 Query 审计快照。
    """
    if isinstance(hits, dict):
        out = dict(hits)
        raw_hits = out.get("results")
        if not isinstance(raw_hits, list):
            raw_hits = out.get("hits") if isinstance(out.get("hits"), list) else []
        list_hits = [h for h in raw_hits if isinstance(h, dict)]
    else:
        list_hits = [h for h in (hits or []) if isinstance(h, dict)]
        out = {"hits": list_hits}
    packed = pack_retrieve_hits_as_query_response(
        list_hits, channel=channel, query=query
    )
    enforced = enforce_abstain_citations(
        packed, require_citations_on_hit=require_citations_on_hit
    )
    out["n21_query"] = enforced
    out["n21_list_enforced"] = True
    out["certified"] = False
    out["n21_full_conformance"] = False
    try:
        # 为什么：N20 — Wiki/KB list 信封挂约束观测；不改 n21_query / list 主结构
        from core.harness.knowledge_pipeline.constraint_layers import (
            maybe_attach_wiki_kb_constraint_hotpath,
        )

        out = maybe_attach_wiki_kb_constraint_hotpath(out, channel=channel)
    except Exception:
        logger.warning(
            "N20 wiki_kb list constraint hotpath skipped", exc_info=True
        )
    tid = (tenant_id or "").strip()
    if tid:
        try:
            # 为什么：N19 — list 信封旁路落 Query 快照；空 tenant 跳过
            from core.harness.knowledge_pipeline.fact_query_audit import (
                maybe_record_wiki_kb_hotpath,
            )

            out = maybe_record_wiki_kb_hotpath(
                tenant_id=tid,
                response=out,
                channel=channel,
                query=query or "",
            )
        except Exception:
            logger.warning(
                "N19 wiki_kb list hotpath audit skipped", exc_info=True
            )
    return out


def query_wiki_with_abstain(
    query: str,
    *,
    tenant_id: str = "",
    collection_ids: Optional[List[str]] = None,
    top_k: int = 8,
    require_citations_on_hit: bool = True,
) -> Dict[str, Any]:
    """Wiki 查询形入口：retrieve → pack → enforce（N21；certified 恒 false）。

    Args:
        query: 查询。
        tenant_id: 租户。
        collection_ids: Wiki collection 列表。
        top_k: 召回上限。
        require_citations_on_hit: 无引用则降级 abstain。
    """
    from core.harness.syscalls.retrieval import sys_wiki_retrieve

    q = (query or "").strip()
    hits: List[Dict[str, Any]] = []
    if q:
        try:
            raw = sys_wiki_retrieve(
                q,
                collection_ids=collection_ids or ["default"],
                tenant_id=tenant_id or "",
                top_k=int(top_k),
            )
            hits = raw if isinstance(raw, list) else []
        except Exception as exc:
            # 为什么：检索失败不得假绿命中 → 空 hits → abstain
            logger.warning("query_wiki_with_abstain retrieve failed: %s", exc, exc_info=True)
            hits = []
    packed = pack_retrieve_hits_as_query_response(hits, channel="wiki", query=q)
    out = enforce_abstain_citations(
        packed, require_citations_on_hit=require_citations_on_hit
    )
    try:
        # 为什么：N20 — Wiki 查询形挂约束观测；统一 Gateway 另由 _finish 挂 F.1
        from core.harness.knowledge_pipeline.constraint_layers import (
            maybe_attach_wiki_kb_constraint_hotpath,
        )

        out = maybe_attach_wiki_kb_constraint_hotpath(out, channel="wiki")
    except Exception:
        logger.warning(
            "N20 wiki query constraint hotpath skipped", exc_info=True
        )
    if (tenant_id or "").strip():
        try:
            # 为什么：N19 — Wiki 查询形旁路落快照；与 Gateway 分立
            from core.harness.knowledge_pipeline.fact_query_audit import (
                maybe_record_wiki_kb_hotpath,
            )

            out = maybe_record_wiki_kb_hotpath(
                tenant_id=tenant_id,
                response=out,
                channel="wiki",
                query=q,
            )
        except Exception:
            logger.warning(
                "N19 wiki query hotpath audit skipped", exc_info=True
            )
    return out


def query_kb_with_abstain(
    query: str,
    *,
    tenant_id: str = "",
    doc_ids: Optional[List[str]] = None,
    collection_id: str = "",
    top_k: int = 8,
    require_citations_on_hit: bool = True,
) -> Dict[str, Any]:
    """KB 查询形入口：retrieve → pack → enforce（N21；certified 恒 false）。

    Args:
        query: 查询。
        tenant_id: 租户。
        doc_ids: 可选文档 id 过滤。
        collection_id: collection。
        top_k: 召回上限。
        require_citations_on_hit: 无引用则降级 abstain。
    """
    from core.harness.knowledge.domain_router import DomainRouter
    from core.harness.syscalls.retrieval import sys_kb_retrieve

    q = (query or "").strip()
    tid = (tenant_id or "").strip() or DomainRouter.default_tenant()
    cid = (collection_id or "").strip() or DomainRouter.default_collection()
    hits: List[Dict[str, Any]] = []
    if q:
        try:
            raw = sys_kb_retrieve(
                q,
                list(doc_ids or []),
                tenant_id=tid,
                collection_id=cid,
                top_k=int(top_k),
            )
            hits = raw if isinstance(raw, list) else []
        except Exception as exc:
            # 为什么：检索失败不得假绿命中 → 空 hits → abstain
            logger.warning("query_kb_with_abstain retrieve failed: %s", exc, exc_info=True)
            hits = []
    packed = pack_retrieve_hits_as_query_response(hits, channel="kb", query=q)
    out = enforce_abstain_citations(
        packed, require_citations_on_hit=require_citations_on_hit
    )
    try:
        # 为什么：N20 — KB 查询形挂约束观测；统一 Gateway index 路由另由 _finish 挂
        from core.harness.knowledge_pipeline.constraint_layers import (
            maybe_attach_wiki_kb_constraint_hotpath,
        )

        out = maybe_attach_wiki_kb_constraint_hotpath(out, channel="kb")
    except Exception:
        logger.warning(
            "N20 kb query constraint hotpath skipped", exc_info=True
        )
    if tid:
        try:
            # 为什么：N19 — KB 查询形旁路落快照；与 Gateway 分立
            from core.harness.knowledge_pipeline.fact_query_audit import (
                maybe_record_wiki_kb_hotpath,
            )

            out = maybe_record_wiki_kb_hotpath(
                tenant_id=tid,
                response=out,
                channel="kb",
                query=q,
            )
        except Exception:
            logger.warning(
                "N19 kb query hotpath audit skipped", exc_info=True
            )
    return out


def normalize_materials_citations(citations: Any) -> List[Dict[str, str]]:
    """将 MaterialsChat/CRAG 引用归一为 ``source_id`` 列表。

    Args:
        citations: 原始 citations（dict/str 混排）。
    """
    out: List[Dict[str, str]] = []
    if not isinstance(citations, list):
        return out
    for c in citations:
        if isinstance(c, dict):
            sid = str(
                c.get("source")
                or c.get("source_id")
                or c.get("title")
                or c.get("doc_id")
                or ""
            ).strip()
            if not sid:
                continue
            out.append(
                {
                    "source_id": sid,
                    "locator": str(c.get("title") or c.get("locator") or ""),
                    "quote": str(c.get("text") or c.get("quote") or "")[:200],
                }
            )
        elif isinstance(c, str) and c.strip():
            out.append({"source_id": c.strip(), "locator": "", "quote": ""})
    return out


def is_materials_trivial_bypass(output: Optional[Dict[str, Any]]) -> bool:
    """判定 MaterialsChat 输出是否为 time/math/greeting 等 trivial 捷径。

    Args:
        output: Agent 输出 dict。
    """
    if not isinstance(output, dict):
        return False
    strategy = str(output.get("strategy") or "").strip().lower()
    intent = str(output.get("intent") or "").strip().lower()
    quality = str(output.get("quality") or "").strip().lower()
    return (
        strategy in _TRIVIAL_STRATEGIES
        or intent in _TRIVIAL_INTENTS
        or quality in _TRIVIAL_QUALITIES
    )


def enforce_materials_chat_output(
    output: Optional[Dict[str, Any]],
    *,
    require_citations_on_hit: bool = True,
) -> Dict[str, Any]:
    """MaterialsChat RAG 出口：归一 citations 后 enforce（保留其余字段）。

    Args:
        output: Agent 输出 dict（含 answer/citations）。
        require_citations_on_hit: 无引用则降级 abstain。
    """
    if not isinstance(output, dict):
        raise QueryAbstainCitationsError("materials_output_must_be_dict")
    out = dict(output)
    probe = {
        "answer": str(out.get("answer") or ""),
        "citations": normalize_materials_citations(out.get("citations")),
        "abstained": out.get("abstained") is True,
    }
    enforced = enforce_abstain_citations(
        probe, require_citations_on_hit=require_citations_on_hit
    )
    out["answer"] = enforced.get("answer") or ""
    out["citations"] = enforced.get("citations") or []
    out["abstained"] = enforced.get("abstained") is True
    out["n21_enforced"] = True
    out["n21_channel"] = "materials_chat"
    out["certified"] = False
    out["n21_full_conformance"] = False
    if enforced.get("route_reason"):
        out["route_reason"] = str(out.get("route_reason") or "") + str(
            enforced.get("route_reason") or ""
        )
    return out


def enforce_materials_chat_shortcut_output(
    output: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """MaterialsChat 非 RAG 捷径出口：允许无 citations 的 trivial 答案。

    未标记 trivial 的输出回退到 RAG enforce（无引用 → abstain），防假捷径绿通。

    Args:
        output: Agent 捷径输出 dict（strategy/intent/quality=trivial）。
    """
    if not isinstance(output, dict):
        raise QueryAbstainCitationsError("materials_shortcut_output_must_be_dict")
    if not is_materials_trivial_bypass(output):
        # 为什么：未声明 trivial 却走捷径门 → 按 RAG 门处理，防空引用假绿
        return enforce_materials_chat_output(output, require_citations_on_hit=True)
    out = dict(output)
    # 为什么：捷径允许无 citations 的确定性答案；仍禁自签 certified
    probe = {
        "answer": str(out.get("answer") or ""),
        "citations": normalize_materials_citations(out.get("citations")),
        "abstained": out.get("abstained") is True,
    }
    enforced = enforce_abstain_citations(probe, require_citations_on_hit=False)
    out["answer"] = enforced.get("answer") or ""
    out["citations"] = enforced.get("citations") or []
    out["abstained"] = enforced.get("abstained") is True
    out["n21_enforced"] = True
    out["n21_channel"] = "materials_chat_shortcut"
    out["n21_shortcut"] = True
    out["certified"] = False
    out["n21_full_conformance"] = False
    if enforced.get("route_reason"):
        out["route_reason"] = str(out.get("route_reason") or "") + str(
            enforced.get("route_reason") or ""
        )
    return out


def is_materials_cache_hit(output: Optional[Dict[str, Any]]) -> bool:
    """判定 MaterialsChat 输出是否为语义缓存命中出口。

    Args:
        output: Agent 输出 dict。
    """
    if not isinstance(output, dict):
        return False
    strategy = str(output.get("strategy") or "").strip().lower()
    quality = str(output.get("quality") or "").strip().lower()
    mode = str(output.get("mode") or "").strip().lower()
    return (
        strategy in _CACHE_HIT_STRATEGIES
        or quality in _CACHE_HIT_QUALITIES
        or mode in _CACHE_HIT_MODES
    )


def enforce_materials_chat_cache_hit_output(
    output: Optional[Dict[str, Any]],
    *,
    require_citations_on_hit: bool = True,
) -> Dict[str, Any]:
    """MaterialsChat cache_hit 出口：知识答案须 citations（无引用 → abstain）。

    未标记 cache_hit 的输出回退到 RAG enforce，防假缓存绿通。

    Args:
        output: Agent 缓存命中输出 dict。
        require_citations_on_hit: 无引用则降级 abstain。
    """
    if not isinstance(output, dict):
        raise QueryAbstainCitationsError("materials_cache_hit_output_must_be_dict")
    if not is_materials_cache_hit(output):
        # 为什么：未声明 cache_hit 却走缓存门 → 按 RAG 门处理
        return enforce_materials_chat_output(
            output, require_citations_on_hit=require_citations_on_hit
        )
    out = dict(output)
    # 为什么：缓存答案仍是知识命中，无 citations 不得绿通
    probe = {
        "answer": str(out.get("answer") or ""),
        "citations": normalize_materials_citations(out.get("citations")),
        "abstained": out.get("abstained") is True,
    }
    enforced = enforce_abstain_citations(
        probe, require_citations_on_hit=require_citations_on_hit
    )
    out["answer"] = enforced.get("answer") or ""
    out["citations"] = enforced.get("citations") or []
    out["abstained"] = enforced.get("abstained") is True
    out["n21_enforced"] = True
    out["n21_channel"] = "materials_chat_cache_hit"
    out["n21_cache_hit"] = True
    out["certified"] = False
    out["n21_full_conformance"] = False
    if enforced.get("route_reason"):
        out["route_reason"] = str(out.get("route_reason") or "") + str(
            enforced.get("route_reason") or ""
        )
    return out


def pack_graphrag_result_as_query_response(
    result: Optional[Dict[str, Any]],
    *,
    query: str = "",
) -> Dict[str, Any]:
    """将 GraphRAG ``retrieve`` 结果打包为查询形响应。

    Args:
        result: GraphRAGRetriever.retrieve 回执。
        query: 原始查询。
    """
    r = result if isinstance(result, dict) else {}
    chunks = r.get("chunks") or []
    hits: List[Dict[str, Any]] = []
    if isinstance(chunks, list):
        for c in chunks:
            if not isinstance(c, dict):
                continue
            hits.append(
                {
                    "title": c.get("title") or "",
                    "text": c.get("content") or c.get("text") or "",
                    "source": c.get("source")
                    or c.get("doc_id")
                    or c.get("title")
                    or "",
                    "score": c.get("score"),
                }
            )
    packed = pack_retrieve_hits_as_query_response(
        hits, channel="graphrag", query=query
    )
    packed["graphrag_mode"] = r.get("mode") or ""
    return packed


def attach_graphrag_n21_envelope(
    result: Optional[Dict[str, Any]],
    *,
    query: str = "",
    require_citations_on_hit: bool = True,
    tenant_id: str = "",
) -> Dict[str, Any]:
    """给 GraphRAG 结果附加 ``n21_query``；租户非空时挂 N06 ``gateway_f1``。

    Args:
        result: GraphRAG retrieve 回执。
        query: 原始查询。
        require_citations_on_hit: 无引用则 abstain。
        tenant_id: 非空时附加 ``gateway_f1``（N06 graphrag 路由）。
    """
    out = dict(result) if isinstance(result, dict) else {}
    packed = pack_graphrag_result_as_query_response(out, query=query)
    enforced = enforce_abstain_citations(
        packed, require_citations_on_hit=require_citations_on_hit
    )
    out["n21_query"] = enforced
    out["certified"] = False
    out["n21_full_conformance"] = False
    out["n21_graphrag_enforced"] = True
    tid = (tenant_id or "").strip()
    if tid:
        try:
            # 为什么：GraphRAG 生产出口收敛到统一 Gateway F.1；非 certified
            from core.harness.knowledge_pipeline.fact_ledger import (
                graphrag_to_f1_envelope,
            )

            out["gateway_f1"] = graphrag_to_f1_envelope(
                tenant_id=tid, result=out, query=query
            )
        except Exception:
            logger.warning(
                "N06 graphrag F.1 attach skipped", exc_info=True
            )
    try:
        # 为什么：N20 — GraphRAG 出口挂约束观测信封；不改 n21/gateway_f1
        from core.harness.knowledge_pipeline.constraint_layers import (
            maybe_attach_graphrag_constraint_hotpath,
        )

        out = maybe_attach_graphrag_constraint_hotpath(out)
    except Exception:
        logger.warning(
            "N20 graphrag constraint hotpath skipped", exc_info=True
        )
    if tid:
        try:
            # 为什么：N19 — 直出旁路须落 Query 快照；与 unified Gateway 分立
            from core.harness.knowledge_pipeline.fact_query_audit import (
                maybe_record_graphrag_hotpath,
            )

            out = maybe_record_graphrag_hotpath(
                tenant_id=tid, result=out, query=query or ""
            )
        except Exception:
            logger.warning(
                "N19 graphrag hotpath audit skipped", exc_info=True
            )
    return out


def evaluate_query_abstain_citations_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N21 deepen 门槛门（certified / n21_full 恒 false）。

    Args:
        suite: ``run_query_abstain_citations_suite`` 回执。
    """
    s = suite or {}
    issues: List[str] = []
    # 为什么：禁止套件自签 certified（防假绿 deepen ≠ N21 全量认证）
    if s.get("certified") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("n21_full_conformance") is True:
        issues.append("honesty_n21_full_flag_forbidden")
    # 为什么：本 deepen 须声明 Wiki/KB + Materials/GraphRAG + 捷径/缓存已接线，防旧套件冒充
    if s.get("wiki_kb_query_entry") is not True:
        issues.append("wiki_kb_query_entry_required")
    if s.get("materials_graphrag_entry") is not True:
        issues.append("materials_graphrag_entry_required")
    if s.get("materials_shortcut_entry") is not True:
        issues.append("materials_shortcut_entry_required")
    if s.get("materials_cache_hit_entry") is not True:
        issues.append("materials_cache_hit_entry_required")
    if s.get("list_query_shape_entry") is not True:
        issues.append("list_query_shape_entry_required")
    cases = s.get("cases") or []
    if cases:
        failed = [c for c in cases if isinstance(c, dict) and not c.get("ok")]
        if failed:
            issues.append(f"suite_cases_failed:{len(failed)}")
        ids = {str(c.get("id") or "") for c in cases if isinstance(c, dict)}
        missing = [x for x in _SUITE_CASES if x not in ids]
        if missing:
            issues.append(f"suite_cases_missing:{','.join(missing)}")
    elif not s.get("ok"):
        issues.append("suite_not_ok")
    return {
        "ok": not issues and bool(s.get("ok", True)),
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n21_full_conformance": False,
        "wiki_kb_query_entry": True,
        "materials_graphrag_entry": True,
        "materials_shortcut_entry": True,
        "materials_cache_hit_entry": True,
        "list_query_shape_entry": True,
        "note": (
            "Abstain+citations + Wiki/KB + Materials + GraphRAG + list n21_query envelope; "
            "not N21 certified / not rewrite list primary return type"
        ),
    }


async def run_query_abstain_citations_suite(
    *,
    tenant_id: str = "n21-abstain-tenant",
) -> Dict[str, Any]:
    """N21 deepen：abstain+citations 防假绿套件（certified 恒 false）。

    Args:
        tenant_id: 租户。
    """
    from core.harness.knowledge_pipeline.fact_ledger import (
        FactLedger,
        unified_query_gateway,
    )

    cases: List[Dict[str, Any]] = []
    tmp = tempfile.TemporaryDirectory(prefix="n21-abstain-")
    root = Path(tmp.name)
    lg = FactLedger(
        db_path=str(root / "fact_ledger.sqlite3"),
        raw_dir=root / "raw",
    )
    await lg.initialize()
    try:
        bad = {
            "abstained": True,
            "citations": [{"source_id": "leak"}],
            "answer": "should clear",
        }
        enforced = enforce_abstain_citations(bad)
        v1 = validate_abstain_citations(enforced)
        cases.append(
            {
                "id": "abstain_clears_citations",
                "ok": enforced.get("citations") == [] and v1.get("ok") is True,
                "detail": "",
            }
        )
        cases.append(
            {
                "id": "abstain_clears_answer",
                "ok": enforced.get("answer") == "",
                "detail": "",
            }
        )

        hit_no_cite = {
            "abstained": False,
            "citations": [],
            "answer": "fake hit",
        }
        enforced2 = enforce_abstain_citations(hit_no_cite)
        cases.append(
            {
                "id": "hit_requires_citations",
                "ok": enforced2.get("abstained") is True
                and enforced2.get("citations") == [],
                "detail": "",
            }
        )

        # Fact gateway 路径
        src = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n21",
            kind="file",
            uri="file://n21/a.txt",
            content=b"status open",
            connector="n21",
            domain_id="suite-domain",
        )
        await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n21",
            subject="Order:N21",
            predicate="status",
            object="open",
            evidence=[
                {
                    "source_id": src["source_id"],
                    "locator": "1",
                    "quote": "status open",
                    "fetched_at": src["fetched_at"],
                }
            ],
            source_policy="n21",
            extractor_version="n21",
            review_status="published",
            confidence=0.9,
            allow_bootstrap_published=True,
            domain_id="suite-domain",
        )
        fact_resp = await lg.query_facts_gateway(
            tenant_id=tenant_id,
            query="status",
            require_citations=True,
        )
        fact_norm = enforce_abstain_citations(fact_resp)
        fact_v = validate_abstain_citations(fact_norm)
        cases.append(
            {
                "id": "fact_gateway_path",
                "ok": fact_v.get("ok") is True
                and (
                    fact_norm.get("abstained") is True
                    or bool(fact_norm.get("citations"))
                ),
                "detail": ",".join(fact_v.get("errors") or []),
            }
        )

        # unified object_set 路径（无类型时可能 abstain）
        uq = await unified_query_gateway(
            tenant_id=tenant_id,
            query="Order",
            route="object_set",
            ledger=lg,
        )
        uq_norm = enforce_abstain_citations(uq if isinstance(uq, dict) else {})
        uq_v = validate_abstain_citations(uq_norm)
        cases.append(
            {
                "id": "object_set_path",
                "ok": uq_v.get("ok") is True,
                "detail": ",".join(uq_v.get("errors") or []),
            }
        )

        # Wiki 查询形：有 source 命中保留；无标识命中 → abstain
        wiki_hit = pack_retrieve_hits_as_query_response(
            [{"title": "N21Page", "text": "wiki hit", "source": "wiki:N21Page", "score": 0.9}],
            channel="wiki",
            query="wiki hit",
        )
        wiki_ok = enforce_abstain_citations(wiki_hit)
        wiki_empty = query_wiki_with_abstain(
            "n21-wiki-no-such-page-xyz",
            tenant_id=tenant_id,
            collection_ids=["default"],
            top_k=3,
        )
        wiki_v = validate_abstain_citations(wiki_ok)
        cases.append(
            {
                "id": "wiki_path",
                "ok": (
                    wiki_v.get("ok") is True
                    and wiki_ok.get("abstained") is False
                    and bool(wiki_ok.get("citations"))
                    and wiki_empty.get("abstained") is True
                    and wiki_empty.get("n21_enforced") is True
                ),
                "detail": ",".join(wiki_v.get("errors") or []),
            }
        )

        # KB 查询形：无 source 假命中必须降级 abstain；空检索 abstain
        kb_fake = enforce_abstain_citations(
            pack_retrieve_hits_as_query_response(
                [{"text": "orphan chunk", "score": 0.5}],
                channel="kb",
                query="orphan",
            )
        )
        kb_live = query_kb_with_abstain(
            "n21-kb-no-such-doc-xyz",
            tenant_id=tenant_id,
            top_k=3,
        )
        kb_v = validate_abstain_citations(kb_fake)
        cases.append(
            {
                "id": "kb_path",
                "ok": (
                    kb_v.get("ok") is True
                    and kb_fake.get("abstained") is True
                    and kb_live.get("abstained") is True
                    and kb_live.get("channel") == "kb"
                ),
                "detail": ",".join(kb_v.get("errors") or []),
            }
        )

        # MaterialsChat RAG 出口：无引用假答案 → abstain；有 source 保留
        mat_fake = enforce_materials_chat_output(
            {"answer": "fake rag", "citations": [], "strategy": "direct_retrieve"}
        )
        mat_ok = enforce_materials_chat_output(
            {
                "answer": "grounded",
                "citations": [{"source": "wiki:P", "text": "grounded"}],
                "strategy": "direct_retrieve",
            }
        )
        mat_v = validate_abstain_citations(
            {
                "answer": mat_ok.get("answer") or "",
                "citations": mat_ok.get("citations") or [],
                "abstained": mat_ok.get("abstained") is True,
            }
        )
        cases.append(
            {
                "id": "materials_path",
                "ok": (
                    mat_fake.get("abstained") is True
                    and mat_fake.get("citations") == []
                    and mat_ok.get("abstained") is False
                    and bool(mat_ok.get("citations"))
                    and mat_v.get("ok") is True
                    and mat_ok.get("n21_channel") == "materials_chat"
                ),
                "detail": ",".join(mat_v.get("errors") or []),
            }
        )

        # MaterialsChat 非 RAG 捷径：trivial 可无 citations；假捷径回退 RAG abstain
        sc_ok = enforce_materials_chat_shortcut_output(
            {
                "answer": "14:30",
                "citations": [],
                "strategy": "trivial_bypass",
                "intent": "trivial",
                "quality": "trivial",
                "turn_summary": "time query",
            }
        )
        sc_fake = enforce_materials_chat_shortcut_output(
            {
                "answer": "pretend shortcut",
                "citations": [],
                "strategy": "direct_retrieve",
            }
        )
        sc_v = validate_abstain_citations(
            {
                "answer": sc_ok.get("answer") or "",
                "citations": sc_ok.get("citations") or [],
                "abstained": sc_ok.get("abstained") is True,
            },
            require_citations_on_hit=False,
        )
        cases.append(
            {
                "id": "materials_shortcut_path",
                "ok": (
                    sc_ok.get("abstained") is False
                    and sc_ok.get("answer") == "14:30"
                    and sc_ok.get("citations") == []
                    and sc_ok.get("n21_channel") == "materials_chat_shortcut"
                    and sc_ok.get("n21_shortcut") is True
                    and sc_fake.get("abstained") is True
                    and sc_fake.get("n21_channel") == "materials_chat"
                    and sc_v.get("ok") is True
                ),
                "detail": ",".join(sc_v.get("errors") or []),
            }
        )

        # MaterialsChat cache_hit：有引用保留；无引用 abstain；假缓存回退 RAG
        ch_ok = enforce_materials_chat_cache_hit_output(
            {
                "answer": "cached grounded",
                "citations": [{"source": "wiki:C", "text": "cached"}],
                "strategy": "cache_hit",
                "quality": "cached",
                "mode": "cache",
            }
        )
        ch_empty = enforce_materials_chat_cache_hit_output(
            {
                "answer": "cached fake",
                "citations": [],
                "strategy": "cache_hit",
                "quality": "cached",
                "mode": "cache",
            }
        )
        ch_fake = enforce_materials_chat_cache_hit_output(
            {
                "answer": "not really cache",
                "citations": [],
                "strategy": "direct_retrieve",
            }
        )
        ch_v = validate_abstain_citations(
            {
                "answer": ch_ok.get("answer") or "",
                "citations": ch_ok.get("citations") or [],
                "abstained": ch_ok.get("abstained") is True,
            }
        )
        cases.append(
            {
                "id": "materials_cache_hit_path",
                "ok": (
                    ch_ok.get("abstained") is False
                    and bool(ch_ok.get("citations"))
                    and ch_ok.get("n21_channel") == "materials_chat_cache_hit"
                    and ch_ok.get("n21_cache_hit") is True
                    and ch_empty.get("abstained") is True
                    and ch_fake.get("abstained") is True
                    and ch_fake.get("n21_channel") == "materials_chat"
                    and ch_v.get("ok") is True
                ),
                "detail": ",".join(ch_v.get("errors") or []),
            }
        )

        # GraphRAG 信封：无 chunk → abstain；有 source chunk 保留
        gr_empty = attach_graphrag_n21_envelope(
            {"mode": "vector_only", "chunks": []}, query="none"
        )
        gr_ok = attach_graphrag_n21_envelope(
            {
                "mode": "graphrag",
                "chunks": [
                    {"title": "G1", "content": "graph hit", "source": "doc:G1"}
                ],
            },
            query="graph hit",
        )
        gr_env = gr_ok.get("n21_query") or {}
        cases.append(
            {
                "id": "graphrag_path",
                "ok": (
                    (gr_empty.get("n21_query") or {}).get("abstained") is True
                    and gr_empty.get("n21_graphrag_enforced") is True
                    and gr_env.get("abstained") is False
                    and bool(gr_env.get("citations"))
                    and gr_ok.get("certified") is False
                ),
                "detail": "",
            }
        )

        # list 主结构不变：挂 n21_query；无 source 假命中 → abstain
        list_ok = attach_list_retrieve_n21_envelope(
            [{"title": "L1", "text": "list hit", "source": "wiki:L1"}],
            channel="wiki",
            query="list hit",
        )
        list_fake = attach_list_retrieve_n21_envelope(
            [{"text": "orphan list", "score": 0.2}],
            channel="kb",
            query="orphan",
        )
        list_ctx = attach_list_retrieve_n21_envelope(
            {
                "results": [
                    {"title": "C1", "text": "ctx hit", "source": "wiki:C1"}
                ],
                "fts5_matches": [],
                "related_pages": [],
            },
            channel="wiki_context",
            query="ctx",
        )
        list_env = list_ok.get("n21_query") or {}
        cases.append(
            {
                "id": "list_query_shape_path",
                "ok": (
                    list_ok.get("n21_list_enforced") is True
                    and isinstance(list_ok.get("hits"), list)
                    and list_env.get("abstained") is False
                    and bool(list_env.get("citations"))
                    and (list_fake.get("n21_query") or {}).get("abstained") is True
                    and isinstance(list_ctx.get("results"), list)
                    and (list_ctx.get("n21_query") or {}).get("abstained") is False
                    and list_ok.get("certified") is False
                ),
                "detail": "",
            }
        )

        cases.append(
            {
                "id": "honesty_certified_false",
                "ok": fact_norm.get("certified") is False
                and uq_norm.get("n21_full_conformance") is False
                and wiki_ok.get("n21_full_conformance") is False
                and kb_live.get("certified") is False
                and mat_ok.get("n21_full_conformance") is False
                and sc_ok.get("n21_full_conformance") is False
                and ch_ok.get("n21_full_conformance") is False
                and gr_ok.get("n21_full_conformance") is False
                and list_ok.get("n21_full_conformance") is False,
                "detail": "",
            }
        )

        passed = sum(1 for c in cases if c.get("ok"))
        return {
            "ok": passed == len(_SUITE_CASES),
            "passed": passed,
            "total": len(_SUITE_CASES),
            "cases": cases,
            "certified": False,
            "n21_full_conformance": False,
            "wiki_kb_query_entry": True,
            "materials_graphrag_entry": True,
            "materials_shortcut_entry": True,
            "materials_cache_hit_entry": True,
            "list_query_shape_entry": True,
            "measured_at": time.time(),
            "note": (
                "Abstain+citations + Wiki/KB + Materials + GraphRAG + list n21_query envelope; "
                "not N21 certified / not rewrite list primary return type"
            ),
        }
    finally:
        tmp.cleanup()
