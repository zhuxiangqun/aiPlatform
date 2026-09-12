"""T3a: role/tag/project skill subscription filter.

required_skills are always kept. Optional skills may be filtered by allow_tags /
allow_roles from stage config, project overlay, or team subscription seed.
No agent_id branching.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

_SEED_SUB = (
    Path(__file__).resolve().parents[2]
    / "workspace_seeds"
    / "team_harness"
    / "skill_subscription.yaml"
)


def aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")).expanduser()


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.debug("skill_subscription yaml load failed: %s", path, exc_info=True)
        return {}


def load_subscription_defaults() -> Dict[str, Any]:
    """team/skill_subscription.yaml → ~/.aiplat override → seed."""
    for path in (
        aiplat_home() / "team" / "skill_subscription.yaml",
        aiplat_home() / "skill_subscription.yaml",
        _SEED_SUB,
    ):
        data = _read_yaml(path)
        if data:
            return data
    return {}


def resolve_subscription_policy(
    stage: Any = None,
    state: Optional[Mapping[str, Any]] = None,
    *,
    project: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge subscription policy: defaults ← project ← state ← stage fields."""
    base = load_subscription_defaults()
    allow_tags = list(base.get("allow_tags") or [])
    allow_roles = list(base.get("allow_roles") or [])
    enabled = base.get("enabled")
    if enabled is None:
        enabled = True

    for src in (project, state):
        if not isinstance(src, Mapping):
            continue
        sub = src.get("skill_subscription") or src.get("_skill_subscription")
        if isinstance(sub, Mapping):
            if sub.get("allow_tags") is not None:
                allow_tags = list(sub.get("allow_tags") or [])
            if sub.get("allow_roles") is not None:
                allow_roles = list(sub.get("allow_roles") or [])
            if sub.get("enabled") is not None:
                enabled = bool(sub.get("enabled"))
        meta = src.get("metadata") if isinstance(src.get("metadata"), Mapping) else None
        if meta and isinstance(meta.get("skill_subscription"), Mapping):
            sub = meta["skill_subscription"]
            if sub.get("allow_tags") is not None:
                allow_tags = list(sub.get("allow_tags") or [])
            if sub.get("allow_roles") is not None:
                allow_roles = list(sub.get("allow_roles") or [])

    if stage is not None:
        st_tags = getattr(stage, "skill_allow_tags", None)
        if st_tags is None and isinstance(stage, Mapping):
            st_tags = stage.get("skill_allow_tags")
        if st_tags:
            allow_tags = list(st_tags)
        st_roles = getattr(stage, "skill_allow_roles", None)
        if st_roles is None and isinstance(stage, Mapping):
            st_roles = stage.get("skill_allow_roles")
        if st_roles:
            allow_roles = list(st_roles)

    env = os.getenv("AIPLAT_SKILL_SUBSCRIPTION", "").strip().lower()
    if env in ("0", "false", "off", "no"):
        enabled = False
    elif env in ("1", "true", "on", "yes"):
        enabled = True

    return {
        "enabled": bool(enabled),
        "allow_tags": [str(t).strip() for t in allow_tags if str(t).strip()],
        "allow_roles": [str(r).strip() for r in allow_roles if str(r).strip()],
    }


def _skill_name(skill: Any) -> str:
    if skill is None:
        return ""
    if isinstance(skill, str):
        return skill.strip()
    for attr in ("name", "id", "skill_id", "skill_name"):
        val = getattr(skill, attr, None)
        if val:
            return str(val).strip()
    if isinstance(skill, Mapping):
        for key in ("name", "id", "skill_id"):
            if skill.get(key):
                return str(skill[key]).strip()
    return str(skill).strip()


def _skill_tags(skill: Any) -> List[str]:
    tags: Any = None
    if hasattr(skill, "tags"):
        tags = getattr(skill, "tags", None)
    elif isinstance(skill, Mapping):
        tags = skill.get("tags")
    if tags is None and hasattr(skill, "metadata"):
        meta = getattr(skill, "metadata", None)
        if isinstance(meta, Mapping):
            tags = meta.get("tags")
    if not isinstance(tags, (list, tuple, set)):
        return []
    return [str(t).strip() for t in tags if str(t).strip()]


def _skill_roles_allowed(skill: Any) -> List[str]:
    perms = None
    if hasattr(skill, "permissions"):
        perms = getattr(skill, "permissions", None)
    elif isinstance(skill, Mapping):
        perms = skill.get("permissions")
    if isinstance(perms, Mapping):
        roles = perms.get("roles_allowed") or perms.get("roles") or []
        if isinstance(roles, (list, tuple, set)):
            return [str(r).strip() for r in roles if str(r).strip()]
    return []


def skill_matches_subscription(
    skill: Any,
    *,
    allow_tags: Sequence[str],
    allow_roles: Sequence[str],
    actor_role: str = "",
) -> bool:
    """True if optional skill passes tag/role filters (empty allow_* = pass)."""
    if allow_tags:
        tags = set(_skill_tags(skill))
        if not tags.intersection({str(t) for t in allow_tags}):
            return False
    if allow_roles:
        roles = set(_skill_roles_allowed(skill))
        # Skills without roles_allowed stay available (most engine skills use capability lists).
        if roles:
            actor = str(actor_role or "").strip()
            if actor and actor not in roles:
                return False
            if not actor:
                # No actor role → keep skills that declare roles (avoid stripping catalog).
                pass
    return True


def filter_skills_by_subscription(
    skills: Sequence[Any],
    *,
    required: Optional[Sequence[str]] = None,
    allow_tags: Optional[Sequence[str]] = None,
    allow_roles: Optional[Sequence[str]] = None,
    actor_role: str = "",
    enabled: bool = True,
) -> List[Any]:
    """Keep required_skills always; filter optional by tags/roles when enabled."""
    req = [str(s).strip() for s in (required or []) if str(s).strip()]
    req_set = set(req)
    items = list(skills or [])
    if not enabled or (not allow_tags and not allow_roles):
        # Still ensure required names appear first when present in list
        if not req_set:
            return items
        ordered: List[Any] = []
        seen = set()
        by_name = {_skill_name(s): s for s in items if _skill_name(s)}
        for name in req:
            if name in by_name and name not in seen:
                ordered.append(by_name[name])
                seen.add(name)
        for s in items:
            n = _skill_name(s)
            if n not in seen:
                ordered.append(s)
                seen.add(n)
        return ordered

    tags = list(allow_tags or [])
    roles = list(allow_roles or [])
    out: List[Any] = []
    seen: set = set()
    by_name = {_skill_name(s): s for s in items if _skill_name(s)}

    for name in req:
        if name in by_name and name not in seen:
            out.append(by_name[name])
            seen.add(name)
        # required missing from catalog is not filtered away — caller may load by name

    for s in items:
        name = _skill_name(s)
        if not name or name in seen:
            continue
        if name in req_set:
            out.append(s)
            seen.add(name)
            continue
        if skill_matches_subscription(
            s, allow_tags=tags, allow_roles=roles, actor_role=actor_role
        ):
            out.append(s)
            seen.add(name)
    return out


def assert_required_intact(
    filtered: Sequence[Any],
    required: Sequence[str],
) -> bool:
    """DoD: after filter, every required name that was loadable remains."""
    names = {_skill_name(s) for s in filtered}
    for r in required or []:
        rr = str(r).strip()
        if rr and rr not in names:
            # Only fail if we had a chance to include it — empty filtered with required is fail
            return False
    return True


def apply_stage_skill_subscription(
    skills: Sequence[Any],
    stage: Any = None,
    state: Optional[Mapping[str, Any]] = None,
    *,
    project: Optional[Mapping[str, Any]] = None,
    actor_role: str = "",
) -> List[Any]:
    """Convenience: resolve policy from stage/state then filter."""
    policy = resolve_subscription_policy(stage, state, project=project)
    required = []
    if stage is not None:
        required = list(getattr(stage, "required_skills", None) or [])
        if not required and isinstance(stage, Mapping):
            required = list(stage.get("required_skills") or [])
    if not actor_role and isinstance(state, Mapping):
        actor_role = str(
            state.get("actor_role")
            or state.get("user_role")
            or (state.get("metadata") or {}).get("actor_role")
            or ""
        )
    out = filter_skills_by_subscription(
        skills,
        required=required,
        allow_tags=policy.get("allow_tags") or [],
        allow_roles=policy.get("allow_roles") or [],
        actor_role=actor_role,
        enabled=bool(policy.get("enabled", True)),
    )
    if required and not assert_required_intact(out, required):
        # required may be missing from catalog — keep filtered set, audit for DoD
        logger.warning(
            "skill subscription: required_skills not fully intact after filter: %s",
            required,
        )
    return out
