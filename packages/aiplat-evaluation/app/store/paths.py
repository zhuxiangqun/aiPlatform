"""Parse AIPLAT_EVAL_DB_URL into a local SQLite filesystem path."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote


def sqlite_path_from_url(db_url: str) -> Path:
    """Resolve sqlite URL / bare path to a Path (SQLAlchemy-compatible).

    Accepts:
      - sqlite:///relative.db          → relative.db
      - sqlite:///./data/x.db          → ./data/x.db
      - sqlite:////abs/path.db         → /abs/path.db
      - bare relative/absolute paths
    Rejects non-sqlite schemes (PG reserved for later).
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
            f"A2 local store supports sqlite only; got scheme={scheme!r}. "
            "Postgres wiring is out of A2 scope."
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
