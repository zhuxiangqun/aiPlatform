"""W10 N18 实现方语义测试最小切片（附录 N / conformance README）。

职责：对真实 FactLedger + ActionExecution 跑最小探针套件；门槛门。
非目标：不替代标准包 mock 语义校验；不替换生产 RBAC 策略源；不宣称 N18 全量认证。
"""
from __future__ import annotations

import logging
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# conformance README「Real implementation tests」最小必跑子集
REQUIRED_CASES = (
    "raw_immutable",
    "published_requires_evidence",
    "citation_resolves",
    "cross_tenant_isolation",
    "customer_action_audit",
)


def _case(name: str, *, ok: bool, detail: str = "") -> Dict[str, Any]:
    """组装单条用例结果。

    Args:
        name: 用例 id。
        ok: 是否通过。
        detail: 失败或补充说明。
    """
    return {"id": name, "ok": bool(ok), "detail": detail or ""}


async def _probe_raw_immutable(ledger: Any, *, tenant_id: str) -> Dict[str, Any]:
    """Raw 不可变：sha256 + 快照文件。

    Args:
        ledger: FactLedger 实例。
        tenant_id: 租户。
    """
    content = b"n18-implementer-raw"
    src = await ledger.register_source(
        tenant_id=tenant_id,
        collection_id="n18-kb",
        kind="file",
        uri="mem://n18/raw-1",
        content=content,
        connector="n18_implementer_semantics",
    )
    if not src.get("immutable"):
        return _case("raw_immutable", ok=False, detail="immutable_flag_false")
    sha = str(src.get("sha256") or "")
    if len(sha) != 64:
        return _case("raw_immutable", ok=False, detail="sha256_len")
    raw_path = Path(ledger.raw_dir) / tenant_id / f"{src['source_id']}.bin"
    if not raw_path.is_file():
        return _case("raw_immutable", ok=False, detail="snapshot_missing")
    return _case("raw_immutable", ok=True)


async def _probe_published_requires_evidence(ledger: Any, *, tenant_id: str) -> Dict[str, Any]:
    """published 无 evidence 必须拒绝。

    Args:
        ledger: FactLedger 实例。
        tenant_id: 租户。
    """
    from core.harness.knowledge_pipeline.fact_ledger import FactLedgerError

    try:
        await ledger.put_fact(
            tenant_id=tenant_id,
            collection_id="n18-kb",
            subject="Order:n18-1",
            predicate="status",
            object="open",
            evidence=[],
            source_policy="n18_policy",
            extractor_version="n18-1.0",
            review_status="published",
            confidence=0.9,
            domain_id="pilot-domain",
            allow_bootstrap_published=True,
        )
        return _case(
            "published_requires_evidence",
            ok=False,
            detail="accepted_without_evidence",
        )
    except FactLedgerError:
        return _case("published_requires_evidence", ok=True)
    except Exception as exc:  # noqa: BLE001 — 探针捕获后记失败
        return _case(
            "published_requires_evidence",
            ok=False,
            detail=f"unexpected:{type(exc).__name__}",
        )


async def _probe_citation_resolves(ledger: Any, *, tenant_id: str) -> Dict[str, Any]:
    """已发布 Claim/Fact 的 evidence source 必须可解析。

    Args:
        ledger: FactLedger 实例。
        tenant_id: 租户。
    """
    src = await ledger.register_source(
        tenant_id=tenant_id,
        collection_id="n18-kb",
        kind="text",
        uri="mem://n18/cite-1",
        content=b"status open",
        connector="n18_implementer_semantics",
    )
    evidence = [
        {
            "source_id": src["source_id"],
            "locator": "1",
            "quote": "status open",
        }
    ]
    fact = await ledger.put_fact(
        tenant_id=tenant_id,
        collection_id="n18-kb",
        subject="Order:n18-cite",
        predicate="status",
        object="open",
        evidence=evidence,
        source_policy="n18_policy",
        extractor_version="n18-1.0",
        review_status="published",
        confidence=0.91,
        domain_id="pilot-domain",
        allow_bootstrap_published=True,
    )
    got = await ledger.get_source(src["source_id"], tenant_id=tenant_id)
    if got is None:
        return _case("citation_resolves", ok=False, detail="source_missing")
    if not fact.get("evidence"):
        return _case("citation_resolves", ok=False, detail="fact_no_evidence")
    # 跨租户不得解析同一 source
    other = await ledger.get_source(src["source_id"], tenant_id=f"{tenant_id}-other")
    if other is not None:
        return _case("citation_resolves", ok=False, detail="cross_tenant_source_leak")
    return _case("citation_resolves", ok=True)


async def _probe_cross_tenant(ledger: Any, *, tenant_a: str, tenant_b: str) -> Dict[str, Any]:
    """跨租户查询不得泄漏 Fact。

    Args:
        ledger: FactLedger 实例。
        tenant_a: 写入租户。
        tenant_b: 查询租户。
    """
    src = await ledger.register_source(
        tenant_id=tenant_a,
        collection_id="n18-kb",
        kind="text",
        uri="mem://n18/tenant-a",
        content=b"secret",
        connector="n18_implementer_semantics",
    )
    fact = await ledger.put_fact(
        tenant_id=tenant_a,
        collection_id="n18-kb",
        subject="Order:n18-secret",
        predicate="status",
        object="hidden",
        evidence=[{"source_id": src["source_id"], "locator": "1", "quote": "x"}],
        source_policy="n18_policy",
        extractor_version="n18-1.0",
        review_status="published",
        confidence=0.9,
        domain_id="pilot-domain",
        allow_bootstrap_published=True,
    )
    same = await ledger.query_facts(tenant_id=tenant_a, domain_id="pilot-domain")
    if not any(r.get("fact_id") == fact["fact_id"] for r in same):
        return _case("cross_tenant_isolation", ok=False, detail="same_tenant_miss")
    other = await ledger.query_facts(tenant_id=tenant_b, domain_id="pilot-domain")
    if any(r.get("fact_id") == fact["fact_id"] for r in other):
        return _case("cross_tenant_isolation", ok=False, detail="cross_tenant_leak")
    return _case("cross_tenant_isolation", ok=True)


def _probe_customer_action_audit(*, db_path: str) -> Dict[str, Any]:
    """customer_action 审计：快照 + 幂等回放。

    Args:
        db_path: ActionExecution SQLite 路径。
    """
    from core.harness.infrastructure.action_execution import (
        lookup_execution,
        persist_execution,
    )

    # 为什么用命名空间前缀：与 W7 ActionExecution 合同一致，避免非 customer_action 绕过
    action_id = "customer_action:pilot:n18_probe"
    tenant_id = "tenant-n18-a"
    key = f"n18-{uuid.uuid4().hex[:10]}"
    first = persist_execution(
        {
            "tenant_id": tenant_id,
            "idempotency_key": key,
            "action_id": action_id,
            "actor": "n18-tester",
            "target": "Order:n18-1",
            "status": "succeeded",
            "policy_decision": "allow",
            "before_snapshot": {"status": "open"},
            "after_snapshot": {"status": "accepted"},
            "run_id": "run-n18",
            "evidence_ref": "ev-n18",
            "approval_id": "appr-n18",
            "started_at": time.time(),
            "completed_at": time.time(),
        },
        db_path=db_path,
    )
    if not first.get("before_snapshot") or not first.get("after_snapshot"):
        return _case("customer_action_audit", ok=False, detail="snapshot_missing")
    if not first.get("evidence_ref") or not first.get("approval_id"):
        return _case("customer_action_audit", ok=False, detail="audit_refs_missing")
    replay = persist_execution(
        {
            "tenant_id": tenant_id,
            "idempotency_key": key,
            "action_id": action_id,
            "actor": "n18-tester",
            "target": "Order:n18-1",
            "status": "succeeded",
            "before_snapshot": {"status": "mutated"},
            "after_snapshot": {"status": "mutated"},
        },
        db_path=db_path,
    )
    # 为什么：幂等键冲突必须回放首条，禁止改写历史快照
    if replay.get("execution_id") != first.get("execution_id"):
        return _case("customer_action_audit", ok=False, detail="idempotent_id_mismatch")
    if (replay.get("before_snapshot") or {}).get("status") != "open":
        return _case("customer_action_audit", ok=False, detail="history_mutated")
    looked = lookup_execution(tenant_id, key, db_path=db_path)
    if not looked or looked.get("approval_id") != "appr-n18":
        return _case("customer_action_audit", ok=False, detail="lookup_failed")
    return _case("customer_action_audit", ok=True)


async def run_implementer_semantics_suite(
    *,
    work_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """跑 N18 最小实现方语义套件（真实 FactLedger / ActionExecution）。

    Args:
        work_dir: 可选工作目录；默认临时目录。

    Returns:
        套件汇总：cases / passed / required / certified=False。
    """
    from core.harness.knowledge_pipeline.fact_ledger import FactLedger

    root = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="n18-sem-"))
    root.mkdir(parents=True, exist_ok=True)
    ledger = FactLedger(
        db_path=str(root / "facts.sqlite3"),
        raw_dir=root / "raw",
    )
    await ledger.initialize()
    tenant_a = "tenant-n18-a"
    tenant_b = "tenant-n18-b"

    cases: List[Dict[str, Any]] = []
    cases.append(await _probe_raw_immutable(ledger, tenant_id=tenant_a))
    cases.append(await _probe_published_requires_evidence(ledger, tenant_id=tenant_a))
    cases.append(await _probe_citation_resolves(ledger, tenant_id=tenant_a))
    cases.append(
        await _probe_cross_tenant(ledger, tenant_a=tenant_a, tenant_b=tenant_b)
    )
    cases.append(
        _probe_customer_action_audit(db_path=str(root / "action_exec.sqlite3"))
    )

    by_id = {c["id"]: c for c in cases}
    missing_required = [cid for cid in REQUIRED_CASES if cid not in by_id]
    failed = [c["id"] for c in cases if not c.get("ok")]
    passed = len(failed) == 0 and not missing_required
    return {
        "ok": passed,
        "passed": passed,
        "cases": cases,
        "required": list(REQUIRED_CASES),
        "missing_required": missing_required,
        "failed": failed,
        "work_dir": str(root),
        # 为什么恒 false：最小探针 ≠ 生产策略源替换 / 全量 conformance
        "certified": False,
        "n18_full_conformance": False,
        "note": (
            "in-process FactLedger+ActionExecution probes; "
            "not deployed RBAC source replacement"
        ),
    }


def evaluate_implementer_semantics_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """评估 N18 门槛门（结构：必跑用例全绿；禁止冒充认证）。

    Args:
        suite: ``run_implementer_semantics_suite`` 回执；缺省视为未跑。

    Returns:
        gate 结果；``certified`` / ``n18_full_conformance`` 恒 false。
    """
    issues: List[str] = []
    if not suite:
        issues.append("suite_not_run")
        return {
            "pass": False,
            "issues": issues,
            "certified": False,
            "n18_full_conformance": False,
            "required": list(REQUIRED_CASES),
        }

    required = list(suite.get("required") or REQUIRED_CASES)
    cases = {c.get("id"): c for c in (suite.get("cases") or []) if c.get("id")}
    for cid in required:
        if cid not in cases:
            issues.append(f"missing_case:{cid}")
        elif not cases[cid].get("ok"):
            issues.append(f"case_failed:{cid}")
    for mid in suite.get("missing_required") or []:
        tag = f"missing_case:{mid}"
        if tag not in issues:
            issues.append(tag)
    if suite.get("certified") is True or suite.get("n18_full_conformance") is True:
        # 为什么：即使调用方误标 certified，门槛门仍拒绝冒充
        issues.append("honesty_certified_flag_forbidden")

    return {
        "pass": len(issues) == 0 and bool(suite.get("passed")),
        "issues": issues,
        "certified": False,
        "n18_full_conformance": False,
        "required": required,
        "failed": list(suite.get("failed") or []),
        "case_count": len(cases),
    }
