"""python -m app.worker — B2-L local worker loop entry."""
from __future__ import annotations

import json
import signal
import sys

from app.config import load_config
from app.store.migrate import apply_migrations
from app.worker.loop import WorkerLoopResult, load_worker_env, run_worker_loop


def main(argv: list[str] | None = None) -> int:
    _ = argv
    cfg = load_config()
    apply_migrations(cfg.db_url)
    knobs = load_worker_env()
    stop = {"flag": False}

    def _handle(_signum, _frame) -> None:
        stop["flag"] = True

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    # Daemon default: stop after idle rounds if MAX_IDLE set; else until signal.
    if knobs["max_jobs"] is None and knobs["max_idle_rounds"] is None:
        knobs["max_idle_rounds"] = None  # run until signal

    print(
        json.dumps(
            {
                "event": "worker_start",
                "db_url": cfg.db_url.split("@")[-1] if "@" in cfg.db_url else cfg.db_url,
                "worker_id": knobs["worker_id"],
                "process_split_authorized": False,
                "environment": "local",
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    result: WorkerLoopResult = run_worker_loop(
        cfg.db_url,
        worker_id=knobs["worker_id"],
        idle_sleep_s=knobs["idle_sleep_s"],
        max_jobs=knobs["max_jobs"],
        max_idle_rounds=knobs["max_idle_rounds"],
        lease_seconds=knobs["lease_seconds"],
        max_attempts=knobs["max_attempts"],
        should_stop=lambda: stop["flag"],
    )
    print(
        json.dumps(
            {
                "event": "worker_stop",
                "processed": result.processed,
                "idle_rounds": result.idle_rounds,
                "stopped_reason": result.stopped_reason,
                "process_split_authorized": False,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
