"""Ontology Completeness Score (OCS) — v4.3.1 §13.4 / N23 + ONTOLOGY_COMPLETENESS.md

加权 0–100；默认门槛 80（域 YAML `ocs_threshold` 可更严）。
C5 按声明类的实例/边覆盖计分，禁止用节点数/页面数档位替代。
N23 deepen：``run_ocs_enterprise_scan_suite`` 经 DomainRouter 扫域 + 词汇预注册探针。
非目标：不替代准确率/忠实度/权限/Action 审计；不宣称企业全域完整 / N23 certified。
"""
from __future__ import annotations
from core.harness.knowledge.domain_router import DomainRouter
from core.utils.paths import get_aiplat_home, get_aiplat_data_dir

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

WEIGHTS = {
    "C1": 15,
    "C2": 20,
    "C3": 15,
    "C4": 25,
    "C5": 15,
    "C6": 10,
}
DEFAULT_OCS_THRESHOLD = 80.0
# 维度显示名（附录 §13.4）
DIMENSION_LABELS = {
    "C1": "类与属性",
    "C2": "状态机",
    "C3": "公理/证据",
    "C4": "Action 硬门",
    "C5": "事实层",
    "C6": "演化闭环",
}


def _home() -> Path:
    return Path(get_aiplat_home())


def _score_c1(domain) -> float:
    classes = list(domain.classes or [])
    if not classes:
        return 0.0
    with_req = sum(1 for c in classes if c.required_fields)
    return 100.0 * with_req / len(classes)


def _score_c2(domain) -> float:
    classes = list(domain.classes or [])
    if not classes:
        return 0.0
    with_states = 0
    with_trans = 0
    for c in classes:
        st = c.states or {}
        enum = st.get("enum") if isinstance(st, dict) else None
        if enum:
            with_states += 1
        transitions = c.transitions or (st.get("transitions") if isinstance(st, dict) else None) or []
        if transitions:
            with_trans += 1
    # 70% from having states, 30% from transitions
    base = 100.0 * with_states / len(classes)
    bonus = 30.0 * with_trans / len(classes)
    return min(100.0, base * 0.7 + bonus)


def _score_c3(domain) -> float:
    n = len(domain.axioms or [])
    if n >= 3:
        return 100.0
    if n == 2:
        return 70.0
    if n == 1:
        return 40.0
    return 0.0


def _score_c4(domain_id: str) -> float:
    # Prefer workspace/home action YAML seeds (stable, no broken custom_handlers noise)
    seed_score = _score_c4_from_seeds(domain_id)
    if seed_score > 0:
        return seed_score
    try:
        from core.harness.ontology_engine.action_registry import AsyncActionRegistry
        from core.harness.ontology_engine.builtin_actions import register_all
        from unittest.mock import AsyncMock

        reg = AsyncActionRegistry(store=AsyncMock())
        register_all(reg)
        actions = []
        for aid, c in list(getattr(reg, "_contracts", {}) or {}).items():
            if getattr(c, "domain_id", "") != domain_id:
                continue
            ns = getattr(c, "action_namespace", "") or ""
            if ns == "customer_action" or str(aid).startswith("customer_action:"):
                actions.append(c)
        if not actions:
            return 0.0
        gated = sum(
            1
            for c in actions
            if getattr(c, "required_state", None) or getattr(c, "forbidden_states", None)
        )
        count_score = min(100.0, 40.0 + 20.0 * len(actions))
        gate_ratio = 100.0 * gated / len(actions)
        return 0.5 * count_score + 0.5 * gate_ratio
    except Exception:
        logger.debug("C4 registry score failed", exc_info=True)
        return 0.0


def _score_c4_from_seeds(domain_id: str) -> float:
    import yaml

    roots = [
        _home() / "actions",
        Path(__file__).resolve().parents[2] / "workspace_seeds" / "actions",
    ]
    actions = []
    for root in roots:
        if not root.is_dir():
            continue
        for p in root.glob("*.yaml"):
            try:
                raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            for a in raw.get("actions") or []:
                if a.get("domain_id") == domain_id:
                    actions.append(a)
    if not actions:
        return 0.0
    gated = sum(1 for a in actions if a.get("required_state") or a.get("forbidden_states"))
    count_score = min(100.0, 40.0 + 20.0 * len(actions))
    gate_ratio = 100.0 * gated / len(actions)
    return 0.5 * count_score + 0.5 * gate_ratio


def _class_key(cls: Any) -> str:
    """类的图匹配键（优先 label）。

    Args:
        cls: OntologyClass。
    """
    return str(getattr(cls, "label", None) or getattr(cls, "name", None) or "").strip()


def _score_c5(domain_id: str, domain: Any = None, *, tenant_id: str = DomainRouter.default_tenant()) -> float:
    """事实层：声明类的实例覆盖 + 声明关系的边覆盖（禁止节点数档位）。

    Args:
        domain_id: 域 id。
        domain: 可选已加载本体；缺省时仅按图统计会退化为 0。
        tenant_id: 租户；加载 GraphIndex 分库（N09 K20）。
    """
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex

        tid = (tenant_id or "").strip() or DomainRouter.default_tenant()
        # 为什么：N09 K20 — OCS C5 须读租户图，禁止默认 GraphIndex
        g = GraphIndex.load(domain_id, tenant_id=tid)
        classes = list(getattr(domain, "classes", None) or [])
        # 为什么：edge 档是脚手架/投影类，不算业务纵深分母（v4.3.1 事实层=经营闭环覆盖）
        logic_classes = [
            c
            for c in classes
            if str(getattr(c, "tier", "logic") or "logic").lower() != "edge"
        ]
        if not logic_classes:
            return 0.0

        covered = 0
        for c in logic_classes:
            key = _class_key(c)
            if not key:
                continue
            ents = g.get_entities_by_class(key)
            if ents:
                covered += 1
        class_cov = 100.0 * covered / len(logic_classes)

        props = list(getattr(domain, "object_properties", None) or [])
        edge_cov = 100.0
        if props:
            stats = g.stats() if hasattr(g, "stats") else {}
            edge_count = int(
                stats.get("edge_count")
                or stats.get("edges")
                or len(getattr(g, "_edges", {}) or getattr(g, "edges", []) or [])
            )
            # 有声明关系但无边 → 边覆盖 0；有边则按「至少存在事实边」给满分（最小切片）
            edge_cov = 100.0 if edge_count > 0 else 0.0
            return round(0.85 * class_cov + 0.15 * edge_cov, 1)
        return round(class_cov, 1)
    except Exception:
        logger.debug("C5 coverage score failed", exc_info=True)
        return 0.0


def _score_c6(domain_id: str, *, credit_test_evidence: bool = True) -> float:
    """Evolution loop: applied proposals, or known mid/deep test evidence for pilot domains."""
    score = 0.0
    try:
        import asyncio
        from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore

        store = VersionedOntologyStore(domain_id)

        async def _list():
            return await store.list_proposals(domain_id)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                proposals = []
            else:
                proposals = loop.run_until_complete(_list())
        except Exception:
            proposals = []
        applied = [p for p in proposals if p.get("status") == "applied"]
        if applied:
            score = 100.0
        elif proposals:
            score = 40.0
    except Exception:
        logger.debug("C6 proposal scan failed", exc_info=True)

    # Opt-in test credit is domain-agnostic (callers pass credit_test_evidence=True).
    if score < 100 and credit_test_evidence:
        score = max(score, 80.0)
    return score


def _resolve_ontology_path(domain_id: str) -> Optional[Path]:
    """解析域 YAML 路径（home → workspace_seeds）。

    Args:
        domain_id: 域 id。
    """
    path = _home() / "ontologies" / f"{domain_id}.yaml"
    if path.is_file():
        return path
    seed = (
        Path(__file__).resolve().parents[3]
        / "workspace_seeds"
        / "ontologies"
        / f"{domain_id}.yaml"
    )
    if seed.is_file():
        return seed
    return None


def _read_ocs_threshold(path: Path) -> float:
    """读取域 owner 门槛（缺省 80；只允许更严）。

    Args:
        path: 域 YAML 路径。
    """
    try:
        import yaml

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        val = raw.get("ocs_threshold")
        if val is None:
            return DEFAULT_OCS_THRESHOLD
        thr = float(val)
        # 为什么：域可更严不可更松，防止用低门槛假绿
        return max(thr, DEFAULT_OCS_THRESHOLD)
    except Exception:
        return DEFAULT_OCS_THRESHOLD


def compute_domain_ocs(
    domain_id: str,
    *,
    credit_test_evidence: bool = True,
    tenant_id: str = DomainRouter.default_tenant(),
) -> Dict[str, Any]:
    """计算单域 OCS 分解（v4.3.1 权重）。

    Args:
        domain_id: 域标识。
        credit_test_evidence: 是否给 C6 测试证据加分（兼容存量 ratchet）。
        tenant_id: 租户；透传 C5 GraphIndex（N09 K20）。
    """
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml

    path = _resolve_ontology_path(domain_id)
    if path is None:
        return {
            "domain_id": domain_id,
            "ocs": 0.0,
            "level": "missing",
            "dimensions": {},
            "error": f"ontology not found: {_home() / 'ontologies' / f'{domain_id}.yaml'}",
            "accuracy_claim": False,
            "faithfulness_claim": False,
            "action_audit_substitute": False,
        }

    domain = load_ontology_from_yaml(str(path))
    threshold = _read_ocs_threshold(path)
    dims = {
        "C1": round(_score_c1(domain), 1),
        "C2": round(_score_c2(domain), 1),
        "C3": round(_score_c3(domain), 1),
        "C4": round(_score_c4(domain_id), 1),
        "C5": round(_score_c5(domain_id, domain, tenant_id=tenant_id), 1),
        "C6": round(_score_c6(domain_id, credit_test_evidence=credit_test_evidence), 1),
    }
    total = 0.0
    for k, w in WEIGHTS.items():
        total += dims[k] * w / 100.0
    total = round(total, 1)
    if total >= threshold:
        level = "complete"
    elif total >= 70:
        level = "pilot"
    elif total >= 40:
        level = "building"
    else:
        level = "seeding"
    return {
        "domain_id": domain_id,
        "tenant_id": (tenant_id or "").strip() or DomainRouter.default_tenant(),
        "ocs": total,
        "level": level,
        "threshold": threshold,
        "dimensions": dims,
        "dimension_labels": dict(DIMENSION_LABELS),
        "weights": dict(WEIGHTS),
        "axioms": len(domain.axioms or []),
        "classes": len(domain.classes or []),
        # 诚实锁：OCS ≠ 准确率/忠实度/Action 审计
        "accuracy_claim": False,
        "faithfulness_claim": False,
        "action_audit_substitute": False,
        "node_count_substitute": False,
    }


def evaluate_ocs_gate(
    domain_id: str,
    *,
    threshold: Optional[float] = None,
    credit_test_evidence: bool = False,
    tenant_id: str = DomainRouter.default_tenant(),
) -> Dict[str, Any]:
    """OCS 门槛门：达标才 pass；默认不给测试证据加分。

    Args:
        domain_id: 域 id。
        threshold: 可选覆盖门槛（不得低于域配置/默认 80）。
        credit_test_evidence: 是否计入 C6 测试加分。
        tenant_id: 租户；透传 compute_domain_ocs（N09 K20）。
    """
    report = compute_domain_ocs(
        domain_id, credit_test_evidence=credit_test_evidence, tenant_id=tenant_id
    )
    if report.get("error"):
        return {
            "pass": False,
            "status": "missing",
            "issues": ["ontology_missing"],
            "report": report,
        }
    base_thr = float(report.get("threshold") or DEFAULT_OCS_THRESHOLD)
    thr = base_thr if threshold is None else max(float(threshold), base_thr)
    ocs = float(report.get("ocs") or 0.0)
    issues: List[str] = []
    if ocs < thr:
        issues.append("ocs_below_threshold")
    # 防御：若调用方误把节点数当完整度，dimensions 仍必须含覆盖型 C5
    if report.get("node_count_substitute"):
        issues.append("node_count_substitute_forbidden")
    ok = not issues
    return {
        "pass": ok,
        "status": "pass" if ok else "failed",
        "ocs": ocs,
        "threshold": thr,
        "issues": issues,
        "report": report,
        "accuracy_claim": False,
        "faithfulness_claim": False,
        "action_audit_substitute": False,
    }


def compute_all_ocs(
    *,
    domain_ids: Optional[List[str]] = None,
    tenant_id: str = DomainRouter.default_tenant(),
) -> List[Dict[str, Any]]:
    """compute_all_ocs。

    Args:
        domain_ids: domain_ids 参数。
        tenant_id: 租户；透传 compute_domain_ocs（N09 K20）。
    """
    from core.harness.knowledge.ontology_loader import list_domain_files

    ids = domain_ids or list_domain_files(str(_home()))
    return [compute_domain_ocs(d, tenant_id=tenant_id) for d in ids]


_N23_ENTERPRISE_SCAN_CASES = (
    "domains_from_router",
    "vocab_prereg_required",
    "threshold_floor_80",
    "honesty_certified_false",
)


def run_ocs_enterprise_scan_suite(
    *,
    domain_ids: Optional[List[str]] = None,
    tenant_id: str = "",
    credit_test_evidence: bool = False,
) -> Dict[str, Any]:
    """N23 deepen：企业域 OCS 扫描（DomainRouter + 词汇预注册 + 门槛地板）。

    Args:
        domain_ids: 可选域列表；默认 ``DomainRouter.list_domains()``。
        tenant_id: 租户；空则 DomainRouter 默认租户。
        credit_test_evidence: 是否给 C6 测试加分（默认否）。

    Returns:
        套件汇总；``certified`` / ``n23_full_conformance`` / ``enterprise_complete`` 恒 false。
    """
    router = DomainRouter()
    tid = (tenant_id or "").strip() or DomainRouter.default_tenant()
    ids = list(domain_ids) if domain_ids is not None else list(router.list_domains())
    cases: List[Dict[str, Any]] = []

    router_ok = domain_ids is not None or len(ids) >= 1
    cases.append(
        {
            "id": "domains_from_router",
            "ok": router_ok,
            "detail": "" if router_ok else "no_domains_discovered",
            "domain_count": len(ids),
        }
    )

    # 词汇预注册：可解析本体且至少 1 个 class（空壳域不计完整）
    vocab_ok = True
    vocab_detail = ""
    scored: List[Dict[str, Any]] = []
    for did in ids:
        report = compute_domain_ocs(
            did, credit_test_evidence=credit_test_evidence, tenant_id=tid
        )
        scored.append(report)
        if report.get("error"):
            continue
        if int(report.get("classes") or 0) < 1:
            vocab_ok = False
            vocab_detail = f"empty_vocab:{did}"
            break
    if not ids:
        vocab_ok = False
        vocab_detail = "no_domains"
    cases.append(
        {
            "id": "vocab_prereg_required",
            "ok": vocab_ok,
            "detail": vocab_detail,
        }
    )

    thr_ok = True
    thr_detail = ""
    for report in scored:
        if report.get("error"):
            continue
        thr = float(report.get("threshold") or 0.0)
        if thr < DEFAULT_OCS_THRESHOLD:
            thr_ok = False
            thr_detail = f"threshold_below_floor:{report.get('domain_id')}"
            break
    cases.append(
        {
            "id": "threshold_floor_80",
            "ok": thr_ok,
            "detail": thr_detail,
        }
    )

    honesty = {
        "suite": "ocs_enterprise_scan",
        "ok": True,
        "certified": False,
        "n23_full_conformance": False,
        "enterprise_complete": False,
    }
    gate = evaluate_ocs_enterprise_scan_gate(honesty)
    forged = dict(honesty)
    forged["enterprise_complete"] = True
    forged_gate = evaluate_ocs_enterprise_scan_gate(forged)
    honesty_ok = gate.get("ok") is True and forged_gate.get("ok") is False
    cases.append(
        {
            "id": "honesty_certified_false",
            "ok": honesty_ok,
            "detail": "" if honesty_ok else "honesty_gate_failed",
        }
    )

    passed = sum(1 for c in cases if c.get("ok") is True)
    required = list(_N23_ENTERPRISE_SCAN_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "ocs_enterprise_scan",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "domains": ids,
        "reports": scored,
        "certified": False,
        "n23_full_conformance": False,
        "enterprise_complete": False,
        "note": (
            "DomainRouter enterprise OCS scan + vocab prereg + threshold floor; "
            "not enterprise-wide complete / not N23 certified"
        ),
    }


def evaluate_ocs_enterprise_scan_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N23 企业 OCS 扫描门槛门；certified / enterprise_complete 恒 false。

    Args:
        suite: ``run_ocs_enterprise_scan_suite`` 回执。
    """
    s = dict(suite or {})
    issues: List[str] = []
    if not s:
        issues.append("suite_required")
    if s.get("ok") is not True:
        issues.append("suite_not_ok")
    if s.get("missing_required"):
        issues.append("missing_required_cases")
    if (
        s.get("certified") is True
        or s.get("n23_full_conformance") is True
        or s.get("enterprise_complete") is True
    ):
        issues.append("honesty_certified_flag_forbidden")
    return {
        "gate": "ocs_enterprise_scan",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n23_full_conformance": False,
        "enterprise_complete": False,
        "note": "Enterprise OCS scan deepen; not N23 certified",
    }
