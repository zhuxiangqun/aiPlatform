"""Phase C3 — DigitalPost: governable org post, not a Goal trigger alias.

Seed: workspace_seeds/org_ingress/pilot_post.json
Override: AIPLAT_HOME/org/pilot_post.json or AIPLAT_HOME/org/posts/*.json
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_REQUIRED = (
    "post_id",
    "title",
    "version",
    "domain_id",
    "org_goal_id",
    "skill_whitelist",
    "interface_refs",
    "data_scope",
    "channel_allowlist",
    "sla",
    "audit_requirements",
)


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def _seed_path() -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "workspace_seeds"
        / "org_ingress"
        / "pilot_post.json"
    )


def _as_list(val: Any) -> List[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    text = str(val).strip()
    return [text] if text else []


def normalize_post(raw: Dict[str, Any]) -> Dict[str, Any]:
    scope = raw.get("scope") if isinstance(raw.get("scope"), dict) else {}
    sla = raw.get("sla") if isinstance(raw.get("sla"), dict) else {}
    policy = raw.get("exception_policy") if isinstance(raw.get("exception_policy"), dict) else {}
    domain = str(raw.get("domain_id") or scope.get("domain_id") or "").strip()
    return {
        "post_id": str(raw.get("post_id") or "").strip(),
        "title": str(raw.get("title") or "").strip(),
        "version": str(raw.get("version") or "").strip(),
        "enabled": bool(raw.get("enabled", True)),
        "scope": {
            "tenant_id": str(scope.get("tenant_id") or "").strip(),
            "domain_id": str(scope.get("domain_id") or domain).strip(),
        },
        "domain_id": domain,
        "org_goal_id": str(raw.get("org_goal_id") or raw.get("goal_template") or "").strip(),
        "skill_whitelist": _as_list(raw.get("skill_whitelist")),
        "interface_refs": _as_list(raw.get("interface_refs")),
        "data_scope": _as_list(raw.get("data_scope")) or ([domain] if domain else []),
        "exception_policy": policy,
        "channel_allowlist": [c.lower() for c in _as_list(raw.get("channel_allowlist"))],
        "quota_hooks": _as_list(raw.get("quota_hooks")),
        "sla": {
            "timeout_sec": int(sla.get("timeout_sec") or 0),
            "escalate": str(sla.get("escalate") or "").strip(),
        },
        "audit_requirements": _as_list(raw.get("audit_requirements")),
        "note": str(raw.get("note") or ""),
    }


def validate_post(post: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    for key in _REQUIRED:
        val = post.get(key)
        if val in ("", None, [], {}):
            errors.append(f"{key} required")
    sla = post.get("sla") if isinstance(post.get("sla"), dict) else {}
    if not sla.get("escalate"):
        errors.append("sla.escalate required")
    if int(sla.get("timeout_sec") or 0) <= 0:
        errors.append("sla.timeout_sec must be > 0")
    channels = post.get("channel_allowlist") or []
    if channels and not any(c in ("feishu", "lark") for c in channels):
        # not an error — post may be paused for ingress; reported as warning via evaluate
        pass
    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "post_id": post.get("post_id"),
    }


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else None
    except Exception:
        logger.warning("digital post unreadable %s", path, exc_info=True)
        return None


def load_posts() -> List[Dict[str, Any]]:
    """Override file wins; else posts dir; else workspace seed."""
    found: List[Dict[str, Any]] = []
    override = _home() / "org" / "pilot_post.json"
    posts_dir = _home() / "org" / "posts"
    if override.is_file():
        raw = _read_json(override)
        if raw:
            found.append(normalize_post(raw))
        return found
    if posts_dir.is_dir():
        for p in sorted(posts_dir.glob("*.json")):
            raw = _read_json(p)
            if raw:
                found.append(normalize_post(raw))
        if found:
            return found
    seed = _seed_path()
    if seed.is_file():
        raw = _read_json(seed)
        if raw:
            found.append(normalize_post(raw))
    return found


def get_post(post_id: str = "") -> Dict[str, Any]:
    posts = load_posts()
    pid = (post_id or "").strip()
    chosen = None
    if pid:
        chosen = next((p for p in posts if p.get("post_id") == pid), None)
    elif posts:
        chosen = posts[0]
    if chosen is None:
        return {"status": "not_found", "post_id": pid, "validation": {"ok": False, "errors": ["not_found"]}}
    val = validate_post(chosen)
    return {"status": "ok" if val["ok"] else "invalid", "post": chosen, "validation": val}


def list_posts() -> Dict[str, Any]:
    items = []
    for post in load_posts():
        val = validate_post(post)
        items.append({"post": post, "validation": val, "status": "ok" if val["ok"] else "invalid"})
    return {"status": "ok", "count": len(items), "items": items}


def evaluate_post_gate(
    channel: str,
    *,
    domain_id: str = "",
    post_id: str = "",
) -> Dict[str, Any]:
    """Whether this channel may start a run under the post (data scope + interface + SLA present)."""
    pack = get_post(post_id)
    if pack.get("status") == "not_found":
        return {"ok": False, "status": "post_missing", "channel": channel}
    post = pack.get("post") or {}
    val = pack.get("validation") or {}
    ch = (channel or "").strip().lower()
    if ch == "lark":
        ch = "feishu"
    if not post.get("enabled"):
        return {"ok": False, "status": "post_disabled", "post_id": post.get("post_id"), "channel": ch}
    allow = list(post.get("channel_allowlist") or [])
    if ch not in allow:
        return {
            "ok": False,
            "status": "post_channel_denied",
            "post_id": post.get("post_id"),
            "channel": ch,
            "channel_allowlist": allow,
        }
    if not val.get("ok"):
        return {
            "ok": False,
            "status": "post_invalid",
            "post_id": post.get("post_id"),
            "errors": val.get("errors"),
            "channel": ch,
        }
    did = (domain_id or post.get("domain_id") or "").strip()
    scope = list(post.get("data_scope") or [])
    if did and scope and did not in scope:
        return {
            "ok": False,
            "status": "data_scope_denied",
            "post_id": post.get("post_id"),
            "domain_id": did,
            "data_scope": scope,
        }
    return {
        "ok": True,
        "status": "ok",
        "post_id": post.get("post_id"),
        "org_goal_id": post.get("org_goal_id"),
        "domain_id": post.get("domain_id"),
        "interface_refs": list(post.get("interface_refs") or []),
        "skill_whitelist": list(post.get("skill_whitelist") or []),
        "sla": post.get("sla"),
        "channel": ch,
    }


_CONSOLE_ROLES = frozenset({"admin", "developer", "operator", "business", "fde", "approver"})


def authorize_console_run(
    *,
    role: str,
    domain_id: str = "",
    goal_id: str = "",
    post_id: str = "",
) -> Dict[str, Any]:
    """One decision for the management run route. Feishu ingress does not call this."""
    role_n = (role or "").strip().lower()
    if role_n not in _CONSOLE_ROLES:
        return {"ok": False, "status": "role_denied", "reason": "role_denied", "role": role_n}
    pack = get_post(post_id)
    if pack.get("status") != "ok":
        return {
            "ok": False,
            "status": str(pack.get("status") or "post_missing"),
            "reason": "post_denied",
            "post_id": post_id,
        }
    post = pack.get("post") or {}
    if not post.get("enabled"):
        return {"ok": False, "status": "post_disabled", "reason": "post_denied", "post_id": post.get("post_id")}
    did = (domain_id or post.get("domain_id") or "").strip()
    scope = list(post.get("data_scope") or [])
    if did and scope and did not in scope:
        return {
            "ok": False,
            "status": "data_scope_denied",
            "reason": "post_denied",
            "post_id": post.get("post_id"),
            "domain_id": did,
        }
    bound = str(post.get("org_goal_id") or "")
    gid = (goal_id or "").strip()
    if gid and bound and gid != bound:
        return {
            "ok": False,
            "status": "goal_not_on_post",
            "reason": "post_denied",
            "post_id": post.get("post_id"),
            "org_goal_id": bound,
        }
    return {
        "ok": True,
        "status": "ok",
        "role": role_n,
        "post_id": post.get("post_id"),
        "org_goal_id": bound,
        "domain_id": did or post.get("domain_id"),
    }
