#!/usr/bin/env python3
"""Emit/refresh B4-S staging scaffold drill template (unsigned only).

Refuses environment=staging or production_signed=true without explicit
proof env vars that are intentionally not set in scaffold mode.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# Tracked template (docs/a3/drills/ is gitignored for live evidence only).
OUT = (
    ROOT
    / "packages"
    / "aiplat-evaluation"
    / "docs"
    / "a3"
    / "templates"
    / "live-scaffold-b4s-staging-template.v0.json"
)


def _refuse(msg: str) -> int:
    print(f"REFUSED: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    """写出未签名 scaffold 模板；拒绝伪装 staging / 签名。

    Returns:
        进程退出码；0 表示写出成功。
    """
    want_staging = os.environ.get("AIPLAT_EVAL_B4S_CLAIM_STAGING", "").strip() in {
        "1",
        "true",
        "yes",
    }
    want_signed = os.environ.get("AIPLAT_EVAL_B4S_CLAIM_SIGNED", "").strip() in {
        "1",
        "true",
        "yes",
    }
    # Scaffold emit never accepts these claims — live path is separate.
    if want_staging:
        return _refuse(
            "scaffold emit cannot set environment=staging "
            "(unset AIPLAT_EVAL_B4S_CLAIM_STAGING; use real-host live path)"
        )
    if want_signed:
        return _refuse(
            "scaffold emit cannot set production_signed=true "
            "(unset AIPLAT_EVAL_B4S_CLAIM_SIGNED; use a3 live sign on real host)"
        )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "kind": "evaluation_a3_live_drill_evidence",
        "schema_version": "aiplat.evaluation.a3.live_drill.v0",
        "drill_id": "scaffold-b4s-staging-template-v0",
        "environment": "scaffold",
        "operator": "scaffold-bot",
        "recorded_at": now,
        "production_signed": False,
        "does_not_authorize_process_split": True,
        "host": {
            "host_id": os.environ.get("AIPLAT_EVAL_B4S_HOST_ID_PLACEHOLDER", ""),
            "confirmed": False,
            "note": (
                "Fill only after owner names independent staging host; "
                "keep environment=scaffold until live."
            ),
        },
        "endpoints": {
            "jwks_url": "",
            "object_store_endpoint": "",
            "pg_dsn_redacted": "",
        },
        "items": {
            "host_confirmed": {"done": False, "evidence": ""},
            "jwks_reachable": {"done": False, "evidence": ""},
            "object_store_reachable": {"done": False, "evidence": ""},
            "pitr_backup_restore_rollback": {"done": False, "evidence": ""},
            "healthz_protocol": {"done": False, "evidence": ""},
            "network_isolated_from_prod_central": {"done": False, "evidence": ""},
        },
        "honesty": (
            "Unsigned scaffold template. Not staging. Not production_signed. "
            "Does not authorize Chart flip."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} environment=scaffold production_signed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
