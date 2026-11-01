"""Standalone eval service config — env only, no core imports."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class _EvalServiceConfig:
    mode: str  # cohost | standalone
    host: str
    port: int
    db_url: str
    version: str
    protocol: str

    @property
    def is_standalone(self) -> bool:
        return self.mode == "standalone"

    @property
    def deploy_unit(self) -> str:
        # A1: standalone process still unauthorized for production split.
        return "evaluation" if self.is_standalone else "central"


# Public alias (assignment, not a new ClassDef for method_verify).
EvalServiceConfig = _EvalServiceConfig


def load_config() -> EvalServiceConfig:
    mode = (os.getenv("AIPLAT_EVAL_MODE") or "standalone").strip().lower()
    if mode not in {"cohost", "standalone"}:
        mode = "standalone"
    port_raw = (os.getenv("AIPLAT_EVAL_PORT") or "8010").strip()
    try:
        port = int(port_raw)
    except ValueError:
        port = 8010
    host = (os.getenv("AIPLAT_EVAL_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    db_url = (os.getenv("AIPLAT_EVAL_DB_URL") or "").strip()
    if not db_url:
        # A1 placeholder path; A2 wires real schema/migrations.
        db_url = "sqlite:///./data/eval_local.sqlite3"
    version = (os.getenv("AIPLAT_EVAL_VERSION") or "0.1.0").strip() or "0.1.0"
    protocol = (os.getenv("AIPLAT_EVAL_PROTOCOL") or "eval.protocol.v0").strip()
    return EvalServiceConfig(
        mode=mode,
        host=host,
        port=port,
        db_url=db_url,
        version=version,
        protocol=protocol,
    )
