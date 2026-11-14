#!/usr/bin/env python3
"""P0-IR contacts SoT loader / validator.

Looks up (in order):
  1. AIPLAT_IR_CONTACTS_PATH
  2. security/ir/contacts.local.yaml
  3. ~/.aiplat/security/ir_contacts.yaml

Example templates are never treated as filled.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ROLES = (
    "security_owner",
    "platform_oncall",
    "ops_infra",
    "exec_sponsor",
)
SCHEMA = "aiplat.ir_contacts.v1"


def _try_yaml_load(text: str) -> Any:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except Exception:
        # Minimal fallback: only support our flat example via json if someone saved json
        return json.loads(text)


def candidate_paths() -> List[Path]:
    """Lookup order. If AIPLAT_IR_CONTACTS_PATH is set, it is the only candidate."""
    env = (os.getenv("AIPLAT_IR_CONTACTS_PATH") or "").strip()
    if env:
        return [Path(env)]
    out: List[Path] = [
        ROOT / "security" / "ir" / "contacts.local.yaml",
    ]
    home = Path(os.getenv("AIPLAT_HOME") or (Path.home() / ".aiplat"))
    out.append(home / "security" / "ir_contacts.yaml")
    return out


def resolve_contacts_path() -> Optional[Path]:
    """resolve_contacts_path。
    """
    for p in candidate_paths():
        if p.is_file():
            return p
    return None


def load_contacts(*, path: Optional[Path] = None) -> Dict[str, Any]:
    """load_contacts。

    Args:
        path: 路径。
    """
    if path is not None:
        p: Optional[Path] = Path(path)
    else:
        env = (os.getenv("AIPLAT_IR_CONTACTS_PATH") or "").strip()
        if env:
            # Explicit override is exclusive: missing file → not filled (no fallback)
            p = Path(env)
            if not p.is_file():
                return {
                    "schema": SCHEMA,
                    "ok": False,
                    "filled": False,
                    "error": "contacts_file_missing",
                    "path": str(p),
                    "candidates": [str(p)],
                    "security_certification": False,
                }
        else:
            p = resolve_contacts_path()
    if p is None:
        return {
            "schema": SCHEMA,
            "ok": False,
            "filled": False,
            "error": "contacts_file_missing",
            "candidates": [str(x) for x in candidate_paths()],
            "security_certification": False,
        }
    raw = _try_yaml_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        return {
            "schema": SCHEMA,
            "ok": False,
            "filled": False,
            "error": "contacts_not_object",
            "path": str(p),
            "security_certification": False,
        }
    return validate_contacts(dict(raw), path=p)


def _blank(v: Any) -> bool:
    s = str(v or "").strip()
    return (not s) or s.upper() in {"TBD", "_TBD_", "TODO", "N/A", "-"}


def validate_contacts(data: Mapping[str, Any], *, path: Optional[Path] = None) -> Dict[str, Any]:
    """validate_contacts。

    Args:
        data: data 参数。
        path: 路径。
    """
    errors: List[str] = []
    if str(data.get("schema") or "") != SCHEMA:
        errors.append(f"schema_mismatch:{data.get('schema')}")
    roles = data.get("roles") if isinstance(data.get("roles"), Mapping) else {}
    missing_roles = [r for r in REQUIRED_ROLES if r not in roles]
    if missing_roles:
        errors.append(f"roles_missing:{','.join(missing_roles)}")
    blanks: List[str] = []
    for role in REQUIRED_ROLES:
        row = roles.get(role) if isinstance(roles.get(role), Mapping) else {}
        if _blank(row.get("name")) or _blank(row.get("channel")):
            blanks.append(role)
    if blanks:
        errors.append(f"blank_or_tbd:{','.join(blanks)}")
    filled = not errors
    return {
        "schema": SCHEMA,
        "ok": filled,
        "filled": filled,
        "path": str(path) if path else None,
        "errors": errors,
        "roles_present": sorted(str(k) for k in roles.keys()),
        "updated_at": data.get("updated_at"),
        "security_certification": False,
        "accuracy_claim": False,
        "honesty": "Filled contacts ≠ IR maturity / certification.",
    }


def main() -> int:
    """main。
    """
    report = load_contacts()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report.get("filled"):
        print("FAIL: IR contacts not filled (see security/ir/contacts.example.yaml)", file=sys.stderr)
        return 1
    print("OK: IR contacts filled", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
