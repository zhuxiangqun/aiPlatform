"""Ontology Package 最小切片（附录 H.3 / W9）— 版本化语义包。

职责：发布包版本；内容哈希校验；依赖锁定；兼容矩阵；发布/回滚。
非目标：不做密码学签名密钥管理；不自动执行 migrations SQL；不宣称 N24 全量符合。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")
_DEP_RE = re.compile(
    r"^\s*(>=|<=|==|>|<)?\s*(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]*)?)\s*$"
)


def _default_db_path() -> str:
    """解析 Package DB（AIPLAT_HOME 约定）。"""
    env = os.environ.get("AIPLAT_ONTOLOGY_PACKAGE_DB")
    if env:
        return env
    home = os.environ.get("AIPLAT_HOME")
    if home:
        return str(Path(home) / "data" / "knowledge_ontology_package.sqlite3")
    return "./data/knowledge_ontology_package.sqlite3"


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """打开/初始化 Package 表。

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
        CREATE TABLE IF NOT EXISTS ontology_packages (
            row_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            package_id TEXT NOT NULL,
            version TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            published_at REAL,
            rolled_back_at REAL,
            UNIQUE(tenant_id, package_id, version)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ontology_package_active (
            tenant_id TEXT NOT NULL,
            package_id TEXT NOT NULL,
            active_version TEXT NOT NULL,
            updated_at REAL,
            PRIMARY KEY(tenant_id, package_id)
        )
        """
    )
    conn.commit()
    return conn


def _parse_semver(version: str) -> Optional[Tuple[int, int, int]]:
    """解析 x.y.z；失败返回 None。

    Args:
        version: 版本字符串。
    """
    m = _SEMVER_RE.match((version or "").strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _cmp_semver(a: str, b: str) -> Optional[int]:
    """比较两个 semver；不可比返回 None。

    Args:
        a: 左版本。
        b: 右版本。
    """
    pa, pb = _parse_semver(a), _parse_semver(b)
    if pa is None or pb is None:
        return None
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0


def satisfies_version_constraint(installed: str, constraint: str) -> bool:
    """检查 installed 是否满足依赖约束（支持 >=/<=/>/</== 与裸版本==）。

    Args:
        installed: 已安装版本。
        constraint: 如 ``>=1.0.0`` / ``1.2.0``。
    """
    raw = (constraint or "").strip()
    if not raw:
        return False
    m = _DEP_RE.match(raw)
    if not m:
        return False
    op = m.group(1) or "=="
    target = m.group(2)
    cmp = _cmp_semver(installed, target)
    if cmp is None:
        return False
    if op == "==":
        return cmp == 0
    if op == ">=":
        return cmp >= 0
    if op == "<=":
        return cmp <= 0
    if op == ">":
        return cmp > 0
    if op == "<":
        return cmp < 0
    return False


def _canonical_payload(payload: Dict[str, Any]) -> str:
    """稳定序列化用于哈希（排除 content_hash 自身）。

    Args:
        payload: 包正文。
    """
    clean = {k: v for k, v in payload.items() if k != "content_hash"}
    return json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_content_hash(payload: Dict[str, Any]) -> str:
    """计算包内容 SHA-256（最小完整性凭证，非 PKI 签名）。

    Args:
        payload: 包正文。
    """
    return hashlib.sha256(_canonical_payload(payload).encode("utf-8")).hexdigest()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """行 → API dict。

    Args:
        row: sqlite Row。
    """
    payload = json.loads(row["payload_json"])
    return {
        "tenant_id": row["tenant_id"],
        "package_id": row["package_id"],
        "version": row["version"],
        "status": row["status"],
        "content_hash": row["content_hash"],
        "published_at": row["published_at"],
        "rolled_back_at": row["rolled_back_at"],
        "payload": payload,
    }


def publish_package(
    *,
    tenant_id: str,
    package_id: str,
    version: str,
    schema: Optional[Sequence[str]] = None,
    actions: Optional[Sequence[str]] = None,
    functions: Optional[Sequence[str]] = None,
    interfaces: Optional[Sequence[str]] = None,
    dependencies: Optional[Sequence[Dict[str, Any]]] = None,
    compatibility: Optional[Dict[str, Any]] = None,
    migrations: Optional[Sequence[str]] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """发布 Ontology Package 版本并设为 active。

    Args:
        tenant_id: 租户。
        package_id: 包 id。
        version: semver。
        schema: ObjectType/类型名列表。
        actions: 动作名列表。
        functions: 函数名列表。
        interfaces: 接口名列表。
        dependencies: ``[{package, version}]`` 依赖锁定。
        compatibility: ``{backward:[], forward:[]}``。
        migrations: 迁移标识列表（仅记录，不执行）。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    pid = (package_id or "").strip()
    ver = (version or "").strip()
    if not tid or not pid or not ver:
        return {"status": "invalid", "error": "tenant_package_version_required"}
    if _parse_semver(ver) is None:
        return {"status": "invalid", "error": "version_not_semver"}

    deps = list(dependencies or [])
    for d in deps:
        if not isinstance(d, dict) or not d.get("package") or not d.get("version"):
            return {"status": "invalid", "error": "dependency_incomplete"}

    payload: Dict[str, Any] = {
        "package_id": pid,
        "version": ver,
        "schema": list(schema or []),
        "actions": list(actions or []),
        "functions": list(functions or []),
        "interfaces": list(interfaces or []),
        "dependencies": deps,
        "compatibility": {
            "backward": list((compatibility or {}).get("backward") or []),
            "forward": list((compatibility or {}).get("forward") or []),
        },
        "migrations": list(migrations or []),
    }
    content_hash = compute_content_hash(payload)
    payload["content_hash"] = content_hash

    conn = _connect(db_path)
    try:
        existing = conn.execute(
            "SELECT row_id FROM ontology_packages WHERE tenant_id=? AND package_id=? AND version=?",
            (tid, pid, ver),
        ).fetchone()
        if existing:
            return {"status": "conflict", "error": "version_exists", "package_id": pid, "version": ver}

        now = time.time()
        row_id = f"pkg-{uuid.uuid4().hex[:16]}"
        conn.execute(
            """
            INSERT INTO ontology_packages(
                row_id, tenant_id, package_id, version, status,
                payload_json, content_hash, published_at, rolled_back_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                row_id,
                tid,
                pid,
                ver,
                "published",
                json.dumps(payload, ensure_ascii=False),
                content_hash,
                now,
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO ontology_package_active(tenant_id, package_id, active_version, updated_at)
            VALUES (?,?,?,?)
            ON CONFLICT(tenant_id, package_id) DO UPDATE SET
                active_version=excluded.active_version,
                updated_at=excluded.updated_at
            """,
            (tid, pid, ver, now),
        )
        conn.commit()
        out = {
            "status": "published",
            "package_id": pid,
            "version": ver,
            "content_hash": content_hash,
            "active": True,
            "payload": payload,
            "published_at": now,
        }
        # 为什么：N24 J6 — Package 热路径 best-effort 写入统一审计总线（非 ActionStore 合并）
        try:
            from core.harness.knowledge_pipeline.unified_audit_bus import (
                append_unified_audit_event,
            )

            append_unified_audit_event(
                tenant_id=tid,
                event_id=f"pkg:{pid}:{ver}",
                stream="package",
                event_type="published",
                occurred_at=float(now),
                actor="",
                subject=f"{pid}@{ver}",
                refs={"content_hash": content_hash},
                payload=out,
            )
        except Exception:
            logger.warning(
                "unified_audit_bus append failed for package %s@%s",
                pid,
                ver,
                exc_info=True,
            )
        return out
    finally:
        conn.close()


def list_package_versions(
    *,
    tenant_id: str,
    package_id: str = "",
    limit: int = 100,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """按租户列出 Ontology Package 版本行（只读；跨租户空）。

    Args:
        tenant_id: 租户（必填）。
        package_id: 可选包 id 过滤。
        limit: 最大条数（1–500）。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    if not tid:
        return []
    lim = max(1, min(int(limit or 100), 500))
    pid = (package_id or "").strip()
    conn = _connect(db_path)
    try:
        if pid:
            rows = conn.execute(
                """
                SELECT * FROM ontology_packages
                WHERE tenant_id=? AND package_id=?
                ORDER BY published_at ASC, version ASC
                LIMIT ?
                """,
                (tid, pid, lim),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM ontology_packages
                WHERE tenant_id=?
                ORDER BY published_at ASC, package_id ASC, version ASC
                LIMIT ?
                """,
                (tid, lim),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_package(
    package_id: str,
    *,
    tenant_id: str,
    version: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """按租户读取包；默认取 active 版本；跨租户隐藏。

    Args:
        package_id: 包 id。
        tenant_id: 租户。
        version: 指定版本；空则 active。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    pid = (package_id or "").strip()
    if not tid or not pid:
        return None
    conn = _connect(db_path)
    try:
        ver = (version or "").strip()
        if not ver:
            active = conn.execute(
                "SELECT active_version FROM ontology_package_active WHERE tenant_id=? AND package_id=?",
                (tid, pid),
            ).fetchone()
            if not active:
                return None
            ver = active["active_version"]
        row = conn.execute(
            """
            SELECT * FROM ontology_packages
            WHERE tenant_id=? AND package_id=? AND version=?
            """,
            (tid, pid, ver),
        ).fetchone()
        if not row:
            return None
        out = _row_to_dict(row)
        active = conn.execute(
            "SELECT active_version FROM ontology_package_active WHERE tenant_id=? AND package_id=?",
            (tid, pid),
        ).fetchone()
        out["active"] = bool(active and active["active_version"] == ver)
        return out
    finally:
        conn.close()


def validate_package(
    package_id: str,
    *,
    tenant_id: str,
    version: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """校验包可验证：必填字段 + content_hash 重算一致 + 依赖约束可解析。

    Args:
        package_id: 包 id。
        tenant_id: 租户。
        version: 指定版本；空则 active。
        db_path: 可选库路径。
    """
    got = get_package(package_id, tenant_id=tenant_id, version=version, db_path=db_path)
    if not got:
        return {"status": "not_found", "valid": False, "error": "package_not_found"}
    payload = dict(got.get("payload") or {})
    issues: List[str] = []
    for key in ("package_id", "version", "schema", "actions", "functions", "interfaces"):
        if key not in payload:
            issues.append(f"missing_{key}")
    if _parse_semver(str(payload.get("version") or "")) is None:
        issues.append("version_not_semver")
    expected = compute_content_hash(payload)
    stored = str(got.get("content_hash") or "")
    if expected != stored:
        # 为什么：哈希不一致即包被篡改或序列化漂移，必须 fail closed
        issues.append("content_hash_mismatch")
    for d in payload.get("dependencies") or []:
        if not isinstance(d, dict):
            issues.append("dependency_shape")
            continue
        if not d.get("package") or not d.get("version"):
            issues.append("dependency_incomplete")
            continue
        if not _DEP_RE.match(str(d.get("version") or "").strip()):
            issues.append("dependency_constraint_unparseable")
    compat = payload.get("compatibility") or {}
    if not isinstance(compat, dict):
        issues.append("compatibility_shape")
    else:
        for side in ("backward", "forward"):
            for v in compat.get(side) or []:
                if _parse_semver(str(v)) is None:
                    issues.append(f"compat_{side}_not_semver")
    ok = len(issues) == 0 and got.get("status") == "published"
    return {
        "status": "ok" if ok else "invalid",
        "valid": ok,
        "package_id": got["package_id"],
        "version": got["version"],
        "content_hash": stored,
        "expected_hash": expected,
        "issues": issues,
    }


def check_compatibility(
    package_id: str,
    *,
    tenant_id: str,
    from_version: str,
    to_version: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """检查 from→to 是否落在兼容矩阵（to 的 backward 含 from，或 from 的 forward 含 to）。

    Args:
        package_id: 包 id。
        tenant_id: 租户。
        from_version: 源版本。
        to_version: 目标版本。
        db_path: 可选库路径。
    """
    src = get_package(package_id, tenant_id=tenant_id, version=from_version, db_path=db_path)
    dst = get_package(package_id, tenant_id=tenant_id, version=to_version, db_path=db_path)
    if not src or not dst:
        return {"status": "not_found", "compatible": False, "error": "package_not_found"}
    if src.get("status") != "published" or dst.get("status") != "published":
        return {"status": "invalid", "compatible": False, "error": "not_published"}

    src_fwd = list((src.get("payload") or {}).get("compatibility", {}).get("forward") or [])
    dst_bwd = list((dst.get("payload") or {}).get("compatibility", {}).get("backward") or [])
    compatible = (to_version in src_fwd) or (from_version in dst_bwd) or (from_version == to_version)
    return {
        "status": "ok",
        "compatible": compatible,
        "package_id": package_id,
        "from_version": from_version,
        "to_version": to_version,
        "via": (
            "same"
            if from_version == to_version
            else ("forward" if to_version in src_fwd else ("backward" if from_version in dst_bwd else "none"))
        ),
    }


def check_dependency_lock(
    *,
    tenant_id: str,
    package_id: str,
    version: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """检查依赖锁定：每个依赖包的 active 版本须满足约束。

    Args:
        tenant_id: 租户。
        package_id: 包 id。
        version: 指定版本；空则 active。
        db_path: 可选库路径。
    """
    got = get_package(package_id, tenant_id=tenant_id, version=version, db_path=db_path)
    if not got:
        return {"status": "not_found", "satisfied": False, "error": "package_not_found"}
    results: List[Dict[str, Any]] = []
    all_ok = True
    for d in (got.get("payload") or {}).get("dependencies") or []:
        dep_id = str(d.get("package") or "")
        constraint = str(d.get("version") or "")
        dep = get_package(dep_id, tenant_id=tenant_id, db_path=db_path)
        installed = (dep or {}).get("version") or ""
        ok = bool(dep) and dep.get("status") == "published" and satisfies_version_constraint(
            installed, constraint
        )
        if not ok:
            all_ok = False
        results.append(
            {
                "package": dep_id,
                "constraint": constraint,
                "installed": installed or None,
                "satisfied": ok,
            }
        )
    return {
        "status": "ok" if all_ok else "unsatisfied",
        "satisfied": all_ok,
        "package_id": got["package_id"],
        "version": got["version"],
        "dependencies": results,
    }


def rollback_package(
    package_id: str,
    *,
    tenant_id: str,
    to_version: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """回滚：将当前 active 标为 rolled_back，切换 active 到 to_version。

    Args:
        package_id: 包 id。
        tenant_id: 租户。
        to_version: 目标已发布版本。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    pid = (package_id or "").strip()
    target = (to_version or "").strip()
    if not tid or not pid or not target:
        return {"status": "invalid", "error": "tenant_package_version_required"}

    conn = _connect(db_path)
    try:
        active = conn.execute(
            "SELECT active_version FROM ontology_package_active WHERE tenant_id=? AND package_id=?",
            (tid, pid),
        ).fetchone()
        if not active:
            return {"status": "not_found", "error": "no_active_version"}
        current = active["active_version"]
        if current == target:
            return {"status": "invalid", "error": "already_active", "version": target}

        target_row = conn.execute(
            """
            SELECT status FROM ontology_packages
            WHERE tenant_id=? AND package_id=? AND version=?
            """,
            (tid, pid, target),
        ).fetchone()
        if not target_row:
            return {"status": "not_found", "error": "target_not_found"}
        if target_row["status"] != "published":
            return {"status": "invalid", "error": "target_not_published"}

        now = time.time()
        conn.execute(
            """
            UPDATE ontology_packages
            SET status='rolled_back', rolled_back_at=?
            WHERE tenant_id=? AND package_id=? AND version=?
            """,
            (now, tid, pid, current),
        )
        conn.execute(
            """
            UPDATE ontology_package_active
            SET active_version=?, updated_at=?
            WHERE tenant_id=? AND package_id=?
            """,
            (target, now, tid, pid),
        )
        conn.commit()
        out = {
            "status": "rolled_back",
            "package_id": pid,
            "from_version": current,
            "to_version": target,
            "active_version": target,
            "rolled_back_at": now,
        }
        # 为什么：N24 J6 — Package 回滚热路径 best-effort 写入统一审计总线
        try:
            from core.harness.knowledge_pipeline.unified_audit_bus import (
                append_unified_audit_event,
            )

            append_unified_audit_event(
                tenant_id=tid,
                event_id=f"pkg:{pid}:{current}:rolled_back",
                stream="package",
                event_type="rolled_back",
                occurred_at=float(now),
                actor="",
                subject=f"{pid}@{current}",
                refs={"to_version": target},
                payload=out,
            )
        except Exception:
            logger.warning(
                "unified_audit_bus append failed for package rollback %s@%s",
                pid,
                current,
                exc_info=True,
            )
        return out
    finally:
        conn.close()
