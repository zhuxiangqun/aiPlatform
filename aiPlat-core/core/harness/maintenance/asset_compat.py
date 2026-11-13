"""Skill asset compat (Phase A): COMPAT.yaml tier / schedulable honesty."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

COMPAT_SCHEMA = "aiplat.asset_compat.v1"
COMPAT_FILENAME = "COMPAT.yaml"
HANDLER_DRAFT = "handler.py.draft"
SKILL_NOT_SCHEDULABLE = "skill_not_schedulable"
TIER_PROMPT_READY = "prompt_ready"
TIER_TOOL_MAPPED = "tool_mapped"
TIER_NEEDS_HANDLER = "needs_handler"
TIER_BLOCKED = "blocked"
_SCHEDULABLE = {TIER_PROMPT_READY, TIER_TOOL_MAPPED}


def _read_frontmatter(skill_dir: Path) -> Dict[str, Any]:
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return {}
    raw = md.read_text(encoding="utf-8", errors="replace")
    if not raw.startswith("---"):
        return {}
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        import yaml

        fm = yaml.safe_load(parts[1]) or {}
        return fm if isinstance(fm, dict) else {}
    except Exception:
        return {}


def compute_skill_compat(
    skill_dir: Path | str,
    *,
    source: Optional[Dict[str, Any]] = None,
    adapt_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    root = Path(skill_dir)
    fm = _read_frontmatter(root)
    has_handler = (root / "handler.py").is_file()
    has_draft = (root / HANDLER_DRAFT).is_file()
    tools = fm.get("tools") if isinstance(fm.get("tools"), list) else []
    missing = fm.get("missing_capabilities") if isinstance(fm.get("missing_capabilities"), list) else []
    block_reason = str(fm.get("block_reason") or "").strip()
    exec_type = str(fm.get("execution_type") or "prompt").lower()
    issues: List[Dict[str, Any]] = []

    if block_reason:
        tier = TIER_BLOCKED
        issues.append({"code": "blocked", "severity": "error", "message": block_reason})
    elif missing:
        # Unmapped critical capabilities → not schedulable (Phase A honesty)
        tier = TIER_NEEDS_HANDLER
        issues.append({
            "code": "missing_capabilities",
            "severity": "error",
            "message": "unmapped critical tools/capabilities: " + ", ".join(str(x) for x in missing[:8]),
        })
    elif exec_type == "handler" and not has_handler:
        tier = TIER_NEEDS_HANDLER
        issues.append({"code": "needs_handler", "severity": "warning", "message": "handler required but missing"})
    elif tools and not missing:
        tier = TIER_TOOL_MAPPED
    elif has_handler or exec_type in {"prompt", ""}:
        tier = TIER_PROMPT_READY
        if has_draft and not has_handler:
            issues.append({
                "code": "handler_draft_disabled",
                "severity": "info",
                "message": "draft present; prompt path schedulable until enable",
            })
    else:
        tier = TIER_NEEDS_HANDLER
        issues.append({"code": "needs_handler", "severity": "warning", "message": "no schedulable path"})

    schedulable = tier in _SCHEDULABLE
    upgrade = "enable_handler" if has_draft and not has_handler else ("none" if schedulable else "needs_handler")
    out: Dict[str, Any] = {
        "schema": COMPAT_SCHEMA,
        "asset_kind": "skill",
        "tier": tier,
        "schedulable": schedulable,
        "issues": issues,
        "mappings": [],
        "missing_critical": [str(x) for x in missing],
        "upgrade": {"recommended": upgrade, "auto_generated_artifacts": [HANDLER_DRAFT] if has_draft else []},
        "ui_state": "现在就能用" if schedulable else ("不能用" if tier == TIER_BLOCKED else "还差几步"),
    }
    if source:
        out["source"] = source
    if adapt_summary:
        out["adapt_summary"] = {k: adapt_summary.get(k) for k in ("adapted", "pattern", "actions", "reason") if k in adapt_summary}
    return out


def write_skill_compat(skill_dir: Path | str, compat: Dict[str, Any]) -> Path:
    path = Path(skill_dir) / COMPAT_FILENAME
    try:
        import yaml

        path.write_text(yaml.safe_dump(compat, sort_keys=False, allow_unicode=True), encoding="utf-8")
    except Exception:
        import json

        path.write_text(json.dumps(compat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_skill_compat(skill_dir: Path | str) -> Optional[Dict[str, Any]]:
    path = Path(skill_dir) / COMPAT_FILENAME
    if not path.is_file():
        return None
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def finalize_skill_compat(
    skill_dir: Path | str,
    *,
    adapt_summary: Optional[Dict[str, Any]] = None,
    source: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    compat = compute_skill_compat(skill_dir, source=source, adapt_summary=adapt_summary)
    write_skill_compat(skill_dir, compat)
    return compat


def is_skill_schedulable(skill_dir: Path | str) -> bool:
    compat = read_skill_compat(skill_dir)
    return True if compat is None else bool(compat.get("schedulable"))


def skill_schedulable_error(skill_dir: Path | str, skill_id: str = "") -> Dict[str, Any]:
    compat = read_skill_compat(skill_dir) or compute_skill_compat(skill_dir)
    return {
        "ok": False,
        "error": SKILL_NOT_SCHEDULABLE,
        "skill_id": skill_id or Path(skill_dir).name,
        "tier": compat.get("tier"),
        "schedulable": False,
        "ui_state": compat.get("ui_state"),
        "actions_required": [compat.get("upgrade", {}).get("recommended") or "review_compat"],
        "issues": compat.get("issues") or [],
    }


def write_handler_draft_from_script(skill_dir: Path | str, script_rel: str) -> Path:
    """Write handler.py.draft only — never enable as handler.py."""
    root = Path(skill_dir)
    path = root / HANDLER_DRAFT
    path.write_text(
        f'"""DRAFT handler for {root.name} — wraps {script_rel}. Not enabled."""\n'
        "import subprocess, sys, time\nfrom pathlib import Path\n\n"
        "async def execute(params: dict) -> dict:\n"
        '    topic = params.get("query", params.get("topic", ""))\n'
        f'    script = Path(__file__).parent / "{script_rel}"\n'
        '    if not topic:\n        return {"error": "query or topic parameter required"}\n'
        "    try:\n"
        "        r = subprocess.run([sys.executable, str(script), topic, '--emit=compact'],\n"
        "            capture_output=True, text=True, timeout=300, cwd=str(Path(__file__).parent))\n"
        '        return {"topic": topic, "output": r.stdout, "stderr": (r.stderr or "")[:500],\n'
        '                "success": r.returncode == 0, "elapsed_s": 0}\n'
        "    except subprocess.TimeoutExpired:\n"
        '        return {"topic": topic, "error": "execution timed out after 300s"}\n',
        encoding="utf-8",
    )
    return path


def enable_handler_draft(skill_dir: Path | str) -> Dict[str, Any]:
    """Promote handler.py.draft → handler.py after human enable."""
    root = Path(skill_dir)
    draft, target = root / HANDLER_DRAFT, root / "handler.py"
    if not draft.is_file():
        return {"ok": False, "error": "no_handler_draft"}
    if target.exists():
        return {"ok": False, "error": "handler_already_exists"}
    target.write_text(draft.read_text(encoding="utf-8"), encoding="utf-8")
    md = root / "SKILL.md"
    if md.is_file():
        raw = md.read_text(encoding="utf-8", errors="replace")
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                try:
                    import yaml

                    fm = yaml.safe_load(parts[1]) or {}
                    if isinstance(fm, dict):
                        fm["execution_type"] = "handler"
                        fm.pop("block_reason", None)
                        header = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
                        md.write_text(f"---\n{header}\n---{parts[2]}", encoding="utf-8")
                except Exception as exc:
                    logger.debug("enable_handler frontmatter update failed: %s", exc)
    compat = finalize_skill_compat(root, adapt_summary={"adapted": True, "pattern": "handler_enabled"})
    return {"ok": True, "tier": compat.get("tier"), "schedulable": compat.get("schedulable"), "compat": compat}
