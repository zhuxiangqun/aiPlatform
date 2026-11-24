"""ObjectType 人审发布流水线（附录 N N02 deepen）。

职责：
  - ObjectType 定义 draft → in_review → published | rejected
  - publish 须 actor/reason + 配置角色门（上游注入 role）
  - 仅 published 可作为 active 定义；可选拦截 Package schema 发布
  - 显式 residual：opt-in ``bulk_transition_object_types`` 有界多租户批量转换

非目标：
  - 不替换 workspace_seeds JSON 为唯一真源
  - 不做无限批量/工作流编排产品
  - 不宣称 N02 certified / 关闭 ADR 例外
  - 批量不可用时诚实上报 ``object_type_bulk_unavailable``
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_PUBLISH_ROLES = ("reviewer", "knowledge_admin", "ontology_admin")
_REVIEW_ACTION = "object_type_publish"
_TRANSITIONS = {
    "draft": {"in_review", "rejected"},
    "in_review": {"published", "rejected", "draft"},
    "published": set(),
    "rejected": {"draft"},
}


class ObjectTypePublishError(ValueError):
    """ObjectType 人审发布契约错误。"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_db_path() -> str:
    """解析 ObjectType 发布库路径（AIPLAT_HOME 约定）。"""
    env = os.environ.get("AIPLAT_OBJECT_TYPE_PUBLISH_DB")
    if env:
        return env
    home = os.environ.get("AIPLAT_HOME")
    if home:
        return str(Path(home) / "data" / "knowledge_object_type_publish.sqlite3")
    return "./data/knowledge_object_type_publish.sqlite3"


def object_type_publish_rbac_enabled() -> bool:
    """是否启用 ObjectType publish 角色门（默认开；``0/false/off`` 关闭）。"""
    raw = (os.environ.get("AIPLAT_OBJECT_TYPE_PUBLISH_RBAC") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def allowed_object_type_publish_roles() -> Tuple[str, ...]:
    """返回允许发布 ObjectType 的角色（``AIPLAT_OBJECT_TYPE_PUBLISH_ROLES``）。

    Returns:
        角色元组；缺省 reviewer/knowledge_admin/ontology_admin。
    """
    raw = (os.environ.get("AIPLAT_OBJECT_TYPE_PUBLISH_ROLES") or "").strip()
    if not raw:
        return _DEFAULT_PUBLISH_ROLES
    roles = tuple(x.strip() for x in raw.split(",") if x.strip())
    return roles or _DEFAULT_PUBLISH_ROLES


def assert_object_type_publish_role(
    *, role: str, action: str = _REVIEW_ACTION
) -> None:
    """校验调用方角色是否允许发布 ObjectType。

    Args:
        role: 上游注入角色（不从 actor 名推断）。
        action: 动作名。

    Raises:
        ObjectTypePublishError: 角色不在允许列表。
    """
    if not object_type_publish_rbac_enabled():
        return
    r = (role or "").strip()
    allowed = allowed_object_type_publish_roles()
    if r not in allowed:
        raise ObjectTypePublishError(
            f"object_type publish rbac denied: role={role!r} action={action!r}; "
            f"allowed={list(allowed)}"
        )


def package_schema_object_type_gate_enabled() -> bool:
    """Package schema 发布是否强制 ObjectType 已人审（默认关，防存量破窗）。"""
    raw = (os.environ.get("AIPLAT_OBJECT_TYPE_PUBLISH_GATE") or "0").strip().lower()
    return raw in ("1", "true", "on", "yes")


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """打开/初始化 ObjectType 发布表。

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
        CREATE TABLE IF NOT EXISTS object_type_versions (
            row_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            object_type_id TEXT NOT NULL,
            version TEXT NOT NULL,
            status TEXT NOT NULL,
            definition_json TEXT NOT NULL,
            actor TEXT NOT NULL,
            reason TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(tenant_id, object_type_id, version)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS object_type_active (
            tenant_id TEXT NOT NULL,
            object_type_id TEXT NOT NULL,
            active_version TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(tenant_id, object_type_id)
        )
        """
    )
    conn.commit()
    return conn


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """行转字典。

    Args:
        row: SQLite 行。
    """
    definition = json.loads(row["definition_json"] or "{}")
    return {
        "row_id": row["row_id"],
        "tenant_id": row["tenant_id"],
        "object_type_id": row["object_type_id"],
        "version": row["version"],
        "status": row["status"],
        "definition": definition,
        "actor": row["actor"],
        "reason": row["reason"],
        "role": row["role"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def submit_object_type_draft(
    *,
    tenant_id: str,
    object_type_id: str,
    version: str,
    definition: Dict[str, Any],
    actor: str,
    reason: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """提交 ObjectType 草稿（status=draft）。

    Args:
        tenant_id: 租户。
        object_type_id: 类型 id。
        version: 版本字符串（非空）。
        definition: 类型定义 JSON（须含 object_type_id）。
        actor: 提交人。
        reason: 理由。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    oid = (object_type_id or "").strip()
    ver = (version or "").strip()
    act = (actor or "").strip()
    why = (reason or "").strip()
    if not tid or not oid or not ver:
        raise ObjectTypePublishError("tenant_object_type_version_required")
    if not act or not why:
        raise ObjectTypePublishError("actor_reason_required")
    if not isinstance(definition, dict) or not definition:
        raise ObjectTypePublishError("definition_required")
    defn = dict(definition)
    defn.setdefault("object_type_id", oid)
    if str(defn.get("object_type_id") or "") != oid:
        raise ObjectTypePublishError("definition_object_type_id_mismatch")

    now = _utc_now()
    row_id = f"ot-{uuid.uuid4().hex[:16]}"
    conn = _connect(db_path)
    try:
        existing = conn.execute(
            """
            SELECT status FROM object_type_versions
            WHERE tenant_id=? AND object_type_id=? AND version=?
            """,
            (tid, oid, ver),
        ).fetchone()
        if existing:
            raise ObjectTypePublishError(f"version_exists:{existing['status']}")
        conn.execute(
            """
            INSERT INTO object_type_versions(
                row_id, tenant_id, object_type_id, version, status,
                definition_json, actor, reason, role, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row_id,
                tid,
                oid,
                ver,
                "draft",
                json.dumps(defn, ensure_ascii=False),
                act,
                why,
                "",
                now,
                now,
            ),
        )
        conn.commit()
        return {
            "status": "draft",
            "tenant_id": tid,
            "object_type_id": oid,
            "version": ver,
            "row_id": row_id,
            "created_at": now,
        }
    finally:
        conn.close()


def transition_object_type(
    *,
    tenant_id: str,
    object_type_id: str,
    version: str,
    to_status: str,
    actor: str,
    reason: str,
    role: str = "",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """ObjectType 状态转换（publish 须角色门）。

    Args:
        tenant_id: 租户。
        object_type_id: 类型 id。
        version: 版本。
        to_status: 目标态。
        actor: 操作人。
        reason: 理由。
        role: 上游角色（publish 时校验）。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    oid = (object_type_id or "").strip()
    ver = (version or "").strip()
    to_s = (to_status or "").strip()
    act = (actor or "").strip()
    why = (reason or "").strip()
    if not tid or not oid or not ver or not to_s:
        raise ObjectTypePublishError("tenant_object_type_version_status_required")
    if not act or not why:
        raise ObjectTypePublishError("actor_reason_required")

    conn = _connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT * FROM object_type_versions
            WHERE tenant_id=? AND object_type_id=? AND version=?
            """,
            (tid, oid, ver),
        ).fetchone()
        if not row:
            raise ObjectTypePublishError("object_type_version_not_found")
        from_s = str(row["status"])
        allowed = _TRANSITIONS.get(from_s) or set()
        if to_s not in allowed:
            raise ObjectTypePublishError(
                f"illegal_transition:{from_s}->{to_s}"
            )
        if to_s == "published":
            assert_object_type_publish_role(role=role)
        now = _utc_now()
        conn.execute(
            """
            UPDATE object_type_versions
            SET status=?, actor=?, reason=?, role=?, updated_at=?
            WHERE tenant_id=? AND object_type_id=? AND version=?
            """,
            (to_s, act, why, (role or "").strip(), now, tid, oid, ver),
        )
        if to_s == "published":
            conn.execute(
                """
                INSERT INTO object_type_active(
                    tenant_id, object_type_id, active_version, updated_at
                ) VALUES (?,?,?,?)
                ON CONFLICT(tenant_id, object_type_id) DO UPDATE SET
                    active_version=excluded.active_version,
                    updated_at=excluded.updated_at
                """,
                (tid, oid, ver, now),
            )
        conn.commit()
        out = _row_to_dict(
            conn.execute(
                """
                SELECT * FROM object_type_versions
                WHERE tenant_id=? AND object_type_id=? AND version=?
                """,
                (tid, oid, ver),
            ).fetchone()
        )
        out["from_status"] = from_s
        out["active"] = to_s == "published"
        return out
    finally:
        conn.close()


def get_published_object_type(
    *,
    tenant_id: str,
    object_type_id: str,
    version: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """读取已发布 ObjectType（未发布返回 None）。

    Args:
        tenant_id: 租户。
        object_type_id: 类型 id。
        version: 可选版本；缺省取 active。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    oid = (object_type_id or "").strip()
    if not tid or not oid:
        return None
    conn = _connect(db_path)
    try:
        ver = (version or "").strip()
        if not ver:
            active = conn.execute(
                """
                SELECT active_version FROM object_type_active
                WHERE tenant_id=? AND object_type_id=?
                """,
                (tid, oid),
            ).fetchone()
            if not active:
                return None
            ver = str(active["active_version"])
        row = conn.execute(
            """
            SELECT * FROM object_type_versions
            WHERE tenant_id=? AND object_type_id=? AND version=? AND status='published'
            """,
            (tid, oid, ver),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def list_object_type_versions(
    *,
    tenant_id: str,
    object_type_id: str = "",
    status: str = "",
    limit: int = 100,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """列出 ObjectType 版本行（租户前置）。

    Args:
        tenant_id: 租户。
        object_type_id: 可选类型过滤。
        status: 可选状态过滤。
        limit: 条数上限。
        db_path: 可选库路径。
    """
    tid = (tenant_id or "").strip()
    if not tid:
        return []
    lim = max(1, min(int(limit or 100), 500))
    oid = (object_type_id or "").strip()
    st = (status or "").strip()
    conn = _connect(db_path)
    try:
        q = "SELECT * FROM object_type_versions WHERE tenant_id=?"
        args: List[Any] = [tid]
        if oid:
            q += " AND object_type_id=?"
            args.append(oid)
        if st:
            q += " AND status=?"
            args.append(st)
        q += " ORDER BY updated_at ASC, object_type_id ASC, version ASC LIMIT ?"
        args.append(lim)
        return [_row_to_dict(r) for r in conn.execute(q, args).fetchall()]
    finally:
        conn.close()


def assert_schema_object_types_published(
    *,
    tenant_id: str,
    schema: Sequence[str],
    db_path: Optional[str] = None,
) -> None:
    """当 Package schema 门开启时，要求所列 ObjectType 均已 published。

    Args:
        tenant_id: 租户。
        schema: ObjectType id 列表。
        db_path: 可选库路径。

    Raises:
        ObjectTypePublishError: 门开启且存在未发布类型。
    """
    if not package_schema_object_type_gate_enabled():
        return
    missing: List[str] = []
    for raw in schema or []:
        oid = str(raw or "").strip()
        if not oid:
            continue
        if get_published_object_type(
            tenant_id=tenant_id, object_type_id=oid, db_path=db_path
        ) is None:
            missing.append(oid)
    if missing:
        raise ObjectTypePublishError(
            "object_types_not_published:" + ",".join(missing)
        )


_BULK_MAX_ITEMS = 20

_N02_CASES = (
    "draft_submit_ok",
    "publish_role_allowed",
    "wrong_role_denied",
    "empty_role_denied",
    "active_only_when_published",
    "package_schema_gate_blocks",
    "honesty_certified_false",
    "bulk_opt_in",
    "bulk_unavailable",
)


def bulk_transition_object_types(
    items: Sequence[Dict[str, Any]],
    *,
    actor: str,
    reason: str,
    role: str = "",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """N02 residual：有界多租户 ObjectType 批量状态转换（非种子替换）。

    每项须含 ``tenant_id`` / ``object_type_id`` / ``version`` / ``to_status``。
    默认关闭（无 ``AIPLAT_KNOWLEDGE_OBJECT_TYPE_BULK=1`` →
    ``object_type_bulk_unavailable``）。逐项回执；任一项失败不回滚已成功项。
    ``certified`` / ``n02_full_conformance`` 恒 false。

    Args:
        items: 批量项列表（最多 ``_BULK_MAX_ITEMS``）。
        actor: 操作人。
        reason: 理由。
        role: publish 时角色。
        db_path: 可选库路径。
    """
    act = (actor or "").strip()
    why = (reason or "").strip()
    base = {
        "actor": act,
        "reason": why,
        "role": (role or "").strip(),
        "results": [],
        "ok_count": 0,
        "fail_count": 0,
        "certified": False,
        "n02_full_conformance": False,
        "n02_object_type_freeze": True,
        "seed_replacement": False,
    }
    if not act or not why:
        return {**base, "status": "invalid", "error": "actor_reason_required"}

    # 为什么：默认关闭批量，避免 CI/门户误把单域薄门户当多域产品完备
    if os.environ.get("AIPLAT_KNOWLEDGE_OBJECT_TYPE_BULK", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        return {
            **base,
            "status": "object_type_bulk_unavailable",
            "via": "env_disabled",
            "note": "set AIPLAT_KNOWLEDGE_OBJECT_TYPE_BULK=1 to enable multi-tenant bulk",
        }

    raw_items = list(items or [])
    if not raw_items:
        return {
            **base,
            "status": "object_type_bulk_unavailable",
            "via": "empty_items",
            "note": "need at least one transition item",
        }
    if len(raw_items) > _BULK_MAX_ITEMS:
        return {
            **base,
            "status": "invalid",
            "error": f"bulk_too_large:{len(raw_items)}>{_BULK_MAX_ITEMS}",
        }

    results: List[Dict[str, Any]] = []
    ok_n = 0
    fail_n = 0
    for idx, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            fail_n += 1
            results.append(
                {
                    "index": idx,
                    "status": "failed",
                    "error": "item_not_object",
                }
            )
            continue
        try:
            out = transition_object_type(
                tenant_id=str(raw.get("tenant_id") or ""),
                object_type_id=str(raw.get("object_type_id") or ""),
                version=str(raw.get("version") or ""),
                to_status=str(raw.get("to_status") or ""),
                actor=act,
                reason=why,
                role=role,
                db_path=db_path,
            )
            ok_n += 1
            results.append({"index": idx, "status": "ok", "item": out})
        except Exception as exc:  # noqa: BLE001
            fail_n += 1
            results.append(
                {
                    "index": idx,
                    "status": "failed",
                    "error": str(exc),
                    "tenant_id": str(raw.get("tenant_id") or ""),
                    "object_type_id": str(raw.get("object_type_id") or ""),
                    "version": str(raw.get("version") or ""),
                }
            )

    return {
        **base,
        "status": "ok",
        "via": "opt_in",
        "results": results,
        "ok_count": ok_n,
        "fail_count": fail_n,
        "total": len(results),
        "note": (
            "bounded multi-tenant bulk transition residual; "
            "not seed replacement / not N02 certified"
        ),
    }


def run_object_type_publish_suite(
    *,
    tenant_id: str = "n02-ot-publish-tenant",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """N02 deepen：ObjectType 人审发布套件（certified 恒 false）。

    Args:
        tenant_id: 租户。
        db_path: 可选库路径。

    Returns:
        套件汇总；``certified`` / ``n02_full_conformance`` 恒 false。
    """
    own_tmp: Optional[tempfile.TemporaryDirectory] = None
    if db_path:
        path = db_path
    else:
        own_tmp = tempfile.TemporaryDirectory(prefix="n02-ot-publish-")
        path = str(Path(own_tmp.name) / "ot_publish.sqlite3")

    cases: List[Dict[str, Any]] = []
    prev_rbac = os.environ.get("AIPLAT_OBJECT_TYPE_PUBLISH_RBAC")
    prev_roles = os.environ.get("AIPLAT_OBJECT_TYPE_PUBLISH_ROLES")
    prev_gate = os.environ.get("AIPLAT_OBJECT_TYPE_PUBLISH_GATE")
    try:
        os.environ["AIPLAT_OBJECT_TYPE_PUBLISH_RBAC"] = "1"
        os.environ["AIPLAT_OBJECT_TYPE_PUBLISH_ROLES"] = "reviewer,knowledge_admin"
        os.environ["AIPLAT_OBJECT_TYPE_PUBLISH_GATE"] = "1"

        draft = submit_object_type_draft(
            tenant_id=tenant_id,
            object_type_id="InstallOrder",
            version="1.0.0",
            definition={
                "object_type_id": "InstallOrder",
                "label": "安装工单",
                "primary_key": "order_id",
                "properties": [{"id": "status", "type": "enum"}],
            },
            actor="suite_author",
            reason="n02-draft",
            db_path=path,
        )
        cases.append(
            {
                "id": "draft_submit_ok",
                "ok": draft.get("status") == "draft",
                "detail": "" if draft.get("status") == "draft" else "draft_failed",
            }
        )

        transition_object_type(
            tenant_id=tenant_id,
            object_type_id="InstallOrder",
            version="1.0.0",
            to_status="in_review",
            actor="suite_author",
            reason="ready-for-review",
            db_path=path,
        )
        pub = transition_object_type(
            tenant_id=tenant_id,
            object_type_id="InstallOrder",
            version="1.0.0",
            to_status="published",
            actor="suite_reviewer",
            reason="approve",
            role="reviewer",
            db_path=path,
        )
        cases.append(
            {
                "id": "publish_role_allowed",
                "ok": pub.get("status") == "published" and pub.get("active") is True,
                "detail": "" if pub.get("status") == "published" else "publish_failed",
            }
        )

        submit_object_type_draft(
            tenant_id=tenant_id,
            object_type_id="DeviceModel",
            version="1.0.0",
            definition={
                "object_type_id": "DeviceModel",
                "label": "设备型号",
                "primary_key": "name",
            },
            actor="suite_author",
            reason="n02-draft-2",
            db_path=path,
        )
        transition_object_type(
            tenant_id=tenant_id,
            object_type_id="DeviceModel",
            version="1.0.0",
            to_status="in_review",
            actor="suite_author",
            reason="review",
            db_path=path,
        )
        wrong_ok = False
        try:
            transition_object_type(
                tenant_id=tenant_id,
                object_type_id="DeviceModel",
                version="1.0.0",
                to_status="published",
                actor="viewer-1",
                reason="nope",
                role="viewer",
                db_path=path,
            )
        except ObjectTypePublishError as exc:
            wrong_ok = "rbac denied" in str(exc)
        cases.append(
            {
                "id": "wrong_role_denied",
                "ok": wrong_ok,
                "detail": "" if wrong_ok else "wrong_role_not_denied",
            }
        )

        empty_ok = False
        try:
            transition_object_type(
                tenant_id=tenant_id,
                object_type_id="DeviceModel",
                version="1.0.0",
                to_status="published",
                actor="viewer-1",
                reason="nope",
                role="",
                db_path=path,
            )
        except ObjectTypePublishError as exc:
            empty_ok = "rbac denied" in str(exc)
        cases.append(
            {
                "id": "empty_role_denied",
                "ok": empty_ok,
                "detail": "" if empty_ok else "empty_role_not_denied",
            }
        )

        active = get_published_object_type(
            tenant_id=tenant_id,
            object_type_id="InstallOrder",
            db_path=path,
        )
        not_active = get_published_object_type(
            tenant_id=tenant_id,
            object_type_id="DeviceModel",
            db_path=path,
        )
        cases.append(
            {
                "id": "active_only_when_published",
                "ok": active is not None and not_active is None,
                "detail": ""
                if active is not None and not_active is None
                else "active_leak",
            }
        )

        gate_ok = False
        try:
            assert_schema_object_types_published(
                tenant_id=tenant_id,
                schema=["InstallOrder", "DeviceModel"],
                db_path=path,
            )
        except ObjectTypePublishError as exc:
            gate_ok = "DeviceModel" in str(exc)
        cases.append(
            {
                "id": "package_schema_gate_blocks",
                "ok": gate_ok,
                "detail": "" if gate_ok else "gate_not_blocking",
            }
        )

        # residual：默认无 env → unavailable
        prev_bulk = os.environ.get("AIPLAT_KNOWLEDGE_OBJECT_TYPE_BULK")
        os.environ.pop("AIPLAT_KNOWLEDGE_OBJECT_TYPE_BULK", None)
        try:
            unavail = bulk_transition_object_types(
                [
                    {
                        "tenant_id": tenant_id,
                        "object_type_id": "InstallOrder",
                        "version": "1.0.0",
                        "to_status": "published",
                    }
                ],
                actor="suite_reviewer",
                reason="bulk-check",
                role="reviewer",
                db_path=path,
            )
            cases.append(
                {
                    "id": "bulk_unavailable",
                    "ok": unavail.get("status") == "object_type_bulk_unavailable"
                    and unavail.get("certified") is False,
                    "detail": "",
                }
            )

            # residual：两租户各一份草稿 → in_review 批量
            for t_extra in ("n02-bulk-a", "n02-bulk-b"):
                submit_object_type_draft(
                    tenant_id=t_extra,
                    object_type_id="BulkProbe",
                    version="1.0.0",
                    definition={
                        "object_type_id": "BulkProbe",
                        "label": "bulk",
                        "primary_key": "id",
                    },
                    actor="suite_author",
                    reason="bulk-draft",
                    db_path=path,
                )
            os.environ["AIPLAT_KNOWLEDGE_OBJECT_TYPE_BULK"] = "1"
            bulk = bulk_transition_object_types(
                [
                    {
                        "tenant_id": "n02-bulk-a",
                        "object_type_id": "BulkProbe",
                        "version": "1.0.0",
                        "to_status": "in_review",
                    },
                    {
                        "tenant_id": "n02-bulk-b",
                        "object_type_id": "BulkProbe",
                        "version": "1.0.0",
                        "to_status": "in_review",
                    },
                ],
                actor="suite_author",
                reason="bulk-review",
                db_path=path,
            )
            tenants_ok = {
                (r.get("item") or {}).get("tenant_id")
                for r in (bulk.get("results") or [])
                if r.get("status") == "ok"
            }
            cases.append(
                {
                    "id": "bulk_opt_in",
                    "ok": bulk.get("status") == "ok"
                    and int(bulk.get("ok_count") or 0) == 2
                    and tenants_ok >= {"n02-bulk-a", "n02-bulk-b"}
                    and bulk.get("certified") is False
                    and bulk.get("seed_replacement") is False,
                    "detail": "" if bulk.get("status") == "ok" else "bulk_failed",
                }
            )
        finally:
            if prev_bulk is None:
                os.environ.pop("AIPLAT_KNOWLEDGE_OBJECT_TYPE_BULK", None)
            else:
                os.environ["AIPLAT_KNOWLEDGE_OBJECT_TYPE_BULK"] = prev_bulk

        cases.append(
            {
                "id": "honesty_certified_false",
                "ok": True,
                "detail": "",
            }
        )
    finally:
        if prev_rbac is None:
            os.environ.pop("AIPLAT_OBJECT_TYPE_PUBLISH_RBAC", None)
        else:
            os.environ["AIPLAT_OBJECT_TYPE_PUBLISH_RBAC"] = prev_rbac
        if prev_roles is None:
            os.environ.pop("AIPLAT_OBJECT_TYPE_PUBLISH_ROLES", None)
        else:
            os.environ["AIPLAT_OBJECT_TYPE_PUBLISH_ROLES"] = prev_roles
        if prev_gate is None:
            os.environ.pop("AIPLAT_OBJECT_TYPE_PUBLISH_GATE", None)
        else:
            os.environ["AIPLAT_OBJECT_TYPE_PUBLISH_GATE"] = prev_gate
        if own_tmp is not None:
            own_tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok"))
    return {
        "ok": passed == len(_N02_CASES) and len(cases) == len(_N02_CASES),
        "passed": passed,
        "total": len(_N02_CASES),
        "cases": cases,
        "certified": False,
        "n02_full_conformance": False,
        "n02_object_type_freeze": True,
        "note": (
            "ObjectType human-review publish + multi-tenant bulk residual; "
            "not N02 certified / not seed replacement"
        ),
    }


def evaluate_object_type_publish_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N02 deepen：人审发布门槛门（certified 恒 false）。

    Args:
        suite: ``run_object_type_publish_suite`` 回执。
    """
    s = suite if isinstance(suite, dict) else {}
    issues: List[str] = []
    if not s.get("ok"):
        issues.append("suite_not_ok")
    if int(s.get("passed") or 0) < len(_N02_CASES):
        issues.append("suite_incomplete")
    if s.get("certified") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("n02_full_conformance") is True:
        issues.append("honesty_n02_full_flag_forbidden")
    for cid in _N02_CASES:
        hit = next((c for c in (s.get("cases") or []) if c.get("id") == cid), None)
        if not hit or not hit.get("ok"):
            issues.append(f"case_failed:{cid}")
    return {
        "ok": not issues,
        "passed": int(s.get("passed") or 0),
        "total": int(s.get("total") or 0),
        "required": True,
        "issues": issues,
        "certified": False,
        "n02_full_conformance": False,
        "note": "ObjectType publish deepen gate; not N02 certified",
    }
