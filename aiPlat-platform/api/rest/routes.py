"""
aiPlat-platform HTTP API (Phase 1/2)

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

from fastapi import FastAPI, Header, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import httpx

# NOTE: repo folder name contains '-', so do NOT import via top-level package name.
# Use subpackages directly (auth/, utils/, etc).
from utils.ids import new_prefixed_id as _new_prefixed_id  # type: ignore
from auth.authenticator import authenticator as _authenticator  # type: ignore
from storage import sqlite as platform_store  # type: ignore


app = FastAPI(title="aiPlat-platform", version="0.1.0")

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
    verify = os.getenv("AIPLAT_PLATFORM_JWT_VERIFY", "false").lower() in ("1", "true", "yes", "y")
    secret = os.getenv("AIPLAT_JWT_SECRET")
    if verify and secret:
        try:
            import jwt  # type: ignore

            return jwt.decode(token, secret, algorithms=["HS256", "RS256"], options={"verify_aud": False})
        except Exception:
            # fallback to unverified decode
            pass
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

    # 3) default fallback
    return Identity(request_id=request_id, tenant_id="default", actor_id="anonymous", scopes=[], auth_type="anonymous")


def _core_base_url() -> str:
    return os.getenv("AIPLAT_CORE_ENDPOINT", "http://localhost:8002").rstrip("/")


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
    except Exception:
        # best-effort: callers will surface errors
        pass


def _new_analysis_run_id() -> str:
    import time, random

    return f"ar_{int(time.time() * 1000):x}{random.randint(0, 0xFFFF):04x}"


def _new_analysis_batch_id() -> str:
    import time, random

    return f"ab_{int(time.time() * 1000):x}{random.randint(0, 0xFFFF):04x}"


def _persist_analysis_run(*, tenant_id: str, doc_id: Optional[str], collection_id: Optional[str], run_type: str, input_obj: Dict[str, Any], output_obj: Optional[Dict[str, Any]]) -> Optional[str]:
    import json, sqlite3

    dbp = _kb_db_path(tenant_id)
    conn = sqlite3.connect(dbp)
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
    except Exception:
        return None
    finally:
        conn.close()


def _persist_analysis_batch(*, tenant_id: str, collection_id: Optional[str], batch_type: str, title: Optional[str], input_obj: Dict[str, Any], output_obj: Dict[str, Any]) -> Optional[str]:
    import json, sqlite3

    dbp = _kb_db_path(tenant_id)
    conn = sqlite3.connect(dbp)
    try:
        _kb_ensure_schema(conn)
        batch_id = _new_analysis_batch_id()
        conn.execute(
            """
            INSERT INTO analysis_batches(
              tenant_id, batch_id, collection_id, batch_type, title, input_json, output_json, created_at
            )
            VALUES(?,?,?,?,?,?,?,strftime('%s','now'))
            """,
            (
                tenant_id,
                batch_id,
                collection_id,
                batch_type,
                title,
                json.dumps(input_obj or {}, ensure_ascii=False),
                json.dumps(output_obj or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
        return batch_id
    except Exception:
        return None
    finally:
        conn.close()


@app.get("/kb/debug")
@app.get("/platform/kb/debug")
@app.get("/api/v1/kb/debug")
async def kb_debug(request: Request):
    """
    Debug endpoint: show where platform thinks KB db/assets are.
    Useful to diagnose AIPLAT_HOME mismatch / tenant mismatch.
    """
    identity = _resolve_identity(request)
    import os as _os

    dbp = _kb_db_path(identity.tenant_id)
    return {
        "identity": {
            "tenant_id": identity.tenant_id,
            "actor_id": identity.actor_id,
            "actor_role": identity.actor_role,
            "auth_type": identity.auth_type,
            "scopes": identity.scopes,
        },
        "AIPLAT_HOME_env": _os.getenv("AIPLAT_HOME"),
        "platform_home": _platform_home(),
        "tenant_dir": _kb_tenant_dir(identity.tenant_id),
        "db_path": dbp,
        "db_exists": _os.path.exists(dbp),
        "db_size": _os.path.getsize(dbp) if _os.path.exists(dbp) else None,
    }


async def _call_core_gateway_execute(identity: Identity, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Forward to core /api/core/gateway/execute and inject standardized headers.
    """
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

    # Force core identity to be platform-authoritative
    body = dict(body or {})
    body["tenant_id"] = identity.tenant_id
    body["user_id"] = identity.actor_id
    # session_id: preserve caller if provided
    if not body.get("session_id"):
        body["session_id"] = body.get("payload", {}).get("session_id") if isinstance(body.get("payload"), dict) else None

    return await _core_request("POST", "/api/core/gateway/execute", identity=identity, json_body=body, extra_headers=headers)


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
    async with httpx.AsyncClient(timeout=60.0) as client:
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


def _extract_core_error_message(resp: Optional[Dict[str, Any]]) -> str:
    if not isinstance(resp, dict):
        return "core_skill_failed"
    err = resp.get("error")
    if isinstance(err, dict):
        msg = str(err.get("message") or "").strip()
        if msg:
            return msg
    for k in ("error_message", "message", "detail"):
        v = resp.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "core_skill_failed"


# -------------------- Health & Debug --------------------


@app.get("/health")
async def health_check(request: Request):
    identity = _resolve_identity(request)
    return {"status": "healthy", "tenant_id": identity.tenant_id}


@app.get("/whoami")
async def whoami(request: Request):
    identity = _resolve_identity(request)
    return {
        "request_id": identity.request_id,
        "tenant_id": identity.tenant_id,
        "actor_id": identity.actor_id,
        "actor_role": identity.actor_role,
        "scopes": identity.scopes,
        "auth_type": identity.auth_type,
    }


# -------------------- Platform proxy execute (PR-02) --------------------


@app.post("/platform/gateway/execute")
async def platform_gateway_execute(request: Request):
    identity = _resolve_identity(request)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be json object")
    return await _call_core_gateway_execute(identity, body)


# -------------------- API v1 (compat for aiPlat-app client / docs) --------------------


class AgentExecuteRequest(BaseModel):
    input: Any
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class KBIngestResponse(BaseModel):
    tenant_id: str
    collection_id: str
    doc_id: str
    pages: int
    budget_rows: int
    budget_pages: List[int]


class KBQueryRequest(BaseModel):
    collection_id: str = "default"
    question: str
    year: Optional[int] = None
    limit: int = 50

class KBCollectionCreateRequest(BaseModel):
    collection_id: str
    name: str = ""


@app.get("/kb/collections")
@app.get("/platform/kb/collections")
@app.get("/api/v1/kb/collections")
async def kb_list_collections(request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")
    import sqlite3, json

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"collections": [], "total": 0}
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
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
    import sqlite3, json

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        raise HTTPException(status_code=404, detail="job_not_found")
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
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
    import sqlite3, json

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"items": [], "total": 0}
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
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
    import sqlite3

    cid = str(req.collection_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="collection_id_required")
    dbp = _kb_db_path(identity.tenant_id)
    conn = sqlite3.connect(dbp)
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


@app.get("/kb/collections/{collection_id}/documents")
@app.get("/platform/kb/collections/{collection_id}/documents")
@app.get("/api/v1/kb/collections/{collection_id}/documents")
async def kb_list_documents(collection_id: str, request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")
    import sqlite3, json

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"documents": [], "total": 0}
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
    try:
        _kb_ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT doc_id, collection_id, source_uri, kind, status, meta_json, created_at
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
    import sqlite3

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        raise HTTPException(status_code=404, detail="db_not_found")
    conn = sqlite3.connect(dbp)
    try:
        _kb_ensure_schema(conn)
        conn.execute("DELETE FROM budget_rows WHERE tenant_id=? AND doc_id=?", (identity.tenant_id, doc_id))
        conn.execute("DELETE FROM assets WHERE tenant_id=? AND doc_id=?", (identity.tenant_id, doc_id))
        conn.execute("DELETE FROM kb_elements WHERE tenant_id=? AND doc_id=?", (identity.tenant_id, doc_id))
        conn.execute("DELETE FROM kb_embeddings WHERE tenant_id=? AND doc_id=?", (identity.tenant_id, doc_id))
        conn.execute("DELETE FROM doc_sources WHERE tenant_id=? AND doc_id=?", (identity.tenant_id, doc_id))
        conn.execute("DELETE FROM url_cache WHERE tenant_id=? AND doc_id=?", (identity.tenant_id, doc_id))
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
    except Exception:
        pass
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
    import sqlite3, json

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        raise HTTPException(status_code=404, detail="db_not_found")
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
    try:
        _kb_ensure_schema(conn)
        row = conn.execute(
            "SELECT doc_id, collection_id, source_uri, kind, meta_json FROM documents WHERE tenant_id=? AND doc_id=?",
            (identity.tenant_id, doc_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="doc_not_found")
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
    core_resp = await _core_request("POST", f"/api/core/skills/kb_ingest_document/execute", identity=identity, json_body=payload)
    job = None
    try:
        if isinstance(core_resp, dict):
            o = core_resp.get("output")
            if isinstance(o, dict):
                job = o.get("output")
    except Exception:
        job = None
    return {"doc_id": doc_id, "job": job, "core": core_resp}


if _HAS_MULTIPART:
    @app.post("/kb/collections/{collection_id}/documents/upload", response_model=Dict[str, Any])
    @app.post("/platform/kb/collections/{collection_id}/documents/upload", response_model=Dict[str, Any])
    @app.post("/api/v1/kb/collections/{collection_id}/documents/upload", response_model=Dict[str, Any])
    async def kb_upload_and_ingest(collection_id: str, request: Request, file: UploadFile = File(...), kind: str = Form("pdf")):
        """Upload and ingest a document (MVP)."""
        identity = _resolve_identity(request)
        _require_scope(identity, "kb:write")

        if not file.filename:
            raise HTTPException(status_code=400, detail="filename_required")

        # Persist upload under tenant
        from pathlib import Path
        import re

        req_kind = str(kind or "").strip().lower()
        safe_name = re.sub(r"[^A-Za-z0-9_.\u4e00-\u9fff-]+", "_", file.filename)
        up_dir = Path(_kb_tenant_dir(identity.tenant_id)) / "uploads"
        dst = up_dir / f"{identity.request_id}_{safe_name}"
        data = await file.read()
        max_size = 500 * 1024 * 1024 if req_kind == "video" else 200 * 1024 * 1024
        if len(data) > max_size:
            raise HTTPException(status_code=413, detail="file_too_large")
        dst.write_bytes(data)

        ext = os.path.splitext(file.filename or "")[1].lower()
        kind = req_kind or ("video" if ext in (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v") else "pdf")

        # Call core engine skill
        # Default OCR engine:
        # - PaddleOCR is heavy and may crash on some macOS setups (libpaddle SIGSEGV).
        # - Prefer tesseract on macOS unless explicitly overridden.
        import sys

        default_ocr_engine = "tesseract" if sys.platform == "darwin" else "paddleocr"
        ocr_engine = os.getenv("AIPLAT_KB_OCR_ENGINE", default_ocr_engine)
        skill_name = "doc_ingest" if kind == "video" else "kb_ingest_document"
        payload = {
            "input": {
                "tenant_id": identity.tenant_id,
                "collection_id": collection_id,
                "file_path": str(dst),
                "kind": kind,
                "ocr_lang": "zh",
                "ocr_engine": ocr_engine,
                "dpi": 240,
                "max_pages": 60,
            },
            "context": {"tenant_id": identity.tenant_id, "actor_id": identity.actor_id, "request_id": identity.request_id},
            "mode": "inline",
        }
        try:
            resp = await _core_request("POST", f"/api/core/skills/{skill_name}/execute", identity=identity, json_body=payload)
            if isinstance(resp, dict) and resp.get("ok") is False:
                raise HTTPException(status_code=502, detail=_extract_core_error_message(resp))
            job = _extract_job_payload(resp)
            if not job:
                raise HTTPException(status_code=502, detail="ingest_job_not_created")
            return {"upload_path": str(dst), "job": job, "core": resp}
        except httpx.HTTPStatusError as e:
            # surface core error body to caller (debug-friendly)
            detail = {"message": "core_skill_failed", "status_code": getattr(e.response, "status_code", None)}
            try:
                detail["body"] = e.response.json() if e.response is not None else None
            except Exception:
                try:
                    detail["body_text"] = e.response.text if e.response is not None else None
                except Exception:
                    pass
            raise HTTPException(status_code=502, detail=detail)
        except Exception as e:
            raise HTTPException(status_code=500, detail={"message": "kb_upload_failed", "error": str(e)})
else:
    @app.post("/kb/collections/{collection_id}/documents/upload", response_model=Dict[str, Any])
    @app.post("/platform/kb/collections/{collection_id}/documents/upload", response_model=Dict[str, Any])
    @app.post("/api/v1/kb/collections/{collection_id}/documents/upload", response_model=Dict[str, Any])
    async def kb_upload_and_ingest(collection_id: str, request: Request):
        raise HTTPException(
            status_code=501,
            detail='upload_requires_python_multipart: please install "python-multipart" and restart platform',
        )


# =========================
# Documents API (generic)
# =========================

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
    else:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="json_body_required")
        collection_id = str(body.get("collection_id") or "default")
        url = body.get("url")
        kind = str(body.get("kind") or "").strip().lower()
        ocr_lang = str(body.get("ocr_lang") or "zh")
        ocr_engine = body.get("ocr_engine")
        dpi = int(body.get("dpi") or 240)
        max_pages = int(body.get("max_pages") or 60)
        if not url:
            raise HTTPException(status_code=400, detail="url_required")
        try:
            from urllib.parse import urlparse

            host = (urlparse(str(url)).netloc or "").lower()
        except Exception:
            host = ""
        if not kind and any(x in host for x in ("toutiao.com", "ixigua.com", "douyin.com", "bilibili.com", "youtube.com", "youtu.be")):
            kind = "video"

    payload = {
        "input": {
            "tenant_id": identity.tenant_id,
            "collection_id": collection_id,
            "file_path": file_path,
            "url": url,
            "kind": kind,
            "ocr_lang": ocr_lang,
            "ocr_engine": ocr_engine,
            "dpi": dpi,
            "max_pages": max_pages,
        },
        "context": {"tenant_id": identity.tenant_id, "actor_id": identity.actor_id, "request_id": identity.request_id},
        "mode": "inline",
    }
    core_resp = await _core_request("POST", f"/api/core/skills/doc_ingest/execute", identity=identity, json_body=payload)
    out = dict(core_resp or {})
    if out.get("ok") is False:
        raise HTTPException(status_code=502, detail=_extract_core_error_message(out))
    job = _extract_job_payload(out)
    if not job:
        raise HTTPException(status_code=502, detail={"message": "ingest_job_not_created", "core": out})
    return {"core": out, "job": job}


@app.post("/api/v1/documents/{doc_id}/refresh", response_model=Dict[str, Any])
@app.post("/platform/documents/{doc_id}/refresh", response_model=Dict[str, Any])
async def documents_refresh(doc_id: str, request: Request, req: Optional[DocRefreshRequest] = None):
    """
    Refresh/re-ingest a document from latest source.
    - Prefer latest URL source if exists.
    - Fallback to latest local source path.
    - force=true bypasses dedupe in core.
    """
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")

    import sqlite3, json

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        raise HTTPException(status_code=404, detail="document_not_found")
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
    try:
        _kb_ensure_schema(conn)
        drow = conn.execute(
            "SELECT * FROM documents WHERE tenant_id=? AND doc_id=?",
            (identity.tenant_id, doc_id),
        ).fetchone()
        if not drow:
            raise HTTPException(status_code=404, detail="document_not_found")
        srows = conn.execute(
            """
            SELECT * FROM doc_sources
            WHERE tenant_id=? AND doc_id=?
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (identity.tenant_id, doc_id),
        ).fetchall()
    finally:
        conn.close()

    doc = dict(drow)
    sources = [dict(r) for r in srows]
    picked = None
    for s in sources:
        if str(s.get("source_type") or "") == "url" and s.get("url"):
            picked = s
            break
    if picked is None and sources:
        picked = sources[0]

    # Fallback to document source_uri
    url = None
    file_path = None
    kind = str(doc.get("kind") or "pdf")
    collection_id = str(doc.get("collection_id") or "default")
    if picked:
        url = picked.get("url") or None
        file_path = picked.get("local_path") or None
        kind = str(picked.get("kind") or kind)
    if not url and not file_path:
        file_path = doc.get("source_uri") or None
    if not url and not file_path:
        raise HTTPException(status_code=400, detail="no_refresh_source")

    force = bool((req.force if req else False))
    payload = {
        "input": {
            "tenant_id": identity.tenant_id,
            "collection_id": collection_id,
            "file_path": file_path,
            "url": url,
            "kind": kind,
            "ocr_lang": "zh",
            "ocr_engine": None,
            "dpi": 240,
            "max_pages": 60,
            "force_reingest": force,
        },
        "context": {"tenant_id": identity.tenant_id, "actor_id": identity.actor_id, "request_id": identity.request_id},
        "mode": "inline",
    }

    core_resp = await _core_request("POST", f"/api/core/skills/doc_ingest/execute", identity=identity, json_body=payload)
    out = dict(core_resp or {})
    job = None
    try:
        o = out.get("output")
        if isinstance(o, dict):
            if "job_id" in o and "doc_id" in o:
                job = o
            elif isinstance(o.get("output"), dict):
                job = o.get("output")
    except Exception:
        job = None
    return {"core": out, "job": job}

class DocQueryRequest(BaseModel):
    doc_id: Optional[str] = None
    collection_id: str = "default"
    question: str
    top_k: int = 8


class ConversationScopeBody(BaseModel):
    collection_id: str = "default"
    doc_ids: List[str] = Field(default_factory=list)
    version: Optional[int] = None


class ConversationCreateBody(BaseModel):
    title: Optional[str] = None
    scope: Optional[ConversationScopeBody] = None
    profile: Optional[Dict[str, Any]] = None


class ConversationQueryBody(BaseModel):
    message: str
    scope_override: Optional[ConversationScopeBody] = None
    options: Optional[Dict[str, Any]] = None


@app.post("/platform/conversations", response_model=Dict[str, Any])
async def create_conversation(req: ConversationCreateBody, request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")
    payload = {
        "tenant_id": identity.tenant_id,
        "user_id": identity.actor_id,
        "title": req.title or "资料对话",
        "scope": (req.scope.model_dump(exclude_none=True) if req.scope else {"collection_id": "default", "doc_ids": []}),
        "profile": req.profile or {"citation_required": True, "answer_style": "concise", "language": "zh-CN"},
    }
    return await _core_request("POST", "/api/core/conversations", identity=identity, json_body=payload)


@app.get("/platform/conversations", response_model=Dict[str, Any])
async def list_conversations(request: Request, limit: int = 100, offset: int = 0):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")
    return await _core_request(
        "GET",
        "/api/core/conversations",
        identity=identity,
        params={"user_id": identity.actor_id, "limit": int(limit), "offset": int(offset)},
    )


@app.get("/platform/conversations/{session_id}", response_model=Dict[str, Any])
async def get_conversation(session_id: str, request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")
    return await _core_request("GET", f"/api/core/conversations/{session_id}", identity=identity)


@app.put("/platform/conversations/{session_id}/scope", response_model=Dict[str, Any])
async def update_conversation_scope(session_id: str, req: ConversationScopeBody, request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")
    return await _core_request(
        "PUT",
        f"/api/core/conversations/{session_id}/scope",
        identity=identity,
        json_body=req.model_dump(exclude_none=True),
    )


@app.post("/platform/conversations/{session_id}/query", response_model=Dict[str, Any])
async def query_conversation(session_id: str, req: ConversationQueryBody, request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")
    payload = {
        "message": req.message,
        "user_id": identity.actor_id,
        "scope_override": req.scope_override.model_dump(exclude_none=True) if req.scope_override else None,
        "options": req.options or {"citation_required": True, "max_citations": 8, "top_k": 8, "language": "zh-CN"},
    }
    out = await _core_request("POST", f"/api/core/conversations/{session_id}/query", identity=identity, json_body=payload)
    if isinstance(out, dict) and isinstance(out.get("output"), dict):
        out["output"] = _normalize_citations_with_assets(tenant_id=identity.tenant_id, data=out.get("output")) or out.get("output")
    return out


@app.post("/api/v1/documents/query", response_model=Dict[str, Any])
@app.post("/platform/documents/query", response_model=Dict[str, Any])
async def documents_query(req: DocQueryRequest, request: Request):
    """Generic doc query (MVP): call core skill doc_query."""
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")  # reuse kb scope for now

    payload = {
        "input": {
            "tenant_id": identity.tenant_id,
            "collection_id": req.collection_id or "default",
            "doc_id": req.doc_id,
            "question": req.question,
            "top_k": int(req.top_k or 8),
        },
        "context": {"tenant_id": identity.tenant_id, "actor_id": identity.actor_id, "request_id": identity.request_id},
        "mode": "inline",
    }
    core_resp = await _core_request("POST", f"/api/core/skills/doc_query/execute", identity=identity, json_body=payload)
    out = dict(core_resp or {})
    data = None
    try:
        o = out.get("output")
        if isinstance(o, dict):
            data = o.get("output") if isinstance(o.get("output"), dict) else o
    except Exception:
        data = None
    data = _normalize_citations_with_assets(tenant_id=identity.tenant_id, data=data)
    run_id = None
    if isinstance(data, dict):
        run_id = _persist_analysis_run(
            tenant_id=identity.tenant_id,
            doc_id=req.doc_id,
            collection_id=req.collection_id or "default",
            run_type="query",
            input_obj={"doc_id": req.doc_id, "collection_id": req.collection_id or "default", "question": req.question, "top_k": int(req.top_k or 8)},
            output_obj=data,
        )
        if run_id:
            data = dict(data)
            data["analysis_run_id"] = run_id
    return {"core": out, "output": data}


class CollectionQueryRequest(BaseModel):
    collection_id: str = "default"
    question: str
    top_k: int = 8


class AnswerRewriteRequest(BaseModel):
    collection_id: str = "default"
    question: str
    current_answer: Optional[str] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)


@app.post("/api/v1/collections/query", response_model=Dict[str, Any])
@app.post("/platform/collections/query", response_model=Dict[str, Any])
async def collections_query(req: CollectionQueryRequest, request: Request):
    """Collection-level query (MVP): reuse core doc_query with doc_id unset."""
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")
    payload = {
        "input": {
            "tenant_id": identity.tenant_id,
            "collection_id": req.collection_id or "default",
            "doc_id": None,
            "question": req.question,
            "top_k": int(req.top_k or 8),
        },
        "context": {"tenant_id": identity.tenant_id, "actor_id": identity.actor_id, "request_id": identity.request_id},
        "mode": "inline",
    }
    core_resp = await _core_request("POST", f"/api/core/skills/doc_query/execute", identity=identity, json_body=payload)
    out = dict(core_resp or {})
    data = None
    try:
        o = out.get("output")
        if isinstance(o, dict):
            data = o.get("output") if isinstance(o.get("output"), dict) else o
    except Exception:
        data = None
    data = _normalize_citations_with_assets(tenant_id=identity.tenant_id, data=data)
    run_id = None
    if isinstance(data, dict):
        run_id = _persist_analysis_run(
            tenant_id=identity.tenant_id,
            doc_id=None,
            collection_id=req.collection_id or "default",
            run_type="query",
            input_obj={"doc_id": None, "collection_id": req.collection_id or "default", "question": req.question, "top_k": int(req.top_k or 8)},
            output_obj=data,
        )
        if run_id:
            data = dict(data)
            data["analysis_run_id"] = run_id
    return {"core": out, "output": data}


@app.post("/api/v1/collections/rewrite-answer", response_model=Dict[str, Any])
@app.post("/platform/collections/rewrite-answer", response_model=Dict[str, Any])
async def collections_rewrite_answer(req: AnswerRewriteRequest, request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")
    payload = {
        "input": {
            "tenant_id": identity.tenant_id,
            "collection_id": req.collection_id or "default",
            "question": req.question,
            "current_answer": req.current_answer or "",
            "items": list(req.items or [])[:8],
        },
        "context": {"tenant_id": identity.tenant_id, "actor_id": identity.actor_id, "request_id": identity.request_id},
        "mode": "inline",
    }
    core_resp = await _core_request("POST", f"/api/core/skills/answer_rewrite/execute", identity=identity, json_body=payload)
    out = dict(core_resp or {})
    data = None
    try:
        o = out.get("output")
        if isinstance(o, dict):
            data = o.get("output") if isinstance(o.get("output"), dict) else o
    except Exception:
        data = None
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="rewrite_output_invalid")
    return data


class DocSummarizeRequest(BaseModel):
    doc_id: str
    profile: str = "key_points"
    max_points: int = 10


class AnalysisBatchCreateRequest(BaseModel):
    collection_id: str = "default"
    batch_type: str
    title: Optional[str] = None
    input: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)


@app.post("/api/v1/analysis-batches", response_model=Dict[str, Any])
@app.post("/platform/analysis-batches", response_model=Dict[str, Any])
async def analysis_batches_create(req: AnalysisBatchCreateRequest, request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")
    batch_id = _persist_analysis_batch(
        tenant_id=identity.tenant_id,
        collection_id=req.collection_id or "default",
        batch_type=req.batch_type,
        title=req.title,
        input_obj=req.input or {},
        output_obj=req.output or {},
    )
    if not batch_id:
        raise HTTPException(status_code=500, detail="analysis_batch_create_failed")
    return {"status": "created", "batch_id": batch_id}


@app.get("/api/v1/analysis-batches", response_model=Dict[str, Any])
@app.get("/platform/analysis-batches", response_model=Dict[str, Any])
async def analysis_batches_list(
    request: Request,
    collection_id: Optional[str] = None,
    batch_type: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")

    import sqlite3, json

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"items": [], "total": 0}
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
    try:
        _kb_ensure_schema(conn)
        where = ["tenant_id=?"]
        vals: List[Any] = [identity.tenant_id]
        if collection_id:
            where.append("collection_id=?")
            vals.append(collection_id)
        if batch_type:
            where.append("batch_type=?")
            vals.append(batch_type)
        if q:
            where.append("(title LIKE ? OR input_json LIKE ? OR output_json LIKE ?)")
            like = f"%{q}%"
            vals.extend([like, like, like])
        where_sql = " AND ".join(where)
        rows = conn.execute(
            f"""
            SELECT *
            FROM analysis_batches
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*vals, int(limit), int(offset)),
        ).fetchall()
        total = conn.execute(
            f"SELECT COUNT(1) AS c FROM analysis_batches WHERE {where_sql}",
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


@app.delete("/api/v1/analysis-batches/{batch_id}", response_model=Dict[str, Any])
@app.delete("/platform/analysis-batches/{batch_id}", response_model=Dict[str, Any])
async def analysis_batches_delete(batch_id: str, request: Request):
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:write")

    import sqlite3

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        raise HTTPException(status_code=404, detail="analysis_batch_not_found")
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
    try:
        _kb_ensure_schema(conn)
        row = conn.execute(
            "SELECT batch_id FROM analysis_batches WHERE tenant_id=? AND batch_id=?",
            (identity.tenant_id, batch_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="analysis_batch_not_found")
        conn.execute(
            "DELETE FROM analysis_batches WHERE tenant_id=? AND batch_id=?",
            (identity.tenant_id, batch_id),
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "deleted", "batch_id": batch_id}


@app.post("/api/v1/documents/summarize", response_model=Dict[str, Any])
@app.post("/platform/documents/summarize", response_model=Dict[str, Any])
async def documents_summarize(req: DocSummarizeRequest, request: Request):
    """Generic doc summarize (MVP): call core skill doc_summarize."""
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")  # reuse kb scope for now

    payload = {
        "input": {
            "tenant_id": identity.tenant_id,
            "collection_id": "default",
            "doc_id": req.doc_id,
            "profile": req.profile,
            "max_points": int(req.max_points or 10),
        },
        "context": {"tenant_id": identity.tenant_id, "actor_id": identity.actor_id, "request_id": identity.request_id},
        "mode": "inline",
    }
    core_resp = await _core_request("POST", f"/api/core/skills/doc_summarize/execute", identity=identity, json_body=payload)
    out = dict(core_resp or {})
    data = None
    try:
        o = out.get("output")
        if isinstance(o, dict):
            data = o.get("output") if isinstance(o.get("output"), dict) else o
    except Exception:
        data = None
    data = _normalize_citations_with_assets(tenant_id=identity.tenant_id, data=data)
    run_id = None
    if isinstance(data, dict):
        run_id = _persist_analysis_run(
            tenant_id=identity.tenant_id,
            doc_id=req.doc_id,
            collection_id="default",
            run_type="summarize",
            input_obj={"doc_id": req.doc_id, "collection_id": "default", "profile": req.profile, "max_points": int(req.max_points or 10)},
            output_obj=data,
        )
        if run_id:
            data = dict(data)
            data["analysis_run_id"] = run_id
    return {"core": out, "output": data}


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

    import sqlite3, json

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"items": [], "total": 0}
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
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


@app.get("/api/v1/documents/{doc_id}", response_model=Dict[str, Any])
@app.get("/platform/documents/{doc_id}", response_model=Dict[str, Any])
async def documents_get(doc_id: str, request: Request):
    """
    Get one document with aggregated stats.
    """
    identity = _resolve_identity(request)
    _require_scope(identity, "kb:read")

    import sqlite3, json

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        raise HTTPException(status_code=404, detail="document_not_found")
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
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

    import sqlite3, json

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"items": [], "total": 0}
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
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

    import sqlite3, json

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"items": [], "total": 0}
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
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

    import sqlite3

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        raise HTTPException(status_code=404, detail="analysis_run_not_found")
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
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

    import sqlite3, json

    fmt = (format or "json").strip().lower()
    if fmt not in ("json", "markdown", "md"):
        raise HTTPException(status_code=400, detail="unsupported_format")

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        raise HTTPException(status_code=404, detail="document_not_found")

    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
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

    import sqlite3, json

    dbp = _kb_db_path(identity.tenant_id)
    if not os.path.exists(dbp):
        return {"items": [], "total": 0}
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
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
                except Exception:
                    pass
    except Exception:
        pass
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
async def list_gateway_routes(enabled: Optional[bool] = None):
    routes = platform_store.list_gateway_routes(enabled=enabled)
    return {"routes": routes, "total": len(routes)}


@app.post("/gateway/routes")  # compat alias
@app.post("/platform/gateway/routes")
async def create_gateway_route(body: Dict[str, Any]):
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
async def get_gateway_route(route_id: str):
    r = platform_store.get_gateway_route(route_id)
    if not r:
        raise HTTPException(status_code=404, detail="route_not_found")
    return r


@app.put("/gateway/routes/{route_id}")  # compat alias
@app.put("/platform/gateway/routes/{route_id}")
async def update_gateway_route(route_id: str, patch: Dict[str, Any]):
    r = platform_store.get_gateway_route(route_id)
    if not r:
        raise HTTPException(status_code=404, detail="route_not_found")
    r.update({k: v for k, v in (patch or {}).items() if v is not None})
    return platform_store.upsert_gateway_route(r)


@app.delete("/gateway/routes/{route_id}")  # compat alias
@app.delete("/platform/gateway/routes/{route_id}")
async def delete_gateway_route(route_id: str):
    platform_store.delete_gateway_route(route_id)
    return {"status": "ok"}


@app.get("/platform/gateway/metrics")
async def gateway_metrics():
    # stubbed metrics
    return {"total_requests": 0, "success_rate": 1.0, "avg_latency_ms": 0, "active_routes": len(platform_store.list_gateway_routes())}


@app.get("/platform/auth/users")
async def list_auth_users(role: Optional[str] = None, status: Optional[str] = None):
    users = platform_store.list_auth_users(role=role, status=status)
    return {"users": users, "total": len(users)}


@app.post("/platform/auth/users")
async def create_auth_user(body: Dict[str, Any]):
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
async def update_auth_user(user_id: str, patch: Dict[str, Any]):
    u = platform_store.get_auth_user(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="user_not_found")
    u.update({k: v for k, v in (patch or {}).items() if v is not None})
    return platform_store.upsert_auth_user(u)


@app.delete("/platform/auth/users/{user_id}")
async def delete_auth_user(user_id: str):
    platform_store.delete_auth_user(user_id)
    return {"status": "ok"}


@app.get("/platform/tenants")
async def list_tenants(status: Optional[str] = None):
    tenants = platform_store.list_tenants(status=status)
    return {"tenants": tenants, "total": len(tenants)}


@app.post("/platform/tenants")
async def create_tenant(body: Dict[str, Any]):
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
async def update_tenant(tenant_id: str, patch: Dict[str, Any]):
    t = platform_store.get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    t.update({k: v for k, v in (patch or {}).items() if v is not None})
    return platform_store.upsert_tenant(t)


@app.delete("/platform/tenants/{tenant_id}")
async def delete_tenant(tenant_id: str):
    platform_store.delete_tenant(tenant_id)
    return {"status": "ok"}


@app.post("/platform/tenants/{tenant_id}/suspend")
async def suspend_tenant(tenant_id: str):
    t = platform_store.get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    t["status"] = "suspended"
    platform_store.upsert_tenant(t)
    return {"status": "ok"}


@app.post("/platform/tenants/{tenant_id}/resume")
async def resume_tenant(tenant_id: str):
    t = platform_store.get_tenant(tenant_id)
    if not t:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    t["status"] = "active"
    platform_store.upsert_tenant(t)
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("AIPLAT_PLATFORM_PORT", "8003")))
