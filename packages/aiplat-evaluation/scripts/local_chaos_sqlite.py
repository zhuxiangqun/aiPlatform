#!/usr/bin/env python3
"""SQLite local chaos: backup → crash simulation → restore (accuracy_claim=false).

Does not flip process_split_authorized. Not staging / PITR / production cert.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _rowcount(db: Path) -> int:
    with sqlite3.connect(db) as c:
        return int(c.execute("SELECT count(*) FROM chaos_runs").fetchone()[0])


def _seed(db: Path, n: int = 5) -> None:
    if db.exists():
        db.unlink()
    with sqlite3.connect(db) as c:
        c.execute(
            "CREATE TABLE chaos_runs ("
            "id INTEGER PRIMARY KEY, task_id TEXT, status TEXT)"
        )
        for i in range(n):
            c.execute(
                "INSERT INTO chaos_runs(task_id, status) VALUES (?, ?)",
                (f"chaos-{i}", "ok"),
            )
        c.commit()


def _backup(db: Path, bak: Path) -> int:
    with sqlite3.connect(db) as c, bak.open("w", encoding="utf-8") as f:
        for line in c.iterdump():
            f.write(line + "\n")
    return bak.stat().st_size


def _restore(bak: Path, db: Path) -> int:
    if db.exists():
        db.unlink()
    with sqlite3.connect(db) as c:
        c.executescript(bak.read_text(encoding="utf-8"))
        c.commit()
    return _rowcount(db)


def run_chaos(work: Path) -> Dict[str, Any]:
    """Run three local chaos scenarios; return aggregate-safe payload."""
    work.mkdir(parents=True, exist_ok=True)
    db = work / "chaos.sqlite3"
    bak = work / "chaos_backup.sql"
    scenarios: List[Dict[str, Any]] = []

    # 1) seed + backup
    _seed(db, n=5)
    before = _rowcount(db)
    bak_bytes = _backup(db, bak)
    scenarios.append(
        {
            "id": "seed_backup",
            "ok": before == 5 and bak_bytes > 0,
            "rows": before,
            "backup_bytes": bak_bytes,
        }
    )

    # 2) crash sim: unlink live DB then restore from backup
    db.unlink()
    assert not db.exists()
    after_crash = _restore(bak, db)
    scenarios.append(
        {
            "id": "crash_unlink_restore",
            "ok": after_crash == before,
            "rows": after_crash,
        }
    )

    # 3) corruption sim: wipe rows, then restore
    with sqlite3.connect(db) as c:
        c.execute("DELETE FROM chaos_runs")
        c.commit()
    assert _rowcount(db) == 0
    after_wipe = _restore(bak, db)
    scenarios.append(
        {
            "id": "wipe_restore",
            "ok": after_wipe == before,
            "rows": after_wipe,
        }
    )

    # 4) partial-restore recover: start empty DB, apply truncated dump, then full restore
    partial = work / "partial.sql"
    lines = bak.read_text(encoding="utf-8").splitlines()
    # Keep schema+begin but drop INSERT lines → empty table after "partial"
    partial.write_text(
        "\n".join(ln for ln in lines if not ln.startswith("INSERT")) + "\n",
        encoding="utf-8",
    )
    bad = work / "partial.sqlite3"
    with sqlite3.connect(bad) as c:
        c.executescript(partial.read_text(encoding="utf-8"))
        c.commit()
        partial_n = int(c.execute("SELECT count(*) FROM chaos_runs").fetchone()[0])
    recovered = _restore(bak, bad)
    scenarios.append(
        {
            "id": "partial_then_full_restore",
            "ok": partial_n == 0 and recovered == before,
            "partial_rows": partial_n,
            "recovered_rows": recovered,
        }
    )

    all_ok = all(bool(s.get("ok")) for s in scenarios)
    return {
        "schema": "eval.local_chaos.aggregate.v1",
        "product_id": "evaluation",
        "environment": "local",
        "backend": "sqlite",
        "accuracy_claim": False,
        "not_accuracy_certification": True,
        "not_staging_evidence": True,
        "process_split_authorized": False,
        "gate_ok": all_ok,
        "scenarios": scenarios,
        "honesty": (
            "local SQLite chaos backup/restore only — "
            "≠ staging; ≠ PITR; ≠ process_split authorize; accuracy_claim=false"
        ),
        "recorded_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="SQLite local chaos drill")
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    payload = run_chaos(args.work)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "gate": "ok" if payload["gate_ok"] else "fail",
                "backend": "sqlite",
                "scenarios_ok": sum(1 for s in payload["scenarios"] if s.get("ok")),
                "out": str(args.out),
                "accuracy_claim": False,
                "process_split_authorized": False,
            },
            ensure_ascii=False,
        )
    )
    return 0 if payload["gate_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
