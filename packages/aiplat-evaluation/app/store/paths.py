"""Parse AIPLAT_EVAL_DB_URL into backend + SQLite path / Postgres DSN."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse, urlunparse


def backend_from_url(db_url: str) -> str:
    """Return 'sqlite' or 'postgres' for the given AIPLAT_EVAL_DB_URL."""
    raw = (db_url or "").strip()
    if not raw:
        raise ValueError("empty AIPLAT_EVAL_DB_URL")
    if "://" not in raw:
        return "sqlite"
    scheme = raw.split(":", 1)[0].lower()
    if scheme in {"sqlite", "file"}:
        return "sqlite"
    if scheme in {"postgres", "postgresql", "postgresql+asyncpg", "postgresql+psycopg"}:
        return "postgres"
    raise ValueError(
        f"unsupported AIPLAT_EVAL_DB_URL scheme={scheme!r}; "
        "use sqlite:///… or postgresql://…"
    )


def postgres_dsn_from_url(db_url: str) -> str:
    """Normalize postgres URL to a plain postgresql:// DSN for asyncpg."""
    raw = (db_url or "").strip()
    if backend_from_url(raw) != "postgres":
        raise ValueError(f"not a postgres URL: {db_url!r}")
    # Strip SQLAlchemy driver suffixes: postgresql+asyncpg:// → postgresql://
    if raw.lower().startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgresql+psycopg2://"):
        if raw.lower().startswith(prefix):
            raw = "postgresql://" + raw[len(prefix) :]
            break
    return raw


def redact_db_url(db_url: str) -> str:
    """Hide password in health payloads."""
    raw = (db_url or "").strip()
    if "://" not in raw or backend_from_url(raw) != "postgres":
        return raw
    dsn = postgres_dsn_from_url(raw)
    parsed = urlparse(dsn)
    if not parsed.password:
        return dsn
    user = parsed.username or ""
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{user}:***@{host}{port}"
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
    )


def sqlite_path_from_url(db_url: str) -> Path:
    """Resolve sqlite URL / bare path to a Path (SQLAlchemy-compatible).

    Accepts:
      - sqlite:///relative.db          → relative.db
      - sqlite:///./data/x.db          → ./data/x.db
      - sqlite:////abs/path.db         → /abs/path.db
      - bare relative/absolute paths
    Rejects non-sqlite schemes (use backend_from_url + postgres_dsn_from_url).
    """
    raw = (db_url or "").strip()
    if not raw:
        raise ValueError("empty AIPLAT_EVAL_DB_URL")

    if "://" not in raw:
        return Path(raw).expanduser()

    lower = raw.lower()
    if lower.startswith("file:"):
        # file:///abs or file:./rel — strip scheme
        rest = raw.split(":", 1)[1]
        if rest.startswith("///"):
            return Path(unquote(rest[2:])).expanduser()  # file:///abs → /abs
        return Path(unquote(rest.lstrip("/"))).expanduser()

    if not lower.startswith("sqlite:"):
        scheme = raw.split(":", 1)[0]
        raise ValueError(
            f"sqlite_path_from_url expects sqlite; got scheme={scheme!r}. "
            "Use postgres_dsn_from_url for postgresql:// URLs."
        )

    # sqlite:////abs/path → absolute (4+ slashes after sqlite:)
    if raw.startswith("sqlite:////"):
        return Path(unquote(raw[len("sqlite:///") :])).expanduser()

    # sqlite:///relative → relative (exactly 3 slashes)
    if raw.startswith("sqlite:///"):
        rest = unquote(raw[len("sqlite:///") :])
        if rest == ":memory:":
            raise ValueError("in-memory sqlite is not supported for A2 local store")
        return Path(rest).expanduser()

    raise ValueError(f"unsupported sqlite URL: {db_url!r}")


# Module-level call site for method_verify same-file wiring.
_DEFAULT_SQLITE_PROBE = sqlite_path_from_url("sqlite:///./data/eval_local.sqlite3")
_ = backend_from_url("postgresql://eval:eval_local@127.0.0.1:5433/eval")
_ = redact_db_url("postgresql://eval:eval_local@127.0.0.1:5433/eval")
