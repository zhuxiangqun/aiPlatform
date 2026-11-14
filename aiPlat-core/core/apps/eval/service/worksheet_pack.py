"""EVAL human worksheet pack facilitation — generate/list/read; never accuracy.

Wraps packages/aiplat-evaluation/scripts/human_worksheet_pack.py.
Annotator sheets ≠ facilitator (gold hints). accuracy_claim stays false.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional, Tuple

_STAMP_RE = re.compile(r"^\d{8}T\d{6}Z$")
_SAFE_FILE_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _pack_root() -> Path:
    return (
        _repo_root()
        / "packages"
        / "aiplat-evaluation"
        / "docs"
        / "a3"
        / "human_pack"
    )


def _script_path() -> Path:
    return (
        _repo_root()
        / "packages"
        / "aiplat-evaluation"
        / "scripts"
        / "human_worksheet_pack.py"
    )


def _load_pack_module() -> ModuleType:
    path = _script_path()
    if not path.is_file():
        raise FileNotFoundError(f"missing worksheet pack script: {path}")
    spec = importlib.util.spec_from_file_location("aiplat_human_worksheet_pack", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _audience_for(name: str) -> str:
    n = name.lower()
    if "facilitator" in n or name == "model_outputs.json":
        return "facilitator_only"
    if "annotator" in n:
        return "annotator"
    if name.endswith(".md") or name == "MANIFEST.json":
        return "ops"
    return "ops"


def worksheet_pack_status(*, tenant_id: str = "eval-v1", limit: int = 20) -> Dict[str, Any]:
    """List existing human_pack stamps (facilitation; not an accuracy claim).

    Args:
        tenant_id: 租户 ID。
        limit: 返回条数上限。
    """
    root = _pack_root()
    packs: List[Dict[str, Any]] = []
    if root.is_dir():
        stamps = sorted(
            (p for p in root.iterdir() if p.is_dir() and _STAMP_RE.match(p.name)),
            key=lambda p: p.name,
            reverse=True,
        )
        for p in stamps[: max(1, min(limit, 100))]:
            files = sorted(f.name for f in p.iterdir() if f.is_file())
            man = None
            man_path = p / "MANIFEST.json"
            if man_path.is_file():
                try:
                    man = json.loads(man_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    man = None
            packs.append(
                {
                    "stamp": p.name,
                    "path": str(p),
                    "files": files,
                    "g2b_task_n": (man or {}).get("g2b_task_n") if isinstance(man, dict) else None,
                    "preference_pair_n": (man or {}).get("preference_pair_n")
                    if isinstance(man, dict)
                    else None,
                }
            )
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "pack_root": str(root),
        "packs": packs,
        "latest_stamp": packs[0]["stamp"] if packs else None,
        "accuracy_claim": False,
        "process_split_authorized": False,
        "note": (
            "Worksheet packs are blank facilitation artifacts. "
            "Send only *_annotator_*.json to humans; keep facilitator/model_outputs private. "
            "accuracy_claim stays false until dual-human gates + owner attestation."
        ),
        "runbook": "packages/aiplat-evaluation/docs/a3/G2B_PREP.md",
    }


def worksheet_pack_generate(
    *,
    tenant_id: str = "eval-v1",
    skip_g2b: bool = False,
    skip_preference: bool = False,
) -> Dict[str, Any]:
    """Generate a new blank pack under docs/a3/human_pack/<stamp>.

    Args:
        tenant_id: 租户 ID。
        skip_g2b: skip_g2b 参数。
        skip_preference: skip_preference 参数。
    """
    mod = _load_pack_module()
    gen = getattr(mod, "generate_human_worksheet_pack", None)
    if not callable(gen):
        raise RuntimeError("generate_human_worksheet_pack missing from pack script")
    result = gen(skip_g2b=skip_g2b, skip_preference=skip_preference)
    if not isinstance(result, dict):
        raise RuntimeError("pack generator returned non-dict")
    result.setdefault("tenant_id", tenant_id)
    result["accuracy_claim"] = False
    result["process_split_authorized"] = False
    result["ok"] = True
    return result


def worksheet_pack_file(
    stamp: str,
    filename: str,
    *,
    tenant_id: str = "eval-v1",
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Read one pack file. Returns (meta_or_error, text_content).

    Args:
        stamp: stamp 参数。
        filename: filename 参数。
        tenant_id: 租户 ID。
    """
    if not _STAMP_RE.match(stamp):
        return {"ok": False, "error": "invalid_stamp"}, None
    if not _SAFE_FILE_RE.match(filename) or ".." in filename:
        return {"ok": False, "error": "invalid_filename"}, None
    path = _pack_root() / stamp / filename
    if not path.is_file():
        return {"ok": False, "error": "not_found", "stamp": stamp, "filename": filename}, None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return {"ok": False, "error": str(e)}, None
    return (
        {
            "ok": True,
            "tenant_id": tenant_id,
            "stamp": stamp,
            "filename": filename,
            "audience": _audience_for(filename),
            "accuracy_claim": False,
            "bytes": len(text.encode("utf-8")),
        },
        text,
    )
