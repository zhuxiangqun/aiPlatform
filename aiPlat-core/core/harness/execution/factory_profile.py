"""Factory profile helpers (F2a): project-level HITL intensity.

factory_profile=standard → keep team YAML hitl flags.
factory_profile=demo → keep HITL only on the final QA-like stage.
"""
from __future__ import annotations

from typing import Any, Iterable, List, Mapping, MutableMapping, Optional, Sequence

FACTORY_PROFILE_STANDARD = "standard"
FACTORY_PROFILE_DEMO = "demo"
FACTORY_PROFILES = frozenset({FACTORY_PROFILE_STANDARD, FACTORY_PROFILE_DEMO})

# Prefer keeping HITL on stages whose output_artifact looks like final QA/acceptance
_DEMO_KEEP_HITL_ARTIFACTS = frozenset({
    "test_report",
    "acceptance",
    "acceptance_report",
})


def normalize_factory_profile(raw: Any, default: str = FACTORY_PROFILE_STANDARD) -> str:
    val = str(raw or default).strip().lower()
    if val in ("minimal", "lite"):
        return FACTORY_PROFILE_DEMO
    if val in FACTORY_PROFILES:
        return val
    return default


def _stage_agent_id(stage: Any) -> str:
    if isinstance(stage, Mapping):
        return str(stage.get("agent_id") or "")
    return str(getattr(stage, "agent_id", "") or "")


def _stage_output_artifact(stage: Any) -> str:
    if isinstance(stage, Mapping):
        return str(stage.get("output_artifact") or "")
    return str(getattr(stage, "output_artifact", "") or "")


def _stage_get_hitl(stage: Any) -> bool:
    if isinstance(stage, Mapping):
        return bool(stage.get("hitl", False))
    return bool(getattr(stage, "hitl", False))


def _stage_set_hitl(stage: Any, hitl: bool, hitl_phase: str = "") -> None:
    if isinstance(stage, MutableMapping):
        stage["hitl"] = hitl
        if not hitl:
            stage["hitl_phase"] = ""
        elif hitl_phase:
            stage["hitl_phase"] = hitl_phase
        return
    setattr(stage, "hitl", hitl)
    if not hitl:
        setattr(stage, "hitl_phase", "")
    elif hitl_phase:
        setattr(stage, "hitl_phase", hitl_phase)


def apply_factory_profile_to_stages(
    stages: Sequence[Any],
    profile: str,
) -> List[Any]:
    """Mutate stage hitl flags according to factory_profile + always disable free spawn.

    demo: disable hitl on all stages except the last stage that is QA-like
    or, if none match, the last stage that originally had hitl=True.

    Phase B W3: every factory stage gets allow_dynamic_spawn=False (contracted
    team pipeline — no DynamicOrchestrator free multi-agent spawn).
    """
    profile = normalize_factory_profile(profile)
    out = list(stages)

    # Always: factory build chain is contracted — no free spawn
    for st in out:
        _stage_set_allow_dynamic_spawn(st, False)

    if profile != FACTORY_PROFILE_DEMO or not out:
        return out

    keep_idx: Optional[int] = None
    for i, st in enumerate(out):
        if _stage_output_artifact(st) in _DEMO_KEEP_HITL_ARTIFACTS:
            keep_idx = i
    if keep_idx is None:
        for i in range(len(out) - 1, -1, -1):
            if _stage_get_hitl(out[i]):
                keep_idx = i
                break
    if keep_idx is None:
        keep_idx = len(out) - 1

    for i, st in enumerate(out):
        if i == keep_idx:
            # Preserve existing hitl_phase from team YAML; do not hardcode business phase names
            _existing = ""
            if isinstance(st, Mapping):
                _existing = str(st.get("hitl_phase") or "")
            else:
                _existing = str(getattr(st, "hitl_phase", "") or "")
            _stage_set_hitl(st, True, hitl_phase=_existing)
        else:
            _stage_set_hitl(st, False)
    return out


def _stage_set_allow_dynamic_spawn(stage: Any, allowed: bool) -> None:
    if isinstance(stage, MutableMapping):
        stage["allow_dynamic_spawn"] = allowed
        return
    try:
        setattr(stage, "allow_dynamic_spawn", allowed)
    except Exception:
        pass  # noqa: cleanup-best-effort


def resolve_project_factory_profile(project: Optional[Mapping[str, Any]]) -> str:
    if not project:
        return FACTORY_PROFILE_STANDARD
    raw = project.get("factory_profile")
    if raw in (None, ""):
        meta = project.get("metadata")
        if isinstance(meta, Mapping):
            raw = meta.get("factory_profile")
    return normalize_factory_profile(raw)
