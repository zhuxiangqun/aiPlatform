#!/usr/bin/env python3
"""FDE audit_schema.v1 ↔ ActionStore mapping (Phase 1).

Default: --dry-run (does not alter any database).

Usage:
  python3 scripts/fde_audit_mapping.py
  python3 scripts/fde_audit_mapping.py --db ./data/execution_store.db --out docs/contracts/audit_mapping_report.md
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "aiPlat-core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from core.harness.infrastructure.action_audit_validate import (  # noqa: E402
    ACTION_AUDIT_COLUMNS,
    build_add_column_sql,
    build_rollback_sql,
    classify_audit_fields,
    render_mapping_report,
)


def _pragma_columns(db_path: Path) -> set[str]:
    if not db_path.is_file():
        return set(ACTION_AUDIT_COLUMNS)
    con = sqlite3.connect(str(db_path))
    try:
        rows = con.execute("PRAGMA table_info(action_audit)").fetchall()
        if not rows:
            return set(ACTION_AUDIT_COLUMNS)
        # PRAGMA table_info: cid, name, type, notnull, dflt_value, pk
        return {r[1] for r in rows}
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="audit_schema ↔ ActionStore mapping dry-run")
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Optional SQLite path; when omitted uses ActionStore schema constants",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "docs" / "contracts" / "audit_mapping_report.md",
        help="Markdown report output path",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply ADD COLUMN NULL (forbidden by default; Phase 1 uses dry-run only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Do not modify DB (default)",
    )
    args = parser.parse_args(argv)

    columns = _pragma_columns(args.db) if args.db else set(ACTION_AUDIT_COLUMNS)
    clf = classify_audit_fields(columns=columns)
    report = render_mapping_report(clf, columns=columns)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nWrote {args.out}")

    if args.apply:
        if not args.db:
            print("ERROR: --apply requires --db", file=sys.stderr)
            return 2
        print("ERROR: Phase 1 forbids destructive apply; use JSON embed. Refusing.", file=sys.stderr)
        print("ADD SQL (manual Phase 2):\n" + "\n".join(build_add_column_sql(clf)), file=sys.stderr)
        print("ROLLBACK:\n" + "\n".join(build_rollback_sql()), file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
