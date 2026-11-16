"""Confidence Calibration Report 最小切片（附录 O / W10）— 可复现校准门。

职责：登记校准报告；校验必填与门槛；失败时 confidence 上限 medium。
非目标：不做真实 ECE 训练；不宣称准确率；不替代 OCS；不做迁移双写。
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
