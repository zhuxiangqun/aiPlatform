"""知识域 Gold 评测流水线（附录 N N10 deepen）。

职责：
  - 登记域级 gold 数据集（cases + 门槛）
  - 按 DomainRouter / 显式域列表跑 Exact-match 评测（FactLedger 对照）
  - 显式 residual：opt-in ``judge_mode=llm`` 有界 object 等价判定（可注入 judge_fn）
  - 套件/门槛门：``accuracy_claim`` / ``certified`` / ``n10_full`` 恒 false

非目标：
  - 不宣称准确率达标或全知识域已 gold 覆盖
  - 不做真实 ECE 训练 / 不关闭 N10 ADR 例外 / 不替代 N13 校准封顶
  - LLM judge 不可用时诚实上报 ``llm_judge_unavailable``，不静默冒充 Exact-match
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Union

from core.harness.knowledge.domain_router import DomainRouter

logger = logging.getLogger(__name__)

_SUITE_CASES = (
    "register_gold_ok",
    "eval_exact_match",
    "missing_gold_reported",
    "multi_domain_scan",
    "honesty_accuracy_false",
    "honesty_certified_false",
    "llm_judge_opt_in",
    "llm_judge_unavailable",
)

LlmJudgeFn = Callable[..., Union[Dict[str, Any], Awaitable[Dict[str, Any]]]]


class KnowledgeGoldEvalError(ValueError):
    """知识域 gold 评测契约错误。"""


async def llm_judge_object_equiv(
    *,
    expected: str,
    actual: str,
    subject: str = "",
    predicate: str = "",
    judge_fn: Optional[LlmJudgeFn] = None,
) -> Dict[str, Any]:
    """N10 residual：有界 LLM object 字符串等价判定（非准确率宣称）。

    仅比较单对 object 文本是否语义等价；默认经 ``sys_llm_generate``，
    失败或未配置时返回 ``status=llm_judge_unavailable``。

    Args:
        expected: gold 期望 object。
        actual: FactLedger 实际 object。
        subject: 可选 subject（写入 judge prompt 上下文）。
        predicate: 可选 predicate。
        judge_fn: 可选注入判定函数（测试/离线）；返回 ``matched`` / ``status``。
    """
    exp = str(expected or "").strip()
    act = str(actual or "").strip()
    base = {
        "expected": exp,
        "actual": act,
        "subject": str(subject or ""),
        "predicate": str(predicate or ""),
        "accuracy_claim": False,
        "certified": False,
        "n10_full_conformance": False,
    }
    if exp == act:
        return {**base, "status": "ok", "matched": True, "via": "exact"}
    if judge_fn is not None:
        try:
            raw = judge_fn(
                expected=exp,
                actual=act,
                subject=subject,
                predicate=predicate,
            )
            if hasattr(raw, "__await__"):
                raw = await raw  # type: ignore[misc]
            if not isinstance(raw, dict):
                return {**base, "status": "llm_judge_unavailable", "matched": False}
            status = str(raw.get("status") or "ok").strip() or "ok"
            if status in {"unavailable", "llm_judge_unavailable"}:
                return {
                    **base,
                    "status": "llm_judge_unavailable",
                    "matched": False,
                    "via": "injected",
                }
            return {
                **base,
                "status": "ok",
                "matched": bool(raw.get("matched")),
                "via": "injected",
            }
        except Exception as exc:  # noqa: BLE001
            logger.debug("llm_judge inject failed: %s", exc)
            return {
                **base,
                "status": "llm_judge_unavailable",
                "matched": False,
                "via": "injected_error",
            }

    # 为什么：默认关闭实网 LLM，避免 CI/离线误把失败当 Exact-match；显式 opt-in 才打模型
    if os.environ.get("AIPLAT_KNOWLEDGE_GOLD_LLM_JUDGE", "").strip() not in {
        "1",
        "true",
        "yes",
    }:
        return {
            **base,
            "status": "llm_judge_unavailable",
            "matched": False,
            "via": "env_disabled",
            "note": "set AIPLAT_KNOWLEDGE_GOLD_LLM_JUDGE=1 to enable live LLM judge",
        }

    try:
        from core.harness.syscalls.llm import sys_llm_generate
        from core.harness.utils.model_injection import best_model_for_purpose

        model = best_model_for_purpose("clarify")
        prompt = (
            "Decide if two knowledge-fact object strings are semantically equivalent. "
            "Reply with exactly YES or NO.\n"
            f"subject={subject}\npredicate={predicate}\n"
            f"expected={exp}\nactual={act}\n"
        )
        # 为什么：prompt-type 判定跳过 CLAUDE.md 全量注入，避免噪声污染 YES/NO
        resp = await sys_llm_generate(
            model,
            prompt,
            model_name=model,
            temperature=0.0,
            max_tokens=8,
            trace_context={"skip_claude_md": True},
            inject_context=False,
        )
        text = ""
        if isinstance(resp, dict):
            text = str(resp.get("content") or resp.get("text") or "")
        else:
            text = str(resp or "")
        ans = text.strip().upper()
        matched = ans.startswith("YES")
        return {
            **base,
            "status": "ok",
            "matched": matched,
            "via": "llm",
            "model": model,
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("llm_judge live call unavailable: %s", exc)
        return {
            **base,
            "status": "llm_judge_unavailable",
            "matched": False,
            "via": "llm_error",
        }


def _default_db_path() -> str:
    """解析 gold 评测库路径（AIPLAT_HOME 约定）。"""
    env = os.environ.get("AIPLAT_KNOWLEDGE_GOLD_EVAL_DB")
    if env:
        return env
    home = os.environ.get("AIPLAT_HOME")
    if home:
        return str(Path(home) / "data" / "knowledge_gold_eval.sqlite3")
    return "./data/knowledge_gold_eval.sqlite3"


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """打开/初始化 gold 数据集与评测结果表。

    Args:
        db_path: 可选库路径。
    """
    path = db_path or _default_db_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gold_datasets (
            dataset_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            domain_id TEXT NOT NULL,
            version TEXT NOT NULL,
            cases_json TEXT NOT NULL,
            threshold REAL NOT NULL,
            created_at REAL NOT NULL,
            UNIQUE(tenant_id, domain_id, version)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gold_eval_runs (
            run_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            domain_id TEXT NOT NULL,
            dataset_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def register_gold_dataset(
    *,
    tenant_id: str,
    domain_id: str,
    version: str,
    cases: Sequence[Dict[str, Any]],
    threshold: float = 0.8,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """登记域级 gold 数据集。

    Args:
        tenant_id: 租户。
        domain_id: 域（调用方注入；非 harness 硬编码业务域）。
        version: 数据集版本。
        cases: ``[{subject,predicate,object}]`` Exact-match 用例。
        threshold: 通过率门槛（0–1）。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    did = (domain_id or "").strip()
    ver = (version or "").strip()
    if not tid or not did or not ver:
        raise KnowledgeGoldEvalError("tenant_domain_version_required")
    case_list: List[Dict[str, Any]] = []
    for c in cases or []:
        if not isinstance(c, dict):
            raise KnowledgeGoldEvalError("case_not_object")
        subj = str(c.get("subject") or "").strip()
        pred = str(c.get("predicate") or "").strip()
        obj = str(c.get("object") or "").strip()
        if not subj or not pred:
            raise KnowledgeGoldEvalError("case_subject_predicate_required")
        case_list.append({"subject": subj, "predicate": pred, "object": obj})
    if not case_list:
        raise KnowledgeGoldEvalError("cases_required")
    thr = float(threshold)
    if thr < 0 or thr > 1:
        raise KnowledgeGoldEvalError("threshold_out_of_range")

    dataset_id = f"gold-{uuid.uuid4().hex[:12]}"
    now = time.time()
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO gold_datasets(
                dataset_id, tenant_id, domain_id, version, cases_json,
                threshold, created_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                dataset_id,
                tid,
                did,
                ver,
                json.dumps(case_list, ensure_ascii=False),
                thr,
                now,
            ),
        )
        conn.commit()
        return {
            "status": "ok",
            "dataset_id": dataset_id,
            "tenant_id": tid,
            "domain_id": did,
            "version": ver,
            "case_count": len(case_list),
            "threshold": thr,
            "accuracy_claim": False,
            "certified": False,
            "n10_full_conformance": False,
        }
    finally:
        conn.close()


def get_gold_dataset(
    *,
    tenant_id: str,
    domain_id: str,
    version: str = "",
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """读取域 gold 数据集（最新或指定 version）。

    Args:
        tenant_id: 租户。
        domain_id: 域。
        version: 可选版本；空则取最新。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    did = (domain_id or "").strip()
    if not tid or not did:
        return None
    conn = _connect(db_path)
    try:
        ver = (version or "").strip()
        if ver:
            row = conn.execute(
                """
                SELECT * FROM gold_datasets
                WHERE tenant_id=? AND domain_id=? AND version=?
                """,
                (tid, did, ver),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT * FROM gold_datasets
                WHERE tenant_id=? AND domain_id=?
                ORDER BY created_at DESC LIMIT 1
                """,
                (tid, did),
            ).fetchone()
        if not row:
            return None
        return {
            "dataset_id": row["dataset_id"],
            "tenant_id": row["tenant_id"],
            "domain_id": row["domain_id"],
            "version": row["version"],
            "cases": json.loads(row["cases_json"] or "[]"),
            "threshold": float(row["threshold"]),
            "created_at": row["created_at"],
        }
    finally:
        conn.close()


async def evaluate_domain_gold(
    *,
    tenant_id: str,
    domain_id: str,
    ledger: Any = None,
    version: str = "",
    db_path: Optional[str] = None,
    judge_mode: str = "exact",
    llm_judge_fn: Optional[LlmJudgeFn] = None,
) -> Dict[str, Any]:
    """对单域跑 Exact-match（可选 LLM object 等价）gold 评测。

    Args:
        tenant_id: 租户。
        domain_id: 域。
        ledger: 可选 FactLedger。
        version: 可选 gold 版本。
        db_path: 可选 gold 库。
        judge_mode: ``exact``（默认）或 ``llm``（N10 residual opt-in）。
        llm_judge_fn: 可选注入 LLM judge（``judge_mode=llm`` 时）。
    """
    from core.harness.knowledge_pipeline.fact_ledger import (
        FactLedger,
        get_fact_ledger,
    )

    tid = (tenant_id or "").strip()
    did = (domain_id or "").strip()
    if not tid or not did:
        raise KnowledgeGoldEvalError("tenant_domain_required")
    mode = (judge_mode or "exact").strip().lower() or "exact"
    if mode not in {"exact", "llm"}:
        raise KnowledgeGoldEvalError("judge_mode_invalid")

    ds = get_gold_dataset(
        tenant_id=tid, domain_id=did, version=version, db_path=db_path
    )
    if not ds:
        return {
            "status": "missing_gold",
            "tenant_id": tid,
            "domain_id": did,
            "passed": False,
            "matched": 0,
            "total": 0,
            "score": 0.0,
            "threshold": None,
            "judge_mode": mode,
            "accuracy_claim": False,
            "certified": False,
            "n10_full_conformance": False,
        }

    store = ledger or get_fact_ledger()
    if isinstance(store, FactLedger):
        await store.initialize()
    facts = await store.query_facts(tenant_id=tid, domain_id=did, limit=5000)
    triples = {
        (
            str(f.get("subject") or ""),
            str(f.get("predicate") or ""),
            str(f.get("object") or ""),
        )
        for f in facts
    }
    by_sp: Dict[tuple, List[str]] = {}
    for s, p, o in triples:
        by_sp.setdefault((s, p), []).append(o)

    matched = 0
    llm_matched = 0
    llm_unavailable = 0
    details: List[Dict[str, Any]] = []
    for c in ds["cases"]:
        key = (c["subject"], c["predicate"], c["object"])
        ok = key in triples
        via = "exact" if ok else "miss"
        judge_receipt: Optional[Dict[str, Any]] = None
        if not ok and mode == "llm":
            candidates = [
                o
                for o in by_sp.get((c["subject"], c["predicate"]), [])
                if o != c["object"]
            ]
            if not candidates:
                llm_unavailable += 1
                via = "llm_judge_unavailable"
            else:
                judged_ok = False
                any_unavailable = False
                for act in candidates:
                    judge_receipt = await llm_judge_object_equiv(
                        expected=c["object"],
                        actual=act,
                        subject=c["subject"],
                        predicate=c["predicate"],
                        judge_fn=llm_judge_fn,
                    )
                    if judge_receipt.get("status") == "llm_judge_unavailable":
                        any_unavailable = True
                        continue
                    if judge_receipt.get("matched"):
                        judged_ok = True
                        break
                if judged_ok:
                    ok = True
                    via = "llm"
                    llm_matched += 1
                elif any_unavailable:
                    llm_unavailable += 1
                    via = "llm_judge_unavailable"
                else:
                    via = "llm_miss"
        if ok:
            matched += 1
        details.append(
            {
                "case": c,
                "matched": ok,
                "via": via,
                "llm_judge": judge_receipt,
            }
        )

    total = len(ds["cases"])
    score = (matched / total) if total else 0.0
    thr = float(ds["threshold"])
    passed = score >= thr
    out = {
        "status": "ok",
        "tenant_id": tid,
        "domain_id": did,
        "dataset_id": ds["dataset_id"],
        "version": ds["version"],
        "matched": matched,
        "total": total,
        "score": score,
        "threshold": thr,
        "passed": passed,
        "details": details,
        "judge_mode": mode,
        "llm_matched": llm_matched,
        "llm_unavailable": llm_unavailable,
        "accuracy_claim": False,
        "certified": False,
        "n10_full_conformance": False,
    }

    conn = _connect(db_path)
    try:
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        conn.execute(
            """
            INSERT INTO gold_eval_runs(
                run_id, tenant_id, domain_id, dataset_id, payload_json, created_at
            ) VALUES (?,?,?,?,?,?)
            """,
            (
                run_id,
                tid,
                did,
                ds["dataset_id"],
                json.dumps(out, ensure_ascii=False),
                time.time(),
            ),
        )
        conn.commit()
        out["run_id"] = run_id
    finally:
        conn.close()
    return out


async def run_knowledge_gold_eval_pipeline(
    *,
    tenant_id: str,
    domain_ids: Optional[Sequence[str]] = None,
    ledger: Any = None,
    db_path: Optional[str] = None,
    judge_mode: str = "exact",
    llm_judge_fn: Optional[LlmJudgeFn] = None,
) -> Dict[str, Any]:
    """跨域 gold 评测流水线（DomainRouter 或显式域列表）。

    Args:
        tenant_id: 租户。
        domain_ids: 可选域列表；默认 ``DomainRouter.list_domains()``。
        ledger: 可选 FactLedger。
        db_path: 可选 gold 库。
        judge_mode: ``exact`` 或 ``llm``（透传 evaluate_domain_gold）。
        llm_judge_fn: 可选注入 LLM judge。
    """
    tid = (tenant_id or "").strip()
    if not tid:
        raise KnowledgeGoldEvalError("tenant_id required")

    router = DomainRouter()
    ids = list(domain_ids) if domain_ids is not None else list(router.list_domains())
    # 为什么：空域列表时仍返回诚实回执，禁止假装全覆盖
    results: List[Dict[str, Any]] = []
    for did in ids:
        results.append(
            await evaluate_domain_gold(
                tenant_id=tid,
                domain_id=str(did),
                ledger=ledger,
                db_path=db_path,
                judge_mode=judge_mode,
                llm_judge_fn=llm_judge_fn,
            )
        )

    with_gold = [r for r in results if r.get("status") == "ok"]
    missing = [r for r in results if r.get("status") == "missing_gold"]
    passed_domains = [r for r in with_gold if r.get("passed")]
    return {
        "status": "ok",
        "tenant_id": tid,
        "domains_scanned": len(ids),
        "with_gold": len(with_gold),
        "missing_gold": len(missing),
        "passed_domains": len(passed_domains),
        "results": results,
        "coverage_complete": len(missing) == 0 and len(ids) > 0 and len(with_gold) == len(ids),
        "judge_mode": (judge_mode or "exact").strip().lower() or "exact",
        "accuracy_claim": False,
        "certified": False,
        "n10_full_conformance": False,
        "note": "Domain gold exact-match (+opt-in llm residual); not full-domain certified / no accuracy claim",
    }


def evaluate_knowledge_gold_eval_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N10 deepen：gold 评测门槛门（certified / accuracy 恒 false）。

    Args:
        suite: ``run_knowledge_gold_eval_suite`` 回执。
    """
    s = suite or {}
    issues: List[str] = []
    # 为什么：禁止套件自签 certified（Exact-match ≠ N10 全量认证）
    if s.get("certified") is True:
        issues.append("honesty_certified_flag_forbidden")
    # 为什么：禁止套件自签 n10_full（加深刀 ≠ 附录 N 全量符合）
    if s.get("n10_full_conformance") is True:
        issues.append("honesty_n10_full_flag_forbidden")
    # 为什么：Exact-match 命中率 ≠ 准确率宣称
    if s.get("accuracy_claim") is True:
        issues.append("honesty_accuracy_claim_forbidden")
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
        "n10_full_conformance": False,
        "accuracy_claim": False,
        "n10_gold_eval_freeze": True,
        "note": "Knowledge gold eval deepen + llm residual; not N10 certified / no accuracy claim",
    }


async def run_knowledge_gold_eval_suite(
    *,
    tenant_id: str = "n10-gold-eval-tenant",
) -> Dict[str, Any]:
    """N10 deepen：gold 评测套件（certified / accuracy 恒 false）。

    Args:
        tenant_id: 租户。
    """
    from core.harness.knowledge_pipeline.fact_ledger import FactLedger

    tmp = tempfile.TemporaryDirectory(prefix="n10-gold-eval-")
    root = Path(tmp.name)
    gold_db = str(root / "gold.sqlite3")
    lg = FactLedger(
        db_path=str(root / "fact_ledger.sqlite3"),
        raw_dir=root / "raw",
    )
    await lg.initialize()
    cases: List[Dict[str, Any]] = []
    try:
        d_a = "suite-domain-a"
        d_b = "suite-domain-b"

        reg = register_gold_dataset(
            tenant_id=tenant_id,
            domain_id=d_a,
            version="v1",
            cases=[
                {
                    "subject": "InstallOrder:WO-N10",
                    "predicate": "status",
                    "object": "open",
                }
            ],
            threshold=1.0,
            db_path=gold_db,
        )
        cases.append(
            {
                "id": "register_gold_ok",
                "ok": reg.get("status") == "ok" and reg.get("accuracy_claim") is False,
                "detail": "",
            }
        )

        src = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n10-gold",
            kind="file",
            uri="file://n10/gold.txt",
            content=b"n10-gold",
            connector="n10",
            domain_id=d_a,
        )
        await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n10-gold",
            subject="InstallOrder:WO-N10",
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
            source_policy="n10",
            extractor_version="n10",
            review_status="published",
            confidence=0.9,
            allow_bootstrap_published=True,
            domain_id=d_a,
        )

        ev = await evaluate_domain_gold(
            tenant_id=tenant_id,
            domain_id=d_a,
            ledger=lg,
            db_path=gold_db,
        )
        cases.append(
            {
                "id": "eval_exact_match",
                "ok": bool(ev.get("passed")) and ev.get("matched") == 1,
                "detail": "" if ev.get("passed") else "match_failed",
            }
        )

        miss = await evaluate_domain_gold(
            tenant_id=tenant_id,
            domain_id=d_b,
            ledger=lg,
            db_path=gold_db,
        )
        cases.append(
            {
                "id": "missing_gold_reported",
                "ok": miss.get("status") == "missing_gold",
                "detail": "",
            }
        )

        pipe = await run_knowledge_gold_eval_pipeline(
            tenant_id=tenant_id,
            domain_ids=[d_a, d_b],
            ledger=lg,
            db_path=gold_db,
        )
        cases.append(
            {
                "id": "multi_domain_scan",
                "ok": pipe.get("domains_scanned") == 2
                and pipe.get("with_gold") == 1
                and pipe.get("missing_gold") == 1
                and pipe.get("coverage_complete") is False,
                "detail": "",
            }
        )

        cases.append(
            {
                "id": "honesty_accuracy_false",
                "ok": pipe.get("accuracy_claim") is False
                and ev.get("accuracy_claim") is False,
                "detail": "",
            }
        )
        cases.append(
            {
                "id": "honesty_certified_false",
                "ok": pipe.get("certified") is False
                and pipe.get("n10_full_conformance") is False,
                "detail": "",
            }
        )

        # residual：LLM judge opt-in（同义 object；注入 judge，不宣称 accuracy）
        d_llm = "suite-domain-llm"
        register_gold_dataset(
            tenant_id=tenant_id,
            domain_id=d_llm,
            version="v1",
            cases=[
                {
                    "subject": "InstallOrder:WO-LLM",
                    "predicate": "status",
                    "object": "opened",
                }
            ],
            threshold=1.0,
            db_path=gold_db,
        )
        src_llm = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n10-gold-llm",
            kind="file",
            uri="file://n10/gold-llm.txt",
            content=b"n10-gold-llm",
            connector="n10",
            domain_id=d_llm,
        )
        await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n10-gold-llm",
            subject="InstallOrder:WO-LLM",
            predicate="status",
            object="open",
            evidence=[
                {
                    "source_id": src_llm["source_id"],
                    "locator": "1",
                    "quote": "ok",
                    "fetched_at": src_llm["fetched_at"],
                }
            ],
            source_policy="n10",
            extractor_version="n10",
            review_status="published",
            confidence=0.9,
            allow_bootstrap_published=True,
            domain_id=d_llm,
        )

        def _syn_judge(*, expected: str, actual: str, **_kw: Any) -> Dict[str, Any]:
            pair = {str(expected), str(actual)}
            return {
                "status": "ok",
                "matched": pair <= {"open", "opened"} or expected == actual,
            }

        llm_ok = await evaluate_domain_gold(
            tenant_id=tenant_id,
            domain_id=d_llm,
            ledger=lg,
            db_path=gold_db,
            judge_mode="llm",
            llm_judge_fn=_syn_judge,
        )
        cases.append(
            {
                "id": "llm_judge_opt_in",
                "ok": bool(llm_ok.get("passed"))
                and int(llm_ok.get("llm_matched") or 0) >= 1
                and llm_ok.get("accuracy_claim") is False
                and llm_ok.get("certified") is False,
                "detail": "" if llm_ok.get("passed") else "llm_opt_in_failed",
            }
        )

        def _unavail_judge(**_kw: Any) -> Dict[str, Any]:
            return {"status": "llm_judge_unavailable", "matched": False}

        llm_un = await evaluate_domain_gold(
            tenant_id=tenant_id,
            domain_id=d_llm,
            ledger=lg,
            db_path=gold_db,
            judge_mode="llm",
            llm_judge_fn=_unavail_judge,
        )
        cases.append(
            {
                "id": "llm_judge_unavailable",
                "ok": llm_un.get("passed") is False
                and int(llm_un.get("llm_unavailable") or 0) >= 1
                and llm_un.get("accuracy_claim") is False,
                "detail": "",
            }
        )

        passed = sum(1 for c in cases if c.get("ok"))
        return {
            "ok": passed == len(_SUITE_CASES),
            "passed": passed,
            "total": len(_SUITE_CASES),
            "cases": cases,
            "pipeline": pipe,
            "certified": False,
            "n10_full_conformance": False,
            "accuracy_claim": False,
            "n10_gold_eval_freeze": True,
            "note": "Knowledge gold eval deepen + llm residual; not full-domain / accuracy certified",
        }
    finally:
        tmp.cleanup()
