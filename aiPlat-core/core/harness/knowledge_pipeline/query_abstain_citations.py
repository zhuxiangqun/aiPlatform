"""查询统一 abstain+citations（附录 N N21 deepen / 防假绿）。

职责：
  - 统一校验/归一化查询响应：abstain 无 citations/answer；有命中须 citations（可选强制）
  - 覆盖 Fact Gateway + unified object_set 路径探针
  - 套件/门槛门：``certified`` / ``n21_full`` 恒 false

非目标：
  - 不强制 Wiki/KB/GraphRAG 全入口热路径改写
  - 不并入 N13 校准封顶宣称
  - 不宣称 N21 certified
"""
from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SUITE_CASES = (
    "abstain_clears_citations",
    "abstain_clears_answer",
    "hit_requires_citations",
    "fact_gateway_path",
    "object_set_path",
    "honesty_certified_false",
)


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
        "note": "Abstain+citations deepen; not Wiki/KB full / not N21 certified",
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

        cases.append(
            {
                "id": "honesty_certified_false",
                "ok": fact_norm.get("certified") is False
                and uq_norm.get("n21_full_conformance") is False,
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
            "measured_at": time.time(),
            "note": "Abstain+citations deepen; not Wiki/KB full / not certified",
        }
    finally:
        tmp.cleanup()
