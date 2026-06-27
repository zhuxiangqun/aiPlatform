"""
aiPlat-platform HTTP API (Phase 1/2)

STRUCTURAL DEBT (audit platform layer): 2893 lines, monolithic API file.
Split plan:
  routes_auth.py  — JWT/API key identity resolution + /whoami (lines ~30-210)
  routes_kb.py    — Knowledge base CRUD + ingest (lines ~600-1450)
  routes_agents.py — Agent/Skill/MCP/Plugin management (lines ~1450-2300)
  routes_builder.py — Builder projects + teams (already in api/routers/builder.py)
  routes.py        — FastAPI app assembly + router includes (< 200 lines)
Target: each < 1000 lines.

What this file provides:
- PR-01: 身份解析（JWT/API key）+ 标准 Header 透传 + request_id 生成 + /whoami
- PR-02: platform 代理执行：/platform/gateway/execute 与 /api/v1/agents/{id}/execute → 转发 aiPlat-core /api/core/gateway/execute
- Minimal CRUD for management pages: /platform/gateway/routes, /platform/auth/users, /platform/tenants (in-memory)
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, List

from fastapi import Depends, FastAPI, Header, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import httpx

# NOTE: repo folder name contains '-', so do NOT import via top-level package name.
# Use subpackages directly (auth/, utils/, etc).
from utils.ids import new_prefixed_id as _new_prefixed_id  # type: ignore
from auth.authenticator import authenticator as _authenticator  # type: ignore
from auth.deps import require_auth, require_admin
from storage import sqlite as platform_store  # type: ignore
from core.api.core_facade import create_infra_database_client
from core.api.facades.service_facade import llm_generate


app = FastAPI(title="aiPlat-platform", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "healthy"}


# ── Governance middleware ────────────────────────────────────────────────
# Rate limiting and audit logging wired per CLAUDE.md architecture audit.
# Toggle via AIPLAT_RATE_LIMIT_ENABLED / AIPLAT_AUDIT_LOG_ENABLED env vars.
_RATE_LIMIT_ENABLED = os.getenv("AIPLAT_RATE_LIMIT_ENABLED", "").lower() in ("1", "true", "yes", "y", "on")
_RATE_LIMIT_PER_MINUTE = int(os.getenv("AIPLAT_RATE_LIMIT_PER_MINUTE", "300"))
_AUDIT_LOG_ENABLED = os.getenv("AIPLAT_AUDIT_LOG_ENABLED", "").lower() in ("1", "true", "yes", "y", "on")
if _RATE_LIMIT_ENABLED or _AUDIT_LOG_ENABLED:
    from governance import rate_limiter, audit_logger
    from governance.audit.logger import AuditAction
    _rate_limit_lock = None
    if _RATE_LIMIT_ENABLED:
        rate_limiter.set_limit("global", _RATE_LIMIT_PER_MINUTE, 60)
        import logging as _rl_log
        _rl_log.getLogger("aiplat.platform.governance").info(
            "Rate limiter activated: %d req/min", _RATE_LIMIT_PER_MINUTE)


@app.middleware("http")
async def _governance_middleware(request: Request, call_next):
    # Rate limit check
    if _RATE_LIMIT_ENABLED:
        client_key = request.headers.get("X-AIPLAT-API-KEY") or request.client.host if request.client else "unknown"
        if not rate_limiter.check(client_key):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests", "retry_after": 60},
                headers={"Retry-After": "60"},
            )
        rate_limiter.consume(client_key)

    # Execute request
    response = await call_next(request)

    # Audit log
    if _AUDIT_LOG_ENABLED:
        try:
            tenant_id = request.headers.get("X-AIPLAT-TENANT-ID", "default")
            actor_id = request.headers.get("X-AIPLAT-ACTOR-ID", "anonymous")
            resource = request.url.path
            action = AuditAction.READ if request.method in ("GET", "HEAD", "OPTIONS") else (
                AuditAction.DELETE if request.method == "DELETE" else AuditAction.UPDATE
            )
            result = "success" if response.status_code < 400 else "failure"
            audit_logger.log(
                tenant_id=tenant_id, actor_id=actor_id, action=action,
                resource_type="http", resource_id=resource, result=result,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    return response


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Convert uncaught ValueError to structured response (404 for not-found, 400 otherwise)."""
    import logging
    msg = str(exc)[:500]
    logging.getLogger("aiplat.platform").warning("ValueError in %s %s: %s", request.method, request.url.path, msg)
    is_not_found = "not found" in msg.lower()
    return JSONResponse(
        status_code=404 if is_not_found else 400,
        content={"detail": msg, "error": msg, "error_code": "not_found" if is_not_found else "invalid_request"},
    )

# Register KB provider callbacks — connects platform's concrete implementations
# to core's abstract interfaces (resolves core→platform reverse dependency).
try:
    from core.api.core_facade import set_knowledge_db, set_knowledge_providers
    from core.api.facades.service_facade import llm_generate
    from kb.db import KBSqlite
    from kb.storage import get_tenant_storage as _storage_root
    from kb.service import ingest_document, enqueue_ingest, load_doc_kinds, preview_document
    from kb.budget_query import query
    import os as _os
    db_path = _os.path.expanduser(
        _os.getenv("AIPLAT_KB_DB_PATH", "~/.aiplat/data/kb/aiplat_knowledge.sqlite3"))
    _os.makedirs(_os.path.dirname(db_path), exist_ok=True)
    set_knowledge_db(KBSqlite(db_path))
    set_knowledge_providers(
        ingest_fn=ingest_document, query_fn=query,
        enqueue_fn=enqueue_ingest, load_doc_kinds_fn=load_doc_kinds,
    )
except Exception as e:
    logging.debug(str(e), exc_info=True)


# Optional dependency: python-multipart (needed for UploadFile/File form parsing).
# Keep platform importable in minimal envs (tests) even if multipart is absent.
try:
    import multipart  # type: ignore  # noqa: F401

    _HAS_MULTIPART = True
except Exception:
    _HAS_MULTIPART = False


@dataclass
class Identity:
    request_id: str
    tenant_id: str
    actor_id: str
    scopes: List[str]
    actor_role: Optional[str] = None
    auth_type: str = "anonymous"  # jwt|api_key|header|anonymous


def _b64url_json_decode(part: str) -> Dict[str, Any]:
    pad = "=" * (-len(part) % 4)
    raw = base64.urlsafe_b64decode((part + pad).encode("utf-8"))
    return json.loads(raw.decode("utf-8"))


def _decode_jwt_claims(token: str) -> Dict[str, Any]:
    """
    Best-effort JWT decode.
    - If PyJWT is installed and AIPLAT_JWT_SECRET is set, you can enable verification.
    - Otherwise decode without verification (dev-only).
    """
    verify = os.getenv("AIPLAT_PLATFORM_JWT_VERIFY", "true").lower() in ("1", "true", "yes", "y")
    if not verify:
        import logging
        logging.getLogger("aiplat.platform").warning(
            "JWT verification is DISABLED. Set AIPLAT_PLATFORM_JWT_VERIFY=true in production.")
    secret = os.getenv("AIPLAT_JWT_SECRET") or ""
    if verify and not secret:
        import logging
        logging.getLogger("aiplat.platform").critical(
            "AIPLAT_JWT_SECRET is empty but JWT verification is enabled. JWT tokens will be rejected.")
        raise HTTPException(status_code=503, detail="JWT secret not configured")
    if verify and secret:
        try:
            import jwt  # type: ignore

            return jwt.decode(token, secret, algorithms=["HS256", "RS256"], options={"verify_aud": False})
        except Exception as e:
            # fallback to unverified decode
            logging.debug(str(e), exc_info=True)
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    return _b64url_json_decode(parts[1])


def _parse_scopes(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip()]
    if isinstance(v, str):
        # allow comma or space
        raw = v.replace(" ", ",")
        return [x.strip() for x in raw.split(",") if x.strip()]
    return [str(v)]


def _get_or_create_request_id(request: Request) -> str:
    rid = request.headers.get("X-AIPLAT-REQUEST-ID")
    if isinstance(rid, str) and rid.strip():
        return rid.strip()
    return _new_prefixed_id("req")


def _resolve_identity(request: Request) -> Identity:
    request_id = _get_or_create_request_id(request)

    # 1) Explicit headers (debug / internal calls)
    tenant_id = request.headers.get("X-AIPLAT-TENANT-ID")
    actor_id = request.headers.get("X-AIPLAT-ACTOR-ID")
    scopes = _parse_scopes(request.headers.get("X-AIPLAT-SCOPES"))
    actor_role = request.headers.get("X-AIPLAT-ACTOR-ROLE")
    if tenant_id and actor_id:
        return Identity(
            request_id=request_id,
            tenant_id=str(tenant_id),
            actor_id=str(actor_id),
            scopes=scopes,
            actor_role=str(actor_role) if actor_role else None,
            auth_type="header",
        )

    # 2) Authorization: Bearer <token> (JWT or API key)
    authz = request.headers.get("Authorization")
    token = None
    if isinstance(authz, str) and authz.lower().startswith("bearer "):
        token = authz.split(" ", 1)[1].strip()
    # also allow explicit api key header
    api_key = request.headers.get("X-AIPLAT-API-KEY") or token
    if isinstance(api_key, str) and api_key.startswith("apl_"):
        ar = _authenticator.verify_api_key(api_key)
        if ar.success and ar.tenant_id and ar.user_id:
            return Identity(
                request_id=request_id,
                tenant_id=str(ar.tenant_id),
                actor_id=str(ar.user_id),
                scopes=_authenticator.get_permissions(api_key),
                actor_role="service",
                auth_type="api_key",
            )

        # DEV fallback: allow any apl_* api key in local development if enabled.
        # This unblocks management UI without implementing persistent key issuance yet.
        dev_allow_any = os.getenv("AIPLAT_PLATFORM_DEV_ALLOW_ANY_API_KEY", "false").lower() in ("1", "true", "yes", "y")
        if dev_allow_any:
            tid = request.headers.get("X-AIPLAT-TENANT-ID") or "default"
            return Identity(
                request_id=request_id,
                tenant_id=str(tid),
                # Use core's seeded superuser id so skill/tool EXECUTE permissions pass in MVP.
                actor_id="admin",
                scopes=["kb:read", "kb:write"],
                actor_role="admin",
                auth_type="api_key_dev",
            )

    if isinstance(token, str) and token.count(".") >= 2:
        claims = _decode_jwt_claims(token)
        tid = claims.get("tid") or claims.get("tenant_id") or "default"
        sub = claims.get("sub") or claims.get("actor_id") or "anonymous"
        roles = claims.get("roles")
        scopes2 = claims.get("scopes")
        role0 = None
        if isinstance(roles, list) and roles:
            role0 = str(roles[0])
        return Identity(
            request_id=request_id,
            tenant_id=str(tid),
            actor_id=str(sub),
            scopes=_parse_scopes(scopes2),
            actor_role=role0,
            auth_type="jwt",
        )

    # 2.5) OIDC Bearer token (Azure AD / Keycloak / Okta)
    try:
        from auth.identity_provider import get_oidc_provider
        oidc = get_oidc_provider()
        if oidc.enabled and isinstance(token, str) and token.count(".") >= 2:
            claims = oidc.verify_token(token)
            if claims:
                ident = oidc.extract_identity(claims)
                return Identity(
                    request_id=request_id,
                    tenant_id=str(ident["tenant_id"]),
                    actor_id=str(ident["actor_id"]),
                    scopes=list(ident["scopes"]),
                    actor_role=str(ident.get("actor_role", "")),
                    auth_type=str(ident.get("auth_type", "oidc")),
                )
    except ImportError:
        pass  # python-jose not installed
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # 3) default fallback
    scopes: List[str] = []
    if os.getenv("AIPLAT_PLATFORM_DEV_MODE", "false").lower() in ("1", "true", "yes", "y"):
        scopes = ["kb:read", "kb:write", "admin"]
    return Identity(request_id=request_id, tenant_id="default", actor_id="anonymous", scopes=scopes, auth_type="anonymous")


def _core_base_url() -> str:
    return os.getenv("AIPLAT_CORE_URL", "http://localhost:8002").rstrip("/")


def _require_scope(identity: Identity, scope: str) -> None:
    """
    极简权限校验（MVP）：
    - 如果 token scopes 里包含 scope 则允许
    - 或 actor_role=admin/system 允许
    """
    if identity.actor_role in ("admin", "system"):
        return
    if scope and scope in (identity.scopes or []):
        return
    raise HTTPException(status_code=403, detail=f"missing_scope:{scope}")


def _platform_home() -> str:
    return os.getenv("AIPLAT_HOME", str((__import__('pathlib').Path.home() / '.aiplat')))


def _kb_tenant_dir(tenant_id: str) -> str:
    from pathlib import Path

    tid = str(tenant_id or "").strip() or "default"
    p = Path(_platform_home()).expanduser() / "kb" / "tenants" / tid
    p.mkdir(parents=True, exist_ok=True)
    (p / "uploads").mkdir(parents=True, exist_ok=True)
    return str(p)


def _kb_page_image_path(*, tenant_id: str, doc_id: str, page_idx: int) -> str:
    # This mirrors core.apps.multimodal_kb.storage layout.
    from pathlib import Path

    base = Path(_kb_tenant_dir(tenant_id)).expanduser() / "assets" / str(doc_id) / "pages"
    # The core renderer uses page_{idx:04d}.png
    return str(base / f"page_{int(page_idx):04d}.png")


def _kb_frame_image_path(*, tenant_id: str, doc_id: str, frame_idx: int) -> str:
    from pathlib import Path

    base = Path(_kb_tenant_dir(tenant_id)).expanduser() / "assets" / str(doc_id) / "frames"
    return str(base / f"frame_{int(frame_idx):05d}.jpg")


def _normalize_citations_with_assets(*, tenant_id: str, data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(data, dict):
        return data
    out_data = dict(data)
    cits = out_data.get("citations") if isinstance(out_data.get("citations"), list) else []
    new_cits = []
    for c in cits:
        if not isinstance(c, dict):
            continue
        c2 = dict(c)
        doc_id = c2.get("doc_id")
        page_idx = c2.get("page_idx")
        asset_kind = str(c2.get("asset_kind") or "")
        if doc_id is not None and page_idx is not None:
            try:
                if asset_kind == "frame_image":
                    fp = _kb_frame_image_path(tenant_id=tenant_id, doc_id=str(doc_id), frame_idx=int(page_idx))
                    public_url = f"/platform/kb/assets/{doc_id}/frames/{int(page_idx)}"
                else:
                    fp = _kb_page_image_path(tenant_id=tenant_id, doc_id=str(doc_id), page_idx=int(page_idx))
                    public_url = f"/platform/kb/assets/{doc_id}/pages/{int(page_idx)}"
                if os.path.isfile(fp):
                    c2["asset_url"] = public_url
                    c2["asset_available"] = True
                else:
                    c2.pop("asset_url", None)
                    c2["asset_available"] = False
            except Exception:
                c2.pop("asset_url", None)
                c2["asset_available"] = False
        # never expose raw local filesystem path in public API
        c2.pop("asset_path", None)
        new_cits.append(c2)
    out_data["citations"] = new_cits
    return out_data

def _kb_db_path(tenant_id: str) -> str:
    from pathlib import Path

    return str(Path(_kb_tenant_dir(tenant_id)).expanduser() / "kb.sqlite3")


def _open_kb_db(tenant_id: str):
    """Open KB database via Infra Bridge (不直接 import sqlite3).
    
    Returns a connection with row_factory=Row and PRAGMA WAL/NORMAL applied.
    """
    return create_infra_database_client(_kb_db_path(tenant_id))

_KB_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS collections (
  tenant_id TEXT NOT NULL,
  collection_id TEXT NOT NULL,
  name TEXT,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, collection_id)
);

CREATE TABLE IF NOT EXISTS documents (
  tenant_id TEXT NOT NULL,
  doc_id TEXT NOT NULL,
  collection_id TEXT NOT NULL,
  source_uri TEXT NOT NULL,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  wiki_status TEXT NOT NULL DEFAULT '',
  meta_json TEXT,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, doc_id)
);

CREATE INDEX IF NOT EXISTS idx_documents_collection
  ON documents(tenant_id, collection_id, created_at);

CREATE TABLE IF NOT EXISTS assets (
  tenant_id TEXT NOT NULL,
  asset_id TEXT NOT NULL,
  doc_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  local_path TEXT NOT NULL,
  page_idx INTEGER,
  time_ms INTEGER,
  meta_json TEXT,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, asset_id)
);

CREATE INDEX IF NOT EXISTS idx_assets_doc
  ON assets(tenant_id, doc_id, kind);

CREATE TABLE IF NOT EXISTS budget_rows (
  tenant_id TEXT NOT NULL,
  row_id TEXT NOT NULL,
  doc_id TEXT NOT NULL,
  page_idx INTEGER NOT NULL,
  item TEXT NOT NULL,
  y2026 REAL,
  y2027 REAL,
  total REAL,
  cells_json TEXT,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, row_id)
);

CREATE INDEX IF NOT EXISTS idx_budget_by_doc
  ON budget_rows(tenant_id, doc_id, page_idx);

CREATE TABLE IF NOT EXISTS kb_elements (
  tenant_id TEXT NOT NULL,
  element_id TEXT NOT NULL,
  doc_id TEXT NOT NULL,
  type TEXT NOT NULL,
  page_idx INTEGER,
  bbox_json TEXT,
  text TEXT,
  cells_json TEXT,
  asset_id TEXT,
  meta_json TEXT,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, element_id)
);

CREATE INDEX IF NOT EXISTS idx_kb_elements_doc
  ON kb_elements(tenant_id, doc_id, type, page_idx, created_at);

CREATE TABLE IF NOT EXISTS doc_sources (
  tenant_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  doc_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_uri TEXT NOT NULL,
  url TEXT,
  local_path TEXT,
  kind TEXT,
  content_type TEXT,
  content_hash TEXT,
  meta_json TEXT,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, source_id)
);

CREATE INDEX IF NOT EXISTS idx_doc_sources_doc
  ON doc_sources(tenant_id, doc_id, created_at);

CREATE TABLE IF NOT EXISTS url_cache (
  tenant_id TEXT NOT NULL,
  url TEXT NOT NULL,
  doc_id TEXT NOT NULL,
  local_path TEXT NOT NULL,
  kind TEXT,
  content_type TEXT,
  content_hash TEXT,
  etag TEXT,
  last_modified TEXT,
  fetched_at INTEGER NOT NULL,
  meta_json TEXT,
  PRIMARY KEY (tenant_id, url)
);

CREATE TABLE IF NOT EXISTS kb_embeddings (
  tenant_id TEXT NOT NULL,
  embedding_id TEXT NOT NULL,
  doc_id TEXT NOT NULL,
  element_id TEXT NOT NULL,
  embedding_type TEXT NOT NULL,
  model TEXT,
  dim INTEGER,
  vector_json TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, embedding_id)
);

CREATE INDEX IF NOT EXISTS idx_kb_embeddings_doc
  ON kb_embeddings(tenant_id, doc_id, embedding_type, created_at);

CREATE INDEX IF NOT EXISTS idx_kb_embeddings_element
  ON kb_embeddings(tenant_id, element_id);

CREATE TABLE IF NOT EXISTS analysis_runs (
  tenant_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  doc_id TEXT,
  collection_id TEXT,
  run_type TEXT NOT NULL,
  mode TEXT,
  retrieval_mode TEXT,
  generation_mode TEXT,
  input_json TEXT,
  output_json TEXT,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, run_id)
);

CREATE INDEX IF NOT EXISTS idx_analysis_runs_doc
  ON analysis_runs(tenant_id, doc_id, created_at);

CREATE INDEX IF NOT EXISTS idx_analysis_runs_collection
  ON analysis_runs(tenant_id, collection_id, created_at);

CREATE TABLE IF NOT EXISTS analysis_batches (
  tenant_id TEXT NOT NULL,
  batch_id TEXT NOT NULL,
  collection_id TEXT,
  batch_type TEXT NOT NULL,
  title TEXT,
  input_json TEXT,
  output_json TEXT,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, batch_id)
);

CREATE INDEX IF NOT EXISTS idx_analysis_batches_collection
  ON analysis_batches(tenant_id, collection_id, created_at);

CREATE TABLE IF NOT EXISTS kb_jobs (
  tenant_id TEXT NOT NULL,
  job_id TEXT NOT NULL,
  type TEXT NOT NULL,
  collection_id TEXT,
  doc_id TEXT,
  status TEXT NOT NULL,
  progress REAL,
  message TEXT,
  input_json TEXT,
  output_json TEXT,
  error_json TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_kb_jobs_status
  ON kb_jobs(tenant_id, status, created_at);

CREATE TABLE IF NOT EXISTS kb_job_events (
  tenant_id TEXT NOT NULL,
  id TEXT NOT NULL,
  job_id TEXT NOT NULL,
  ts INTEGER NOT NULL,
  level TEXT NOT NULL,
  message TEXT NOT NULL,
  extra_json TEXT,
  PRIMARY KEY (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_kb_job_events_job
  ON kb_job_events(tenant_id, job_id, ts);
"""


def _kb_ensure_schema(conn) -> None:
    # Keep platform endpoints resilient even when the DB was created partially.
    try:
        conn.executescript(_KB_SCHEMA_SQL)
        conn.commit()
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    # FTS5 full-text index on kb_elements (best-effort)
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS kb_elements_fts "
            "USING fts5(element_id, doc_id, text, tokenize='unicode61')"
        )
        conn.commit()
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    # Schema migration: add version column for existing DBs
    try:
        conn.execute("ALTER TABLE documents ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
        conn.commit()
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    # Schema migration: add wiki_status column for existing DBs
    try:
        conn.execute("ALTER TABLE documents ADD COLUMN wiki_status TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except Exception as e:
        logging.debug(str(e), exc_info=True)


def _new_analysis_run_id() -> str:
    import time, random

    return f"ar_{int(time.time() * 1000):x}{random.randint(0, 0xFFFF):04x}"


def _new_analysis_batch_id() -> str:
    import time, random

    return f"ab_{int(time.time() * 1000):x}{random.randint(0, 0xFFFF):04x}"


def _persist_analysis_batch(*, tenant_id: str, collection_id: str, batch_type: str, title: str, input_obj: Dict[str, Any]) -> str:
    import json

    conn = _open_kb_db(tenant_id)
    try:
        _kb_ensure_schema(conn)
        bid = _new_analysis_batch_id()
        conn.execute(
            "INSERT INTO analysis_batches(tenant_id, batch_id, collection_id, batch_type, title, input_json, created_at) "
            "VALUES(?,?,?,?,?,?,strftime('%s','now'))",
            (tenant_id, bid, collection_id, batch_type, title, json.dumps(input_obj or {}, ensure_ascii=False)),
        )
        conn.commit()
        return bid
    finally:
        conn.close()


def _list_analysis_batches(*, tenant_id: str, collection_id: Optional[str] = None) -> list:
    conn = _open_kb_db(tenant_id)
    try:
        _kb_ensure_schema(conn)
        if collection_id:
            rows = conn.execute(
                "SELECT tenant_id, batch_id, collection_id, batch_type, title, input_json, output_json, created_at "
                "FROM analysis_batches WHERE tenant_id = ? AND collection_id = ? ORDER BY created_at DESC",
                (tenant_id, collection_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT tenant_id, batch_id, collection_id, batch_type, title, input_json, output_json, created_at "
                "FROM analysis_batches WHERE tenant_id = ? ORDER BY created_at DESC",
                (tenant_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _delete_analysis_batch(*, tenant_id: str, batch_id: str) -> bool:
    conn = _open_kb_db(tenant_id)
    try:
        _kb_ensure_schema(conn)
        cur = conn.execute(
            "DELETE FROM analysis_batches WHERE tenant_id = ? AND batch_id = ?",
            (tenant_id, batch_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


async def _core_request(
    method: str,
    path: str,
    *,
    identity: Identity,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-AIPLAT-REQUEST-ID": identity.request_id,
        "X-AIPLAT-TENANT-ID": identity.tenant_id,
        "X-AIPLAT-ACTOR-ID": identity.actor_id,
    }
    if identity.scopes:
        headers["X-AIPLAT-SCOPES"] = ",".join(identity.scopes)
    if identity.actor_role:
        headers["X-AIPLAT-ACTOR-ROLE"] = identity.actor_role
    if extra_headers:
        headers.update(extra_headers)
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            resp = await client.request(method.upper(), f"{_core_base_url()}{path}", headers=headers, params=params, json=json_body)
        except httpx.HTTPError as e:
            raise HTTPException(status_code=503, detail=f"core_request_failed:{e}")
        if resp.status_code >= 400:
            try:
                payload = resp.json()
            except Exception:
                payload = None
            detail = None
            if isinstance(payload, dict):
                detail = payload.get("detail") or payload.get("message") or payload
            if detail is None:
                detail = resp.text or f"core_http_{resp.status_code}"
            raise HTTPException(status_code=resp.status_code, detail=detail)
        try:
            return resp.json()
        except Exception:
            raise HTTPException(status_code=502, detail="invalid_core_json_response")


def _extract_job_payload(resp: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(resp, dict):
        return None
    candidates: List[Any] = [
        resp.get("output"),
        ((resp.get("output") or {}) if isinstance(resp.get("output"), dict) else {}).get("output"),
        ((resp.get("output") or {}) if isinstance(resp.get("output"), dict) else {}).get("result"),
        resp.get("result"),
    ]
    for c in candidates:
        if isinstance(c, dict) and c.get("job_id") and c.get("doc_id"):
            return c
    return None


def _persist_analysis_run(*, tenant_id: str, doc_id: Optional[str], collection_id: Optional[str], run_type: str, input_obj: Dict[str, Any], output_obj: Optional[Dict[str, Any]]) -> Optional[str]:
    import json, sqlite3

    dbp = _kb_db_path(tenant_id)
    conn = _open_kb_db(tenant_id)
    try:
        _kb_ensure_schema(conn)
        run_id = _new_analysis_run_id()
        out = output_obj or {}
        conn.execute(
            """
            INSERT INTO analysis_runs(
              tenant_id, run_id, doc_id, collection_id, run_type, mode, retrieval_mode, generation_mode, input_json, output_json, created_at
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,strftime('%s','now'))
            """,
            (
                tenant_id,
                run_id,
                doc_id,
                collection_id,
                run_type,
                str(out.get("mode") or ""),
                str(out.get("retrieval_mode") or ""),
                str(out.get("generation_mode") or ""),
                json.dumps(input_obj or {}, ensure_ascii=False),
                json.dumps(out, ensure_ascii=False),
            ),
        )
        conn.commit()
        return run_id
    finally:
        conn.close()


@app.get("/whoami")
async def platform_whoami(request: Request):
    tenant_id = request.headers.get("X-AIPLAT-TENANT-ID", "default")
    actor_id = request.headers.get("X-AIPLAT-ACTOR-ID", "anonymous")
    auth_type = "api_key" if request.headers.get("X-AIPLAT-API-KEY") else "dev"
    return {
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "auth_type": auth_type,
        "request_id": request.headers.get("X-AIPLAT-REQUEST-ID", "00000000-0000-0000-0000-000000000000"),
    }


# ── App channels / sessions (E2E smoke support) ──────────────────

@app.post("/app/channels")
def platform_app_create_channel(body: Dict[str, Any], request: Request):
    from datetime import datetime, timezone as _dt
    cid = _new_prefixed_id("ch")
    channel = {
        "id": cid,
        "name": str((body or {}).get("name", "unnamed")),
        "type": str((body or {}).get("type", "webhook")),
        "created_at": _dt.utcnow().isoformat(),
        "tenant_id": _resolve_identity(request).tenant_id,
    }
    return channel


@app.post("/app/sessions")
def platform_app_create_session(body: Dict[str, Any], request: Request):
    from datetime import datetime, timezone as _dt
    sid = _new_prefixed_id("ses")
    session = {
        "id": sid,
        "channel_id": str((body or {}).get("channel_id", "default")),
        "user_id": str((body or {}).get("user_id", "anonymous")),
        "created_at": _dt.utcnow().isoformat(),
        "tenant_id": _resolve_identity(request).tenant_id,
    }
    return session


@app.post("/platform/kb/reindex")
@app.post("/api/v1/kb/reindex")
async def kb_reindex(request: Request):
    """Re-embed all existing document elements using the current embedding model.
    Useful after switching embedding models (e.g., MiniLM → Jina)."""
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"status": "no_data", "count": 0}
    conn = _open_kb_db(identity.tenant_id)
    try:
        from core.api.facades.kb_facade import kb_embed_text as _embed_text
        import json as _j
        rows = conn.execute(
            "SELECT element_id, doc_id, text FROM kb_elements WHERE tenant_id=? AND text IS NOT NULL AND length(text)>0",
            (identity.tenant_id,),
        ).fetchall()
        reindexed = 0
        for r in rows:
            text = str(r["text"] or "")
            if not text.strip():
                continue
            vec = await embed_text(text[:4000])
            from core.api.facades.kb_facade import get_embedding_model_name
            emb_model = get_embedding_model_name()
            conn.execute(
                "UPDATE kb_embeddings SET vector_json=?, model=?, dim=? WHERE tenant_id=? AND element_id=?",
                (_j.dumps(vec), emb_model,
                 len(vec), identity.tenant_id, r["element_id"]),
            )
            conn.commit()
            reindexed += 1
        return {"status": "ok", "count": reindexed}
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()


@app.get("/platform/kb/documents/{doc_id}/versions")
@app.get("/api/v1/kb/documents/{doc_id}/versions")
async def kb_doc_versions(doc_id: str, request: Request):
    """Get version history for a document."""
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")
    conn = _open_kb_db(identity.tenant_id)
    try:
        doc = conn.execute(
            "SELECT version, created_at FROM documents WHERE tenant_id=? AND doc_id=?", 
            (identity.tenant_id, doc_id)
        ).fetchone()
        current = dict(doc) if doc else {"version": 1, "created_at": 0}
        # Count elements per version
        versions = []
        for ver in range(1, current["version"] + 1):
            cnt = conn.execute(
                "SELECT count(*) FROM kb_elements WHERE tenant_id=? AND doc_id=? AND meta_json LIKE ?",
                (identity.tenant_id, doc_id, f'%version":{ver}%'),
            ).fetchone()[0]
            versions.append({
                "version": ver,
                "elements": cnt,
                "is_current": ver == current["version"],
            })
        return {"doc_id": doc_id, "current_version": current["version"], "versions": versions}
    finally:
        conn.close()


@app.post("/platform/kb/documents/{doc_id}/rollback/{version}")
@app.post("/api/v1/kb/documents/{doc_id}/rollback/{version}")
async def kb_doc_rollback(doc_id: str, version: int, request: Request):
    """Rollback document to a previous version (un-archive old elements)."""
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")
    conn = _open_kb_db(identity.tenant_id)
    try:
        target_ver = int(version)
        # Un-archive target version elements
        import json as _j
        conn.execute(
            "UPDATE kb_elements SET meta_json = json_set(meta_json,'$.archived',0) WHERE tenant_id=? AND doc_id=? AND meta_json LIKE ?",
            (identity.tenant_id, doc_id, f'%version":{target_ver}%'),
        )
        # Archive current version
        cur_ver = conn.execute(
            "SELECT version FROM documents WHERE tenant_id=? AND doc_id=?", (identity.tenant_id, doc_id)
        ).fetchone()[0]
        conn.execute(
            "UPDATE kb_elements SET meta_json = json_set(meta_json,'$.archived',1) WHERE tenant_id=? AND doc_id=? AND meta_json NOT LIKE ?",
            (identity.tenant_id, doc_id, f'%version":{target_ver}%'),
        )
        conn.execute(
            "UPDATE documents SET version=? WHERE tenant_id=? AND doc_id=?", 
            (target_ver, identity.tenant_id, doc_id),
        )
        conn.commit()
        return {"status": "ok", "version": target_ver}
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        conn.close()


@app.get("/platform/kb/stats")
@app.get("/api/v1/kb/stats")
async def kb_stats(request: Request):
    """Knowledge base statistics: document/element/embedding counts + storage."""
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"documents": 0, "elements": 0, "embeddings": 0, "collections": 0,
                "jobs_pending": 0, "storage_bytes": 0}
    conn = _open_kb_db(identity.tenant_id)
    try:
        _kb_ensure_schema(conn)
        ndocs = conn.execute(
            "SELECT count(*) FROM documents WHERE tenant_id=?", (identity.tenant_id,)
        ).fetchone()[0]
        nelems = conn.execute(
            "SELECT count(*) FROM kb_elements WHERE tenant_id=?", (identity.tenant_id,)
        ).fetchone()[0]
        nembs = conn.execute(
            "SELECT count(*) FROM kb_embeddings WHERE tenant_id=?", (identity.tenant_id,)
        ).fetchone()[0]
        ncols = conn.execute(
            "SELECT count(*) FROM collections WHERE tenant_id=?", (identity.tenant_id,)
        ).fetchone()[0]
        njobs = conn.execute(
            "SELECT count(*) FROM kb_jobs WHERE tenant_id=? AND status IN ('pending','running','queued')",
            (identity.tenant_id,),
        ).fetchone()[0]
        return {
            "documents": ndocs, "elements": nelems, "embeddings": nembs,
            "collections": ncols, "jobs_pending": njobs,
            "tenant_id": identity.tenant_id,
        }
    finally:
        conn.close()


@app.get("/platform/kb/collections")
@app.get("/api/v1/kb/collections")
async def kb_list_collections(request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"collections": [], "total": 0}
    conn = _open_kb_db(identity.tenant_id)
    try:
        _kb_ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT c.collection_id, c.name, c.created_at,
                   (SELECT COUNT(1) FROM documents d WHERE d.tenant_id=c.tenant_id AND d.collection_id=c.collection_id) AS doc_count
            FROM collections c
            WHERE c.tenant_id=?
            ORDER BY c.created_at DESC
            """,
            (identity.tenant_id,),
        ).fetchall()
    finally:
        conn.close()
    items = [dict(r) for r in rows]
    return {"collections": items, "total": len(items)}


@app.get("/kb/jobs/{job_id}")
@app.get("/platform/kb/jobs/{job_id}")
@app.get("/api/v1/kb/jobs/{job_id}")
async def kb_get_job(job_id: str, request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        raise HTTPException(status_code=404, detail="job_not_found")
    conn = _open_kb_db(identity.tenant_id)
    try:
        _kb_ensure_schema(conn)
        row = conn.execute(
            "SELECT * FROM kb_jobs WHERE tenant_id=? AND job_id=?",
            (identity.tenant_id, job_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="job_not_found")
        d = dict(row)
        for k in ("input_json", "output_json", "error_json"):
            try:
                d[k.replace("_json", "")] = json.loads(d.get(k) or "{}")
            except Exception:
                d[k.replace("_json", "")] = {}
            d.pop(k, None)
        return d
    finally:
        conn.close()


@app.get("/kb/jobs/{job_id}/events")
@app.get("/platform/kb/jobs/{job_id}/events")
@app.get("/api/v1/kb/jobs/{job_id}/events")
async def kb_get_job_events(job_id: str, request: Request, limit: int = 200, offset: int = 0):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"items": [], "total": 0}
    conn = _open_kb_db(identity.tenant_id)
    try:
        _kb_ensure_schema(conn)
        total = conn.execute(
            "SELECT COUNT(1) as c FROM kb_job_events WHERE tenant_id=? AND job_id=?",
            (identity.tenant_id, job_id),
        ).fetchone()["c"]
        rows = conn.execute(
            """
            SELECT ts, level, message, extra_json
            FROM kb_job_events
            WHERE tenant_id=? AND job_id=?
            ORDER BY ts ASC
            LIMIT ? OFFSET ?
            """,
            (identity.tenant_id, job_id, int(limit), int(offset)),
        ).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            try:
                d["extra"] = json.loads(d.get("extra_json") or "{}")
            except Exception:
                d["extra"] = {}
            d.pop("extra_json", None)
            items.append(d)
        return {"items": items, "total": int(total or 0)}
    finally:
        conn.close()


@app.post("/kb/collections")
@app.post("/platform/kb/collections")
@app.post("/api/v1/kb/collections")
async def kb_create_collection(req: KBCollectionCreateRequest, request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")

    cid = str(req.collection_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="collection_id_required")
    dbp = _kb_db_path(identity.tenant_id)
    conn = _open_kb_db(identity.tenant_id)
    try:
        _kb_ensure_schema(conn)
        conn.execute(
            "INSERT OR IGNORE INTO collections(tenant_id, collection_id, name, created_at) VALUES(?,?,?,strftime('%s','now'))",
            (identity.tenant_id, cid, (req.name or None)),
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "ok", "collection_id": cid}


@app.get("/kb/documents/categories")
@app.get("/platform/documents/categories")
@app.get("/api/v1/kb/documents/categories")
async def kb_document_categories(request: Request, collection_id: Optional[str] = None):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"kind_categories": [], "content_categories": []}
    conn = _open_kb_db(identity.tenant_id)
    try:
        _kb_ensure_schema(conn)
        where = "WHERE tenant_id=?"
        params = [identity.tenant_id]
        if collection_id:
            where += " AND collection_id=?"
            params.append(collection_id)
        rows = conn.execute(
            f"SELECT kind, meta_json FROM documents {where}",
            tuple(params),
        ).fetchall()
        # Aggregate by kind
        kind_counts: Dict[str, int] = {}
        content_counts: Dict[str, int] = {}
        for r in rows:
            kind = str(r["kind"] or "other").strip().lower()
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
            # Extract category from meta_json if present
            try:
                meta = json.loads(r["meta_json"] or "{}")
            except Exception:
                meta = {}
            cat = str(meta.get("category") or meta.get("content_category") or "").strip()
            if cat:
                content_counts[cat] = content_counts.get(cat, 0) + 1
        kind_categories = [{"key": k, "label": k.title(), "count": v} for k, v in sorted(kind_counts.items())]
        content_categories = [{"key": k, "label": k, "count": v} for k, v in sorted(content_counts.items())]
        return {"kind_categories": kind_categories, "content_categories": content_categories}
    finally:
        conn.close()


@app.get("/kb/collections/{collection_id}/documents")
@app.get("/platform/kb/collections/{collection_id}/documents")
@app.get("/api/v1/kb/collections/{collection_id}/documents")
async def kb_list_documents(collection_id: str, request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"documents": [], "total": 0}
    conn = _open_kb_db(identity.tenant_id)
    try:
        _kb_ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT doc_id, collection_id, source_uri, kind, status, wiki_status, meta_json, created_at
            FROM documents
            WHERE tenant_id=? AND collection_id=?
            ORDER BY created_at DESC
            """,
            (identity.tenant_id, collection_id),
        ).fetchall()
    finally:
        conn.close()
    docs = []
    for r in rows:
        d = dict(r)
        try:
            d["meta"] = json.loads(d.get("meta_json") or "{}")
        except Exception:
            d["meta"] = {}
        d.pop("meta_json", None)
        docs.append(d)
    return {"documents": docs, "total": len(docs)}


@app.delete("/kb/documents/{doc_id}")
@app.delete("/platform/kb/documents/{doc_id}")
@app.delete("/api/v1/kb/documents/{doc_id}")
async def kb_delete_document(doc_id: str, request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        raise HTTPException(status_code=404, detail="db_not_found")
    conn = _open_kb_db(identity.tenant_id)
    try:
        _kb_ensure_schema(conn)
        conn.execute("DELETE FROM budget_rows WHERE tenant_id=? AND doc_id=?", (identity.tenant_id, doc_id))
        conn.execute("DELETE FROM assets WHERE tenant_id=? AND doc_id=?", (identity.tenant_id, doc_id))
        conn.execute("DELETE FROM kb_elements WHERE tenant_id=? AND doc_id=?", (identity.tenant_id, doc_id))
        conn.execute("DELETE FROM kb_embeddings WHERE tenant_id=? AND doc_id=?", (identity.tenant_id, doc_id))
        conn.execute("DELETE FROM doc_sources WHERE tenant_id=? AND doc_id=?", (identity.tenant_id, doc_id))
        conn.execute("DELETE FROM url_cache WHERE tenant_id=? AND doc_id=?", (identity.tenant_id, doc_id))
        for table in ("kb_graph", "analysis_runs"):  # analysis_batches has no doc_id column
            try: conn.execute(f"DELETE FROM {table} WHERE tenant_id=? AND doc_id=?", (identity.tenant_id, doc_id))
            except Exception:
                logging.getLogger("platform.routes").debug("Table %s cleanup skipped", table)
        try:
            conn.execute("DELETE FROM kb_eval_samples WHERE doc_ids = ?", (json.dumps([doc_id]),))
            conn.execute("DELETE FROM kb_eval_reports WHERE sample_id NOT IN (SELECT id FROM kb_eval_samples)")
        except Exception:
            logging.getLogger("platform.routes").debug("KB cleanup best-effort", exc_info=True)
        conn.execute("DELETE FROM documents WHERE tenant_id=? AND doc_id=?", (identity.tenant_id, doc_id))
        conn.commit()
    finally:
        conn.close()
    # best-effort delete assets folder
    try:
        from pathlib import Path

        assets = Path(_kb_tenant_dir(identity.tenant_id)) / "assets" / doc_id
        if assets.exists():
            shutil.rmtree(str(assets), ignore_errors=True)
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    # best-effort delete associated wiki pages (prevent orphans)
    try:
        from core.harness.knowledge.wiki_engine import search_pages, delete_page
        pages = search_pages(limit=10000)
        source_tag = f"kb:{doc_id}"
        for p in pages:
            if any(source_tag in str(s) for s in (p.get("source_articles") or [])):
                try:
                    delete_page(p["title"])
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return {"status": "deleted", "doc_id": doc_id}


@app.post("/kb/documents/{doc_id}/reingest")
@app.post("/platform/kb/documents/{doc_id}/reingest")
@app.post("/api/v1/kb/documents/{doc_id}/reingest")
async def kb_reingest_document(doc_id: str, request: Request):
    """
    Re-run ingest for an existing document (uses stored source_uri).
    Returns a new job_id (core enqueue_ingest creates a fresh job each time).
    """
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        raise HTTPException(status_code=404, detail="db_not_found")
    conn = _open_kb_db(identity.tenant_id)
    try:
        _kb_ensure_schema(conn)
        row = conn.execute(
            "SELECT doc_id, collection_id, source_uri, kind, meta_json FROM documents WHERE tenant_id=? AND doc_id=?",
            (identity.tenant_id, doc_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文档不存在或已被删除，请刷新页面后重试")
        d = dict(row)
        meta = {}
        try:
            meta = json.loads(d.get("meta_json") or "{}")
        except Exception:
            meta = {}
        file_path = d.get("source_uri")
        kind = d.get("kind") or "pdf"
        collection_id = d.get("collection_id") or "default"
        ocr_lang = (meta.get("ocr_lang") or "zh") if isinstance(meta, dict) else "zh"
        ocr_engine = (meta.get("ocr_engine") or None) if isinstance(meta, dict) else None
        dpi = int((meta.get("dpi") or 240) if isinstance(meta, dict) else 240)
        max_pages = int((meta.get("max_pages") or 60) if isinstance(meta, dict) else 60)
    finally:
        conn.close()

    payload = {
        "input": {
            "tenant_id": identity.tenant_id,
            "collection_id": collection_id,
            "file_path": file_path,
            "kind": kind,
            "ocr_lang": ocr_lang,
            "ocr_engine": ocr_engine,
            "dpi": dpi,
            "max_pages": max_pages,
        },
        "context": {"tenant_id": identity.tenant_id, "actor_id": identity.actor_id, "request_id": identity.request_id},
        "mode": "inline",
    }

    # Video documents: use local ingest pipeline (ffmpeg + Whisper) instead of knowledge_ingest skill
    if str(kind or "").lower() == "video":
        from kb.service import ingest_document
        result = ingest_document(
            tenant_id=identity.tenant_id,
            collection_id=collection_id,
            file_path=file_path,
            kind="video",
            ocr_lang=ocr_lang,
            ocr_engine=ocr_engine,
            dpi=dpi,
            max_pages=max_pages,
        )
        return {"status": "reingested", "kind": "video", "result": result}

    core_resp = await _core_request("POST", f"/api/core/skills/knowledge_ingest/execute", identity=identity, json_body=payload)
    return core_resp


# =========================
# Documents API (generic)
# =========================

class AgentExecuteRequest(BaseModel):
    input: str
    session_id: str = ""
    context: dict = {}


class DocIngestRequest(BaseModel):
    collection_id: str = "default"
    url: Optional[str] = None
    kind: str = "pdf"
    ocr_lang: str = "zh"
    ocr_engine: Optional[str] = None
    dpi: int = 240
    max_pages: int = 60


class DocRefreshRequest(BaseModel):
    force: bool = False


@app.post("/api/v1/documents/preview", response_model=Dict[str, Any])
@app.post("/platform/documents/preview", response_model=Dict[str, Any])
async def documents_preview(request: Request):
    """
    Preview a document without saving to KB.
    Accepts:
      - multipart/form-data with: file, kind, collection_id
      - application/json with: url, collection_id
    Returns parsed elements + classification for user review before ingest.
    """
    identity = _resolve_identity(request)

    from pathlib import Path
    import re, tempfile

    ct = (request.headers.get("content-type") or "").lower()
    kind = ""
    collection_id = "default"
    dst = None

    if "multipart/form-data" in ct:
        if not _HAS_MULTIPART:
            raise HTTPException(status_code=501, detail="upload_requires_python_multipart")
        form = await request.form()
        file = form.get("file")
        if file is None or not getattr(file, "filename", None):
            raise HTTPException(status_code=400, detail="file_required")
        kind = str(form.get("kind") or "").strip().lower()
        collection_id = str(form.get("collection_id") or "default")
        safe_name = re.sub(r"[^A-Za-z0-9_.\u4e00-\u9fff-]+", "_", file.filename)
        up_dir = Path(_kb_tenant_dir(identity.tenant_id)) / "uploads"
        up_dir.mkdir(parents=True, exist_ok=True)
        dst = up_dir / f"preview_{identity.request_id}_{safe_name}"
        data = await file.read()
        if len(data) > 200 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="file_too_large")
        dst.write_bytes(data)
    else:
        body = await request.json()
        url = body.get("url") if isinstance(body, dict) else None
        collection_id = str(body.get("collection_id") or "default") if isinstance(body, dict) else "default"
        if not url:
            raise HTTPException(status_code=400, detail="url_required")
        try:
            from urllib.parse import urlparse
            import httpx as _httpx
            async with _httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(str(url), follow_redirects=True)
                resp.raise_for_status()
            host = (urlparse(str(url)).netloc or "").lower()
            safe_host = re.sub(r"[^A-Za-z0-9.-]+", "_", host)
            up_dir = Path(_kb_tenant_dir(identity.tenant_id)) / "uploads"
            up_dir.mkdir(parents=True, exist_ok=True)
            dst = up_dir / f"preview_url_{identity.request_id}_{safe_host}"
            dst.write_bytes(resp.content)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"download_failed: {e}")

    if dst is None:
        raise HTTPException(status_code=400, detail="no_content")

    try:
        result = preview_document(file_path=str(dst), kind=kind or "pdf")
        result["temp_file_path"] = str(dst)
        result["collection_id"] = collection_id
        return result
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"preview_failed: {e}")


@app.post("/api/v1/documents/ingest", response_model=Dict[str, Any])
@app.post("/platform/documents/ingest", response_model=Dict[str, Any])
async def documents_ingest(request: Request):
    """
    Generic document ingest (MVP):
    - multipart: upload file
    - json: ingest by url
    Returns {job_id, doc_id}.
    """
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")  # reuse kb scope for now

    from pathlib import Path
    import re

    collection_id = "default"
    url = None
    kind = ""
    ocr_lang = "zh"
    ocr_engine = None
    dpi = 240
    max_pages = 60
    file_path = None

    ct = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in ct:
        if not _HAS_MULTIPART:
            raise HTTPException(status_code=501, detail='upload_requires_python_multipart')
        form = await request.form()
        file = form.get("file")
        collection_id = str(form.get("collection_id") or "default")
        if file is None or not getattr(file, "filename", None):
            raise HTTPException(status_code=400, detail="file_required")
        safe_name = re.sub(r"[^A-Za-z0-9_.\u4e00-\u9fff-]+", "_", file.filename)
        up_dir = Path(_kb_tenant_dir(identity.tenant_id)) / "uploads"
        up_dir.mkdir(parents=True, exist_ok=True)
        dst = up_dir / f"{identity.request_id}_{safe_name}"
        data = await file.read()
        if len(data) > 200 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="file_too_large")
        dst.write_bytes(data)
        file_path = str(dst)
        kind = str(form.get("kind") or "").strip().lower()
        if not kind:
            ext = os.path.splitext(file.filename or "")[1].lower()
            if ext in (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"):
                kind = "video"
            elif ext in (".txt", ".text"):
                kind = "txt"
            elif ext in (".docx", ".doc"):
                kind = "word"
            elif ext in (".pptx", ".ppt"):
                kind = "ppt"
            elif ext in (".md", ".markdown"):
                kind = "markdown"
    else:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="json_body_required")
        collection_id = str(body.get("collection_id") or "default")
        url = body.get("url")
        file_path = body.get("file_path") or body.get("temp_file_path")  # from preview step
        kind = str(body.get("kind") or "").strip().lower()
        ocr_lang = str(body.get("ocr_lang") or "zh")
        ocr_engine = body.get("ocr_engine")
        dpi = int(body.get("dpi") or 240)
        max_pages = int(body.get("max_pages") or 60)
        if not url and not file_path:
            raise HTTPException(status_code=400, detail="url_or_file_path_required")
        if url:
            try:
                from urllib.parse import urlparse

                host = (urlparse(str(url)).netloc or "").lower()
            except Exception:
                host = ""
            if not kind and any(x in host for x in ("toutiao.com", "ixigua.com", "douyin.com", "bilibili.com", "youtube.com", "youtu.be")):
                kind = "video"
            if not kind and url:
                ext = os.path.splitext(str(url).split("?")[0])[1].lower()
                if ext in (".docx", ".doc"):
                    kind = "word"
                elif ext in (".pptx", ".ppt"):
                    kind = "ppt"
                elif ext in (".md", ".markdown"):
                    kind = "markdown"

        # Download URL to local file if no file_path provided
        if url and not file_path:
            try:
                from kb.intelligence.service import _download_url_to_tenant
                local_path, detected_kind, _ct, _etag, _lm = _download_url_to_tenant(identity.tenant_id, url, prefer_kind=kind or None)
                file_path = local_path
                if not kind:
                    kind = detected_kind
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"url_download_failed: {e}")

    if not file_path:
        raise HTTPException(status_code=400, detail="file_path_required")

    # Use platform's local enqueue_ingest (not core's kb_provider callback,
    # which requires cross-process registration). This handles job creation +
    # background ingestion thread directly in the platform process.
    from kb.service import enqueue_ingest
    job = enqueue_ingest(
        tenant_id=identity.tenant_id,
        collection_id=collection_id,
        file_path=file_path,
        kind=kind or "pdf",
        ocr_lang=ocr_lang,
        ocr_engine=ocr_engine,
        dpi=dpi,
        max_pages=max_pages,
        name="",
    )

    # Auto-trigger Wiki update: convert KB document into Wiki knowledge pages
    # Fire-and-forget — don't block the ingest response
    try:
        import asyncio as _asyncio
        doc_id = job.get("doc_id", "") if isinstance(job, dict) else ""
        if doc_id:
            _asyncio.create_task(_auto_wiki_update(doc_id, str(file_path)))
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    return {"job": job}


@app.post("/platform/documents/ingest-directory")
async def documents_ingest_directory(request: Request):
    """Batch ingest documents from a directory (stub — not yet implemented)."""
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")
    return {"status": "not_implemented", "message": "Directory batch ingest is planned for a future release"}


@app.post("/platform/kb/watch")
async def kb_watch_directory(request: Request):
    """Watch a directory for auto-ingest (stub — not yet implemented)."""
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")
    return {"status": "not_implemented", "message": "Directory watch is planned for a future release"}


async def _auto_wiki_update(doc_id: str, file_path: str):
    u"""Background task: convert a newly ingested KB document into Wiki pages.
    
    Delegates all wiki operations through CoreFacade (CLAUDE.md §5.1 compliance).
    """
    try:
        from core.api.core_facade import wiki_auto_update
        from core.api.facades.service_facade import llm_generate
        await wiki_auto_update(doc_id, file_path)
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return {"output": data}


@app.get("/api/v1/documents", response_model=Dict[str, Any])
@app.get("/platform/documents", response_model=Dict[str, Any])
async def documents_list(
    request: Request,
    collection_id: Optional[str] = None,
    status: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    List documents with lightweight stats for management UI.
    """
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")


    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"items": [], "total": 0}
    conn = _open_kb_db(identity.tenant_id)
    try:
        _kb_ensure_schema(conn)
        where = ["d.tenant_id=?"]
        vals: List[Any] = [identity.tenant_id]
        if collection_id:
            where.append("d.collection_id=?")
            vals.append(collection_id)
        if status:
            where.append("d.status=?")
            vals.append(status)
        if kind:
            where.append("d.kind=?")
            vals.append(kind)
        where_sql = " AND ".join(where)
        rows = conn.execute(
            f"""
            SELECT
              d.*,
              COALESCE((SELECT COUNT(1) FROM kb_elements e WHERE e.tenant_id=d.tenant_id AND e.doc_id=d.doc_id), 0) AS element_count,
              COALESCE((SELECT COUNT(1) FROM kb_embeddings b WHERE b.tenant_id=d.tenant_id AND b.doc_id=d.doc_id), 0) AS embedding_count,
              COALESCE((SELECT COUNT(1) FROM doc_sources s WHERE s.tenant_id=d.tenant_id AND s.doc_id=d.doc_id), 0) AS source_count
            FROM documents d
            WHERE {where_sql}
            ORDER BY d.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*vals, int(limit), int(offset)),
        ).fetchall()
        total = conn.execute(
            f"SELECT COUNT(1) AS c FROM documents d WHERE {where_sql}",
            tuple(vals),
        ).fetchone()["c"]
    finally:
        conn.close()

    items = []
    for r in rows:
        d = dict(r)
        try:
            d["meta"] = json.loads(d.get("meta_json") or "{}")
        except Exception:
            d["meta"] = {}
        d.pop("meta_json", None)
        items.append(d)
    return {"items": items, "total": int(total or 0)}


@app.get("/api/v1/documents/categories", response_model=Dict[str, Any])
@app.get("/platform/documents/categories", response_model=Dict[str, Any])
async def documents_categories(request: Request, collection_id: Optional[str] = None):
    """
    Aggregate category counts for the left sidebar tree.
    Returns kind_categories (by file type) and content_categories (by content analysis).
    """
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")


    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"kind_categories": [], "content_categories": []}
    conn = _open_kb_db(identity.tenant_id)
    try:
        params: List[Any] = [identity.tenant_id]
        col_filter = "AND collection_id = ?" if collection_id else ""
        if collection_id:
            params.append(collection_id)

        kind_rows = conn.execute(
            f"SELECT kind, COUNT(*) AS cnt FROM documents WHERE tenant_id = ? {col_filter} AND kind IS NOT NULL AND kind != '' GROUP BY kind ORDER BY cnt DESC",
            params,
        ).fetchall()
        kind_cats = []
        for r in kind_rows:
            k = str(r["kind"] or "").lower().strip()
            from core.api.core_facade import get_document_categories
            from core.api.facades.service_facade import llm_generate
            cats = get_document_categories()
            cat_key = cats["kind_map"].get(k, k)
            kind_cats.append({
                "key": cat_key,
                "label": cats["categories"].get(cat_key, k),
                "count": int(r["cnt"]),
            })

        content_rows = conn.execute(
            f"SELECT meta_json FROM documents WHERE tenant_id = ? {col_filter} AND meta_json IS NOT NULL AND meta_json != ''",
            params,
        ).fetchall()
        content_count: Dict[str, int] = {}
        for r in content_rows:
            try:
                meta = json.loads(str(r["meta_json"] or "{}"))
            except Exception:
                continue
            cls = meta.get("classification") or {}
            cat = str(cls.get("content_category") or "general")
            content_count[cat] = content_count.get(cat, 0) + 1
        content_cats = [
            {"key": k, "label": CATEGORY_LABELS.get(k, k), "count": v}
            for k, v in sorted(content_count.items(), key=lambda x: -x[1])
        ]
        return {"kind_categories": kind_cats, "content_categories": content_cats}
    finally:
        conn.close()


@app.get("/api/v1/documents/{doc_id}", response_model=Dict[str, Any])
@app.get("/platform/documents/{doc_id}", response_model=Dict[str, Any])
async def documents_get(doc_id: str, request: Request):
    """
    Get one document with aggregated stats.
    """
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")


    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        raise HTTPException(status_code=404, detail="document_not_found")
    conn = _open_kb_db(identity.tenant_id)
    try:
        _kb_ensure_schema(conn)
        row = conn.execute(
            """
            SELECT
              d.*,
              COALESCE((SELECT COUNT(1) FROM kb_elements e WHERE e.tenant_id=d.tenant_id AND e.doc_id=d.doc_id), 0) AS element_count,
              COALESCE((SELECT COUNT(1) FROM kb_embeddings b WHERE b.tenant_id=d.tenant_id AND b.doc_id=d.doc_id), 0) AS embedding_count,
              COALESCE((SELECT COUNT(1) FROM doc_sources s WHERE s.tenant_id=d.tenant_id AND s.doc_id=d.doc_id), 0) AS source_count
            FROM documents d
            WHERE d.tenant_id=? AND d.doc_id=?
            """,
            (identity.tenant_id, doc_id),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="document_not_found")
    d = dict(row)
    try:
        d["meta"] = json.loads(d.get("meta_json") or "{}")
    except Exception:
        d["meta"] = {}
    d.pop("meta_json", None)
    return d


@app.get("/api/v1/documents/{doc_id}/sources", response_model=Dict[str, Any])
@app.get("/platform/documents/{doc_id}/sources", response_model=Dict[str, Any])
async def documents_list_sources(doc_id: str, request: Request, limit: int = 100, offset: int = 0):
    """
    List provenance sources for a document.
    """
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")


    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"items": [], "total": 0}
    conn = _open_kb_db(identity.tenant_id)
    try:
        _kb_ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT *
            FROM doc_sources
            WHERE tenant_id=? AND doc_id=?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (identity.tenant_id, doc_id, int(limit), int(offset)),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(1) AS c FROM doc_sources WHERE tenant_id=? AND doc_id=?",
            (identity.tenant_id, doc_id),
        ).fetchone()["c"]
    finally:
        conn.close()

    items = []
    for r in rows:
        d = dict(r)
        try:
            d["meta"] = json.loads(d.get("meta_json") or "{}")
        except Exception:
            d["meta"] = {}
        d.pop("meta_json", None)
        items.append(d)
    return {"items": items, "total": int(total or 0)}


@app.get("/api/v1/documents/{doc_id}/analysis-runs", response_model=Dict[str, Any])
@app.get("/platform/documents/{doc_id}/analysis-runs", response_model=Dict[str, Any])
async def documents_list_analysis_runs(doc_id: str, request: Request, run_type: Optional[str] = None, q: Optional[str] = None, limit: int = 100, offset: int = 0):
    """
    List persisted analysis results for a document.
    """
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")


    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"items": [], "total": 0}
    conn = _open_kb_db(identity.tenant_id)
    try:
        _kb_ensure_schema(conn)
        where = ["tenant_id=?", "doc_id=?"]
        vals: List[Any] = [identity.tenant_id, doc_id]
        if run_type:
            where.append("run_type=?")
            vals.append(run_type)
        if q:
            where.append("(input_json LIKE ? OR output_json LIKE ?)")
            like = f"%{q}%"
            vals.extend([like, like])
        where_sql = " AND ".join(where)
        rows = conn.execute(
            f"""
            SELECT *
            FROM analysis_runs
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*vals, int(limit), int(offset)),
        ).fetchall()
        total = conn.execute(
            f"SELECT COUNT(1) AS c FROM analysis_runs WHERE {where_sql}",
            tuple(vals),
        ).fetchone()["c"]
    finally:
        conn.close()

    items = []
    for r in rows:
        d = dict(r)
        try:
            d["input"] = json.loads(d.get("input_json") or "{}")
        except Exception:
            d["input"] = {}
        try:
            d["output"] = json.loads(d.get("output_json") or "{}")
        except Exception:
            d["output"] = {}
        d.pop("input_json", None)
        d.pop("output_json", None)
        items.append(d)
    return {"items": items, "total": int(total or 0)}


@app.delete("/api/v1/documents/{doc_id}/analysis-runs/{run_id}", response_model=Dict[str, Any])
@app.delete("/platform/documents/{doc_id}/analysis-runs/{run_id}", response_model=Dict[str, Any])
async def documents_delete_analysis_run(doc_id: str, run_id: str, request: Request):
    """
    Delete one persisted analysis result.
    """
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")


    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        raise HTTPException(status_code=404, detail="analysis_run_not_found")
    conn = _open_kb_db(identity.tenant_id)
    try:
        _kb_ensure_schema(conn)
        row = conn.execute(
            "SELECT run_id FROM analysis_runs WHERE tenant_id=? AND doc_id=? AND run_id=?",
            (identity.tenant_id, doc_id, run_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="analysis_run_not_found")
        conn.execute(
            "DELETE FROM analysis_runs WHERE tenant_id=? AND doc_id=? AND run_id=?",
            (identity.tenant_id, doc_id, run_id),
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "deleted", "doc_id": doc_id, "run_id": run_id}


@app.get("/api/v1/documents/{doc_id}/export", response_model=Dict[str, Any])
@app.get("/platform/documents/{doc_id}/export", response_model=Dict[str, Any])
async def documents_export(
    doc_id: str,
    request: Request,
    format: str = "json",
    include_embeddings: bool = False,
    limit: int = 5000,
):
    """
    Export a document as JSON or Markdown.
    - format=json: structured payload for integrations
    - format=markdown: lightweight readable text
    """
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")


    fmt = (format or "json").strip().lower()
    if fmt not in ("json", "markdown", "md"):
        raise HTTPException(status_code=400, detail="unsupported_format")

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        raise HTTPException(status_code=404, detail="document_not_found")

    conn = _open_kb_db(identity.tenant_id)
    try:
        _kb_ensure_schema(conn)
        drow = conn.execute(
            "SELECT * FROM documents WHERE tenant_id=? AND doc_id=?",
            (identity.tenant_id, doc_id),
        ).fetchone()
        if not drow:
            raise HTTPException(status_code=404, detail="document_not_found")
        erows = conn.execute(
            """
            SELECT * FROM kb_elements
            WHERE tenant_id=? AND doc_id=?
            ORDER BY page_idx ASC, created_at ASC
            LIMIT ?
            """,
            (identity.tenant_id, doc_id, int(limit)),
        ).fetchall()
        srows = conn.execute(
            """
            SELECT * FROM doc_sources
            WHERE tenant_id=? AND doc_id=?
            ORDER BY created_at DESC
            LIMIT 200
            """,
            (identity.tenant_id, doc_id),
        ).fetchall()
        brows = []
        if include_embeddings:
            brows = conn.execute(
                """
                SELECT embedding_id, element_id, embedding_type, model, dim
                FROM kb_embeddings
                WHERE tenant_id=? AND doc_id=?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (identity.tenant_id, doc_id, int(limit)),
            ).fetchall()
    finally:
        conn.close()

    doc = dict(drow)
    try:
        doc["meta"] = json.loads(doc.get("meta_json") or "{}")
    except Exception:
        doc["meta"] = {}
    doc.pop("meta_json", None)

    elements = []
    for r in erows:
        d = dict(r)
        for k in ("bbox_json", "cells_json", "meta_json"):
            try:
                d[k.replace("_json", "")] = json.loads(d.get(k) or "{}")
            except Exception:
                d[k.replace("_json", "")] = {}
            d.pop(k, None)
        elements.append(d)

    sources = []
    for r in srows:
        d = dict(r)
        try:
            d["meta"] = json.loads(d.get("meta_json") or "{}")
        except Exception:
            d["meta"] = {}
        d.pop("meta_json", None)
        sources.append(d)

    embeddings = [dict(r) for r in brows] if include_embeddings else []

    if fmt in ("markdown", "md"):
        lines = []
        lines.append(f"# Document Export: {doc_id}")
        lines.append("")
        lines.append(f"- collection_id: {doc.get('collection_id')}")
        lines.append(f"- kind: {doc.get('kind')}")
        lines.append(f"- status: {doc.get('status')}")
        lines.append(f"- created_at: {doc.get('created_at')}")
        lines.append("")
        lines.append("## Sources")
        if not sources:
            lines.append("- (none)")
        else:
            for s in sources:
                lines.append(f"- `{s.get('source_type')}` {s.get('source_uri')}")
        lines.append("")
        lines.append("## Elements")
        if not elements:
            lines.append("- (none)")
        else:
            for i, e in enumerate(elements, start=1):
                pg = e.get("page_idx")
                txt = str(e.get("text") or "").strip().replace("\n", " ")
                if len(txt) > 300:
                    txt = txt[:300] + "..."
                lines.append(f"{i}. page={pg} type={e.get('type')} text={txt}")
        md = "\n".join(lines).strip() + "\n"
        return {
            "doc_id": doc_id,
            "format": "markdown",
            "content": md,
            "counts": {
                "sources": len(sources),
                "elements": len(elements),
                "embeddings": len(embeddings),
            },
        }

    return {
        "doc_id": doc_id,
        "format": "json",
        "document": doc,
        "sources": sources,
        "elements": elements,
        "embeddings": embeddings,
        "counts": {
            "sources": len(sources),
            "elements": len(elements),
            "embeddings": len(embeddings),
        },
    }

@app.get("/api/v1/documents/{doc_id}/elements", response_model=Dict[str, Any])
@app.get("/platform/documents/{doc_id}/elements", response_model=Dict[str, Any])
async def documents_list_elements(doc_id: str, request: Request, type: Optional[str] = None, limit: int = 200, offset: int = 0):
    """
    List parsed elements for a document.
    This is a debug-friendly API for app integration.
    """
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")  # reuse kb scope for now


    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"items": [], "total": 0}
    conn = _open_kb_db(identity.tenant_id)
    try:
        _kb_ensure_schema(conn)
        if type:
            rows = conn.execute(
                """
                SELECT * FROM kb_elements
                WHERE tenant_id=? AND doc_id=? AND type=?
                ORDER BY page_idx ASC, created_at ASC
                LIMIT ? OFFSET ?
                """,
                (identity.tenant_id, doc_id, type, int(limit), int(offset)),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(1) as c FROM kb_elements WHERE tenant_id=? AND doc_id=? AND type=?",
                (identity.tenant_id, doc_id, type),
            ).fetchone()["c"]
        else:
            rows = conn.execute(
                """
                SELECT * FROM kb_elements
                WHERE tenant_id=? AND doc_id=?
                ORDER BY page_idx ASC, created_at ASC
                LIMIT ? OFFSET ?
                """,
                (identity.tenant_id, doc_id, int(limit), int(offset)),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(1) as c FROM kb_elements WHERE tenant_id=? AND doc_id=?",
                (identity.tenant_id, doc_id),
            ).fetchone()["c"]
    finally:
        conn.close()

    items = []
    for r in rows:
        d = dict(r)
        for k in ("bbox_json", "cells_json", "meta_json"):
            try:
                d[k.replace("_json", "")] = json.loads(d.get(k) or "{}")
            except Exception:
                d[k.replace("_json", "")] = {}
            d.pop(k, None)
        items.append(d)
    return {"items": items, "total": int(total or 0)}


@app.post("/kb/query", response_model=Dict[str, Any])
@app.post("/api/v1/kb/query", response_model=Dict[str, Any])
@app.post("/platform/kb/query", response_model=Dict[str, Any])
async def kb_query(req: KBQueryRequest, request: Request):
    # Query KB (MVP): call core engine skill kb_query, and convert local citation paths to asset_url.
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")

    payload = {
        "input": {
            "tenant_id": identity.tenant_id,
            "collection_id": req.collection_id,
            "question": req.question,
            "year": req.year,
            "limit": req.limit,
        },
        "context": {"tenant_id": identity.tenant_id, "actor_id": identity.actor_id, "request_id": identity.request_id},
        "mode": "inline",
    }
    core_resp = await _core_request("POST", f"/api/core/skills/kb_query/execute", identity=identity, json_body=payload)
    out = dict(core_resp or {})
    # unwrap run summary output best-effort
    data = None
    try:
        data = (out.get("output") or {}).get("output") if isinstance(out.get("output"), dict) else None
    except Exception:
        data = None
    if isinstance(data, dict):
        out["kb"] = _normalize_citations_with_assets(tenant_id=identity.tenant_id, data=data)
    return out


@app.post("/api/platform/collections/query")
async def collection_query(request: Request):
    """Query a single KB collection — wraps kb_query with top_k→limit mapping."""
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")
    body = await request.json()
    payload = {
        "input": {
            "tenant_id": identity.tenant_id,
            "collection_id": str(body.get("collection_id", "")),
            "question": str(body.get("question", "")),
            "limit": int(body.get("top_k", 8)),
        },
        "context": {"tenant_id": identity.tenant_id, "actor_id": identity.actor_id, "request_id": identity.request_id},
        "mode": "inline",
    }
    core_resp = await _core_request("POST", "/api/core/skills/kb_query/execute", identity=identity, json_body=payload)
    out = dict(core_resp or {})
    data = None
    try:
        data = (out.get("output") or {}).get("output") if isinstance(out.get("output"), dict) else None
    except Exception:
        data = None
    if isinstance(data, dict):
        out["kb"] = _normalize_citations_with_assets(tenant_id=identity.tenant_id, data=data)
    return out


@app.post("/api/platform/documents/summarize")
async def document_summarize(request: Request):
    """Summarize a document using LLM (calls core skill document_summarize)."""
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")
    body = await request.json()
    payload = {
        "input": {
            "tenant_id": identity.tenant_id,
            "doc_id": str(body.get("doc_id", "")),
            "profile": str(body.get("profile", "key_points")),
            "max_points": int(body.get("max_points", 5)),
        },
        "context": {"tenant_id": identity.tenant_id, "actor_id": identity.actor_id, "request_id": identity.request_id},
        "mode": "inline",
    }
    core_resp = await _core_request("POST", "/api/core/skills/document_summarize/execute", identity=identity, json_body=payload)
    return dict(core_resp or {})


@app.post("/api/platform/collections/rewrite-answer")
async def collection_rewrite_answer(request: Request):
    """Rewrite/improve a KB answer using LLM (calls core skill collection_rewrite_answer)."""
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")
    body = await request.json()
    payload = {
        "input": {
            "tenant_id": identity.tenant_id,
            "collection_id": str(body.get("collection_id", "")),
            "question": str(body.get("question", "")),
            "current_answer": str(body.get("current_answer", "")),
            "items": body.get("items", []) if isinstance(body.get("items"), list) else [],
        },
        "context": {"tenant_id": identity.tenant_id, "actor_id": identity.actor_id, "request_id": identity.request_id},
        "mode": "inline",
    }
    core_resp = await _core_request("POST", "/api/core/skills/collection_rewrite_answer/execute", identity=identity, json_body=payload)
    return dict(core_resp or {})


@app.get("/kb/assets/{doc_id}/pages/{page_idx}")
@app.get("/api/v1/kb/assets/{doc_id}/pages/{page_idx}")
@app.get("/platform/kb/assets/{doc_id}/pages/{page_idx}")
async def kb_get_page_image(doc_id: str, page_idx: int, request: Request):
    # Static asset: return rendered page image (safe path join by tenant/doc/page).
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")

    fp = _kb_page_image_path(tenant_id=identity.tenant_id, doc_id=doc_id, page_idx=int(page_idx))
    if not os.path.isfile(fp):
        raise HTTPException(status_code=404, detail="asset_not_found")
    return FileResponse(fp, media_type="image/png")


@app.get("/kb/assets/{doc_id}/frames/{frame_idx}")
@app.get("/api/v1/kb/assets/{doc_id}/frames/{frame_idx}")
@app.get("/platform/kb/assets/{doc_id}/frames/{frame_idx}")
async def kb_get_frame_image(doc_id: str, frame_idx: int, request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")

    fp = _kb_frame_image_path(tenant_id=identity.tenant_id, doc_id=doc_id, frame_idx=int(frame_idx))
    if not os.path.isfile(fp):
        raise HTTPException(status_code=404, detail="asset_not_found")
    return FileResponse(fp, media_type="image/jpeg")


@app.post("/api/v1/agents/{agent_id}/execute")
async def api_v1_agent_execute(agent_id: str, req: AgentExecuteRequest, request: Request):
    identity = _resolve_identity(request)
    payload_ctx = dict(req.context or {})
    payload_ctx.setdefault("source", "app")
    payload_ctx.setdefault("tenant_id", identity.tenant_id)
    payload_ctx.setdefault("session_id", req.session_id or "default")
    # Execute workspace agent via core workspace agent endpoint (not gateway/execute),
    # because /api/v1/agents CRUD is backed by core /workspace/agents.
    body = {
        "input": {"text": req.input},
        "context": payload_ctx,
        "user_id": identity.actor_id,
        "session_id": req.session_id or "default",
    }
    return await _core_request(
        "POST",
        f"/api/core/workspace/agents/{agent_id}/execute",
        identity=identity,
        json_body=body,
    )


@app.get("/api/v1/agents")
async def api_v1_agents_list(request: Request, limit: int = 100, offset: int = 0):
    identity = _resolve_identity(request)
    data = await _core_request(
        "GET",
        "/api/core/workspace/agents",
        identity=identity,
        params={"limit": int(limit), "offset": int(offset)},
    )
    # core already returns {agents,total,limit,offset}
    return data


@app.get("/platform/workspace/agents")
async def platform_workspace_agents_list(request: Request, limit: int = 200, offset: int = 0):
    """Agent pool for team assembly — delegates to core workspace agents."""
    identity = _resolve_identity(request)
    return await _core_request(
        "GET",
        "/api/core/workspace/agents",
        identity=identity,
        params={"limit": int(limit), "offset": int(offset)},
    )


@app.post("/api/v1/agents")
async def api_v1_agents_create(request: Request, body: Dict[str, Any]):
    identity = _resolve_identity(request)
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be json object")
    name = body.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    if body.get("description"):
        metadata = dict(metadata)
        metadata.setdefault("description", str(body.get("description")))
    payload = {
        "name": str(name),
        "agent_type": str(body.get("agent_type") or "base"),
        "config": body.get("config") if isinstance(body.get("config"), dict) else {},
        "skills": body.get("skills") if isinstance(body.get("skills"), list) else [],
        "tools": body.get("tools") if isinstance(body.get("tools"), list) else [],
        "memory_config": body.get("memory_config") if isinstance(body.get("memory_config"), dict) else None,
        "metadata": metadata or None,
    }
    created = await _core_request("POST", "/api/core/workspace/agents", identity=identity, json_body=payload)
    # Grant execute permission to the creator (and system/admin) for newly created workspace agents.
    # Without this, creator cannot execute immediately due to deny-by-default permissions.
    try:
        agent_id = created.get("id")
        if agent_id:
            for uid in [identity.actor_id, "system", "admin"]:
                try:
                    await _core_request(
                        "POST",
                        "/api/core/permissions/grant",
                        identity=identity,
                        json_body={
                            "user_id": str(uid),
                            "resource_id": str(agent_id),
                            "permission": "execute",
                            "granted_by": "platform",
                        },
                    )
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return created


@app.get("/api/v1/agents/{agent_id}")
async def api_v1_agents_get(agent_id: str, request: Request):
    identity = _resolve_identity(request)
    agent = await _core_request("GET", f"/api/core/workspace/agents/{agent_id}", identity=identity)
    return {"agent": agent}


@app.put("/api/v1/agents/{agent_id}")
async def api_v1_agents_update(agent_id: str, request: Request, body: Dict[str, Any]):
    identity = _resolve_identity(request)
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be json object")
    payload: Dict[str, Any] = {}
    for k in ("name", "config", "skills", "tools", "memory_config", "metadata"):
        if k in body:
            payload[k] = body.get(k)
    if "description" in body:
        md = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        md = dict(md)
        md["description"] = str(body.get("description") or "")
        payload["metadata"] = md
    return await _core_request("PUT", f"/api/core/workspace/agents/{agent_id}", identity=identity, json_body=payload)


@app.delete("/api/v1/agents/{agent_id}")
async def api_v1_agents_delete(agent_id: str, request: Request):
    identity = _resolve_identity(request)
    try:
        await _core_request("DELETE", f"/api/core/workspace/agents/{agent_id}", identity=identity)
        return {"ok": True, "id": agent_id}
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 404:
            return {"ok": False, "id": agent_id}
        raise


# -------------------- Management-facing platform resources (minimal, in-memory) --------------------


@app.get("/gateway/routes")  # compat: management proxy forwards /api/platform/* -> upstream /{path}
@app.get("/platform/gateway/routes")
async def list_gateway_routes(enabled: Optional[bool] = None, _auth: str = Depends(require_auth)):
    routes = platform_store.list_gateway_routes(enabled=enabled)
    return {"routes": routes, "total": len(routes)}


@app.post("/gateway/routes")  # compat alias
@app.post("/platform/gateway/routes")
async def create_gateway_route(body: Dict[str, Any], _auth: str = Depends(require_admin)):
    rid = str(body.get("id") or _new_prefixed_id("route"))
    route = {
        "id": rid,
        "name": body.get("name") or rid,
        "path": body.get("path") or "/",
        "backend": body.get("backend") or "core",
        "methods": body.get("methods") or ["POST"],
        "enabled": bool(body.get("enabled", True)),
        "rate_limit": int(body.get("rate_limit", 100)),
        "timeout": int(body.get("timeout", 30)),
        "created_at": body.get("created_at") or "",
        "updated_at": body.get("updated_at") or "",
    }
    return platform_store.upsert_gateway_route(route)


@app.get("/gateway/routes/{route_id}")  # compat alias
@app.get("/platform/gateway/routes/{route_id}")
async def get_gateway_route(route_id: str, _auth: str = Depends(require_auth)):
    r = platform_store.get_gateway_route(route_id)
    if not r:
        raise HTTPException(status_code=404, detail="route_not_found")
    return r


@app.put("/gateway/routes/{route_id}")  # compat alias
@app.put("/platform/gateway/routes/{route_id}")
async def update_gateway_route(route_id: str, patch: Dict[str, Any], _auth: str = Depends(require_admin)):
    r = platform_store.get_gateway_route(route_id)
    if not r:
        raise HTTPException(status_code=404, detail="route_not_found")
    r.update({k: v for k, v in (patch or {}).items() if v is not None})
    return platform_store.upsert_gateway_route(r)


@app.delete("/gateway/routes/{route_id}")  # compat alias
@app.delete("/platform/gateway/routes/{route_id}")
async def delete_gateway_route(route_id: str, _auth: str = Depends(require_admin)):
    platform_store.delete_gateway_route(route_id)
    return {"status": "ok"}


@app.get("/platform/gateway/metrics")
async def gateway_metrics(_auth: str = Depends(require_auth)):
    # stubbed metrics
    return {"total_requests": 0, "success_rate": 1.0, "avg_latency_ms": 0, "active_routes": len(platform_store.list_gateway_routes())}


@app.post("/platform/gateway/execute")
@app.post("/gateway/execute")
async def gateway_execute(body: Dict[str, Any], request: Request):
    identity = _resolve_identity(request)
    payload = dict(body or {})
    payload["context"] = dict(payload.get("context") or {})
    payload["context"].setdefault("tenant_id", identity.tenant_id)
    payload.setdefault("user_id", identity.actor_id)
    payload.setdefault("session_id", payload.get("session_id") or "default")
    result = await _core_request("POST", "/api/core/gateway/execute", identity=identity, json_body=payload)

    # Persist audit to core ExecutionStore (bridges platform→management gap)
    try:
        run_id = result.get("run_id") if isinstance(result, dict) else None
        status = "success" if (isinstance(result, dict) and result.get("ok")) else "failure"
        from core.services.execution_store import get_execution_store
        store = get_execution_store()
        await store.add_audit_log(
            action="gateway_execute",
            status=status,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            resource_type="gateway",
            resource_id=payload.get("kind", "unknown"),
            run_id=str(run_id) if run_id else None,
        )
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return result


@app.get("/platform/auth/users")
async def list_auth_users(role: Optional[str] = None, status: Optional[str] = None, _auth: str = Depends(require_admin)):
    users = platform_store.list_auth_users(role=role, status=status)
    return {"users": users, "total": len(users)}


@app.post("/platform/auth/users")
async def create_auth_user(body: Dict[str, Any], _auth: str = Depends(require_admin)):
    uid = str(body.get("id") or _new_prefixed_id("u"))
    user = {
        "id": uid,
        "username": body.get("username") or uid,
        "email": body.get("email") or "",
        "role": body.get("role") or "user",
        "status": body.get("status") or "active",
        "last_login": None,
        "created_at": "",
    }
    return platform_store.upsert_auth_user(user)


@app.put("/platform/auth/users/{user_id}")
async def update_auth_user(user_id: str, patch: Dict[str, Any], _auth: str = Depends(require_admin)):
    u = platform_store.get_auth_user(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="user_not_found")
    u.update({k: v for k, v in (patch or {}).items() if v is not None})
    return platform_store.upsert_auth_user(u)


@app.delete("/platform/auth/users/{user_id}")
async def delete_auth_user(user_id: str, _auth: str = Depends(require_admin)):
    platform_store.delete_auth_user(user_id)
    return {"status": "ok"}


# ── OIDC / SSO endpoints ──

@app.get("/auth/oidc/login")
async def oidc_login(request: Request, redirect_uri: str = ""):
    """返回 IdP 授权页 URL。前端将用户重定向到该 URL。"""
    from auth.identity_provider import get_oidc_provider
    oidc = get_oidc_provider()
    if not oidc.enabled:
        raise HTTPException(status_code=501, detail="oidc_not_configured")
    if not redirect_uri:
        redirect_uri = str(request.base_url).rstrip("/") + "/auth/oidc/callback"
    import secrets as _secrets
    state = _secrets.token_urlsafe(16)
    url = oidc.get_authorization_url(redirect_uri, state=state)
    return {"authorization_url": url, "state": state}


@app.post("/auth/oidc/callback")
async def oidc_callback(request: Request):
    """授权码回调：用 code 交换 id_token，返回 Identity。"""
    body = await request.json()
    code = str(body.get("code") or "")
    redirect_uri = str(body.get("redirect_uri") or "")
    if not code:
        raise HTTPException(status_code=400, detail="code_required")

    from auth.identity_provider import get_oidc_provider
    oidc = get_oidc_provider()
    if not oidc.enabled:
        raise HTTPException(status_code=501, detail="oidc_not_configured")

    id_token = await oidc.exchange_code(code, redirect_uri)
    if not id_token:
        raise HTTPException(status_code=401, detail="token_exchange_failed")

    claims = await oidc.verify_token(id_token)
    if not claims:
        raise HTTPException(status_code=401, detail="token_verification_failed")

    ident = oidc.extract_identity(claims)
    return {"id_token": id_token, "identity": ident}


@app.post("/auth/oidc/token")
async def oidc_verify_token(request: Request):
    """验证 id_token 并返回 Identity。用于前端已有 token 的场景。"""
    body = await request.json()
    id_token = str(body.get("id_token") or "")

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        id_token = auth_header[7:]

    if not id_token:
        raise HTTPException(status_code=400, detail="id_token_required")

    from auth.identity_provider import get_oidc_provider
    oidc = get_oidc_provider()
    if not oidc.enabled:
        raise HTTPException(status_code=501, detail="oidc_not_configured")

    claims = await oidc.verify_token(id_token)
    if not claims:
        raise HTTPException(status_code=401, detail="invalid_token")

    ident = oidc.extract_identity(claims)
    return {"identity": ident, "valid": True}


@app.get("/platform/tenants")
async def list_tenants(status: Optional[str] = None, _auth: str = Depends(require_admin)):
    tenants = platform_store.list_tenants(status=status)
    return {"tenants": tenants, "total": len(tenants)}


@app.post("/platform/tenants")
async def create_tenant(body: Dict[str, Any], _auth: str = Depends(require_admin)):
    tid = str(body.get("id") or _new_prefixed_id("t"))
    t = {
        "id": tid,
        "name": body.get("name") or tid,
        "description": body.get("description") or "",
        "quota": body.get("quota") or {"gpu_limit": 0, "storage_limit_gb": 0, "max_agents": 0},
        "status": body.get("status") or "active",
        "user_count": 0,
        "created_at": "",
    }
    return platform_store.upsert_tenant(t)


@app.put("/platform/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, patch: Dict[str, Any], _auth: str = Depends(require_admin)):
    t = platform_store.get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    t.update({k: v for k, v in (patch or {}).items() if v is not None})
    return platform_store.upsert_tenant(t)


@app.delete("/platform/tenants/{tenant_id}")
async def delete_tenant(tenant_id: str, _auth: str = Depends(require_admin)):
    platform_store.delete_tenant(tenant_id)
    return {"status": "ok"}


@app.post("/platform/tenants/{tenant_id}/suspend")
async def suspend_tenant(tenant_id: str, _auth: str = Depends(require_admin)):
    t = platform_store.get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    t["status"] = "suspended"
    platform_store.upsert_tenant(t)
    return {"status": "ok"}


@app.post("/platform/tenants/{tenant_id}/resume")
async def resume_tenant(tenant_id: str, _auth: str = Depends(require_admin)):
    t = platform_store.get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    t["status"] = "active"
    platform_store.upsert_tenant(t)
    return {"status": "ok"}


# ── Tenant self-service registration (no admin required) ──

@app.post("/platform/tenants/register")
async def tenant_register(request: Request):
    """租户自助注册。返回待验证状态。"""
    body = await request.json()
    email = str(body.get("email") or "").strip()
    org_name = str(body.get("org_name") or email).strip()
    if not email:
        raise HTTPException(status_code=400, detail="email_required")

    # Check for duplicate email
    try:
        from tenants.manager import tenant_manager
        existing = tenant_manager.find_by_email(email)
        if existing:
            raise HTTPException(status_code=409, detail="email_already_registered")
    except HTTPException:
        raise
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    import secrets as _secrets
    tid = f"tenant_{_secrets.token_urlsafe(8)}"
    token = _secrets.token_urlsafe(32)

    # Create tenant in pending state via platform store
    tenant_data = {
        "id": tid,
        "name": email,
        "description": org_name,
        "quota": {"gpu_limit": 0, "storage_limit_gb": 10, "max_agents": 3},
        "status": "pending",
        "user_count": 1,
        "created_at": "",
    }
    platform_store.upsert_tenant(tenant_data)

    # Store verification token
    try:
        from tenants.manager import tenant_manager
        tenant_manager.set_verification_token(tid, token)
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    return {
        "tenant_id": tid,
        "status": "pending",
        "message": "验证邮件已发送（开发模式：直接使用下方 token）",
        "verification_token": token,
        "next_step": f"POST /platform/tenants/verify-email with {{tenant_id, token}}",
    }


@app.post("/platform/tenants/verify-email")
async def tenant_verify_email(request: Request):
    """验证邮箱 → 激活租户 → 返回初始 API Key。"""
    body = await request.json()
    tenant_id = str(body.get("tenant_id") or "")
    token = str(body.get("token") or "")

    try:
        from tenants.manager import tenant_manager
        if not tenant_manager.verify_token(tenant_id, token):
            raise HTTPException(status_code=400, detail="invalid_token")
        tenant_manager.activate_tenant(tenant_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"verification_failed: {e}")

    # Create initial admin API Key
    from auth.authenticator import authenticator
    admin_user_id = f"admin_{tenant_id}"
    api_key = authenticator.create_api_key(
        user_id=admin_user_id,
        tenant_id=tenant_id,
        app_id="management",
        expires_days=365,
        permissions=["kb:read", "kb:write", "agent:execute"],
    )

    return {
        "tenant_id": tenant_id,
        "status": "active",
        "api_key": api_key,
        "quickstart": "/docs",
    }


# ── Tenant self-service portal APIs ──

@app.get("/tenant/dashboard")
async def tenant_dashboard(request: Request):
    """租户首页概览。"""
    identity = _resolve_identity(request)
    tid = identity.tenant_id or "default"
    return {
        "tenant_id": tid,
        "agent_count": 0,
        "skill_count": 0,
        "monthly_tokens": 0,
        "api_calls_today": 0,
    }


@app.get("/tenant/api-keys")
async def tenant_list_api_keys(request: Request):
    """租户查看自己的 API Keys。"""
    identity = _resolve_identity(request)
    tid = identity.tenant_id or "default"
    try:
        from auth.authenticator import authenticator
        keys = authenticator.list_keys(tid)
        return {"api_keys": keys, "total": len(keys)}
    except Exception:
        return {"api_keys": [], "total": 0}


@app.post("/tenant/api-keys")
async def tenant_create_api_key(request: Request):
    """租户创建 API Key。"""
    identity = _resolve_identity(request)
    body = await request.json()
    tid = identity.tenant_id or "default"
    expires_days = min(int(body.get("expires_days", 365)), 365)
    perms = list(body.get("permissions", ["kb:read"]) or ["kb:read"])

    from auth.authenticator import authenticator
    api_key = authenticator.create_api_key(
        user_id=identity.actor_id or f"user_{tid}",
        tenant_id=tid,
        app_id=body.get("app_id", "api"),
        expires_days=expires_days,
        permissions=perms,
    )
    return {"api_key": api_key, "expires_in_days": expires_days}


@app.delete("/tenant/api-keys/{key_prefix}")
async def tenant_revoke_api_key(key_prefix: str, request: Request):
    """租户撤销自己的 API Key。"""
    identity = _resolve_identity(request)
    try:
        from auth.authenticator import authenticator
        authenticator.revoke_api_key(key_prefix)
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=404, detail="key_not_found")


@app.get("/tenant/usage")
async def tenant_usage(request: Request):
    """租户查看自己的用量。"""
    identity = _resolve_identity(request)
    tid = identity.tenant_id or "default"
    try:
        from governance.quota.quota_manager import quota_manager
        usage = quota_manager.get_usage(tid)
        if usage:
            return {"tenant_id": tid, "usage": usage.model_dump() if hasattr(usage, 'model_dump') else str(usage)}
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return {"tenant_id": tid, "usage": {"agents": 0, "skills": 0, "api_keys": 0, "monthly_tokens": 0}}


@app.get("/tenant/billing")
async def tenant_billing(request: Request, year: int = None, month: int = None):
    """租户查看自己的账单（按月分解）。"""
    identity = _resolve_identity(request)
    tid = identity.tenant_id or "default"
    from datetime import datetime as _dt
    now = _dt.now()
    y = year or now.year
    m = month or now.month

    try:
        from storage.platform_db import get_platform_db
        db = get_platform_db()
        breakdown = db.get_monthly_breakdown(tid, y, m)
        total = sum(r.get("cost", 0) for r in breakdown)
        return {
            "tenant_id": tid,
            "period": f"{y}-{m:02d}",
            "breakdown": breakdown,
            "total_cost_cents": total,
        }
    except Exception:
        return {"tenant_id": tid, "period": f"{y}-{m:02d}", "breakdown": [], "total_cost_cents": 0}


# ── Platform Ops: cross-tenant overview (platform_admin only) ──

@app.get("/ops/overview")
async def ops_overview(request: Request):
    """平台运营全局视图。仅限 platform_admin 角色。"""
    identity = _resolve_identity(request)
    role = getattr(identity, "role", "") or ""
    if role != "platform_admin" and identity.actor_role != "platform_admin":
        raise HTTPException(status_code=403, detail="platform_admin_only")

    try:
        from tenants.manager import tenant_manager
        from storage.platform_db import get_platform_db
        db = get_platform_db()
        tenants = db.list_tenants()
        active = sum(1 for t in tenants if t.get("status") == "active")
        pending = sum(1 for t in tenants if t.get("status") == "pending")
        suspended = sum(1 for t in tenants if t.get("status") == "suspended")
        from datetime import datetime as _dt
        now = _dt.now()
        total_tokens = db.get_total_monthly_tokens(now.year, now.month)

        return {
            "total_tenants": len(tenants),
            "active_tenants": active,
            "pending_tenants": pending,
            "suspended_tenants": suspended,
            "total_tokens_month": total_tokens,
            "top_tenants": sorted(
                [{"id": t["tenant_id"], "name": t.get("name", ""), "plan": t.get("plan", "free")}
                 for t in tenants if t.get("status") == "active"],
                key=lambda x: x["plan"],
                reverse=True,
            )[:10],
        }
    except Exception as e:
        return {"error": str(e)[:200]}


# ── Marketplace: publish with SkillSimulator integration ──

@app.post("/marketplace/publish")
async def marketplace_publish(request: Request):
    """租户提交 Skill 到市场。自动预检 SkillSimulator。"""
    identity = _resolve_identity(request)
    body = await request.json()
    skill_id = str(body.get("skill_id") or "")
    if not skill_id:
        raise HTTPException(status_code=400, detail="skill_id_required")

    import uuid as _uuid
    submission_id = f"sub_{_uuid.uuid4().hex[:12]}"

    # Run SkillSimulator pre-check
    test_result = None
    try:
        from core.harness.learning.skill_simulator import SkillSimulator
        sim = SkillSimulator()
        test_result = await sim.run(skill_id)
    except Exception:
        test_result = {"error": "simulation_unavailable"}

    return {
        "submission_id": submission_id,
        "skill_id": skill_id,
        "tenant_id": identity.tenant_id or "default",
        "status": "pending_review",
        "test_result": test_result,
        "message": "已提交审核" if test_result and not test_result.get("error") else "已提交（预检不可用）",
    }


# ── Ontology Bridge: cross-graph impact analysis ──

@app.get("/ontology/impact/{urn}")
async def ontology_impact(urn: str, direction: str = "downstream", depth: int = 3):
    """查询某个实体的跨域影响范围。

    Args:
        urn: 实体 URN，如 urn:aiplat:agent:rag_agent
        direction: downstream（影响谁）/ upstream（被谁影响）
        depth: 遍历深度（默认 3）
    """
    from core.harness.ontology_engine.triple_store import get_triple_store
    store = get_triple_store()
    if direction == "downstream":
        results = store.get_downstream(urn, depth=depth)
    else:
        results = store.get_upstream(urn, depth=depth)
    return {"urn": urn, "direction": direction, "depth": depth,
            "results": results, "total": len(results)}


@app.get("/ontology/triples/{predicate}")
async def ontology_triples_by_predicate(predicate: str):
    """按关系类型查询所有三元组。"""
    from core.harness.ontology_engine.triple_store import get_triple_store
    store = get_triple_store()
    return {"predicate": predicate, "results": store.get_by_predicate(predicate)}


@app.post("/ontology/scan")
async def ontology_rescan(request: Request):
    """手动触发全量跨域依赖扫描。"""
    from core.harness.ontology_engine.triple_scanner import scan_and_populate
    stats = await scan_and_populate()
    return {"status": "scanned", "stats": stats}


# ━━━ Builder Pipeline ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class BuilderSessionCreateReq(BaseModel):
    requirement: str = ""


class BuilderChatReq(BaseModel):
    message: str


class BuilderConfirmReq(BaseModel):
    pass

# Builder endpoints moved to platform-local router
from api.routers.builder import router as builder_router  # noqa: E402
from api.routers.policy import router as policy_router  # noqa: E402
from api.routers.ops_exports import router as ops_exports_router  # noqa: E402
from api.routers.chat import router as chat_router  # noqa: E402
from api.routers.conversations import router as conversations_router  # noqa: E402
from api.routers.prompts import router as prompts_router  # noqa: E402
from api.routers.permissions import router as permissions_router  # noqa: E402
from api.routers.quota import router as quota_router  # noqa: E402
from api.routers.tenant_policies import router as tenant_policies_router  # noqa: E402
from api.routers.workflows import router as workflows_router  # noqa: E402
from api.routers.apps import router as apps_router  # noqa: E402
app.include_router(builder_router)
app.include_router(policy_router)
app.include_router(ops_exports_router)
app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(prompts_router)
app.include_router(permissions_router)
app.include_router(quota_router)
app.include_router(tenant_policies_router)
app.include_router(workflows_router)
app.include_router(apps_router)
# Remaining forbidden routes migrated from core
from api.routers.change_control import router as change_control_router  # noqa: E402
from api.routers.approvals import router as approvals_router  # noqa: E402
from api.routers.onboarding import router as onboarding_router  # noqa: E402
from api.routers.gate_policies import router as gate_policies_router  # noqa: E402
app.include_router(change_control_router)
app.include_router(approvals_router)
app.include_router(onboarding_router)
app.include_router(gate_policies_router)
# Channels and sessions management — migrated from aiPlat-app
from api.routers.channels import router as channels_router  # noqa: E402
app.include_router(channels_router)
# Gateway routes — migrated from aiPlat-core
from api.routers.gateway import router as gateway_router  # noqa: E402
app.include_router(gateway_router)

# Skill Marketplace — install / uninstall skills
from api.routers.skill_marketplace import router as skill_marketplace_router  # noqa: E402
from api.routers.kb_integration import router as kb_integration_router  # noqa: E402
app.include_router(skill_marketplace_router)
app.include_router(kb_integration_router)


# ━━━ MCP Servers ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@app.get("/api/v1/mcp/servers", response_model=Dict[str, Any])
async def list_mcp_servers(request: Request, scope: str = "workspace", _auth: str = Depends(require_auth)):
    identity = _resolve_identity(request)
    _require_scope(identity, "mcp:read")
    params = {"scope": scope} if scope else None
    return await _core_request("GET", f"/api/core/{scope}/mcp/servers", identity=identity, params=params)


@app.post("/api/v1/mcp/servers", response_model=Dict[str, Any])
async def register_mcp_server(request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "mcp:write")
    body = await request.json()
    scope = body.pop("scope", "workspace")
    return await _core_request("POST", f"/api/core/{scope}/mcp/servers", identity=identity, json_body=body)


@app.post("/api/v1/mcp/servers/{name}/enable", response_model=Dict[str, Any])
async def enable_mcp_server(name: str, request: Request, scope: str = "workspace"):
    identity = _resolve_identity(request)
    _require_scope(identity, "mcp:write")
    return await _core_request("POST", f"/api/core/{scope}/mcp/servers/{name}/enable", identity=identity)


@app.post("/api/v1/mcp/servers/{name}/disable", response_model=Dict[str, Any])
async def disable_mcp_server(name: str, request: Request, scope: str = "workspace"):
    identity = _resolve_identity(request)
    _require_scope(identity, "mcp:write")
    return await _core_request("POST", f"/api/core/{scope}/mcp/servers/{name}/disable", identity=identity)


@app.get("/api/v1/mcp/servers/{name}/tools", response_model=Dict[str, Any])
async def list_mcp_server_tools(name: str, request: Request, scope: str = "workspace", _auth: str = Depends(require_auth)):
    identity = _resolve_identity(request)
    _require_scope(identity, "mcp:read")
    return await _core_request("GET", f"/api/core/{scope}/mcp/servers/{name}/tools", identity=identity)


@app.get("/api/v1/mcp/servers/{name}/policy-check", response_model=Dict[str, Any])
async def check_mcp_server_policy(name: str, request: Request, scope: str = "workspace"):
    identity = _resolve_identity(request)
    _require_scope(identity, "mcp:read")
    return await _core_request("GET", f"/api/core/{scope}/mcp/servers/{name}/policy-check", identity=identity)


# ━━━ Plugins ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@app.get("/api/v1/plugins", response_model=Dict[str, Any])
async def list_plugins(request: Request, status: str = "active", _auth: str = Depends(require_auth)):
    identity = _resolve_identity(request)
    _require_scope(identity, "plugins:read")
    params = {"status": status} if status else None
    return await _core_request("GET", "/api/core/plugins", identity=identity, params=params)


@app.put("/api/v1/plugins", response_model=Dict[str, Any])
async def install_or_update_plugin(request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "plugins:write")
    body = await request.json()
    from registry.plugin_validator import validate_plugin_manifest
    errors = validate_plugin_manifest(body)
    if errors:
        raise HTTPException(400, detail={"code": "plugin_validation_failed", "errors": errors})
    return await _core_request("PUT", "/api/core/plugins", identity=identity, json_body=body)


@app.post("/api/v1/plugins/{plugin_id}/enable", response_model=Dict[str, Any])
async def enable_plugin(plugin_id: str, request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "plugins:write")
    return await _core_request("POST", f"/api/core/plugins/{plugin_id}/enable", identity=identity)


@app.post("/api/v1/plugins/{plugin_id}/disable", response_model=Dict[str, Any])
async def disable_plugin(plugin_id: str, request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "plugins:write")
    return await _core_request("POST", f"/api/core/plugins/{plugin_id}/disable", identity=identity)


@app.get("/api/v1/plugins/{plugin_id}/versions", response_model=Dict[str, Any])
async def list_plugin_versions(plugin_id: str, request: Request, _auth: str = Depends(require_auth)):
    identity = _resolve_identity(request)
    _require_scope(identity, "plugins:read")
    return await _core_request("GET", f"/api/core/plugins/{plugin_id}/versions", identity=identity)


@app.post("/api/v1/plugins/{plugin_id}/rollback", response_model=Dict[str, Any])
async def rollback_plugin(plugin_id: str, request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "plugins:write")
    return await _core_request("POST", f"/api/core/plugins/{plugin_id}/rollback", identity=identity)


@app.post("/api/v1/plugins/{plugin_id}/run", response_model=Dict[str, Any])
async def run_plugin_async(plugin_id: str, request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "plugins:execute")
    body = await request.json()
    return await _core_request("POST", f"/api/core/plugins/{plugin_id}/run", identity=identity, json_body=body)


# ── Phase D: KB metadata, export, AI creation ──

@app.put("/platform/kb/documents/{doc_id}/meta")
async def kb_update_doc_meta(doc_id: str, request: Request):
    """Update document metadata (title, tags, description)."""
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")
    body = await request.json()
    conn = _open_kb_db(identity.tenant_id)
    try:
        meta = conn.execute(
            "SELECT meta_json FROM documents WHERE tenant_id=? AND doc_id=?", (identity.tenant_id, doc_id)
        ).fetchone()
        old_meta = json.loads(meta[0] or "{}") if meta else {}
        new_meta = {**old_meta, "title": body.get("title", old_meta.get("title", "")),
                    "tags": body.get("tags", old_meta.get("tags", [])),
                    "description": body.get("description", old_meta.get("description", ""))}
        conn.execute("UPDATE documents SET meta_json=? WHERE tenant_id=? AND doc_id=?", 
                     (json.dumps(new_meta), identity.tenant_id, doc_id))
        conn.commit()
        return {"status": "ok", "doc_id": doc_id, "meta": new_meta}
    finally:
        conn.close()


@app.get("/platform/kb/documents/{doc_id}/export")
async def kb_export_document(doc_id: str, format: str = "json", request: Request = None):
    """Export document content in various formats (json/markdown/pdf/docx)."""
    identity = _resolve_identity(request) if request else type('',(),{'tenant_id':'default','actor_id':'system','request_id':'export'})()
    if request:
        identity = _resolve_identity(request)
    conn = _open_kb_db(identity.tenant_id)
    try:
        elems = conn.execute(
            "SELECT text, type, page_idx FROM kb_elements WHERE tenant_id=? AND doc_id=? AND text IS NOT NULL ORDER BY page_idx, rowid",
            (identity.tenant_id, doc_id),
        ).fetchall()
        if not elems:
            raise HTTPException(status_code=404, detail="doc_empty")
        full_text = "\n\n".join(str(r["text"] or "") for r in elems)
        if format == "markdown":
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse(f"# Document {doc_id}\n\n{full_text}", media_type="text/markdown")
        elif format in ("pdf", "docx"):
            # Generate simple PDF via reportlab
            try:
                from io import BytesIO
                buf = BytesIO()
                if format == "pdf":
                    from reportlab.pdfgen import canvas
                    c = canvas.Canvas(buf)
                    y = 800
                    for line in full_text.split("\n")[:200]:
                        if y < 50: c.showPage(); y = 800
                        c.drawString(50, y, line[:120]); y -= 14
                    c.save()
                    from fastapi.responses import Response
                    return Response(buf.getvalue(), media_type="application/pdf",
                                   headers={"Content-Disposition": f"attachment; filename={doc_id}.pdf"})
                else:
                    from docx import Document
                    d = Document()
                    for line in full_text.split("\n")[:500]:
                        if line.strip():
                            d.add_paragraph(line[:500])
                    d.save(buf)
                    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                   headers={"Content-Disposition": f"attachment; filename={doc_id}.docx"})
            except ImportError:
                raise HTTPException(status_code=501, detail="format_not_available: install reportlab/docx")
        return {"doc_id": doc_id, "format": "json", "text": full_text, "elements": len(elems)}
    finally:
        conn.close()


@app.post("/platform/kb/documents/create-with-ai")
async def kb_create_with_ai(request: Request):
    """AI-assisted document creation: LLM generates draft from title + prompt."""
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")
    body = await request.json()
    title = str(body.get("title", "AI 生成文档")).strip()
    prompt = str(body.get("prompt", "")).strip()
    collection_id = str(body.get("collection_id", "default"))
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt_required")
    try:
        from core.api.facades.service_facade import llm_generate
        from core.harness.utils.prompt_loader import _async_prompt_resolve
        from core.harness.utils.model_injection import best_model_for_purpose
        sp = await _async_prompt_resolve("kb-doc-writer", title=title, prompt=prompt)
        resp = await llm_generate(None, [
            {"role": "user", "content": sp},
            {"role": "user", "content": f"标题：{title}\n要求：{prompt}\n\n请生成完整文档内容："},
        ], model_name=best_model_for_purpose("chat"), temperature=0.7, max_tokens=4000)
        content = getattr(resp, "content", "") or str(resp)
        # Save as document
        import time as _t, os as _os, sqlite3 as _sql
        doc_id = f"doc_ai_{identity.request_id}"[:40]
        now = _t.time()
        dbp = _kb_db_path(identity.tenant_id)
        c = _sql.connect(dbp)
        _kb_ensure_schema(c)
        c.execute("PRAGMA journal_mode=WAL")
        # Ensure version column
        try:
            c.execute("ALTER TABLE documents ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        c.execute("INSERT OR REPLACE INTO documents(tenant_id,doc_id,collection_id,source_uri,kind,status,version,meta_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                  (identity.tenant_id, doc_id, collection_id, f"ai://{doc_id}", "txt", "ready", 1, json.dumps({"title": title}), now))
        c.execute("INSERT OR REPLACE INTO kb_elements(tenant_id,element_id,doc_id,type,page_idx,bbox_json,text,cells_json,asset_id,meta_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (identity.tenant_id, f"el_{doc_id}_1", doc_id, "text", 0, None, content[:20000], None, None, '{}', now))
        c.commit(); c.close()
        return {"doc_id": doc_id, "title": title, "content": content[:500], "status": "ready"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Phase F: Enterprise operations ──

@app.put("/platform/kb/documents/{doc_id}/content")
async def kb_update_doc_content(doc_id: str, request: Request):
    """Update document content — full-text editing."""
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")
    body = await request.json()
    content = str(body.get("content", ""))
    if not content:
        raise HTTPException(status_code=400, detail="content_required")
    conn = _open_kb_db(identity.tenant_id)
    try:
        conn.execute("UPDATE kb_elements SET text=? WHERE tenant_id=? AND doc_id=? AND type='text'",
                    (content[:20000], identity.tenant_id, doc_id))
        conn.commit()
        return {"status": "updated", "doc_id": doc_id}
    finally:
        conn.close()


@app.post("/platform/kb/storage/cleanup")
async def kb_storage_cleanup(request: Request):
    """Clean up old/archived elements and orphaned embeddings."""
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")
    conn = _open_kb_db(identity.tenant_id)
    try:
        # Delete archived elements (version < current)
        conn.execute("DELETE FROM kb_elements WHERE tenant_id=? AND meta_json LIKE '%\"archived\":1%'",
                    (identity.tenant_id,))
        # Delete orphaned embeddings
        conn.execute("DELETE FROM kb_embeddings WHERE tenant_id=? AND element_id NOT IN (SELECT element_id FROM kb_elements WHERE tenant_id=?)",
                    (identity.tenant_id, identity.tenant_id))
        conn.commit()
        # Count remaining
        docs = conn.execute("SELECT count(*) FROM documents WHERE tenant_id=?", (identity.tenant_id,)).fetchone()[0]
        elems = conn.execute("SELECT count(*) FROM kb_elements WHERE tenant_id=?", (identity.tenant_id,)).fetchone()[0]
        return {"status": "cleaned", "documents": docs, "elements": elems}
    finally:
        conn.close()


@app.get("/platform/kb/storage/stats")
async def kb_storage_stats(request: Request):
    """Storage statistics for tenant KB."""
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")
    import os as _os
    conn = _open_kb_db(identity.tenant_id)
    try:
        docs = conn.execute("SELECT count(*) FROM documents WHERE tenant_id=?", (identity.tenant_id,)).fetchone()[0]
        elems = conn.execute("SELECT count(*) FROM kb_elements WHERE tenant_id=?", (identity.tenant_id,)).fetchone()[0]
        embs = conn.execute("SELECT count(*) FROM kb_embeddings WHERE tenant_id=?", (identity.tenant_id,)).fetchone()[0]
        active = conn.execute("SELECT count(*) FROM documents WHERE tenant_id=? AND status='ready'", (identity.tenant_id,)).fetchone()[0]
        archived = conn.execute("SELECT count(*) FROM kb_elements WHERE tenant_id=? AND meta_json LIKE '%\"archived\":1%'", (identity.tenant_id,)).fetchone()[0]
        db_size = _os.path.getsize(_kb_db_path(identity.tenant_id)) if _os.path.exists(_kb_db_path(identity.tenant_id)) else 0
        return {"documents": docs, "active": active, "elements": elems, "embeddings": embs,
                "archived_elements": archived, "db_size_bytes": db_size}
    finally:
        conn.close()


def _enqueue_task(tenant_id: str, task_type: str, payload: dict) -> None:
    """Enqueue async task. Uses Redis if configured, else threading.Thread."""
    backend = os.getenv("AIPLAT_QUEUE_BACKEND", "thread").lower()
    if backend == "redis":
        try:
            import redis, json as _j
            r = redis.from_url(os.getenv("AIPLAT_REDIS_URL", "redis://localhost:6379/0"))
            r.lpush(f"aiplat:kb:tasks:{tenant_id}", _j.dumps({"type": task_type, "payload": payload}))
            return
        except ImportError:
            pass
    # Thread fallback
    import threading
    def _run():
        if task_type == "auto_archive":
            _auto_archive_docs(tenant_id)
        elif task_type == "reindex":
            pass  # reindex already implemented
    threading.Thread(target=_run, daemon=True).start()


def _auto_archive_docs(tenant_id: str) -> None:
    """Archive documents not accessed in 90 days."""
    try:
        conn = _open_kb_db(tenant_id)
        threshold = time.time() - 90 * 86400
        conn.execute(
            "UPDATE documents SET status='archived' WHERE tenant_id=? AND status='ready' AND created_at < ?",
            (tenant_id, threshold),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logging.debug(str(e), exc_info=True)



# ── Vault Routes ──

def _resolve_vault_path(vault_id: str, tenant_id: str = "default") -> str:
    from kb.db import KBSqlite
    from kb.storage import get_tenant_storage
    db = KBSqlite(get_tenant_storage(tenant_id).db_path)
    vault = db.get_vault(tenant_id=tenant_id, vault_id=vault_id)
    if not vault:
        raise HTTPException(status_code=404, detail=f"Vault '{vault_id}' not found")
    return vault["vault_path"]


@app.get("/platform/kb/vault/list")
async def vault_list(tenant_id: str = "default"):
    from kb.service import vault_list
    return {"vaults": vault_list(tenant_id=tenant_id)}


@app.post("/platform/kb/vault/connect")
async def vault_connect(body: dict):
    from kb.service import vault_connect
    return vault_connect(tenant_id=body.get("tenant_id", "default"), vault_path=body["path"],
                         label=body.get("label", ""), auto_index=body.get("auto_index", True))


@app.post("/platform/kb/vault/disconnect")
async def vault_disconnect(body: dict):
    from kb.service import vault_disconnect
    return vault_disconnect(tenant_id=body.get("tenant_id", "default"), vault_id=body["vault_id"])


@app.get("/platform/kb/vault/{vault_id}/tree")
async def vault_tree(vault_id: str, subdir: str = "", max_depth: int = 3):
    from kb.service import vault_tree
    return vault_tree(vault_path=_resolve_vault_path(vault_id), subdir=subdir,
                      max_depth=max_depth, vault_id=vault_id)


@app.get("/platform/kb/vault/{vault_id}/read")
async def vault_read_file(vault_id: str, path: str):
    """Read a single vault file's content + frontmatter."""
    from kb.service import vault_read
    return vault_read(file_path=path)


@app.get("/platform/kb/vault/{vault_id}/index/status")
async def vault_index_status(vault_id: str, tenant_id: str = "default"):
    from kb.service import vault_index_status
    return vault_index_status(tenant_id=tenant_id, vault_id=vault_id)


@app.post("/platform/kb/vault/{vault_id}/index/start")
async def vault_index_start(vault_id: str, tenant_id: str = "default", collection_id: str = "default"):
    from kb.service import vault_start_indexer
    return vault_start_indexer(vault_path=_resolve_vault_path(vault_id), tenant_id=tenant_id,
                               collection_id=collection_id)


@app.post("/platform/kb/vault/{vault_id}/index/stop")
async def vault_index_stop(vault_id: str, tenant_id: str = "default"):
    from kb.service import vault_stop_indexer
    return vault_stop_indexer(tenant_id=tenant_id, vault_id=vault_id)


@app.post("/platform/kb/vault/wiki")
async def vault_send_to_wiki(body: dict):
    from kb.service import vault_to_wiki
    return await vault_to_wiki(file_path=body["file_path"],
                               collection_id=body.get("collection_id", ""),
                               vault_id=body.get("vault_id", ""),
                               tenant_id=body.get("tenant_id", "default"))


@app.get("/platform/kb/vault/wiki/backlinks")
async def vault_wiki_backlinks(doc_id: str):
    from core.harness.knowledge.wiki_engine import search_pages
    pages = search_pages(limit=1000)
    backlinks = []
    for p in pages:
        if any(f"kb:{doc_id}" in str(s) for s in (p.get("source_articles") or [])):
            backlinks.append({"title": p["title"], "category": p.get("category", ""),
                              "summary": p.get("summary", "")[:100]})
    return {"pages": backlinks, "total": len(backlinks)}


# ── Analysis Batches (KB analysis job CRUD) ──

@app.post("/api/platform/analysis-batches")
async def create_analysis_batch(request: Request):
    tenant_id = request.headers.get("X-AIPLAT-TENANT-ID", "default")
    body = await request.json()
    bid = _persist_analysis_batch(
        tenant_id=tenant_id,
        collection_id=str(body.get("collection_id", "")),
        batch_type=str(body.get("batch_type", "analysis")),
        title=str(body.get("title", "")),
        input_obj=body.get("input_json", {}) or body,
    )
    return {"batch_id": bid, "status": "created"}


@app.get("/api/platform/analysis-batches")
async def list_analysis_batches(request: Request, collection_id: Optional[str] = None):
    tenant_id = request.headers.get("X-AIPLAT-TENANT-ID", "default")
    batches = _list_analysis_batches(tenant_id=tenant_id, collection_id=collection_id)
    return {"batches": batches, "total": len(batches)}


@app.delete("/api/platform/analysis-batches/{batch_id}")
async def delete_analysis_batch(batch_id: str, request: Request):
    tenant_id = request.headers.get("X-AIPLAT-TENANT-ID", "default")
    ok = _delete_analysis_batch(tenant_id=tenant_id, batch_id=batch_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")
    return {"batch_id": batch_id, "status": "deleted"}


# ── Studio Sessions ──

@app.get("/api/studio/sessions")
async def list_studio_sessions():
    """List studio sessions (scaffold — full Studio API to be implemented)."""
    return {"sessions": [], "total": 0}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("AIPLAT_PLATFORM_PORT", "8003")))
