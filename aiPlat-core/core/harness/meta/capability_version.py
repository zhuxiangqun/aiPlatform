"""Resolve five-capability package versions (A2 SSOT).

SSOT: reports/five-products/versions.yaml
Fallback: packages/aiplat-*/package.json then \"0.0.0\".
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

_CAP_TO_PACKAGE = {
    "aiplat": "aiplat-central",
    "pi": "aiplat-pi-runtime",
    "ontology": "aiplat-ontology",
    "evaluation": "aiplat-evaluation",
    "fde": "aiplat-fde",
}


def _repo_root() -> Path:
    # Prefer walk-up to versions.yaml; else aiPlat-core/core/harness/meta → parents[4]
    here = Path(__file__).resolve()
    for p in [here] + list(here.parents):
        if (p / "reports" / "five-products" / "versions.yaml").is_file():
            return p
        if (p / "packages" / "aiplat-central" / "package.json").is_file():
            return p
    return here.parents[4]


@lru_cache(maxsize=1)
def load_versions_ssot() -> Dict[str, str]:
    root = _repo_root()
    path = root / "reports" / "five-products" / "versions.yaml"
    out: Dict[str, str] = {}
    if not path.is_file():
        return out
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        for c in data.get("capabilities") or []:
            cid = str((c or {}).get("id") or "").strip()
            ver = str((c or {}).get("version") or "").strip()
            if cid and ver:
                out[cid] = ver
        return out
    except Exception:
        # Minimal line scan: blocks with id: / version:
        cur: Optional[str] = None
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("- id:"):
                cur = s.split(":", 1)[1].strip().strip('"').strip("'")
            elif s.startswith("version:") and cur:
                out[cur] = s.split(":", 1)[1].strip().strip('"').strip("'")
                cur = None
        return out


def _package_json_version(capability_id: str) -> str:
    pkg = _CAP_TO_PACKAGE.get(str(capability_id or "").strip())
    if not pkg:
        return ""
    path = _repo_root() / "packages" / pkg / "package.json"
    if not path.is_file():
        return ""
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("version") or "")
    except Exception:
        return ""


def resolve_capability_version(capability_id: str, *, default: str = "0.0.0") -> str:
    """Return semver for a capability id (aiplat|pi|ontology|evaluation|fde)."""
    cid = str(capability_id or "").strip().lower()
    if not cid:
        return default
    ssot = load_versions_ssot()
    if cid in ssot and ssot[cid]:
        return ssot[cid]
    pkg_ver = _package_json_version(cid)
    return pkg_ver or default
