"""记录级语义校验运行时权威（附录 N N17 deepen）。

职责：
  - 对 Fact/Claim/Query/Action 等记录跑标准级语义规则（非仅离线附录示例）
  - 扫描 FactLedger 租户内 Fact 并汇总违规
  - 套件/门槛门：``certified`` / ``n17_full`` 恒 false

非目标：
  - 不替换 ``reference_policy.json`` 为部署 RBAC（N18）
  - 不跑 semantic_cases 全量状态机序列对真实 Fact Store
  - 不宣称 N17 certified / 附录 N 全量符合
"""
from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SUITE_CASES = (
    "fact_published_needs_evidence",
    "fact_lifecycle_coherence",
    "query_abstain_no_citations",
    "transition_fact_review",
    "ledger_scan_reports",
    "honesty_certified_false",
)

# 与标准包 validate_semantics_v4.3.1.TRANSITIONS 对齐的最小子集
TRANSITIONS: Dict[str, Dict[str, set]] = {
    "fact_review": {
        "draft": {"reviewed", "rejected"},
        "reviewed": {"published", "rejected"},
        "published": {"reviewed", "rejected"},
        "rejected": {"draft"},
    },
    "fact_lifecycle": {
        "active": {"superseded", "retracted", "archived"},
        "superseded": {"archived"},
        "retracted": {"archived"},
        "archived": set(),
    },
    "claim_status": {
        "accepted": {"contested", "retracted", "archived"},
        "contested": {"accepted", "retracted", "archived"},
        "retracted": {"archived"},
        "archived": set(),
    },
}


class RecordSemanticsError(ValueError):
    """记录级语义校验契约错误。"""


def validate_record(kind: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """对单条记录跑记录级语义规则。

    Args:
        kind: 记录类型（fact/claim/query_response/action_contract/action_execution/
            verification_result/source_policy/claim_state）。
        data: 记录载荷。

    Returns:
        ``{ok, kind, errors}``。
    """
    k = (kind or "").strip().lower()
    if not k:
        raise RecordSemanticsError("kind_required")
    if not isinstance(data, dict):
        raise RecordSemanticsError("data_must_be_dict")
    errors = _example_errors(k, data)
    return {
        "ok": not errors,
        "kind": k,
        "errors": errors,
        "certified": False,
        "n17_full_conformance": False,
    }


def validate_transition(
    machine: str,
    from_state: str,
    to_state: str,
) -> Dict[str, Any]:
    """校验状态机单步转换是否允许。

    Args:
        machine: 状态机名（fact_review / fact_lifecycle / claim_status）。
        from_state: 源状态。
        to_state: 目标状态。
    """
    m = (machine or "").strip()
    a = (from_state or "").strip()
    b = (to_state or "").strip()
    if not m or not a or not b:
        raise RecordSemanticsError("machine_from_to_required")
    allowed = TRANSITIONS.get(m, {}).get(a, set())
    ok = b in allowed
    return {
        "ok": ok,
        "machine": m,
        "from": a,
        "to": b,
        "allowed": sorted(allowed),
        "certified": False,
        "n17_full_conformance": False,
    }


def _example_errors(kind: str, data: Dict[str, Any]) -> List[str]:
    """标准包 example_errors 的运行时可调用副本。

    Args:
        kind: 记录类型。
        data: 记录载荷。
    """
    errors: List[str] = []
    if kind in {"fact", "claim"}:
        if not data.get("evidence"):
            errors.append("evidence is empty")
        if data.get("review_status") == "published" and data.get("status") not in {
            "active",
            "accepted",
        }:
            errors.append("published review must have active/accepted lifecycle status")
        if data.get("review_status") != "published" and data.get("status") in {
            "active",
            "accepted",
        }:
            errors.append("active/accepted lifecycle requires published review")
        vf = data.get("valid_from")
        ra = data.get("recorded_at")
        if vf and ra and str(ra) < str(vf):
            errors.append("recorded_at earlier than valid_from")
    if kind == "action_contract" and data.get("risk_level") in {
        "high",
        "critical",
    } and not data.get("rollback_action_id"):
        errors.append("high/critical action requires rollback_action_id")
    if kind == "action_execution":
        if data.get("status") == "succeeded" and "result" not in data:
            errors.append("succeeded execution requires result")
        if data.get("status") == "failed" and "error" not in data:
            errors.append("failed execution requires error")
    if kind == "query_response":
        if data.get("abstained") is True and data.get("citations"):
            errors.append("abstained response must not contain citations")
        if data.get("partial") is True and not data.get("degraded_reason"):
            errors.append("partial response requires degraded_reason")
        if data.get("degraded") is True and not data.get("degraded_reason"):
            errors.append("degraded response requires degraded_reason")
    if kind == "verification_result":
        if data.get("valid") is True:
            if data.get("status") != "ok":
                errors.append("valid=true requires status=ok")
            if not data.get("checks_run"):
                errors.append("valid=true requires non-empty checks_run")
            if data.get("skipped_checks"):
                errors.append("valid=true requires empty skipped_checks")
    if kind == "source_policy" and not data.get("scope"):
        errors.append("source policy scope is empty")
    if kind == "claim_state" and not data.get("decision"):
        errors.append("claim state requires decision")
    return errors


async def scan_ledger_facts(
    *,
    tenant_id: str,
    domain_id: Optional[str] = None,
    collection_id: Optional[str] = None,
    limit: int = 100,
    ledger: Any = None,
) -> Dict[str, Any]:
    """扫描 FactLedger 租户内 Fact，跑 fact 记录级语义规则。

    Args:
        tenant_id: 租户（必填）。
        domain_id: 可选域过滤。
        collection_id: 可选集合过滤。
        limit: 扫描上限。
        ledger: 可选 FactLedger；缺省 ``get_fact_ledger()``。
    """
    tid = (tenant_id or "").strip()
    if not tid:
        raise RecordSemanticsError("tenant_id_required")
    from core.harness.knowledge_pipeline.fact_ledger import get_fact_ledger

    lg = ledger if ledger is not None else get_fact_ledger()
    facts = await lg.query_facts(
        tenant_id=tid,
        domain_id=domain_id,
        collection_id=collection_id,
        limit=limit,
    )
    violations: List[Dict[str, Any]] = []
    for fact in facts:
        result = validate_record("fact", fact)
        if not result["ok"]:
            violations.append(
                {
                    "fact_id": fact.get("fact_id"),
                    "subject": fact.get("subject"),
                    "errors": result["errors"],
                }
            )
    scanned = len(facts)
    return {
        "ok": True,
        "tenant_id": tid,
        "domain_id": domain_id or "",
        "scanned": scanned,
        "violations": violations,
        "violation_count": len(violations),
        "clean": len(violations) == 0,
        "certified": False,
        "n17_full_conformance": False,
        "runtime_authority": True,
        "note": "Record-level scan; not N17 certified / not full semantic_cases",
    }


def evaluate_record_semantics_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N17 deepen 门槛门（certified / n17_full 恒 false）。

    Args:
        suite: ``run_record_semantics_suite`` 回执。
    """
    s = suite or {}
    issues: List[str] = []
    # 为什么：禁止套件自签 certified（记录级 deepen ≠ N17 全量认证）
    if s.get("certified") is True:
        issues.append("honesty_certified_flag_forbidden")
    # 为什么：禁止套件自签 n17_full（加深刀 ≠ 附录 N 全量符合）
    if s.get("n17_full_conformance") is True:
        issues.append("honesty_n17_full_flag_forbidden")
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
        "n17_full_conformance": False,
        "note": "Record semantics deepen; not N17 certified / not RBAC source replace",
    }


async def run_record_semantics_suite(
    *,
    tenant_id: str = "n17-record-sem-tenant",
) -> Dict[str, Any]:
    """N17 deepen：记录级语义套件（certified 恒 false）。

    Args:
        tenant_id: 租户。
    """
    from core.harness.knowledge_pipeline.fact_ledger import FactLedger

    tmp = tempfile.TemporaryDirectory(prefix="n17-record-sem-")
    root = Path(tmp.name)
    lg = FactLedger(
        db_path=str(root / "fact_ledger.sqlite3"),
        raw_dir=root / "raw",
    )
    await lg.initialize()
    cases: List[Dict[str, Any]] = []
    try:
        # 1) published 无 evidence → 违规
        bad_pub = validate_record(
            "fact",
            {
                "evidence": [],
                "review_status": "published",
                "status": "active",
            },
        )
        cases.append(
            {
                "id": "fact_published_needs_evidence",
                "ok": bad_pub.get("ok") is False
                and "evidence is empty" in (bad_pub.get("errors") or []),
                "detail": "",
            }
        )

        # 2) draft + active → 生命周期不一致
        bad_life = validate_record(
            "fact",
            {
                "evidence": [{"source_id": "s1"}],
                "review_status": "draft",
                "status": "active",
            },
        )
        cases.append(
            {
                "id": "fact_lifecycle_coherence",
                "ok": bad_life.get("ok") is False
                and any(
                    "published review" in e for e in (bad_life.get("errors") or [])
                ),
                "detail": "",
            }
        )

        # 3) abstain + citations → 违规
        bad_q = validate_record(
            "query_response",
            {"abstained": True, "citations": [{"id": "c1"}]},
        )
        cases.append(
            {
                "id": "query_abstain_no_citations",
                "ok": bad_q.get("ok") is False
                and any("citations" in e for e in (bad_q.get("errors") or [])),
                "detail": "",
            }
        )

        # 4) draft→published 非法
        tr = validate_transition("fact_review", "draft", "published")
        cases.append(
            {
                "id": "transition_fact_review",
                "ok": tr.get("ok") is False,
                "detail": "",
            }
        )

        # 5) 写入合法 Fact 后扫描 clean；再注入非法记录级视图
        src = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n17-sem",
            kind="file",
            uri="file://n17/sem.txt",
            content=b"n17-sem",
            connector="n17",
            domain_id="suite-domain",
        )
        await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n17-sem",
            subject="InstallOrder:WO-N17",
            predicate="status",
            object="open",
            evidence=[
                {
                    "source_id": src["source_id"],
                    "locator": "1",
                    "quote": "ok",
                    "fetched_at": src["fetched_at"],
                }
            ],
            source_policy="n17",
            extractor_version="n17",
            review_status="published",
            confidence=0.9,
            allow_bootstrap_published=True,
            domain_id="suite-domain",
        )
        scan = await scan_ledger_facts(
            tenant_id=tenant_id,
            domain_id="suite-domain",
            ledger=lg,
        )
        # 合法 published+evidence+active 应 clean
        cases.append(
            {
                "id": "ledger_scan_reports",
                "ok": scan.get("scanned", 0) >= 1
                and scan.get("clean") is True
                and scan.get("runtime_authority") is True
                and scan.get("certified") is False,
                "detail": "" if scan.get("clean") else str(scan.get("violations")),
            }
        )

        cases.append(
            {
                "id": "honesty_certified_false",
                "ok": scan.get("certified") is False
                and scan.get("n17_full_conformance") is False,
                "detail": "",
            }
        )

        passed = sum(1 for c in cases if c.get("ok"))
        return {
            "ok": passed == len(_SUITE_CASES),
            "passed": passed,
            "total": len(_SUITE_CASES),
            "cases": cases,
            "scan": scan,
            "certified": False,
            "n17_full_conformance": False,
            "runtime_authority": True,
            "measured_at": time.time(),
            "note": "Record semantics deepen; not N17 certified / not RBAC replace",
        }
    finally:
        tmp.cleanup()
