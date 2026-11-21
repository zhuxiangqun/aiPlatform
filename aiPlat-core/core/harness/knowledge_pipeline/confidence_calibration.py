"""Confidence Calibration Report 最小切片（附录 O / W10 / N13）— 可复现校准门。

职责：登记校准报告；校验必填与门槛；失败时 confidence 上限 medium；
  Operational 查询路径封顶（``apply_calibration_ceiling``）+ 流水线套件。
非目标：不做真实 ECE 训练；不宣称准确率；不替代 OCS；不做迁移双写；
  不宣称 N13 certified。
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 附录 O / §9.6.7 默认门槛（域可更严，不可更松）
DEFAULT_ECE_MAX = 0.05
DEFAULT_HIGH_PRECISION_MIN = 0.90
DEFAULT_SAMPLE_MIN = 100
DEFAULT_DUAL_ANNOTATION_MIN = 0.20
CONFIDENCE_LEVELS = ("low", "medium", "high")


def _default_db_path() -> str:
    """解析校准报告 DB（AIPLAT_HOME 约定）。"""
    env = os.environ.get("AIPLAT_CONFIDENCE_CALIBRATION_DB")
    if env:
        return env
    home = os.environ.get("AIPLAT_HOME")
    if home:
        return str(Path(home) / "data" / "knowledge_confidence_calibration.sqlite3")
    return "./data/knowledge_confidence_calibration.sqlite3"


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """打开/初始化校准报告表。

    Args:
        db_path: 可选库路径。
    """
    path = db_path or _default_db_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS calibration_reports (
            calibration_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            domain TEXT NOT NULL,
            query_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at REAL,
            UNIQUE(tenant_id, domain, query_type, calibration_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS calibration_active (
            tenant_id TEXT NOT NULL,
            domain TEXT NOT NULL,
            query_type TEXT NOT NULL,
            calibration_id TEXT NOT NULL,
            updated_at REAL,
            PRIMARY KEY(tenant_id, domain, query_type)
        )
        """
    )
    conn.commit()
    return conn


def _parse_iso_date(value: str) -> Optional[datetime]:
    """解析 ISO 日期/时间；失败返回 None。

    Args:
        value: 日期字符串。
    """
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """行 → API dict。

    Args:
        row: sqlite Row。
    """
    payload = json.loads(row["payload_json"])
    return {
        "calibration_id": row["calibration_id"],
        "tenant_id": row["tenant_id"],
        "domain": row["domain"],
        "query_type": row["query_type"],
        "status": row["status"],
        "created_at": row["created_at"],
        "payload": payload,
    }


def publish_calibration_report(
    *,
    tenant_id: str,
    domain: str,
    query_type: str,
    dataset_version: str,
    sample_size: int,
    label_protocol: str,
    inter_annotator_agreement: float,
    weights: Optional[Dict[str, Any]] = None,
    calibration_version: str,
    ece: float,
    brier: float,
    high_precision: float,
    coverage: float,
    approved_by: str,
    valid_until: str,
    model_version: str = "",
    index_version: str = "",
    source_policy_version: str = "",
    sample_shortage_justification: str = "",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """发布校准报告并设为该域/query_type 的 active。

    Args:
        tenant_id: 租户。
        domain: 域 id。
        query_type: 查询类型。
        dataset_version: 数据集版本。
        sample_size: 样本量。
        label_protocol: 标注规程说明。
        inter_annotator_agreement: 一致率（0–1；双人标注比例代理）。
        weights: 校准权重对象。
        calibration_version: 校准规程版本。
        ece: Expected Calibration Error。
        brier: Brier score。
        high_precision: high 档精度。
        coverage: 覆盖率。
        approved_by: 批准人。
        valid_until: 有效期（ISO）。
        model_version: 绑定模型版本。
        index_version: 绑定索引版本。
        source_policy_version: 来源策略版本。
        sample_shortage_justification: 样本不足时的统计论证。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    dom = (domain or "").strip()
    qt = (query_type or "").strip()
    if not tid or not dom or not qt:
        return {"status": "invalid", "error": "tenant_domain_query_required"}
    if not (dataset_version or "").strip() or not (calibration_version or "").strip():
        return {"status": "invalid", "error": "dataset_or_calibration_version_required"}
    if not (approved_by or "").strip():
        return {"status": "invalid", "error": "approved_by_required"}
    if _parse_iso_date(valid_until) is None:
        return {"status": "invalid", "error": "valid_until_invalid"}

    payload: Dict[str, Any] = {
        "domain": dom,
        "query_type": qt,
        "dataset_version": dataset_version.strip(),
        "sample_size": int(sample_size),
        "label_protocol": (label_protocol or "").strip(),
        "inter_annotator_agreement": float(inter_annotator_agreement),
        "weights": dict(weights or {}),
        "calibration_version": calibration_version.strip(),
        "ece": float(ece),
        "brier": float(brier),
        "high_precision": float(high_precision),
        "coverage": float(coverage),
        "approved_by": approved_by.strip(),
        "valid_until": valid_until.strip(),
        "model_version": (model_version or "").strip(),
        "index_version": (index_version or "").strip(),
        "source_policy_version": (source_policy_version or "").strip(),
        "sample_shortage_justification": (sample_shortage_justification or "").strip(),
    }

    gate = evaluate_calibration_gate(payload)
    status = "approved" if gate["pass"] else "failed"
    cid = f"cal-{uuid.uuid4().hex[:16]}"
    payload["calibration_id"] = cid
    now = time.time()

    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO calibration_reports(
                calibration_id, tenant_id, domain, query_type,
                payload_json, status, created_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                cid,
                tid,
                dom,
                qt,
                json.dumps(payload, ensure_ascii=False),
                status,
                now,
            ),
        )
        # 为什么：失败报告也登记以便审计，但不得成为 active
        if status == "approved":
            conn.execute(
                """
                INSERT INTO calibration_active(tenant_id, domain, query_type, calibration_id, updated_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(tenant_id, domain, query_type) DO UPDATE SET
                    calibration_id=excluded.calibration_id,
                    updated_at=excluded.updated_at
                """,
                (tid, dom, qt, cid, now),
            )
        conn.commit()
        return {
            "status": status,
            "calibration_id": cid,
            "active": status == "approved",
            "gate": gate,
            "payload": payload,
        }
    finally:
        conn.close()


def get_calibration_report(
    calibration_id: Optional[str] = None,
    *,
    tenant_id: str,
    domain: str = "",
    query_type: str = "",
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """按 id 或域/query_type active 读取；跨租户隐藏。

    Args:
        calibration_id: 报告 id；空则取 active。
        tenant_id: 租户。
        domain: 域（取 active 时必填）。
        query_type: 查询类型（取 active 时必填）。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    if not tid:
        return None
    conn = _connect(db_path)
    try:
        cid = (calibration_id or "").strip()
        if not cid:
            dom = (domain or "").strip()
            qt = (query_type or "").strip()
            if not dom or not qt:
                return None
            active = conn.execute(
                """
                SELECT calibration_id FROM calibration_active
                WHERE tenant_id=? AND domain=? AND query_type=?
                """,
                (tid, dom, qt),
            ).fetchone()
            if not active:
                return None
            cid = active["calibration_id"]
        row = conn.execute(
            """
            SELECT * FROM calibration_reports
            WHERE calibration_id=? AND tenant_id=?
            """,
            (cid, tid),
        ).fetchone()
        if not row:
            return None
        out = _row_to_dict(row)
        active = conn.execute(
            """
            SELECT calibration_id FROM calibration_active
            WHERE tenant_id=? AND domain=? AND query_type=?
            """,
            (tid, out["domain"], out["query_type"]),
        ).fetchone()
        out["active"] = bool(active and active["calibration_id"] == cid)
        return out
    finally:
        conn.close()


def evaluate_calibration_gate(payload: Dict[str, Any]) -> Dict[str, Any]:
    """按附录 O 门槛评估报告（不读库）。

    Args:
        payload: 报告字段。
    """
    issues: List[str] = []
    required = (
        "domain",
        "query_type",
        "dataset_version",
        "sample_size",
        "label_protocol",
        "inter_annotator_agreement",
        "weights",
        "calibration_version",
        "ece",
        "brier",
        "high_precision",
        "coverage",
        "approved_by",
        "valid_until",
    )
    for key in required:
        if key not in payload or payload.get(key) in (None, ""):
            issues.append(f"missing_{key}")

    sample_size = int(payload.get("sample_size") or 0)
    justification = str(payload.get("sample_shortage_justification") or "").strip()
    if sample_size < DEFAULT_SAMPLE_MIN and not justification:
        issues.append("sample_size_below_100_without_justification")

    iaa = float(payload.get("inter_annotator_agreement") or 0.0)
    if iaa < DEFAULT_DUAL_ANNOTATION_MIN:
        issues.append("dual_annotation_below_20pct")

    ece = float(payload.get("ece") or 999.0)
    if ece > DEFAULT_ECE_MAX:
        issues.append("ece_above_threshold")

    high_precision = float(payload.get("high_precision") or 0.0)
    if high_precision < DEFAULT_HIGH_PRECISION_MIN:
        issues.append("high_precision_below_threshold")

    valid_until = _parse_iso_date(str(payload.get("valid_until") or ""))
    if valid_until is None:
        issues.append("valid_until_invalid")
    else:
        now = datetime.now(timezone.utc)
        vu = valid_until if valid_until.tzinfo else valid_until.replace(tzinfo=timezone.utc)
        if vu < now:
            issues.append("expired")

    if not isinstance(payload.get("weights"), dict):
        issues.append("weights_not_object")

    ok = len(issues) == 0
    return {
        "pass": ok,
        "issues": issues,
        "thresholds": {
            "ece_max": DEFAULT_ECE_MAX,
            "high_precision_min": DEFAULT_HIGH_PRECISION_MIN,
            "sample_min": DEFAULT_SAMPLE_MIN,
            "dual_annotation_min": DEFAULT_DUAL_ANNOTATION_MIN,
        },
    }


def validate_calibration_report(
    calibration_id: Optional[str] = None,
    *,
    tenant_id: str,
    domain: str = "",
    query_type: str = "",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """校验已登记报告是否仍通过门槛。

    Args:
        calibration_id: 报告 id；空则 active。
        tenant_id: 租户。
        domain: 域。
        query_type: 查询类型。
        db_path: 可选库路径。
    """
    got = get_calibration_report(
        calibration_id,
        tenant_id=tenant_id,
        domain=domain,
        query_type=query_type,
        db_path=db_path,
    )
    if not got:
        return {
            "status": "not_found",
            "valid": False,
            "error": "calibration_not_found",
            "max_confidence": "medium",
        }
    gate = evaluate_calibration_gate(got.get("payload") or {})
    # 为什么：登记为 failed 或门槛不通过时，不得放行 high
    valid = got.get("status") == "approved" and gate["pass"]
    return {
        "status": "ok" if valid else "invalid",
        "valid": valid,
        "calibration_id": got["calibration_id"],
        "domain": got["domain"],
        "query_type": got["query_type"],
        "gate": gate,
        "max_confidence": "high" if valid else "medium",
    }


def resolve_max_confidence(
    *,
    tenant_id: str,
    domain: str,
    query_type: str,
    requested: str = "high",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """解析允许的最大 confidence；校准失败/缺失/过期 → 最高 medium。

    Args:
        tenant_id: 租户。
        domain: 域。
        query_type: 查询类型。
        requested: 请求档位 low|medium|high。
        db_path: 可选库路径。
    """
    req = (requested or "high").strip().lower()
    if req not in CONFIDENCE_LEVELS:
        return {"status": "invalid", "error": "unknown_confidence_level", "requested": requested}

    v = validate_calibration_report(
        tenant_id=tenant_id,
        domain=domain,
        query_type=query_type,
        db_path=db_path,
    )
    ceiling = v.get("max_confidence") or "medium"
    order = {level: i for i, level in enumerate(CONFIDENCE_LEVELS)}
    allowed = req if order[req] <= order[ceiling] else ceiling
    return {
        "status": "ok",
        "requested": req,
        "allowed": allowed,
        "capped": allowed != req,
        "ceiling": ceiling,
        "calibration": {
            "valid": bool(v.get("valid")),
            "calibration_id": v.get("calibration_id"),
            "issues": (v.get("gate") or {}).get("issues") or (
                [v.get("error")] if v.get("error") else []
            ),
        },
    }


def apply_calibration_ceiling(
    *,
    tenant_id: str,
    domain: str,
    query_type: str,
    confidence: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """将查询路径 confidence 按校准天花板封顶（缺失/失败 → ≤medium）。

    Args:
        tenant_id: 租户。
        domain: 域 id；空则不封顶（返回原档）。
        query_type: 校准 query_type。
        confidence: 当前档位。
        db_path: 可选校准库。

    Returns:
        ``confidence`` / ``capped`` / ``resolve``；``certified`` 不宣称。
    """
    dom = (domain or "").strip()
    req = (confidence or "low").strip().lower()
    if not dom:
        return {
            "confidence": req if req in CONFIDENCE_LEVELS else "low",
            "capped": False,
            "resolve": {"status": "skipped", "reason": "domain_required_for_ceiling"},
        }
    if req not in CONFIDENCE_LEVELS:
        req = "low"
    resolved = resolve_max_confidence(
        tenant_id=tenant_id,
        domain=dom,
        query_type=(query_type or "fact_gateway").strip() or "fact_gateway",
        requested=req,
        db_path=db_path,
    )
    if resolved.get("status") != "ok":
        # 为什么：解析失败时诚实封顶 medium，禁止 silent 放行 high
        allowed = "medium" if req == "high" else req
        return {
            "confidence": allowed,
            "capped": allowed != req,
            "resolve": resolved,
        }
    return {
        "confidence": resolved["allowed"],
        "capped": bool(resolved.get("capped")),
        "resolve": resolved,
    }


_N13_CALIBRATION_PIPELINE_CASES = (
    "failed_cal_caps_gateway_high",
    "approved_cal_allows_high",
    "missing_cal_caps_high",
    "honesty_certified_false",
)


async def run_calibration_pipeline_suite(
    *,
    tenant_id: str = "n13-cal-pipeline-tenant",
    domain_id: str = "n13-cal-probe",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """N13 Operational 校准流水线加深：publish → 查询路径封顶 → 门槛门。

    Args:
        tenant_id: 租户。
        domain_id: 探针域（调用方传入；非业务硬编码）。
        db_path: 可选临时校准库。

    Returns:
        套件汇总；``certified`` / ``n13_full_conformance`` 恒 false。
    """
    import tempfile

    from core.harness.knowledge_pipeline.fact_ledger import FactLedger

    own_db = not db_path
    tmp: Optional[tempfile.TemporaryDirectory] = None
    if own_db:
        tmp = tempfile.TemporaryDirectory(prefix="n13-cal-pipeline-")
        root = Path(tmp.name)
        cal_db = str(root / "cal.sqlite3")
        ledger_root = root
    else:
        cal_db = db_path  # type: ignore[assignment]
        ledger_root = Path(tempfile.mkdtemp(prefix="n13-cal-ledger-"))

    lg = FactLedger(
        db_path=str(ledger_root / "fact_ledger.sqlite3"),
        raw_dir=ledger_root / "raw",
    )
    await lg.initialize()
    cases: List[Dict[str, Any]] = []
    try:
        src = await lg.register_source(
            tenant_id=tenant_id,
            collection_id="n13-cal",
            kind="file",
            uri="file://n13/cal.txt",
            content=b"n13-cal",
            connector="n13",
            domain_id=domain_id,
        )
        await lg.put_fact(
            tenant_id=tenant_id,
            collection_id="n13-cal",
            subject="Probe:n13",
            predicate="note",
            object="ok",
            evidence=[
                {
                    "source_id": src["source_id"],
                    "locator": "1",
                    "quote": "ok",
                    "fetched_at": src["fetched_at"],
                }
            ],
            source_policy="n13",
            extractor_version="n13",
            review_status="published",
            confidence=0.9,
            allow_bootstrap_published=True,
            domain_id=domain_id,
        )

        from datetime import timedelta as _td

        future = (datetime.now(timezone.utc) + _td(days=30)).strftime("%Y-%m-%d")

        # 失败校准不得放行 high
        fail = publish_calibration_report(
            tenant_id=tenant_id,
            domain=domain_id,
            query_type="fact_gateway",
            dataset_version="gold-v1",
            sample_size=120,
            label_protocol="dual",
            inter_annotator_agreement=0.3,
            weights={"w": 1},
            calibration_version="cal-v1",
            ece=0.2,
            brier=0.2,
            high_precision=0.95,
            coverage=0.7,
            approved_by="owner",
            valid_until=future,
            db_path=cal_db,
        )
        gw_fail = await lg.query_facts_gateway(
            tenant_id=tenant_id,
            query="ok",
            domain_id=domain_id,
            calibration_db_path=cal_db,
            calibration_query_type="fact_gateway",
        )
        fail_ok = (
            fail.get("status") == "failed"
            and gw_fail.get("confidence") == "medium"
            and gw_fail.get("calibration_capped") is True
            and gw_fail.get("abstained") is False
        )
        cases.append(
            {
                "id": "failed_cal_caps_gateway_high",
                "ok": fail_ok,
                "detail": "" if fail_ok else "failed_cal_did_not_cap",
            }
        )

        # 达标校准允许 high
        ok_pub = publish_calibration_report(
            tenant_id=tenant_id,
            domain=domain_id,
            query_type="fact_gateway",
            dataset_version="gold-v1",
            sample_size=120,
            label_protocol="dual",
            inter_annotator_agreement=0.3,
            weights={"w": 1},
            calibration_version="cal-v2",
            ece=0.02,
            brier=0.1,
            high_precision=0.95,
            coverage=0.8,
            approved_by="owner",
            valid_until=future,
            db_path=cal_db,
        )
        gw_ok = await lg.query_facts_gateway(
            tenant_id=tenant_id,
            query="ok",
            domain_id=domain_id,
            calibration_db_path=cal_db,
            calibration_query_type="fact_gateway",
        )
        allow_ok = (
            ok_pub.get("status") == "approved"
            and gw_ok.get("confidence") == "high"
            and gw_ok.get("calibration_capped") is False
        )
        cases.append(
            {
                "id": "approved_cal_allows_high",
                "ok": allow_ok,
                "detail": "" if allow_ok else "approved_cal_not_high",
            }
        )

        # 缺失校准 → medium
        gw_miss = await lg.query_facts_gateway(
            tenant_id=tenant_id,
            query="ok",
            domain_id=domain_id,
            calibration_db_path=cal_db,
            calibration_query_type="missing_qt",
        )
        miss_ok = (
            gw_miss.get("confidence") == "medium"
            and gw_miss.get("calibration_capped") is True
        )
        cases.append(
            {
                "id": "missing_cal_caps_high",
                "ok": miss_ok,
                "detail": "" if miss_ok else "missing_cal_not_capped",
            }
        )

        honesty = {
            "suite": "calibration_pipeline",
            "ok": True,
            "certified": False,
            "n13_full_conformance": False,
        }
        gate = evaluate_calibration_pipeline_gate(honesty)
        honesty_ok = gate.get("ok") is True and gate.get("certified") is False
        forged = dict(honesty)
        forged["n13_full_conformance"] = True
        forged_gate = evaluate_calibration_pipeline_gate(forged)
        honesty_ok = honesty_ok and forged_gate.get("ok") is False
        cases.append(
            {
                "id": "honesty_certified_false",
                "ok": honesty_ok,
                "detail": "" if honesty_ok else "honesty_gate_failed",
            }
        )
    finally:
        if tmp is not None:
            tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok") is True)
    required = list(_N13_CALIBRATION_PIPELINE_CASES)
    missing = [x for x in required if not any(c.get("id") == x for c in cases)]
    ok = passed == len(required) and not missing
    return {
        "suite": "calibration_pipeline",
        "ok": ok,
        "passed": passed,
        "total": len(cases),
        "required_cases": required,
        "missing_required": missing,
        "cases": cases,
        "certified": False,
        "n13_full_conformance": False,
        "note": (
            "Operational calibration ceiling on fact gateway; "
            "not real ECE training / not N13 certified"
        ),
    }


def evaluate_calibration_pipeline_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N13 校准流水线门槛门；certified 恒 false。

    Args:
        suite: ``run_calibration_pipeline_suite`` 回执。
    """
    s = dict(suite or {})
    issues: List[str] = []
    if not s:
        issues.append("suite_required")
    if s.get("ok") is not True:
        issues.append("suite_not_ok")
    if s.get("missing_required"):
        issues.append("missing_required_cases")
    if s.get("certified") is True or s.get("n13_full_conformance") is True:
        issues.append("honesty_certified_flag_forbidden")
    return {
        "gate": "calibration_pipeline",
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n13_full_conformance": False,
        "note": "Operational calibration pipeline; not N13 certified",
    }
