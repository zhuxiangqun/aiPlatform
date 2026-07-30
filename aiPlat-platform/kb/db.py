from __future__ import annotations



import json

from contextlib import contextmanager

from dataclasses import dataclass

from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple



from core.utils.ids import new_prefixed_id

from core.api.facades.kb_facade import kb_create_infra_db_client

import logging





SCHEMA_SQL = """

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

  kind TEXT NOT NULL, -- page_image/table_image/frame_image

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

  cells_json TEXT, -- {y2026:{text,bbox},...}

  created_at INTEGER NOT NULL,

  PRIMARY KEY (tenant_id, row_id)

);



CREATE INDEX IF NOT EXISTS idx_budget_by_doc

  ON budget_rows(tenant_id, doc_id, page_idx);



-- Unified multimodal elements (content_list) for generic document intelligence.

CREATE TABLE IF NOT EXISTS kb_elements (

  tenant_id TEXT NOT NULL,

  element_id TEXT NOT NULL,

  doc_id TEXT NOT NULL,

  type TEXT NOT NULL, -- text|table|image|transcript|equation

  page_idx INTEGER,

  bbox_json TEXT,

  text TEXT,

  cells_json TEXT, -- for tables

  asset_id TEXT,  -- optional link to assets.asset_id

  meta_json TEXT,

  created_at INTEGER NOT NULL,

  PRIMARY KEY (tenant_id, element_id)

);



CREATE INDEX IF NOT EXISTS idx_kb_elements_doc

  ON kb_elements(tenant_id, doc_id, type, page_idx, created_at);



-- Document sources (provenance): one document may have multiple sources (upload/url).

CREATE TABLE IF NOT EXISTS doc_sources (

  tenant_id TEXT NOT NULL,

  source_id TEXT NOT NULL,

  doc_id TEXT NOT NULL,

  source_type TEXT NOT NULL, -- upload|url

  source_uri TEXT NOT NULL,

  url TEXT,

  local_path TEXT,

  kind TEXT,

  content_type TEXT,

  content_hash TEXT, -- sha256 hex

  meta_json TEXT,

  created_at INTEGER NOT NULL,

  PRIMARY KEY (tenant_id, source_id)

);



CREATE INDEX IF NOT EXISTS idx_doc_sources_doc

  ON doc_sources(tenant_id, doc_id, created_at);



-- URL cache: reuse downloaded artifacts and map URL -> doc_id.

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



-- Embeddings for semantic retrieval (MVP: vectors stored as JSON arrays in SQLite).

CREATE TABLE IF NOT EXISTS kb_embeddings (

  tenant_id TEXT NOT NULL,

  embedding_id TEXT NOT NULL,

  doc_id TEXT NOT NULL,

  element_id TEXT NOT NULL,

  embedding_type TEXT NOT NULL, -- text|table_summary|caption|transcript

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



CREATE TABLE IF NOT EXISTS kb_jobs (

  tenant_id TEXT NOT NULL,

  job_id TEXT NOT NULL,

  type TEXT NOT NULL, -- ingest|query|reindex|delete

  collection_id TEXT,

  doc_id TEXT,

  status TEXT NOT NULL, -- queued|running|completed|failed|canceled

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

  level TEXT NOT NULL, -- info|warn|error

  message TEXT NOT NULL,

  extra_json TEXT,

  PRIMARY KEY (tenant_id, id)

);



CREATE INDEX IF NOT EXISTS idx_kb_job_events_job

  ON kb_job_events(tenant_id, job_id, ts);



-- Watched directories for auto-ingest

CREATE TABLE IF NOT EXISTS kb_watches (

  tenant_id TEXT NOT NULL,

  watch_id TEXT NOT NULL,

  directory_path TEXT NOT NULL,

  collection_id TEXT NOT NULL DEFAULT 'default',

  recursive INTEGER NOT NULL DEFAULT 1,

  pattern TEXT NOT NULL DEFAULT '*.md',

  enabled INTEGER NOT NULL DEFAULT 1,

  last_synced REAL NOT NULL DEFAULT 0.0,

  PRIMARY KEY (tenant_id, watch_id)

);



-- Connected vaults (direct filesystem link, no copy)

CREATE TABLE IF NOT EXISTS kb_vaults (

  tenant_id TEXT NOT NULL,

  vault_id TEXT NOT NULL,

  vault_path TEXT NOT NULL,

  label TEXT NOT NULL,

  enabled INTEGER NOT NULL DEFAULT 1,

  auto_index INTEGER NOT NULL DEFAULT 1,

  last_indexed REAL NOT NULL DEFAULT 0.0,

  created_at REAL NOT NULL DEFAULT (strftime('%s','now')),

  PRIMARY KEY (tenant_id, vault_id)

);



-- Per-file wiki status within a vault (e.g. ready | wikified | failed)

CREATE TABLE IF NOT EXISTS kb_vault_files (

  vault_id TEXT NOT NULL,

  file_path TEXT NOT NULL,

  status TEXT NOT NULL DEFAULT 'wikified',

  doc_id TEXT NOT NULL DEFAULT '',

  last_wikified_at REAL NOT NULL DEFAULT (strftime('%s','now')),

  PRIMARY KEY (vault_id, file_path)

);

"""





@dataclass

class KBRow:

    tenant_id: str

    row: Dict[str, Any]





def _extract_year(doc_id: str) -> Optional[int]:

    """Extract year (e.g. 2024) from document ID string."""

    import re

    m = re.search(r'(20\d{2})', str(doc_id))

    return int(m.group(1)) if m else None





def _extract_quarter(doc_id: str) -> Optional[int]:

    """Extract quarter (1-4) from document ID string (e.g. Q3)."""

    import re

    m = re.search(r'Q([1-4])', str(doc_id), re.IGNORECASE)

    return int(m.group(1)) if m else None





class KBSqlite:

    def __init__(self, db_path: str):

        self.db_path = db_path



    def connect(self):

        return kb_create_infra_db_client(self.db_path)



    def ensure_schema(self) -> None:

        with self.connect() as conn:

            conn.executescript(SCHEMA_SQL)

            # Migration: add wiki_status column for existing DBs

            try:

                conn.execute("ALTER TABLE documents ADD COLUMN wiki_status TEXT NOT NULL DEFAULT ''")

            except Exception as e:

                logging.debug(str(e), exc_info=True)

            # PR A: add year/quarter columns for time-aware retrieval

            for col in ("year", "quarter"):

                try:

                    conn.execute(

                        f"ALTER TABLE kb_elements ADD COLUMN {col} INTEGER"

                    )

                except Exception:

                    pass  # column already exists  # noqa: schema-idempotent

            conn.commit()

        # FTS5 full-text search on kb_elements (created separately to handle missing fts5 builds)

        self._ensure_fts5()



    def _ensure_fts5(self) -> None:

        """Create FTS5 index on kb_elements.text if not exists."""

        try:

            with self.connect() as conn:

                conn.execute("""

                    CREATE VIRTUAL TABLE IF NOT EXISTS kb_elements_fts 

                    USING fts5(element_id, doc_id, text, tokenize='unicode61')

                """)

            conn.commit()

            # Also insert into FTS5 index for full-text search

            if text and text.strip():  # noqa: F821

                try:

                    conn.execute(

                        "INSERT OR REPLACE INTO kb_elements_fts(rowid, element_id, doc_id, text) "

                        "VALUES((SELECT rowid FROM kb_elements WHERE tenant_id=? AND element_id=?), ?, ?, ?)",

                        (tenant_id, element_id, element_id, doc_id, text),  # noqa: F821

                    )

                    conn.commit()

                except Exception as e:

                    logging.debug(str(e), exc_info=True)

        except Exception as e:

            logging.debug(str(e), exc_info=True)



    def search_fts(self, *, tenant_id: str, query: str, doc_ids: Optional[List[str]] = None,

                   limit: int = 20, year: Optional[int] = None, quarter: Optional[int] = None,

                   ) -> List[Dict[str, Any]]:

        """Full-text search kb_elements via FTS5, filtered by doc_ids + optional time."""

        try:

            import json as _json

            with self.connect() as conn:

                base_sql = """SELECT e.element_id, e.doc_id, e.type, e.page_idx, e.text, e.cells_json,

                                     e.meta_json, fts.rank AS score

                              FROM kb_elements_fts fts

                              JOIN kb_elements e ON fts.rowid = e.rowid

                              WHERE kb_elements_fts MATCH ? AND e.tenant_id = ?"""

                params: list = [query, tenant_id]



                if doc_ids:

                    placeholders = ",".join(["?"] * len(doc_ids))

                    base_sql += f" AND e.doc_id IN ({placeholders})"

                    params += doc_ids



                if year is not None:

                    base_sql += " AND e.year = ?"

                    params.append(int(year))

                if quarter is not None:

                    base_sql += " AND e.quarter = ?"

                    params.append(int(quarter))



                base_sql += " ORDER BY fts.rank LIMIT ?"

                params.append(limit)

                rows = conn.execute(base_sql, params).fetchall()

                result = []

                for r in rows:

                    d = dict(r)

                    if d.get("cells_json"):

                        try:

                            d["cells"] = _json.loads(d["cells_json"])

                        except Exception:

                            logging.getLogger(__name__).debug('search_fts failed', exc_info=True)
                    result.append(d)

                return result

        except Exception:

            return []



    def upsert_collection(self, *, tenant_id: str, collection_id: str, name: str = "") -> None:

        with self.connect() as conn:

            conn.execute(

                "INSERT OR IGNORE INTO collections(tenant_id, collection_id, name, created_at) VALUES(?,?,?,strftime('%s','now'))",

                (tenant_id, collection_id, name or None),

            )

            conn.commit()



    def upsert_document(

        self,

        *,

        tenant_id: str,

        doc_id: str,

        collection_id: str,

        source_uri: str,

        kind: str,

        status: str,

        meta: Optional[Dict[str, Any]] = None,

    ) -> None:

        with self.connect() as conn:

            conn.execute(

                """

                INSERT INTO documents(tenant_id, doc_id, collection_id, source_uri, kind, status, meta_json, created_at)

                VALUES(?,?,?,?,?,?,?,strftime('%s','now'))

                ON CONFLICT(tenant_id, doc_id) DO UPDATE SET

                  collection_id=excluded.collection_id,

                  source_uri=excluded.source_uri,

                  kind=excluded.kind,

                  status=excluded.status,

                  meta_json=excluded.meta_json

                """,

                (tenant_id, doc_id, collection_id, source_uri, kind, status, json.dumps(meta or {}, ensure_ascii=False)),

            )

            conn.commit()



    def insert_asset(

        self,

        *,

        tenant_id: str,

        asset_id: str,

        doc_id: str,

        kind: str,

        local_path: str,

        page_idx: Optional[int] = None,

        time_ms: Optional[int] = None,

        meta: Optional[Dict[str, Any]] = None,

    ) -> None:

        with self.connect() as conn:

            conn.execute(

                """

                INSERT OR REPLACE INTO assets(tenant_id, asset_id, doc_id, kind, local_path, page_idx, time_ms, meta_json, created_at)

                VALUES(?,?,?,?,?,?,?,?,strftime('%s','now'))

                """,

                (

                    tenant_id,

                    asset_id,

                    doc_id,

                    kind,

                    local_path,

                    page_idx,

                    time_ms,

                    json.dumps(meta or {}, ensure_ascii=False),

                ),

            )

            conn.commit()



    def insert_budget_row(

        self,

        *,

        tenant_id: str,

        row_id: str,

        doc_id: str,

        page_idx: int,

        item: str,

        y2026: Optional[float],

        y2027: Optional[float],

        total: Optional[float],

        cells: Dict[str, Any],

    ) -> None:

        with self.connect() as conn:

            conn.execute(

                """

                INSERT OR REPLACE INTO budget_rows(tenant_id, row_id, doc_id, page_idx, item, y2026, y2027, total, cells_json, created_at)

                VALUES(?,?,?,?,?,?,?,?,?,strftime('%s','now'))

                """,

                (tenant_id, row_id, doc_id, page_idx, item, y2026, y2027, total, json.dumps(cells or {}, ensure_ascii=False)),

            )

            conn.commit()



    def insert_element(

        self,

        *,

        tenant_id: str,

        element_id: str,

        doc_id: str,

        type: str,

        page_idx: Optional[int] = None,

        bbox: Optional[Any] = None,

        text: Optional[str] = None,

        cells: Optional[Any] = None,

        asset_id: Optional[str] = None,

        meta: Optional[Dict[str, Any]] = None,

    ) -> None:

        meta = meta or {}

        # PR A: extract year/quarter from doc_id or meta

        year = meta.get("year") or _extract_year(doc_id)

        quarter = meta.get("quarter") or _extract_quarter(doc_id)

        with self.connect() as conn:

            conn.execute(

                """

                INSERT OR REPLACE INTO kb_elements(

                  tenant_id, element_id, doc_id, type, page_idx, bbox_json, text, cells_json, asset_id, meta_json, year, quarter, created_at

                )

                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,strftime('%s','now'))

                """,

                (

                    tenant_id,

                    element_id,

                    doc_id,

                    type,

                    page_idx,

                    json.dumps(bbox, ensure_ascii=False) if bbox is not None else None,

                    text,

                    json.dumps(cells, ensure_ascii=False) if cells is not None else None,

                    asset_id,

                    json.dumps(meta, ensure_ascii=False),

                    year,

                    quarter,

                ),

            )

            conn.commit()



    def insert_elements_batch(self, *, elements: List[Dict[str, Any]]) -> None:

        with self.connect() as conn:

            conn.execute("BEGIN")

            for el in elements:

                doc_id = el.get("doc_id", el.get("element_id", ""))

                year = el.get("year") or _extract_year(doc_id)

                quarter = el.get("quarter") or _extract_quarter(doc_id)

                conn.execute(

                    """

                    INSERT OR REPLACE INTO kb_elements(

                      tenant_id, element_id, doc_id, type, page_idx, bbox_json, text, cells_json, asset_id, meta_json, year, quarter, created_at

                    )

                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,strftime('%s','now'))

                    """,

                    (

                        el["tenant_id"], el["element_id"], doc_id,

                        el["type"], el.get("page_idx"),

                        json.dumps(el.get("bbox"), ensure_ascii=False) if el.get("bbox") is not None else None,

                        el.get("text"),

                        json.dumps(el.get("cells"), ensure_ascii=False) if el.get("cells") is not None else None,

                        el.get("asset_id"),

                        json.dumps(el.get("meta") or {}, ensure_ascii=False),

                        year,

                        quarter,

                    ),

                )

            conn.commit()



    def list_elements(

        self,

        *,

        tenant_id: str,

        doc_id: str,

        type: Optional[str] = None,

        limit: int = 200,

        offset: int = 0,

    ) -> List[Dict[str, Any]]:

        with self.connect() as conn:

            if type:

                rows = conn.execute(

                    """

                    SELECT * FROM kb_elements

                    WHERE tenant_id=? AND doc_id=? AND type=?

                    ORDER BY page_idx ASC, created_at ASC

                    LIMIT ? OFFSET ?

                    """,

                    (tenant_id, doc_id, type, int(limit), int(offset)),

                ).fetchall()

            else:

                rows = conn.execute(

                    """

                    SELECT * FROM kb_elements

                    WHERE tenant_id=? AND doc_id=?

                    ORDER BY page_idx ASC, created_at ASC

                    LIMIT ? OFFSET ?

                    """,

                    (tenant_id, doc_id, int(limit), int(offset)),

                ).fetchall()

        out = []

        for r in rows:

            d = dict(r)

            for k in ("bbox_json", "cells_json", "meta_json"):

                try:

                    d[k.replace("_json", "")] = json.loads(d.get(k) or "{}")

                except Exception:

                    d[k.replace("_json", "")] = {}

                d.pop(k, None)

            out.append(d)

        return out



    def count_elements(self, *, tenant_id: str, doc_id: str) -> int:

        with self.connect() as conn:

            row = conn.execute(

                "SELECT COUNT(1) AS c FROM kb_elements WHERE tenant_id=? AND doc_id=?",

                (tenant_id, doc_id),

            ).fetchone()

        return int(row["c"] or 0) if row else 0



    def insert_doc_source(

        self,

        *,

        tenant_id: str,

        source_id: str,

        doc_id: str,

        source_type: str,

        source_uri: str,

        url: Optional[str] = None,

        local_path: Optional[str] = None,

        kind: Optional[str] = None,

        content_type: Optional[str] = None,

        content_hash: Optional[str] = None,

        meta: Optional[Dict[str, Any]] = None,

    ) -> None:

        with self.connect() as conn:

            conn.execute(

                """

                INSERT OR REPLACE INTO doc_sources(

                  tenant_id, source_id, doc_id, source_type, source_uri, url, local_path,

                  kind, content_type, content_hash, meta_json, created_at

                )

                VALUES(?,?,?,?,?,?,?,?,?,?,?,strftime('%s','now'))

                """,

                (

                    tenant_id,

                    source_id,

                    doc_id,

                    source_type,

                    source_uri,

                    url,

                    local_path,

                    kind,

                    content_type,

                    content_hash,

                    json.dumps(meta or {}, ensure_ascii=False),

                ),

            )

            conn.commit()



    def get_url_cache(self, *, tenant_id: str, url: str) -> Optional[Dict[str, Any]]:

        with self.connect() as conn:

            row = conn.execute(

                "SELECT * FROM url_cache WHERE tenant_id=? AND url=?",

                (tenant_id, url),

            ).fetchone()

        return dict(row) if row else None



    def upsert_url_cache(

        self,

        *,

        tenant_id: str,

        url: str,

        doc_id: str,

        local_path: str,

        kind: Optional[str] = None,

        content_type: Optional[str] = None,

        content_hash: Optional[str] = None,

        etag: Optional[str] = None,

        last_modified: Optional[str] = None,

        meta: Optional[Dict[str, Any]] = None,

    ) -> None:

        with self.connect() as conn:

            conn.execute(

                """

                INSERT OR REPLACE INTO url_cache(

                  tenant_id, url, doc_id, local_path, kind, content_type, content_hash, etag, last_modified, fetched_at, meta_json

                )

                VALUES(?,?,?,?,?,?,?,?,?,strftime('%s','now'),?)

                """,

                (

                    tenant_id,

                    url,

                    doc_id,

                    local_path,

                    kind,

                    content_type,

                    content_hash,

                    etag,

                    last_modified,

                    json.dumps(meta or {}, ensure_ascii=False),

                ),

            )

            conn.commit()



    def insert_embedding(

        self,

        *,

        tenant_id: str,

        embedding_id: str,

        doc_id: str,

        element_id: str,

        embedding_type: str,

        vector: List[float],

        model: Optional[str] = None,

    ) -> None:

        with self.connect() as conn:

            conn.execute(

                """

                INSERT OR REPLACE INTO kb_embeddings(

                  tenant_id, embedding_id, doc_id, element_id, embedding_type, model, dim, vector_json, created_at

                )

                VALUES(?,?,?,?,?,?,?,?,strftime('%s','now'))

                """,

                (

                    tenant_id,

                    embedding_id,

                    doc_id,

                    element_id,

                    embedding_type,

                    model,

                    int(len(vector)),

                    json.dumps(vector, ensure_ascii=False),

                ),

            )

            conn.commit()



    def insert_embeddings_batch(self, *, embeddings: List[Dict[str, Any]]) -> None:

        with self.connect() as conn:

            conn.execute("BEGIN")

            for emb in embeddings:

                conn.execute(

                    """

                    INSERT OR REPLACE INTO kb_embeddings(

                      tenant_id, embedding_id, doc_id, element_id, embedding_type, model, dim, vector_json, created_at

                    )

                    VALUES(?,?,?,?,?,?,?,?,strftime('%s','now'))

                    """,

                    (

                        emb["tenant_id"], emb["embedding_id"], emb["doc_id"],

                        emb["element_id"], emb["embedding_type"], emb.get("model"),

                        int(len(emb["vector"])),

                        json.dumps(emb["vector"], ensure_ascii=False),

                    ),

                )

            conn.commit()



    def list_embeddings_by_doc(

        self,

        *,

        tenant_id: str,

        doc_id: str,

        embedding_type: str = "text",

        limit: int = 20000,

    ) -> List[Dict[str, Any]]:

        with self.connect() as conn:

            rows = conn.execute(

                """

                SELECT element_id, model, dim, vector_json

                FROM kb_embeddings

                WHERE tenant_id=? AND doc_id=? AND embedding_type=?

                ORDER BY created_at ASC

                LIMIT ?

                """,

                (tenant_id, doc_id, embedding_type, int(limit)),

            ).fetchall()

        out: List[Dict[str, Any]] = []

        for r in rows:

            d = dict(r)

            try:

                d["vector"] = json.loads(d.get("vector_json") or "[]")

            except Exception:

                d["vector"] = []

            d.pop("vector_json", None)

            out.append(d)

        return out



    def get_elements_by_ids(self, *, tenant_id: str, element_ids: List[str]) -> Dict[str, Dict[str, Any]]:

        if not element_ids:

            return {}

        with self.connect() as conn:

            placeholders = ",".join(["?"] * len(element_ids))

            rows = conn.execute(

                f"SELECT * FROM kb_elements WHERE tenant_id=? AND element_id IN ({placeholders})",

                (tenant_id, *element_ids),

            ).fetchall()

        out: Dict[str, Dict[str, Any]] = {}

        for r in rows:

            d = dict(r)

            for k in ("bbox_json", "cells_json", "meta_json"):

                try:

                    d[k.replace("_json", "")] = json.loads(d.get(k) or "{}")

                except Exception:

                    d[k.replace("_json", "")] = {}

                d.pop(k, None)

            out[str(d.get("element_id"))] = d

        return out



    def archive_doc_data(self, *, tenant_id: str, doc_id: str) -> None:

        """

        Archive old document elements and embeddings by marking them with version in meta_json.

        Increment document version for new ingest.

        """

        import json as _j

        with self.connect() as conn:

            # Get current version

            cur = conn.execute(

                "SELECT version FROM documents WHERE tenant_id=? AND doc_id=?", (tenant_id, doc_id)

            ).fetchone()

            old_ver = int(cur[0] if cur else 1)

            new_ver = old_ver + 1

            # Mark elements as archived

            conn.execute(

                "UPDATE kb_elements SET meta_json = json_set(COALESCE(meta_json,'{}'),'$.archived',1,'$.version',?) WHERE tenant_id=? AND doc_id=?",

                (old_ver, tenant_id, doc_id),

            )

            conn.execute(

                "UPDATE kb_embeddings SET model = model || ' (v' || ? || ')' WHERE tenant_id=? AND doc_id=?",

                (old_ver, tenant_id, doc_id),

            )

            # Increment document version

            conn.execute(

                "UPDATE documents SET version=? WHERE tenant_id=? AND doc_id=?",

                (new_ver, tenant_id, doc_id),

            )

            conn.commit()

            conn.commit()



    def list_budget_rows(self, *, tenant_id: str, collection_id: str, year: int = 2026) -> List[Dict[str, Any]]:

        """

        从指定 collection 下所有文档聚合预算表行。

        """

        ycol = "y2026" if int(year) == 2026 else "y2027"

        # Filter out obviously non-numeric rows produced by noisy OCR/table detection.

        # Many false positives have all numeric columns NULL; keep only rows with at least one amount.

        amount_filter = "((b.y2026 IS NOT NULL) OR (b.total IS NOT NULL))" if int(year) == 2026 else "((b.y2027 IS NOT NULL) OR (b.total IS NOT NULL))"

        with self.connect() as conn:

            rows = conn.execute(

                f"""

                SELECT b.*, d.source_uri, a.local_path as page_image_path

                FROM budget_rows b

                JOIN documents d ON d.tenant_id=b.tenant_id AND d.doc_id=b.doc_id

                LEFT JOIN assets a ON a.tenant_id=b.tenant_id AND a.doc_id=b.doc_id AND a.kind='page_image' AND a.page_idx=b.page_idx

                WHERE b.tenant_id=? AND d.collection_id=? AND {amount_filter}

                ORDER BY b.page_idx ASC, b.item ASC

                """,

                (tenant_id, collection_id),

            ).fetchall()



        out: List[Dict[str, Any]] = []

        for r in rows:

            d = dict(r)

            try:

                d["cells"] = json.loads(d.get("cells_json") or "{}")

            except Exception:

                d["cells"] = {}

            d.pop("cells_json", None)

            out.append(d)

        return out



    def create_job(

        self,

        *,

        tenant_id: str,

        job_id: str,

        type: str,

        collection_id: Optional[str] = None,

        doc_id: Optional[str] = None,

        status: str = "queued",

        progress: Optional[float] = None,

        message: str = "",

        input: Optional[Dict[str, Any]] = None,

    ) -> None:

        with self.connect() as conn:

            conn.execute(

                """

                INSERT OR REPLACE INTO kb_jobs(

                  tenant_id, job_id, type, collection_id, doc_id, status, progress, message,

                  input_json, output_json, error_json, created_at, updated_at

                )

                VALUES(?,?,?,?,?,?,?,?,?,?,?,strftime('%s','now'),strftime('%s','now'))

                """,

                (

                    tenant_id,

                    job_id,

                    type,

                    collection_id,

                    doc_id,

                    status,

                    progress,

                    message or None,

                    json.dumps(input or {}, ensure_ascii=False),

                    None,

                    None,

                ),

            )

            conn.commit()



    def update_job(

        self,

        *,

        tenant_id: str,

        job_id: str,

        status: Optional[str] = None,

        progress: Optional[float] = None,

        message: Optional[str] = None,

        output: Optional[Dict[str, Any]] = None,

        error: Optional[Dict[str, Any]] = None,

    ) -> None:

        sets: List[str] = ["updated_at=strftime('%s','now')"]

        vals: List[Any] = []

        if status is not None:

            sets.append("status=?")

            vals.append(status)

        if progress is not None:

            sets.append("progress=?")

            vals.append(progress)

        if message is not None:

            sets.append("message=?")

            vals.append(message)

        if output is not None:

            sets.append("output_json=?")

            vals.append(json.dumps(output, ensure_ascii=False))

        if error is not None:

            sets.append("error_json=?")

            vals.append(json.dumps(error, ensure_ascii=False))

        if len(sets) == 1:

            return

        with self.connect() as conn:

            conn.execute(

                f"UPDATE kb_jobs SET {', '.join(sets)} WHERE tenant_id=? AND job_id=?",

                (*vals, tenant_id, job_id),

            )

            conn.commit()



    def get_job(self, *, tenant_id: str, job_id: str) -> Optional[Dict[str, Any]]:

        with self.connect() as conn:

            row = conn.execute(

                "SELECT * FROM kb_jobs WHERE tenant_id=? AND job_id=?",

                (tenant_id, job_id),

            ).fetchone()

        if not row:

            return None

        d = dict(row)

        for k in ("input_json", "output_json", "error_json"):

            try:

                d[k.replace("_json", "")] = json.loads(d.get(k) or "{}")

            except Exception:

                d[k.replace("_json", "")] = {}

            d.pop(k, None)

        return d



    def append_job_event(

        self,

        *,

        tenant_id: str,

        job_id: str,

        level: str,

        message: str,

        extra: Optional[Dict[str, Any]] = None,

        event_id: Optional[str] = None,

        ts: Optional[int] = None,

    ) -> None:

        import time



        eid = event_id or new_prefixed_id("kbevt")

        tsv = int(ts or time.time())

        with self.connect() as conn:

            conn.execute(

                """

                INSERT OR REPLACE INTO kb_job_events(tenant_id, id, job_id, ts, level, message, extra_json)

                VALUES(?,?,?,?,?,?,?)

                """,

                (tenant_id, eid, job_id, tsv, level, message, json.dumps(extra or {}, ensure_ascii=False)),

            )

            conn.commit()



    def list_job_events(self, *, tenant_id: str, job_id: str, limit: int = 200, offset: int = 0) -> Dict[str, Any]:

        with self.connect() as conn:

            total = (

                conn.execute(

                    "SELECT COUNT(1) as c FROM kb_job_events WHERE tenant_id=? AND job_id=?",

                    (tenant_id, job_id),

                ).fetchone()["c"]

                or 0

            )

            rows = conn.execute(

                """

                SELECT ts, level, message, extra_json

                FROM kb_job_events

                WHERE tenant_id=? AND job_id=?

                ORDER BY ts ASC

                LIMIT ? OFFSET ?

                """,

                (tenant_id, job_id, int(limit), int(offset)),

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

        return {"items": items, "total": int(total)}



    # ── Watched Directories ──



    def upsert_watch(self, *, tenant_id: str, watch_id: str, directory_path: str, collection_id: str = "default", recursive: bool = True, pattern: str = "*.md", enabled: bool = True) -> None:

        with self.connect() as conn:

            conn.execute(

                """INSERT OR REPLACE INTO kb_watches (tenant_id, watch_id, directory_path, collection_id, recursive, pattern, enabled, last_synced)

                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",

                (tenant_id, watch_id, directory_path, collection_id, int(recursive), pattern, int(enabled), 0.0),

            )

            conn.commit()



    def delete_watch(self, *, tenant_id: str, watch_id: str) -> None:

        with self.connect() as conn:

            conn.execute("DELETE FROM kb_watches WHERE tenant_id=? AND watch_id=?", (tenant_id, watch_id))

            conn.commit()



    def list_watches(self, *, tenant_id: str, enabled_only: bool = True) -> List[Dict[str, Any]]:

        with self.connect() as conn:

            if enabled_only:

                rows = conn.execute(

                    "SELECT * FROM kb_watches WHERE tenant_id=? AND enabled=1", (tenant_id,)

                ).fetchall()

            else:

                rows = conn.execute(

                    "SELECT * FROM kb_watches WHERE tenant_id=?", (tenant_id,)

                ).fetchall()

        return [dict(r) for r in rows]



    def touch_watch(self, *, tenant_id: str, watch_id: str) -> None:

        import time

        with self.connect() as conn:

            conn.execute(

                "UPDATE kb_watches SET last_synced=? WHERE tenant_id=? AND watch_id=?",

                (time.time(), tenant_id, watch_id),

            )

            conn.commit()



    # ── Connected Vaults ──



    def upsert_vault(self, *, tenant_id: str, vault_id: str, vault_path: str, label: str = "", auto_index: bool = True) -> None:

        with self.connect() as conn:

            conn.execute(

                """INSERT OR REPLACE INTO kb_vaults (tenant_id, vault_id, vault_path, label, auto_index)

                   VALUES (?, ?, ?, ?, ?)""",

                (tenant_id, vault_id, vault_path, label or vault_path.split("/")[-1], int(auto_index)),

            )

            conn.commit()



    def delete_vault(self, *, tenant_id: str, vault_id: str) -> None:

        with self.connect() as conn:

            conn.execute("DELETE FROM kb_vaults WHERE tenant_id=? AND vault_id=?", (tenant_id, vault_id))

            conn.commit()



    def list_vaults(self, *, tenant_id: str) -> List[Dict[str, Any]]:

        with self.connect() as conn:

            rows = conn.execute(

                "SELECT * FROM kb_vaults WHERE tenant_id=? ORDER BY created_at DESC", (tenant_id,)

            ).fetchall()

        return [dict(r) for r in rows]



    def get_vault(self, *, tenant_id: str, vault_id: str) -> Optional[Dict[str, Any]]:

        with self.connect() as conn:

            row = conn.execute(

                "SELECT * FROM kb_vaults WHERE tenant_id=? AND vault_id=?", (tenant_id, vault_id)

            ).fetchone()

        return dict(row) if row else None



    def touch_vault(self, *, tenant_id: str, vault_id: str) -> None:

        import time

        with self.connect() as conn:

            conn.execute(

                "UPDATE kb_vaults SET last_indexed=? WHERE tenant_id=? AND vault_id=?",

                (time.time(), tenant_id, vault_id),

            )

            conn.commit()



    def upsert_vault_file(self, *, vault_id: str, file_path: str, doc_id: str) -> None:

        """Record that a vault file has been wikified."""

        import time

        with self.connect() as conn:

            conn.execute(

                "INSERT OR REPLACE INTO kb_vault_files(vault_id, file_path, status, doc_id, last_wikified_at) "

                "VALUES(?, ?, 'wikified', ?, ?)",

                (vault_id, file_path, doc_id, time.time()),

            )

            conn.commit()



    def upsert_vault_file_failed(self, *, vault_id: str, file_path: str, error: str = "") -> None:

        """Record that a vault file failed wiki conversion."""

        import time

        with self.connect() as conn:

            conn.execute(

                "INSERT OR REPLACE INTO kb_vault_files(vault_id, file_path, status, doc_id, last_wikified_at) "

                "VALUES(?, ?, 'failed', ?, ?)",

                (vault_id, file_path, error[:200], time.time()),

            )

            conn.commit()



    def get_vault_file_statuses(self, *, vault_id: str) -> dict:

        """Return {file_path: status} map for a vault."""

        with self.connect() as conn:

            rows = conn.execute(

                "SELECT file_path, status FROM kb_vault_files WHERE vault_id=?",

                (vault_id,),

            ).fetchall()

        return {r["file_path"]: r["status"] for r in rows}

