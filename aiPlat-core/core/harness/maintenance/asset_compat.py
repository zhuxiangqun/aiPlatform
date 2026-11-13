"""Asset compat: Skill A + Agent B + Tool/MCP C (COMPAT.yaml honesty)."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

COMPAT_SCHEMA = "aiplat.asset_compat.v1"
COMPAT_FILENAME = "COMPAT.yaml"
HANDLER_DRAFT = "handler.py.draft"
TOOL_IMPL_DRAFT_SUFFIX = ".py.draft"
SKILL_NOT_SCHEDULABLE = "skill_not_schedulable"
AGENT_NOT_USABLE = "agent_not_usable"
TOOL_NOT_SCHEDULABLE = "tool_not_schedulable"
MCP_NOT_SCHEDULABLE = "mcp_not_schedulable"
TIER_PROMPT_READY = "prompt_ready"
TIER_TOOL_MAPPED = "tool_mapped"
TIER_NEEDS_HANDLER = "needs_handler"
TIER_BLOCKED = "blocked"
# Agent tiers (Phase B)
TIER_PERSONA_READY = "persona_ready"
TIER_BOUND_READY = "bound_ready"
TIER_NEEDS_BINDING = "needs_binding"
# Tool tiers (Phase C)
TIER_MAPPED = "mapped"
TIER_SCHEMA_ONLY = "schema_only"
TIER_NEEDS_IMPL = "needs_impl"
# MCP tiers (Phase C)
TIER_CONNECTABLE = "connectable"
TIER_CONNECTED = "connected"
TIER_GATED = "gated"
_SCHEDULABLE = {TIER_PROMPT_READY, TIER_TOOL_MAPPED}
_AGENT_CHAT_OK = {TIER_PERSONA_READY, TIER_BOUND_READY, TIER_NEEDS_BINDING}
_TOOL_SCHEDULABLE = {TIER_MAPPED}
_MCP_SCHEDULABLE = {TIER_CONNECTED, TIER_GATED}


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


# ── Agent Phase B ─────────────────────────────────────────────────────────────


def _read_agent_frontmatter(agent_dir: Path) -> Dict[str, Any]:
    md = agent_dir / "AGENT.md"
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


def _skill_search_roots() -> List[Path]:
    roots: List[Path] = []
    try:
        from core.utils.paths import get_aiplat_data_dir

        roots.append(Path(get_aiplat_data_dir("skills")))
    except Exception:
        logger.debug("skill search root: get_aiplat_data_dir failed", exc_info=True)
    for key in (
        "AIPLAT_WORKSPACE_SKILLS_PATH",
        "AIPLAT_ENGINE_SKILLS_PATH",
        "AIPLAT_WORKSPACE_SKILLS_PATHS",
        "AIPLAT_ENGINE_SKILLS_PATHS",
    ):
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        for part in raw.split(os.pathsep):
            p = Path(part).expanduser()
            if p.is_dir():
                roots.append(p)
    # Packaged engine skills (best-effort)
    try:
        engine = Path(__file__).resolve().parents[2] / "engine" / "skills"
        if engine.is_dir():
            roots.append(engine)
    except Exception:
        logger.debug("skill search root: engine skills path resolve failed", exc_info=True)
    # Dedup preserve order
    seen: set[str] = set()
    out: List[Path] = []
    for r in roots:
        key = str(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def resolve_skill_dir(skill_id: str) -> Optional[Path]:
    """Locate a skill directory by id (workspace then engine paths)."""
    sid = str(skill_id or "").strip()
    if not sid:
        return None
    for root in _skill_search_roots():
        cand = root / sid
        if (cand / "SKILL.md").is_file():
            return cand
    return None


def compute_agent_compat(
    agent_dir: Path | str,
    *,
    source: Optional[Dict[str, Any]] = None,
    adapt_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Score Agent COMPAT: persona_ready / bound_ready / needs_binding / blocked."""
    root = Path(agent_dir)
    fm = _read_agent_frontmatter(root)
    issues: List[Dict[str, Any]] = []
    block_reason = str(fm.get("block_reason") or "").strip()
    missing_caps = fm.get("missing_capabilities") if isinstance(fm.get("missing_capabilities"), list) else []
    required = fm.get("required_skills") if isinstance(fm.get("required_skills"), list) else None
    if required is None:
        required = fm.get("skills") if isinstance(fm.get("skills"), list) else []
    required = [str(x).strip() for x in required if str(x).strip()]

    missing_skills: List[str] = []
    unschedulable_skills: List[str] = []
    for sid in required:
        sdir = resolve_skill_dir(sid)
        if sdir is None:
            missing_skills.append(sid)
            continue
        if not is_skill_schedulable(sdir):
            unschedulable_skills.append(sid)

    if block_reason:
        tier = TIER_BLOCKED
        issues.append({"code": "blocked", "severity": "error", "message": block_reason})
    elif missing_caps:
        tier = TIER_NEEDS_BINDING
        issues.append({
            "code": "missing_capabilities",
            "severity": "error",
            "message": "unmapped critical tools/capabilities: " + ", ".join(str(x) for x in missing_caps[:8]),
        })
    elif missing_skills or unschedulable_skills:
        tier = TIER_NEEDS_BINDING
        if missing_skills:
            issues.append({
                "code": "missing_skills",
                "severity": "warning",
                "message": "required skills not installed: " + ", ".join(missing_skills[:8]),
            })
        if unschedulable_skills:
            issues.append({
                "code": "unschedulable_skills",
                "severity": "warning",
                "message": "required skills not schedulable: " + ", ".join(unschedulable_skills[:8]),
            })
    elif required:
        tier = TIER_BOUND_READY
    else:
        tier = TIER_PERSONA_READY

    chat_ok = tier in _AGENT_CHAT_OK
    # persona_ready (no required deps) and bound_ready: full surface available
    full_ok = tier in {TIER_PERSONA_READY, TIER_BOUND_READY}

    if tier == TIER_BLOCKED:
        ui = "不能用"
        upgrade = "blocked"
    elif tier == TIER_NEEDS_BINDING:
        ui = "还差几步"
        upgrade = "bind_dependencies"
    else:
        ui = "现在就能用"
        upgrade = "none"

    out: Dict[str, Any] = {
        "schema": COMPAT_SCHEMA,
        "asset_kind": "agent",
        "tier": tier,
        "schedulable": chat_ok,  # can enter chat/trial path
        "chat_ok": chat_ok,
        "full_ok": full_ok,
        "issues": issues,
        "mappings": [],
        "dependencies": {
            "required_skills": required,
            "missing_skills": missing_skills,
            "unschedulable_skills": unschedulable_skills,
        },
        "missing_critical": [str(x) for x in missing_caps] + list(missing_skills),
        "upgrade": {"recommended": upgrade, "auto_generated_artifacts": []},
        "ui_state": ui,
    }
    if source:
        out["source"] = source
    if adapt_summary:
        out["adapt_summary"] = {
            k: adapt_summary.get(k) for k in ("adapted", "pattern", "actions", "reason") if k in adapt_summary
        }
    return out


def write_agent_compat(agent_dir: Path | str, compat: Dict[str, Any]) -> Path:
    path = Path(agent_dir) / COMPAT_FILENAME
    try:
        import yaml

        path.write_text(yaml.safe_dump(compat, sort_keys=False, allow_unicode=True), encoding="utf-8")
    except Exception:
        import json

        path.write_text(json.dumps(compat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_agent_compat(agent_dir: Path | str) -> Optional[Dict[str, Any]]:
    path = Path(agent_dir) / COMPAT_FILENAME
    if not path.is_file():
        return None
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def finalize_agent_compat(
    agent_dir: Path | str,
    *,
    adapt_summary: Optional[Dict[str, Any]] = None,
    source: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    compat = compute_agent_compat(agent_dir, source=source, adapt_summary=adapt_summary)
    write_agent_compat(agent_dir, compat)
    return compat


def is_agent_chat_ok(agent_dir: Path | str) -> bool:
    """Fail-open when COMPAT missing (legacy agents)."""
    compat = read_agent_compat(agent_dir)
    if compat is None:
        return True
    if "chat_ok" in compat:
        return bool(compat.get("chat_ok"))
    return bool(compat.get("schedulable"))


def is_agent_fully_usable(agent_dir: Path | str) -> bool:
    """Fail-open when COMPAT missing (legacy agents)."""
    compat = read_agent_compat(agent_dir)
    if compat is None:
        return True
    if "full_ok" in compat:
        return bool(compat.get("full_ok"))
    return bool(compat.get("tier") in (TIER_BOUND_READY, TIER_PERSONA_READY))


def agent_compat_error(agent_dir: Path | str, agent_id: str = "", *, mode: str = "full") -> Dict[str, Any]:
    compat = read_agent_compat(agent_dir) or compute_agent_compat(agent_dir)
    return {
        "ok": False,
        "status": "error",
        "output": None,
        "error": AGENT_NOT_USABLE,
        "agent_id": agent_id or Path(agent_dir).name,
        "tier": compat.get("tier"),
        "schedulable": bool(compat.get("schedulable")),
        "chat_ok": bool(compat.get("chat_ok")),
        "full_ok": bool(compat.get("full_ok")),
        "ui_state": compat.get("ui_state"),
        "mode": mode,
        "actions_required": [compat.get("upgrade", {}).get("recommended") or "review_compat"],
        "issues": compat.get("issues") or [],
        "dependencies": compat.get("dependencies") or {},
    }


def resolve_agent_dir_from_info(agent_info: Any) -> Optional[Path]:
    """Prefer metadata.filesystem.agent_dir (AgentManager load shape)."""
    meta = getattr(agent_info, "metadata", None) or {}
    if not isinstance(meta, dict):
        return None
    fs = meta.get("filesystem") if isinstance(meta.get("filesystem"), dict) else {}
    raw = fs.get("agent_dir") if isinstance(fs, dict) else None
    if raw and Path(str(raw)).is_dir():
        return Path(str(raw))
    return None


# ── Shared COMPAT I/O ─────────────────────────────────────────────────────────


def _write_compat_file(path: Path, compat: Dict[str, Any]) -> Path:
    try:
        import yaml

        path.write_text(yaml.safe_dump(compat, sort_keys=False, allow_unicode=True), encoding="utf-8")
    except Exception:
        import json

        path.write_text(json.dumps(compat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _read_compat_file(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _ui_for_tier(tier: str, *, schedulable: bool) -> str:
    if tier == TIER_BLOCKED or (not schedulable and tier in {TIER_SCHEMA_ONLY, TIER_CONNECTABLE}):
        if tier == TIER_BLOCKED:
            return "不能用"
        if tier in {TIER_SCHEMA_ONLY, TIER_NEEDS_IMPL, TIER_CONNECTABLE, TIER_GATED, TIER_NEEDS_BINDING, TIER_NEEDS_HANDLER}:
            return "还差几步" if tier != TIER_SCHEMA_ONLY else "不能用"
    if schedulable:
        return "现在就能用"
    return "不能用" if tier == TIER_BLOCKED else "还差几步"


# ── MCP Phase C ───────────────────────────────────────────────────────────────


def resolve_mcp_dir(mcp_id: str) -> Optional[Path]:
    sid = str(mcp_id or "").strip()
    if not sid:
        return None
    roots: List[Path] = []
    try:
        from core.utils.paths import get_aiplat_data_dir

        roots.append(Path(get_aiplat_data_dir("mcps")))
    except Exception:
        logger.debug("mcp search root resolve failed", exc_info=True)
    for key in ("AIPLAT_WORKSPACE_MCP_PATH", "AIPLAT_ENGINE_MCP_PATH"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            roots.append(Path(raw).expanduser())
    for root in roots:
        cand = root / sid
        if (cand / "server.yaml").is_file() or (cand / "mcp.json").is_file():
            return cand
    return None


def resolve_mcp_dir_from_info(server_info: Any) -> Optional[Path]:
    meta = getattr(server_info, "metadata", None) or {}
    if isinstance(meta, dict):
        fs = meta.get("filesystem") if isinstance(meta.get("filesystem"), dict) else {}
        raw = fs.get("server_dir") if isinstance(fs, dict) else None
        if raw and Path(str(raw)).is_dir():
            return Path(str(raw))
    name = str(getattr(server_info, "name", "") or "").strip()
    return resolve_mcp_dir(name) if name else None


def compute_mcp_compat(
    mcp_dir: Path | str,
    *,
    source: Optional[Dict[str, Any]] = None,
    adapt_summary: Optional[Dict[str, Any]] = None,
    connection_status: Optional[str] = None,
) -> Dict[str, Any]:
    """Score MCP COMPAT: connectable / connected / gated / blocked."""
    root = Path(mcp_dir)
    issues: List[Dict[str, Any]] = []
    prev = _read_compat_file(root / COMPAT_FILENAME) or {}
    status = str(connection_status or prev.get("connection_status") or TIER_CONNECTABLE).strip().lower()
    block_reason = ""
    try:
        import yaml

        sy = root / "server.yaml"
        if sy.is_file():
            data = yaml.safe_load(sy.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                block_reason = str(data.get("block_reason") or "").strip()
                meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
                if not block_reason and isinstance(meta, dict):
                    block_reason = str(meta.get("block_reason") or "").strip()
    except Exception:
        logger.debug("mcp server.yaml read skipped", exc_info=True)

    pol: Dict[str, Any] = {}
    try:
        import yaml

        py = root / "policy.yaml"
        if py.is_file():
            raw = yaml.safe_load(py.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                pol = raw
    except Exception:
        logger.debug("mcp policy.yaml read skipped", exc_info=True)

    if block_reason:
        tier = TIER_BLOCKED
        issues.append({"code": "blocked", "severity": "error", "message": block_reason})
    elif status == TIER_BLOCKED:
        tier = TIER_BLOCKED
        issues.append({"code": "blocked", "severity": "error", "message": "connection blocked"})
    elif status == TIER_CONNECTED:
        if pol.get("approval_required") or str(pol.get("risk_level") or "").lower() == "high":
            tier = TIER_GATED
            issues.append({
                "code": "gated_high_risk",
                "severity": "warning",
                "message": "connected; high-risk tools may require individual confirmation",
            })
        else:
            tier = TIER_CONNECTED
    elif status == TIER_GATED:
        tier = TIER_GATED
    else:
        tier = TIER_CONNECTABLE
        issues.append({
            "code": "not_connected",
            "severity": "warning",
            "message": "server not connected; auto-connect pending or failed",
        })

    schedulable = tier in _MCP_SCHEDULABLE
    ui = _ui_for_tier(tier, schedulable=schedulable)
    upgrade = "none" if schedulable else ("blocked" if tier == TIER_BLOCKED else "connect")
    out: Dict[str, Any] = {
        "schema": COMPAT_SCHEMA,
        "asset_kind": "mcp",
        "tier": tier,
        "schedulable": schedulable,
        "connection_status": status if status in {TIER_CONNECTED, TIER_CONNECTABLE, TIER_BLOCKED, TIER_GATED} else TIER_CONNECTABLE,
        "issues": issues,
        "mappings": [],
        "dependencies": {},
        "missing_critical": [],
        "upgrade": {"recommended": upgrade, "auto_generated_artifacts": []},
        "ui_state": ui,
    }
    if source:
        out["source"] = source
    if adapt_summary:
        out["adapt_summary"] = {
            k: adapt_summary.get(k) for k in ("adapted", "pattern", "actions", "reason") if k in adapt_summary
        }
    return out


def write_mcp_compat(mcp_dir: Path | str, compat: Dict[str, Any]) -> Path:
    return _write_compat_file(Path(mcp_dir) / COMPAT_FILENAME, compat)


def read_mcp_compat(mcp_dir: Path | str) -> Optional[Dict[str, Any]]:
    return _read_compat_file(Path(mcp_dir) / COMPAT_FILENAME)


def finalize_mcp_compat(
    mcp_dir: Path | str,
    *,
    adapt_summary: Optional[Dict[str, Any]] = None,
    source: Optional[Dict[str, Any]] = None,
    connection_status: Optional[str] = None,
) -> Dict[str, Any]:
    compat = compute_mcp_compat(
        mcp_dir, source=source, adapt_summary=adapt_summary, connection_status=connection_status
    )
    write_mcp_compat(mcp_dir, compat)
    return compat


def mark_mcp_connection(
    mcp_dir: Path | str,
    status: str,
    *,
    adapt_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Rewrite COMPAT after connect/disconnect — never leave fake connected."""
    st = str(status or TIER_CONNECTABLE).strip().lower()
    if st not in {TIER_CONNECTED, TIER_CONNECTABLE, TIER_BLOCKED, TIER_GATED}:
        st = TIER_CONNECTABLE
    return finalize_mcp_compat(
        mcp_dir,
        connection_status=st,
        adapt_summary=adapt_summary or {"adapted": True, "pattern": f"mcp_{st}"},
    )


def is_mcp_schedulable(mcp_dir: Path | str) -> bool:
    compat = read_mcp_compat(mcp_dir)
    return True if compat is None else bool(compat.get("schedulable"))


def mcp_schedulable_error(mcp_dir: Path | str, mcp_id: str = "") -> Dict[str, Any]:
    compat = read_mcp_compat(mcp_dir) or compute_mcp_compat(mcp_dir)
    return {
        "ok": False,
        "error": MCP_NOT_SCHEDULABLE,
        "mcp_id": mcp_id or Path(mcp_dir).name,
        "tier": compat.get("tier"),
        "schedulable": False,
        "ui_state": compat.get("ui_state"),
        "actions_required": [compat.get("upgrade", {}).get("recommended") or "connect"],
        "issues": compat.get("issues") or [],
    }


# ── Tool Phase C ──────────────────────────────────────────────────────────────


def tool_compat_path(tool_py: Path | str) -> Path:
    """COMPAT lives beside tool .py as {stem}.COMPAT.yaml (flat tools dir)."""
    p = Path(tool_py)
    stem = p.name[:-3] if p.name.endswith(".py") else p.stem
    return p.parent / f"{stem}.COMPAT.yaml"


def tool_draft_path(tool_py: Path | str) -> Path:
    p = Path(tool_py)
    if p.name.endswith(".py"):
        return p.parent / (p.name + ".draft")  # name.py.draft
    return Path(str(p) + TOOL_IMPL_DRAFT_SUFFIX)


def resolve_tool_py_path(tool_id: str) -> Optional[Path]:
    tid = str(tool_id or "").strip()
    if not tid:
        return None
    roots: List[Path] = []
    env = (os.environ.get("AIPLAT_TOOLS_PATH") or "").strip()
    if env:
        roots.append(Path(env).expanduser())
    try:
        from core.utils.paths import get_aiplat_data_dir

        roots.append(Path(get_aiplat_data_dir("tools")))
    except Exception:
        logger.debug("tool search root resolve failed", exc_info=True)
    for root in roots:
        cand = root / f"{tid}.py"
        if cand.is_file():
            return cand
        draft = root / f"{tid}.py.draft"
        if draft.is_file():
            return cand  # canonical path even if only draft exists
    return None


def resolve_tool_py_from_obj(tool: Any) -> Optional[Path]:
    cfg = getattr(tool, "_config", None)
    meta = getattr(cfg, "metadata", None) if cfg is not None else None
    if not isinstance(meta, dict):
        meta = getattr(tool, "metadata", None) if isinstance(getattr(tool, "metadata", None), dict) else {}
    if isinstance(meta, dict):
        prov = meta.get("provenance") if isinstance(meta.get("provenance"), dict) else {}
        raw = prov.get("tool_path") if isinstance(prov, dict) else None
        if raw and Path(str(raw)).is_file():
            return Path(str(raw))
        if raw and Path(str(raw)).parent.is_dir():
            # draft-only: path points to intended .py
            return Path(str(raw))
    name = str(getattr(tool, "name", None) or getattr(tool, "get_name", lambda: "")() or "").strip()
    return resolve_tool_py_path(name) if name else None


def compute_tool_compat(
    tool_py: Path | str,
    *,
    source: Optional[Dict[str, Any]] = None,
    adapt_summary: Optional[Dict[str, Any]] = None,
    mapped_to: Optional[str] = None,
    mcp_projection: bool = False,
) -> Dict[str, Any]:
    """Score Tool COMPAT: mapped / schema_only / needs_impl / blocked."""
    path = Path(tool_py)
    issues: List[Dict[str, Any]] = []
    has_impl = path.is_file()
    draft = tool_draft_path(path)
    has_draft = draft.is_file()
    schema_sidecar = path.parent / f"{path.stem}.schema.json"
    has_schema = schema_sidecar.is_file()
    prev = _read_compat_file(tool_compat_path(path)) or {}
    block_reason = str(prev.get("block_reason") or "").strip()
    pattern = ""
    if isinstance(adapt_summary, dict):
        pattern = str(adapt_summary.get("pattern") or "")
    mapped_name = mapped_to or (prev.get("mapped_to") if isinstance(prev.get("mapped_to"), str) else None)
    is_mcp = bool(mcp_projection or prev.get("mcp_projection") or pattern == "mcp_projection")

    if block_reason:
        tier = TIER_BLOCKED
        issues.append({"code": "blocked", "severity": "error", "message": block_reason})
    elif is_mcp or mapped_name:
        tier = TIER_MAPPED
    elif has_draft and not has_impl:
        tier = TIER_NEEDS_IMPL
        issues.append({"code": "needs_impl", "severity": "warning", "message": "impl draft present; enable required"})
    elif has_schema and not has_impl:
        tier = TIER_SCHEMA_ONLY
        issues.append({"code": "schema_only", "severity": "error", "message": "schema only; real calls denied"})
    elif has_impl:
        # Live .py on disk = mapped (workspace-authored or enabled draft).
        # New imports must write .py.draft only (see write_tool_impl_draft).
        if pattern in {"generated_draft", "import_draft", "needs_impl"}:
            tier = TIER_NEEDS_IMPL
            issues.append({"code": "needs_impl", "severity": "warning", "message": "generated impl not enabled"})
        else:
            tier = TIER_MAPPED
    else:
        tier = TIER_NEEDS_IMPL
        issues.append({"code": "needs_impl", "severity": "warning", "message": "no impl or schema"})

    schedulable = tier in _TOOL_SCHEDULABLE
    ui = _ui_for_tier(tier, schedulable=schedulable)
    if tier == TIER_NEEDS_IMPL:
        upgrade = "enable_impl"
    elif tier == TIER_SCHEMA_ONLY:
        upgrade = "provide_impl"
    elif tier == TIER_BLOCKED:
        upgrade = "blocked"
    else:
        upgrade = "none"
    out: Dict[str, Any] = {
        "schema": COMPAT_SCHEMA,
        "asset_kind": "tool",
        "tier": tier,
        "schedulable": schedulable,
        "issues": issues,
        "mappings": ([{"to": mapped_name}] if mapped_name else []) + ([{"kind": "mcp_projection"}] if is_mcp else []),
        "mapped_to": mapped_name,
        "mcp_projection": is_mcp,
        "dependencies": {},
        "missing_critical": [],
        "upgrade": {
            "recommended": upgrade,
            "auto_generated_artifacts": [draft.name] if has_draft else [],
        },
        "ui_state": ui,
    }
    if source:
        out["source"] = source
    if adapt_summary:
        out["adapt_summary"] = {
            k: adapt_summary.get(k) for k in ("adapted", "pattern", "actions", "reason") if k in adapt_summary
        }
    return out


def write_tool_compat(tool_py: Path | str, compat: Dict[str, Any]) -> Path:
    return _write_compat_file(tool_compat_path(tool_py), compat)


def read_tool_compat(tool_py: Path | str) -> Optional[Dict[str, Any]]:
    return _read_compat_file(tool_compat_path(tool_py))


def finalize_tool_compat(
    tool_py: Path | str,
    *,
    adapt_summary: Optional[Dict[str, Any]] = None,
    source: Optional[Dict[str, Any]] = None,
    mapped_to: Optional[str] = None,
    mcp_projection: bool = False,
) -> Dict[str, Any]:
    compat = compute_tool_compat(
        tool_py,
        source=source,
        adapt_summary=adapt_summary,
        mapped_to=mapped_to,
        mcp_projection=mcp_projection,
    )
    write_tool_compat(tool_py, compat)
    return compat


def is_tool_schedulable(tool_py: Path | str) -> bool:
    compat = read_tool_compat(tool_py)
    return True if compat is None else bool(compat.get("schedulable"))


def tool_schedulable_error(tool_py: Path | str, tool_id: str = "") -> Dict[str, Any]:
    compat = read_tool_compat(tool_py) or compute_tool_compat(tool_py)
    return {
        "ok": False,
        "error": TOOL_NOT_SCHEDULABLE,
        "tool_id": tool_id or Path(tool_py).stem,
        "tier": compat.get("tier"),
        "schedulable": False,
        "ui_state": compat.get("ui_state"),
        "actions_required": [compat.get("upgrade", {}).get("recommended") or "review_compat"],
        "issues": compat.get("issues") or [],
    }


def write_tool_impl_draft(tool_py: Path | str, code: str) -> Path:
    """Write {name}.py.draft only — never enable as .py."""
    draft = tool_draft_path(tool_py)
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text(code, encoding="utf-8")
    return draft


def enable_tool_impl_draft(tool_py: Path | str) -> Dict[str, Any]:
    """Promote {name}.py.draft → {name}.py after human enable."""
    target = Path(tool_py)
    draft = tool_draft_path(target)
    if not draft.is_file():
        return {"ok": False, "error": "no_impl_draft"}
    if target.exists():
        return {"ok": False, "error": "impl_already_exists"}
    target.write_text(draft.read_text(encoding="utf-8"), encoding="utf-8")
    compat = finalize_tool_compat(target, adapt_summary={"adapted": True, "pattern": "impl_enabled"})
    return {"ok": True, "tier": compat.get("tier"), "schedulable": compat.get("schedulable"), "compat": compat}
