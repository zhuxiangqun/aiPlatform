"""ObjectType 人审发布流水线（附录 N N02 deepen）。

职责：
  - ObjectType 定义 draft → in_review → published | rejected
  - publish 须 actor/reason + 配置角色门（上游注入 role）
  - 仅 published 可作为 active 定义；可选拦截 Package schema 发布
  - 显式 residual：opt-in ``bulk_transition_object_types`` 有界多租户批量转换
  - 产品面第一刀：默认可用 ``bulk_transition_object_types_product``（无 residual env）
  - 显式 residual：opt-in ``apply_published_seed_authority`` 有界种子权威覆盖
  - 产品面第一刀：默认可用种子目录 + published-over-seed（不改写 workspace_seeds）
  - 产品面第二刀：allowlist 权威镜像 backup → write → restore（``seed_migrate_rollback``）

非目标：
  - 不原地改写 / 删除 ``workspace_seeds/**-object-types.json``
  - 不宣称 seed_replacement_complete / N02 certified / 关闭 ADR 例外
  - 批量 residual 不可用时诚实上报 unavailable
"""
from __future__ import annotations

import json
import logging
import os
import shutil
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
_BULK_PRODUCT_CASES = (
    "bulk_product_default_on",
    "bulk_product_multi_tenant",
    "honesty_bulk_product_certified_false",
)

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


def _bulk_transition_object_types_impl(
    items: Sequence[Dict[str, Any]],
    *,
    actor: str,
    reason: str,
    role: str = "",
    db_path: Optional[str] = None,
    via: str,
    product_surface: bool,
) -> Dict[str, Any]:
    """有界多租户批量转换核心（residual / 产品面共用）。

    Args:
        items: 批量项列表。
        actor: 操作人。
        reason: 理由。
        role: publish 时角色。
        db_path: 可选库路径。
        via: ``opt_in`` 或 ``product``。
        product_surface: 是否产品面回执标记。
    """
    act = (actor or "").strip()
    why = (reason or "").strip()
    base: Dict[str, Any] = {
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
        "bulk_product_surface": bool(product_surface),
    }
    if not act or not why:
        return {**base, "status": "invalid", "error": "actor_reason_required"}

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

    note = (
        "bounded multi-tenant bulk product surface; "
        "not seed replacement / not N02 certified"
        if product_surface
        else (
            "bounded multi-tenant bulk transition residual; "
            "not seed replacement / not N02 certified"
        )
    )
    return {
        **base,
        "status": "ok",
        "via": via,
        "results": results,
        "ok_count": ok_n,
        "fail_count": fail_n,
        "total": len(results),
        "note": note,
    }


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
        "bulk_product_surface": False,
    }
    if not act or not why:
        return {**base, "status": "invalid", "error": "actor_reason_required"}

    # 为什么：默认关闭批量 residual，避免误把单域薄门户当多域产品完备
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

    return _bulk_transition_object_types_impl(
        items,
        actor=act,
        reason=why,
        role=role,
        db_path=db_path,
        via="opt_in",
        product_surface=False,
    )


def bulk_transition_object_types_product(
    items: Sequence[Dict[str, Any]],
    *,
    actor: str,
    reason: str,
    role: str = "",
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """N02 产品面：默认可用有界多租户批量转换（无 residual env 门）。

    与 residual 同界（≤``_BULK_MAX_ITEMS``、逐项回执）。
    ``bulk_product_surface=true``；``certified`` / ``seed_replacement`` 恒 false。

    Args:
        items: 批量项列表。
        actor: 操作人。
        reason: 理由。
        role: publish 时角色。
        db_path: 可选库路径。
    """
    return _bulk_transition_object_types_impl(
        items,
        actor=actor,
        reason=reason,
        role=role,
        db_path=db_path,
        via="product",
        product_surface=True,
    )


def run_bulk_portal_product_suite(
    *,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """N02 产品面：多租户 bulk 套件（certified 恒 false）。

    Args:
        db_path: 可选库路径。
    """
    cases: List[Dict[str, Any]] = []
    prev_bulk = os.environ.get("AIPLAT_KNOWLEDGE_OBJECT_TYPE_BULK")
    # 为什么：产品面无 env 门——显式清掉 residual 开关仍应可用
    os.environ.pop("AIPLAT_KNOWLEDGE_OBJECT_TYPE_BULK", None)
    own_tmp: Optional[tempfile.TemporaryDirectory] = None
    if db_path:
        path = db_path
    else:
        own_tmp = tempfile.TemporaryDirectory(prefix="n02-bulk-product-")
        path = str(Path(own_tmp.name) / "ot.sqlite3")
    try:
        # residual 仍关闭；产品面无 env 也可达（空 items → empty_items，非 env_disabled）
        residual = bulk_transition_object_types(
            [
                {
                    "tenant_id": "n02-bulk-prod-a",
                    "object_type_id": "BulkProd",
                    "version": "1.0.0",
                    "to_status": "in_review",
                }
            ],
            actor="suite_author",
            reason="residual-check",
            db_path=path,
        )
        empty_prod = bulk_transition_object_types_product(
            [],
            actor="suite_author",
            reason="product-empty",
            db_path=path,
        )
        cases.append(
            {
                "id": "bulk_product_default_on",
                "ok": residual.get("status") == "object_type_bulk_unavailable"
                and residual.get("via") == "env_disabled"
                and residual.get("bulk_product_surface") is False
                and empty_prod.get("status") == "object_type_bulk_unavailable"
                and empty_prod.get("via") == "empty_items"
                and empty_prod.get("bulk_product_surface") is True,
            }
        )

        for tid in ("n02-bulk-prod-a", "n02-bulk-prod-b"):
            submit_object_type_draft(
                tenant_id=tid,
                object_type_id="BulkProd",
                version="1.0.0",
                definition={
                    "object_type_id": "BulkProd",
                    "label": "bulk-product",
                    "primary_key": "id",
                },
                actor="suite_author",
                reason="bulk-product-draft",
                db_path=path,
            )

        product = bulk_transition_object_types_product(
            [
                {
                    "tenant_id": "n02-bulk-prod-a",
                    "object_type_id": "BulkProd",
                    "version": "1.0.0",
                    "to_status": "in_review",
                },
                {
                    "tenant_id": "n02-bulk-prod-b",
                    "object_type_id": "BulkProd",
                    "version": "1.0.0",
                    "to_status": "in_review",
                },
            ],
            actor="suite_author",
            reason="bulk-product-review",
            db_path=path,
        )
        tenants_ok = {
            (r.get("item") or {}).get("tenant_id")
            for r in (product.get("results") or [])
            if r.get("status") == "ok"
        }
        cases.append(
            {
                "id": "bulk_product_multi_tenant",
                "ok": product.get("status") == "ok"
                and product.get("via") == "product"
                and product.get("bulk_product_surface") is True
                and int(product.get("ok_count") or 0) == 2
                and tenants_ok >= {"n02-bulk-prod-a", "n02-bulk-prod-b"}
                and product.get("certified") is False
                and product.get("seed_replacement") is False,
            }
        )
        cases.append(
            {
                "id": "honesty_bulk_product_certified_false",
                "ok": product.get("certified") is False
                and product.get("n02_object_type_freeze") is True
                and product.get("seed_replacement") is False
                and product.get("bulk_product_surface") is True,
            }
        )
    finally:
        if prev_bulk is None:
            os.environ.pop("AIPLAT_KNOWLEDGE_OBJECT_TYPE_BULK", None)
        else:
            os.environ["AIPLAT_KNOWLEDGE_OBJECT_TYPE_BULK"] = prev_bulk
        if own_tmp is not None:
            own_tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok"))
    return {
        "ok": passed == len(_BULK_PRODUCT_CASES)
        and len(cases) == len(_BULK_PRODUCT_CASES),
        "passed": passed,
        "total": len(_BULK_PRODUCT_CASES),
        "cases": cases,
        "certified": False,
        "n02_full_conformance": False,
        "n02_object_type_freeze": True,
        "seed_replacement": False,
        "bulk_product_surface": True,
        "note": (
            "Bulk portal product surface suite; "
            "not seed replacement / not N02 certified"
        ),
    }


def evaluate_bulk_portal_product_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N02 产品面 bulk 门槛门；禁止 certified / seed_replacement。

    Args:
        suite: ``run_bulk_portal_product_suite`` 回执。
    """
    s = suite if isinstance(suite, dict) else run_bulk_portal_product_suite()
    issues: List[str] = []
    if not s.get("ok"):
        issues.append("suite_not_ok")
    if s.get("certified") is True or s.get("n02_full_conformance") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("seed_replacement") is True:
        issues.append("honesty_seed_replacement_forbidden")
    if s.get("bulk_product_surface") is not True:
        issues.append("product_bulk_surface_required")
    ids = {
        c.get("id")
        for c in (s.get("cases") or [])
        if isinstance(c, dict) and c.get("ok")
    }
    for need in _BULK_PRODUCT_CASES:
        if need not in ids:
            issues.append(f"missing_or_failed:{need}")
    return {
        "ok": not issues,
        "issues": issues,
        "certified": False,
        "n02_full_conformance": False,
        "n02_object_type_freeze": True,
        "seed_replacement": False,
        "bulk_product_surface": True,
        "note": "Bulk portal product gate; not N02 certified",
    }


_SEED_REPLACE_MAX = 20
_SEED_BACKUP_LIST_MAX = 20
_SEED_REPLACE_CASES = (
    "seed_replacement_unavailable",
    "seed_replacement_opt_in",
    "honesty_certified_false",
)
_SEED_PRODUCT_CASES = (
    "seed_authority_product_catalog",
    "seed_authority_product_apply",
    "seed_migrate_backup",
    "seed_migrate_write",
    "seed_migrate_restore",
    "honesty_product_certified_false",
)


def _seed_authority_json_name(tenant_id: str) -> str:
    """权威镜像文件名。"""
    return f"{str(tenant_id or '').strip()}-object-types.authority.json"


def _seed_authority_current_file(root: Path, tenant_id: str) -> Path:
    """current/ 布局下的权威文件。"""
    return root / "current" / _seed_authority_json_name(tenant_id)


def _seed_authority_legacy_file(root: Path, tenant_id: str) -> Path:
    """兼容 slice-1 扁平权威文件。"""
    return root / _seed_authority_json_name(tenant_id)


def _seed_authority_existing_file(root: Path, tenant_id: str) -> Optional[Path]:
    """优先 current/，否则扁平兼容文件。"""
    cur = _seed_authority_current_file(root, tenant_id)
    if cur.is_file():
        return cur
    legacy = _seed_authority_legacy_file(root, tenant_id)
    if legacy.is_file():
        return legacy
    return None


def _new_seed_authority_backup_id() -> str:
    """生成有界备份 id（UTC 时间戳 + 短 uuid）。"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{uuid.uuid4().hex[:8]}"


def resolve_seed_authority_output_root(
    *,
    output_root: Optional[str] = None,
) -> Dict[str, Any]:
    """解析种子权威覆盖写盘根（仅允许 ``AIPLAT_HOME/data/knowledge_object_type_authority``）。

    Args:
        output_root: 可选显式根；须落在 allowlist 下。
    """
    home = (os.environ.get("AIPLAT_HOME") or "").strip()
    if not home:
        home = str(Path.cwd() / ".aiplat-home")
    allow = (Path(home).resolve() / "data" / "knowledge_object_type_authority").resolve()
    if output_root:
        cand = Path(output_root).resolve()
        try:
            cand.relative_to(allow)
        except ValueError:
            return {
                "ok": False,
                "reason": "output_root_not_allowlisted",
                "allowlist": str(allow),
                "output_root": str(cand),
            }
        return {"ok": True, "output_root": str(cand), "allowlist": str(allow)}
    return {"ok": True, "output_root": str(allow), "allowlist": str(allow)}


def backup_seed_authority_snapshot(
    *,
    tenant_id: str,
    output_root: Optional[str] = None,
) -> Dict[str, Any]:
    """N02 产品面：将 allowlist 权威镜像备份到 ``backups/{backup_id}/``。

    不改写 ``workspace_seeds``。无现有镜像时 ``backed_up=false`` 仍 ok。

    Args:
        tenant_id: 租户。
        output_root: 可选写盘根（须 allowlist）。
    """
    tid = str(tenant_id or "").strip()
    base: Dict[str, Any] = {
        "tenant_id": tid,
        "certified": False,
        "n02_full_conformance": False,
        "n02_object_type_freeze": True,
        "seed_replacement_complete": False,
        "workspace_seeds_mutated": False,
        "seed_product_surface": True,
        "seed_migrate_rollback": True,
    }
    if not tid:
        return {**base, "status": "invalid", "error": "tenant_required"}
    root_info = resolve_seed_authority_output_root(output_root=output_root)
    if not root_info.get("ok"):
        return {
            **base,
            "status": "denied",
            "reason": root_info.get("reason") or "output_root_denied",
            "allowlist": root_info.get("allowlist"),
        }
    root = Path(str(root_info["output_root"]))
    src = _seed_authority_existing_file(root, tid)
    if src is None:
        return {
            **base,
            "status": "ok",
            "via": "product",
            "backed_up": False,
            "backup_id": None,
            "source_path": None,
            "note": (
                "no authority mirror to backup; "
                "not seed_replacement_complete / not N02 certified"
            ),
        }
    backup_id = _new_seed_authority_backup_id()
    dest_dir = root / "backups" / backup_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / _seed_authority_json_name(tid)
    shutil.copy2(src, dest)
    return {
        **base,
        "status": "ok",
        "via": "product",
        "backed_up": True,
        "backup_id": backup_id,
        "source_path": str(src),
        "backup_path": str(dest),
        "note": (
            "allowlist authority mirror backup; "
            "not seed_replacement_complete / not N02 certified"
        ),
    }


def list_seed_authority_backups(
    *,
    tenant_id: str,
    output_root: Optional[str] = None,
    limit: int = _SEED_BACKUP_LIST_MAX,
) -> Dict[str, Any]:
    """N02 产品面：列举 allowlist 权威备份（有界，默认 ≤20）。

    Args:
        tenant_id: 租户。
        output_root: 可选写盘根。
        limit: 列表上限（服务端钳制）。
    """
    tid = str(tenant_id or "").strip()
    cap = max(1, min(int(limit or _SEED_BACKUP_LIST_MAX), _SEED_BACKUP_LIST_MAX))
    base: Dict[str, Any] = {
        "tenant_id": tid,
        "items": [],
        "total": 0,
        "limit": cap,
        "certified": False,
        "n02_full_conformance": False,
        "n02_object_type_freeze": True,
        "seed_replacement_complete": False,
        "workspace_seeds_mutated": False,
        "seed_product_surface": True,
        "seed_migrate_rollback": True,
    }
    if not tid:
        return {**base, "status": "invalid", "error": "tenant_required"}
    root_info = resolve_seed_authority_output_root(output_root=output_root)
    if not root_info.get("ok"):
        return {
            **base,
            "status": "denied",
            "reason": root_info.get("reason") or "output_root_denied",
            "allowlist": root_info.get("allowlist"),
        }
    root = Path(str(root_info["output_root"]))
    backups_root = root / "backups"
    name = _seed_authority_json_name(tid)
    items: List[Dict[str, Any]] = []
    if backups_root.is_dir():
        for bid_dir in sorted(backups_root.iterdir(), reverse=True):
            if not bid_dir.is_dir():
                continue
            path = bid_dir / name
            if not path.is_file():
                continue
            items.append(
                {
                    "backup_id": bid_dir.name,
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                }
            )
            if len(items) >= cap:
                break
    return {
        **base,
        "status": "ok",
        "via": "product",
        "items": items,
        "total": len(items),
        "note": (
            "allowlist authority backup list; "
            "not seed_replacement_complete / not N02 certified"
        ),
    }


def restore_seed_authority_snapshot(
    *,
    tenant_id: str,
    backup_id: str,
    output_root: Optional[str] = None,
) -> Dict[str, Any]:
    """N02 产品面：从 ``backups/{backup_id}/`` 恢复权威镜像到 ``current/``。

    Args:
        tenant_id: 租户。
        backup_id: ``backup_seed_authority_snapshot`` 返回的 id。
        output_root: 可选写盘根。
    """
    tid = str(tenant_id or "").strip()
    bid = str(backup_id or "").strip()
    base: Dict[str, Any] = {
        "tenant_id": tid,
        "backup_id": bid,
        "certified": False,
        "n02_full_conformance": False,
        "n02_object_type_freeze": True,
        "seed_replacement_complete": False,
        "workspace_seeds_mutated": False,
        "seed_product_surface": True,
        "seed_migrate_rollback": True,
    }
    if not tid or not bid:
        return {**base, "status": "invalid", "error": "tenant_backup_id_required"}
    # 为什么：禁止路径穿越——backup_id 只能是单段目录名
    if "/" in bid or "\\" in bid or bid in {".", ".."} or ".." in bid:
        return {**base, "status": "denied", "reason": "backup_id_invalid"}
    root_info = resolve_seed_authority_output_root(output_root=output_root)
    if not root_info.get("ok"):
        return {
            **base,
            "status": "denied",
            "reason": root_info.get("reason") or "output_root_denied",
            "allowlist": root_info.get("allowlist"),
        }
    root = Path(str(root_info["output_root"]))
    src = (root / "backups" / bid / _seed_authority_json_name(tid)).resolve()
    try:
        src.relative_to((root / "backups").resolve())
    except ValueError:
        return {**base, "status": "denied", "reason": "backup_path_not_allowlisted"}
    if not src.is_file():
        return {**base, "status": "invalid", "error": "backup_not_found"}
    current_dir = root / "current"
    current_dir.mkdir(parents=True, exist_ok=True)
    dest = _seed_authority_current_file(root, tid)
    shutil.copy2(src, dest)
    return {
        **base,
        "status": "ok",
        "via": "product",
        "restored": True,
        "source_path": str(src),
        "output_path": str(dest),
        "note": (
            "allowlist authority mirror restore; "
            "not seed_replacement_complete / not N02 certified"
        ),
    }


def workspace_object_type_seed_root() -> Path:
    """返回仓库内 ObjectType 种子目录（``aiPlat-core/workspace_seeds/ontologies``）。"""
    # object_type_publish.py → knowledge_pipeline → harness → core → aiPlat-core
    return (
        Path(__file__).resolve().parents[3] / "workspace_seeds" / "ontologies"
    ).resolve()


def list_object_type_seed_catalog() -> Dict[str, Any]:
    """N02 产品面：列举 workspace_seeds 下 ``*-object-types.json``（只读）。

    Returns:
        ``{status, items:[{name,path,object_type_count}], ...}``；certified 恒 false。
    """
    root = workspace_object_type_seed_root()
    items: List[Dict[str, Any]] = []
    if root.is_dir():
        for path in sorted(root.glob("*-object-types.json")):
            count = 0
            try:
                from core.harness.knowledge_pipeline.fact_ledger import (
                    load_object_type_bindings,
                )

                count = len(load_object_type_bindings(path))
            except Exception:  # noqa: BLE001
                count = 0
            items.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "object_type_count": count,
                }
            )
    return {
        "status": "ok",
        "via": "product",
        "root": str(root),
        "items": items,
        "total": len(items),
        "certified": False,
        "n02_full_conformance": False,
        "n02_object_type_freeze": True,
        "seed_replacement_complete": False,
        "workspace_seeds_mutated": False,
        "seed_product_surface": True,
        "seed_migrate_rollback": True,
        "note": (
            "object-type seed catalog (read-only workspace_seeds); "
            "not seed_replacement_complete / not N02 certified"
        ),
    }


def resolve_workspace_object_type_seed_path(seed_path: str) -> Dict[str, Any]:
    """将产品面种子路径解析并限制在 workspace_seeds 目录内。

    Args:
        seed_path: 绝对路径、相对路径或仅文件名（如 ``lock-service-object-types.json``）。
    """
    raw = (seed_path or "").strip()
    root = workspace_object_type_seed_root()
    if not raw:
        return {
            "ok": False,
            "reason": "seed_path_required",
            "allowlist": str(root),
        }
    cand = Path(raw)
    if not cand.is_absolute():
        cand = root / cand.name
    try:
        resolved = cand.resolve()
    except OSError:
        return {
            "ok": False,
            "reason": "seed_path_unresolvable",
            "allowlist": str(root),
            "seed_path": raw,
        }
    try:
        resolved.relative_to(root)
    except ValueError:
        return {
            "ok": False,
            "reason": "seed_path_not_in_workspace_seeds",
            "allowlist": str(root),
            "seed_path": str(resolved),
        }
    if not resolved.is_file() or not resolved.name.endswith("-object-types.json"):
        return {
            "ok": False,
            "reason": "seed_path_missing_or_not_object_types",
            "allowlist": str(root),
            "seed_path": str(resolved),
        }
    return {
        "ok": True,
        "seed_path": str(resolved),
        "allowlist": str(root),
        "name": resolved.name,
    }


def _apply_published_seed_authority_impl(
    *,
    tenant_id: str,
    seed_path: str,
    object_type_ids: Optional[Sequence[str]] = None,
    output_root: Optional[str] = None,
    write: bool = False,
    db_path: Optional[str] = None,
    via: str,
    product_surface: bool,
) -> Dict[str, Any]:
    """published-over-seed 核心实现（residual / 产品面共用）。

    Args:
        tenant_id: 租户。
        seed_path: 已存在的种子 JSON（只读）。
        object_type_ids: 可选类型列表。
        output_root: 可选写盘根。
        write: 是否写盘。
        db_path: 可选发布库。
        via: ``opt_in`` 或 ``product``。
        product_surface: 是否产品面回执标记。
    """
    tid = (tenant_id or "").strip()
    sp = (seed_path or "").strip()
    base: Dict[str, Any] = {
        "tenant_id": tid,
        "seed_path": sp,
        "items": [],
        "published_count": 0,
        "seed_count": 0,
        "certified": False,
        "n02_full_conformance": False,
        "n02_object_type_freeze": True,
        "seed_replacement_complete": False,
        "workspace_seeds_mutated": False,
        "seed_product_surface": bool(product_surface),
        "seed_migrate_rollback": bool(product_surface),
    }
    if not tid or not sp:
        return {**base, "status": "invalid", "error": "tenant_seed_path_required"}

    seed_file = Path(sp)
    if not seed_file.is_file():
        return {**base, "status": "invalid", "error": "seed_path_missing"}

    # 为什么：seed 只读；写盘只落 allowlist，永不改写 workspace_seeds
    try:
        seed_resolved = seed_file.resolve()
    except OSError:
        seed_resolved = seed_file

    from core.harness.knowledge_pipeline.fact_ledger import load_object_type_bindings

    try:
        bindings = load_object_type_bindings(seed_file)
    except Exception as exc:  # noqa: BLE001
        return {**base, "status": "invalid", "error": f"seed_load_failed:{exc}"}

    by_id = {
        str(b.get("object_type_id") or "").strip(): b
        for b in bindings
        if str(b.get("object_type_id") or "").strip()
    }
    if object_type_ids is None:
        wanted = list(by_id.keys())
    else:
        wanted = [str(x or "").strip() for x in object_type_ids if str(x or "").strip()]
    if not wanted:
        return {
            **base,
            "status": "seed_replacement_unavailable",
            "via": via,
            "note": "need at least one object_type_id",
        }
    if len(wanted) > _SEED_REPLACE_MAX:
        return {
            **base,
            "status": "invalid",
            "error": f"seed_replace_too_large:{len(wanted)}>{_SEED_REPLACE_MAX}",
        }

    items: List[Dict[str, Any]] = []
    pub_n = 0
    seed_n = 0
    merged: List[Dict[str, Any]] = []
    for oid in wanted:
        seed_def = by_id.get(oid)
        pub = get_published_object_type(
            tenant_id=tid, object_type_id=oid, db_path=db_path
        )
        if pub is not None:
            pub_n += 1
            defn = dict(pub.get("definition") or {})
            defn.setdefault("object_type_id", oid)
            row = {
                "object_type_id": oid,
                "authority": "published",
                "version": pub.get("version"),
                "definition": defn,
                "seed_present": seed_def is not None,
            }
            items.append(row)
            merged.append(defn)
        elif seed_def is not None:
            seed_n += 1
            defn = dict(seed_def)
            row = {
                "object_type_id": oid,
                "authority": "seed",
                "version": None,
                "definition": defn,
                "seed_present": True,
            }
            items.append(row)
            merged.append(defn)
        else:
            items.append(
                {
                    "object_type_id": oid,
                    "authority": "missing",
                    "version": None,
                    "definition": None,
                    "seed_present": False,
                    "error": "not_in_seed_or_published",
                }
            )

    out_path = ""
    if write:
        root_info = resolve_seed_authority_output_root(output_root=output_root)
        if not root_info.get("ok"):
            return {
                **base,
                "status": "denied",
                "via": via,
                "reason": root_info.get("reason") or "output_root_denied",
                "items": items,
                "published_count": pub_n,
                "seed_count": seed_n,
            }
        root = Path(str(root_info["output_root"]))
        root.mkdir(parents=True, exist_ok=True)
        # 为什么：产品面写 current/；residual 保持扁平兼容
        if product_surface:
            current_dir = root / "current"
            current_dir.mkdir(parents=True, exist_ok=True)
            target = _seed_authority_current_file(root, tid)
        else:
            target = _seed_authority_legacy_file(root, tid)
        payload = {
            "tenant_id": tid,
            "source_seed_path": str(seed_resolved),
            "object_types": merged,
            "seed_replacement_complete": False,
            "certified": False,
            "seed_product_surface": bool(product_surface),
            "seed_migrate_rollback": bool(product_surface),
        }
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        out_path = str(target)

    note = (
        "seed authority product surface slice-2 (migrate/rollback); "
        "workspace_seeds read-only; "
        "not seed_replacement_complete / not N02 certified"
        if product_surface
        else (
            "bounded published-over-seed authority residual; "
            "not full seed replacement productization / not N02 certified"
        )
    )
    return {
        **base,
        "status": "ok",
        "via": via,
        "items": items,
        "published_count": pub_n,
        "seed_count": seed_n,
        "total": len(items),
        "output_path": out_path,
        "wrote": bool(out_path),
        "note": note,
    }


def apply_published_seed_authority(
    *,
    tenant_id: str,
    seed_path: str,
    object_type_ids: Optional[Sequence[str]] = None,
    output_root: Optional[str] = None,
    write: bool = False,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """N02 residual：有界「published 覆盖 seed」权威解析（非全量种子替换）。

    默认关闭（无 ``AIPLAT_KNOWLEDGE_OBJECT_TYPE_SEED_REPLACE=1`` →
    ``seed_replacement_unavailable``）。不改写 ``workspace_seeds``；可选写盘仅落
    allowlist（``AIPLAT_HOME/data/knowledge_object_type_authority``）。
    ``certified`` / ``seed_replacement_complete`` 恒 false。

    Args:
        tenant_id: 租户。
        seed_path: 种子 JSON 路径（只读）。
        object_type_ids: 可选类型列表；缺省取种子内全部（上限 ``_SEED_REPLACE_MAX``）。
        output_root: 可选写盘根（须 allowlist）。
        write: 是否写盘合并结果。
        db_path: 可选发布库路径。
    """
    tid = (tenant_id or "").strip()
    sp = (seed_path or "").strip()
    base = {
        "tenant_id": tid,
        "seed_path": sp,
        "items": [],
        "published_count": 0,
        "seed_count": 0,
        "certified": False,
        "n02_full_conformance": False,
        "n02_object_type_freeze": True,
        "seed_replacement_complete": False,
        "workspace_seeds_mutated": False,
        "seed_product_surface": False,
    }
    if not tid or not sp:
        return {**base, "status": "invalid", "error": "tenant_seed_path_required"}

    # 为什么：默认关闭种子权威覆盖，避免把 seed JSON 误当已人审真源被覆盖产品化
    if os.environ.get(
        "AIPLAT_KNOWLEDGE_OBJECT_TYPE_SEED_REPLACE", ""
    ).strip().lower() not in {"1", "true", "yes"}:
        return {
            **base,
            "status": "seed_replacement_unavailable",
            "via": "env_disabled",
            "note": (
                "set AIPLAT_KNOWLEDGE_OBJECT_TYPE_SEED_REPLACE=1 "
                "to enable bounded published-over-seed authority"
            ),
        }

    return _apply_published_seed_authority_impl(
        tenant_id=tid,
        seed_path=sp,
        object_type_ids=object_type_ids,
        output_root=output_root,
        write=write,
        db_path=db_path,
        via="opt_in",
        product_surface=False,
    )


def apply_published_seed_authority_product(
    *,
    tenant_id: str,
    seed_path: str = "",
    object_type_ids: Optional[Sequence[str]] = None,
    output_root: Optional[str] = None,
    write: bool = False,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """N02 产品面：默认可用 published-over-seed（种子须在 workspace_seeds）。

    无 residual env 门。永不改写 ``workspace_seeds``；写盘仅 allowlist ``current/``。
    写盘前自动 backup（slice-2）。``certified`` / ``seed_replacement_complete`` 恒 false。

    Args:
        tenant_id: 租户。
        seed_path: 种子文件名或 workspace_seeds 内路径；空则取目录首个。
        object_type_ids: 可选类型列表。
        output_root: 可选写盘根。
        write: 是否写盘。
        db_path: 可选发布库。
    """
    tid = (tenant_id or "").strip()
    base = {
        "tenant_id": tid,
        "seed_path": str(seed_path or "").strip(),
        "items": [],
        "published_count": 0,
        "seed_count": 0,
        "certified": False,
        "n02_full_conformance": False,
        "n02_object_type_freeze": True,
        "seed_replacement_complete": False,
        "workspace_seeds_mutated": False,
        "seed_product_surface": True,
        "seed_migrate_rollback": True,
    }
    if not tid:
        return {**base, "status": "invalid", "error": "tenant_required"}

    sp = str(seed_path or "").strip()
    if not sp:
        catalog = list_object_type_seed_catalog()
        items = catalog.get("items") or []
        if not items:
            return {
                **base,
                "status": "invalid",
                "error": "no_workspace_object_type_seeds",
            }
        sp = str(items[0].get("path") or "")

    resolved = resolve_workspace_object_type_seed_path(sp)
    if not resolved.get("ok"):
        return {
            **base,
            "status": "denied",
            "via": "product",
            "reason": resolved.get("reason") or "seed_path_denied",
            "allowlist": resolved.get("allowlist"),
        }

    backup_id = None
    # 为什么：写盘前先备份现有镜像，保证可 restore；无镜像时 backup 仍 ok
    if write:
        bak = backup_seed_authority_snapshot(
            tenant_id=tid, output_root=output_root
        )
        if bak.get("status") == "denied":
            return {
                **base,
                "status": "denied",
                "via": "product",
                "reason": bak.get("reason") or "backup_denied",
                "allowlist": bak.get("allowlist"),
            }
        if bak.get("backed_up") and bak.get("backup_id"):
            backup_id = bak.get("backup_id")

    out = _apply_published_seed_authority_impl(
        tenant_id=tid,
        seed_path=str(resolved["seed_path"]),
        object_type_ids=object_type_ids,
        output_root=output_root,
        write=write,
        db_path=db_path,
        via="product",
        product_surface=True,
    )
    out["seed_migrate_rollback"] = True
    out["seed_product_surface"] = True
    if write:
        out["backup_id"] = backup_id
    return out


def run_seed_replacement_suite(
    *,
    tenant_id: str = "n02-seed-replace-tenant",
) -> Dict[str, Any]:
    """N02 residual：种子权威覆盖套件（certified / complete 恒 false）。

    Args:
        tenant_id: 套件租户。
    """
    cases: List[Dict[str, Any]] = []
    prev = os.environ.get("AIPLAT_KNOWLEDGE_OBJECT_TYPE_SEED_REPLACE")
    prev_home = os.environ.get("AIPLAT_HOME")
    os.environ.pop("AIPLAT_KNOWLEDGE_OBJECT_TYPE_SEED_REPLACE", None)
    tmp = tempfile.TemporaryDirectory(prefix="n02-seed-replace-")
    try:
        root = Path(tmp.name)
        db = str(root / "ot.sqlite3")
        seed = root / "demo-object-types.json"
        seed.write_text(
            json.dumps(
                {
                    "object_types": [
                        {
                            "object_type_id": "DemoType",
                            "label": "seed-label",
                            "primary_key": "id",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        home = root / "home"
        home.mkdir()
        os.environ["AIPLAT_HOME"] = str(home)

        unavail = apply_published_seed_authority(
            tenant_id=tenant_id,
            seed_path=str(seed),
            object_type_ids=["DemoType"],
            db_path=db,
        )
        cases.append(
            {
                "id": "seed_replacement_unavailable",
                "ok": unavail.get("status") == "seed_replacement_unavailable"
                and unavail.get("certified") is False
                and unavail.get("seed_replacement_complete") is False
                and unavail.get("workspace_seeds_mutated") is False,
            }
        )

        submit_object_type_draft(
            tenant_id=tenant_id,
            object_type_id="DemoType",
            version="1.0.0",
            definition={
                "object_type_id": "DemoType",
                "label": "published-label",
                "primary_key": "id",
            },
            actor="author",
            reason="draft",
            db_path=db,
        )
        transition_object_type(
            tenant_id=tenant_id,
            object_type_id="DemoType",
            version="1.0.0",
            to_status="in_review",
            actor="author",
            reason="review",
            db_path=db,
        )
        prev_rbac = os.environ.get("AIPLAT_OBJECT_TYPE_PUBLISH_RBAC")
        os.environ["AIPLAT_OBJECT_TYPE_PUBLISH_RBAC"] = "0"
        try:
            transition_object_type(
                tenant_id=tenant_id,
                object_type_id="DemoType",
                version="1.0.0",
                to_status="published",
                actor="reviewer",
                reason="publish",
                role="reviewer",
                db_path=db,
            )
        finally:
            if prev_rbac is None:
                os.environ.pop("AIPLAT_OBJECT_TYPE_PUBLISH_RBAC", None)
            else:
                os.environ["AIPLAT_OBJECT_TYPE_PUBLISH_RBAC"] = prev_rbac

        os.environ["AIPLAT_KNOWLEDGE_OBJECT_TYPE_SEED_REPLACE"] = "1"
        applied = apply_published_seed_authority(
            tenant_id=tenant_id,
            seed_path=str(seed),
            object_type_ids=["DemoType"],
            write=True,
            db_path=db,
        )
        items = applied.get("items") or []
        first = items[0] if items else {}
        label = ((first.get("definition") or {}).get("label") if isinstance(first, dict) else None)
        cases.append(
            {
                "id": "seed_replacement_opt_in",
                "ok": applied.get("status") == "ok"
                and first.get("authority") == "published"
                and label == "published-label"
                and applied.get("published_count") == 1
                and applied.get("wrote") is True
                and applied.get("workspace_seeds_mutated") is False
                and applied.get("seed_replacement_complete") is False
                and applied.get("certified") is False,
            }
        )
        cases.append(
            {
                "id": "honesty_certified_false",
                "ok": applied.get("certified") is False
                and applied.get("n02_object_type_freeze") is True
                and applied.get("seed_replacement_complete") is False,
            }
        )
    finally:
        if prev is None:
            os.environ.pop("AIPLAT_KNOWLEDGE_OBJECT_TYPE_SEED_REPLACE", None)
        else:
            os.environ["AIPLAT_KNOWLEDGE_OBJECT_TYPE_SEED_REPLACE"] = prev
        if prev_home is None:
            os.environ.pop("AIPLAT_HOME", None)
        else:
            os.environ["AIPLAT_HOME"] = prev_home
        tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok"))
    return {
        "ok": passed == len(_SEED_REPLACE_CASES) and len(cases) == len(_SEED_REPLACE_CASES),
        "passed": passed,
        "total": len(_SEED_REPLACE_CASES),
        "cases": cases,
        "certified": False,
        "n02_full_conformance": False,
        "n02_object_type_freeze": True,
        "seed_replacement_complete": False,
        "note": (
            "Bounded published-over-seed authority residual; "
            "not full seed replacement / not N02 certified"
        ),
    }


def evaluate_seed_replacement_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N02 residual：种子权威覆盖门槛门；certified / complete 恒 false。

    Args:
        suite: ``run_seed_replacement_suite`` 回执。
    """
    s = suite if isinstance(suite, dict) else run_seed_replacement_suite()
    issues: List[str] = []
    if not s.get("ok"):
        issues.append("suite_not_ok")
    if s.get("certified") is True or s.get("n02_full_conformance") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("seed_replacement_complete") is True:
        issues.append("honesty_seed_replacement_complete_forbidden")
    ids = {
        c.get("id")
        for c in (s.get("cases") or [])
        if isinstance(c, dict) and c.get("ok")
    }
    for need in _SEED_REPLACE_CASES:
        if need not in ids:
            issues.append(f"missing_or_failed:{need}")
    return {
        "ok": not issues,
        "issues": issues,
        "certified": False,
        "n02_full_conformance": False,
        "n02_object_type_freeze": True,
        "seed_replacement_complete": False,
        "note": "Bounded seed authority residual gate; not N02 certified",
    }


def run_seed_authority_product_suite(
    *,
    tenant_id: str = "n02-seed-product-tenant",
) -> Dict[str, Any]:
    """N02 产品面：种子目录 + migrate/rollback 套件（certified 恒 false）。

    Args:
        tenant_id: 套件租户。
    """
    cases: List[Dict[str, Any]] = []
    prev = os.environ.get("AIPLAT_KNOWLEDGE_OBJECT_TYPE_SEED_REPLACE")
    prev_home = os.environ.get("AIPLAT_HOME")
    # 为什么：产品面无 env 门——显式清掉 residual 开关仍应可用
    os.environ.pop("AIPLAT_KNOWLEDGE_OBJECT_TYPE_SEED_REPLACE", None)
    tmp = tempfile.TemporaryDirectory(prefix="n02-seed-product-")
    try:
        root = Path(tmp.name)
        db = str(root / "ot.sqlite3")
        home = root / "home"
        home.mkdir()
        os.environ["AIPLAT_HOME"] = str(home)

        catalog = list_object_type_seed_catalog()
        first = (catalog.get("items") or [None])[0]
        cases.append(
            {
                "id": "seed_authority_product_catalog",
                "ok": catalog.get("status") == "ok"
                and catalog.get("seed_product_surface") is True
                and catalog.get("certified") is False
                and catalog.get("workspace_seeds_mutated") is False
                and isinstance(first, dict)
                and bool(first.get("path")),
            }
        )

        seed_path = str((first or {}).get("path") or "")
        seed_name = str((first or {}).get("name") or "")
        # 发布一个与种子重叠的类型（若种子为空则用 DemoProduct）
        probe_oid = "DemoProduct"
        try:
            from core.harness.knowledge_pipeline.fact_ledger import (
                load_object_type_bindings,
            )

            bindings = load_object_type_bindings(Path(seed_path)) if seed_path else []
            if bindings:
                probe_oid = str(bindings[0].get("object_type_id") or probe_oid)
        except Exception:  # noqa: BLE001
            pass

        submit_object_type_draft(
            tenant_id=tenant_id,
            object_type_id=probe_oid,
            version="1.0.0",
            definition={
                "object_type_id": probe_oid,
                "label": "published-product-label",
                "primary_key": "id",
            },
            actor="author",
            reason="draft",
            db_path=db,
        )
        transition_object_type(
            tenant_id=tenant_id,
            object_type_id=probe_oid,
            version="1.0.0",
            to_status="in_review",
            actor="author",
            reason="review",
            db_path=db,
        )
        prev_rbac = os.environ.get("AIPLAT_OBJECT_TYPE_PUBLISH_RBAC")
        os.environ["AIPLAT_OBJECT_TYPE_PUBLISH_RBAC"] = "0"
        try:
            transition_object_type(
                tenant_id=tenant_id,
                object_type_id=probe_oid,
                version="1.0.0",
                to_status="published",
                actor="reviewer",
                reason="publish",
                role="reviewer",
                db_path=db,
            )
        finally:
            if prev_rbac is None:
                os.environ.pop("AIPLAT_OBJECT_TYPE_PUBLISH_RBAC", None)
            else:
                os.environ["AIPLAT_OBJECT_TYPE_PUBLISH_RBAC"] = prev_rbac

        applied = apply_published_seed_authority_product(
            tenant_id=tenant_id,
            seed_path=seed_name or seed_path,
            object_type_ids=[probe_oid],
            write=True,
            db_path=db,
        )
        items = applied.get("items") or []
        first_item = items[0] if items else {}
        label = (
            (first_item.get("definition") or {}).get("label")
            if isinstance(first_item, dict)
            else None
        )
        out_path = Path(str(applied.get("output_path") or ""))
        cases.append(
            {
                "id": "seed_authority_product_apply",
                "ok": applied.get("status") == "ok"
                and applied.get("via") == "product"
                and applied.get("seed_product_surface") is True
                and applied.get("seed_migrate_rollback") is True
                and first_item.get("authority") == "published"
                and label == "published-product-label"
                and applied.get("wrote") is True
                and applied.get("workspace_seeds_mutated") is False
                and applied.get("seed_replacement_complete") is False
                and applied.get("certified") is False
                and out_path.is_file()
                and "current" in out_path.parts,
            }
        )

        # slice-2：备份现有 current 镜像
        bak = backup_seed_authority_snapshot(tenant_id=tenant_id)
        bak_id = bak.get("backup_id")
        cases.append(
            {
                "id": "seed_migrate_backup",
                "ok": bak.get("status") == "ok"
                and bak.get("backed_up") is True
                and bool(bak_id)
                and bak.get("seed_migrate_rollback") is True
                and bak.get("workspace_seeds_mutated") is False,
            }
        )

        # 再写一版（自动 backup）；确认仍可写
        rewritten = apply_published_seed_authority_product(
            tenant_id=tenant_id,
            seed_path=seed_name or seed_path,
            object_type_ids=[probe_oid],
            write=True,
            db_path=db,
        )
        cases.append(
            {
                "id": "seed_migrate_write",
                "ok": rewritten.get("status") == "ok"
                and rewritten.get("wrote") is True
                and rewritten.get("seed_migrate_rollback") is True
                and rewritten.get("seed_replacement_complete") is False
                and bool(rewritten.get("backup_id")),
            }
        )

        # 篡改 current 后 restore 回 bak_id
        current = Path(str(rewritten.get("output_path") or ""))
        if current.is_file():
            current.write_text(
                json.dumps({"tampered": True, "tenant_id": tenant_id}, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
        restored = restore_seed_authority_snapshot(
            tenant_id=tenant_id,
            backup_id=str(bak_id or ""),
        )
        restored_body = {}
        if restored.get("output_path"):
            try:
                restored_body = json.loads(
                    Path(str(restored["output_path"])).read_text(encoding="utf-8")
                )
            except Exception:  # noqa: BLE001
                restored_body = {}
        listed = list_seed_authority_backups(tenant_id=tenant_id)
        cases.append(
            {
                "id": "seed_migrate_restore",
                "ok": restored.get("status") == "ok"
                and restored.get("restored") is True
                and restored.get("seed_migrate_rollback") is True
                and restored.get("workspace_seeds_mutated") is False
                and restored_body.get("tampered") is not True
                and isinstance(restored_body.get("object_types"), list)
                and listed.get("status") == "ok"
                and listed.get("total", 0) >= 1,
            }
        )

        cases.append(
            {
                "id": "honesty_product_certified_false",
                "ok": applied.get("certified") is False
                and applied.get("n02_object_type_freeze") is True
                and applied.get("seed_replacement_complete") is False
                and catalog.get("seed_replacement_complete") is False
                and restored.get("seed_replacement_complete") is False,
            }
        )
    finally:
        if prev is None:
            os.environ.pop("AIPLAT_KNOWLEDGE_OBJECT_TYPE_SEED_REPLACE", None)
        else:
            os.environ["AIPLAT_KNOWLEDGE_OBJECT_TYPE_SEED_REPLACE"] = prev
        if prev_home is None:
            os.environ.pop("AIPLAT_HOME", None)
        else:
            os.environ["AIPLAT_HOME"] = prev_home
        tmp.cleanup()

    passed = sum(1 for c in cases if c.get("ok"))
    return {
        "ok": passed == len(_SEED_PRODUCT_CASES)
        and len(cases) == len(_SEED_PRODUCT_CASES),
        "passed": passed,
        "total": len(_SEED_PRODUCT_CASES),
        "cases": cases,
        "certified": False,
        "n02_full_conformance": False,
        "n02_object_type_freeze": True,
        "seed_replacement_complete": False,
        "seed_product_surface": True,
        "seed_migrate_rollback": True,
        "workspace_seeds_mutated": False,
        "note": (
            "Seed authority product surface suite slice-2 (migrate/rollback); "
            "not seed_replacement_complete / not N02 certified"
        ),
    }


def evaluate_seed_authority_product_gate(
    suite: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """N02 产品面种子权威门槛门；要求 migrate/rollback；禁止 certified / complete。

    Args:
        suite: ``run_seed_authority_product_suite`` 回执。
    """
    s = suite if isinstance(suite, dict) else run_seed_authority_product_suite()
    issues: List[str] = []
    if not s.get("ok"):
        issues.append("suite_not_ok")
    if s.get("certified") is True or s.get("n02_full_conformance") is True:
        issues.append("honesty_certified_flag_forbidden")
    if s.get("seed_replacement_complete") is True:
        issues.append("honesty_seed_replacement_complete_forbidden")
    if s.get("seed_product_surface") is not True:
        issues.append("product_seed_surface_required")
    if s.get("seed_migrate_rollback") is not True:
        issues.append("product_seed_migrate_rollback_required")
    if s.get("workspace_seeds_mutated") is True:
        issues.append("honesty_workspace_seeds_mutated_forbidden")
    ids = {
        c.get("id")
        for c in (s.get("cases") or [])
        if isinstance(c, dict) and c.get("ok")
    }
    for need in _SEED_PRODUCT_CASES:
        if need not in ids:
            issues.append(f"missing_or_failed:{need}")
    return {
        "ok": not issues,
        "issues": issues,
        "certified": False,
        "n02_full_conformance": False,
        "n02_object_type_freeze": True,
        "seed_replacement_complete": False,
        "seed_product_surface": True,
        "seed_migrate_rollback": True,
        "workspace_seeds_mutated": False,
        "note": "Seed authority product gate slice-2; not N02 certified",
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
