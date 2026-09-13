"""Opt-in user-facing output style (A0).

Locked ADHD ruleset + whitelist overrides. Does not rewrite tool/stack payloads.
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence

logger = logging.getLogger(__name__)

STYLE_DEFAULT = "default"
STYLE_ADHD = "adhd"
STYLE_VERSION = "adhd_v2"
WHITELIST_OVERRIDE_KEYS = frozenset({"list_cap", "time_estimate_unit", "locale"})

_SEED_SKILL = (
    Path(__file__).resolve().parents[2]
    / "workspace_seeds"
    / "skills"
    / "output_style_adhd"
    / "SKILL.md"
)


def resolve_output_style(
    source: Optional[Mapping[str, Any]] = None,
    *,
    default: str = STYLE_DEFAULT,
) -> str:
    """Resolve style from project/session/extra mapping."""
    if not source:
        return default
    raw = source.get("output_style")
    if raw in (None, ""):
        meta = source.get("metadata")
        if isinstance(meta, Mapping):
            raw = meta.get("output_style")
    style = str(raw or default).strip().lower()
    if style in (STYLE_DEFAULT, STYLE_ADHD, "off", ""):
        return STYLE_DEFAULT if style in ("off", "") else style
    return default


def whitelist_overrides(source: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Return only allowed tenant override keys."""
    if not source:
        return {}
    raw = source.get("output_style_overrides") or {}
    if not isinstance(raw, Mapping):
        meta = source.get("metadata")
        if isinstance(meta, Mapping):
            raw = meta.get("output_style_overrides") or {}
    if not isinstance(raw, Mapping):
        return {}
    out: Dict[str, Any] = {}
    for k, v in raw.items():
        if str(k) in WHITELIST_OVERRIDE_KEYS:
            out[str(k)] = v
    return out


def skill_body_path() -> Path:
    home = Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat"))
    ws = home / "skills" / "output_style_adhd" / "SKILL.md"
    if ws.is_file():
        return ws
    return _SEED_SKILL


def load_adhd_skill_text() -> str:
    path = skill_body_path()
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("output_style_adhd SKILL.md missing at %s", path)
        return ""


def skill_body_hash() -> str:
    text = load_adhd_skill_text()
    if not text:
        return ""
    # Hash rules body after frontmatter for lock checks
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            body = parts[2]
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def build_style_overlay(
    style: str,
    overrides: Optional[Mapping[str, Any]] = None,
) -> str:
    """Ephemeral system-tail overlay (Prompt-cache safe: append only)."""
    if resolve_output_style({"output_style": style}) != STYLE_ADHD:
        return ""
    ov = dict(overrides or {})
    list_cap = int(ov.get("list_cap") or 5)
    unit = str(ov.get("time_estimate_unit") or "minutes")
    locale = str(ov.get("locale") or "zh-CN")
    return (
        f"[output_style={STYLE_ADHD} version={STYLE_VERSION} hash={skill_body_hash()}]\n"
        f"Apply locked ADHD user-facing style. list_cap={list_cap}; "
        f"time_estimate_unit={unit}; locale={locale}.\n"
        "Hard constraints: (1) no invented time estimates — omit or say "
        "'耗时未知' unless grounded in tool/history; (2) high-risk side issues "
        "(security/data-loss/leak) get a separate ⚠ paragraph, never one buried "
        "line; (3) list_cap is presentation-only — never truncate analysis/tool "
        "results/candidates.\n"
        "Lead with the next action; number steps; restate state; grade tangents; "
        "no preamble/closers. Keep tool results and stack traces verbatim "
        "in fenced code blocks. Do not alter JSON contracts.\n"
    )


def inject_output_style(
    messages: Sequence[Mapping[str, Any]],
    *,
    style: str = STYLE_DEFAULT,
    overrides: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Append style overlay to the last system message, or insert a system tail.

    Skips injection when style is default. Never mutates tool-role contents.
    """
    msgs: List[Dict[str, Any]] = [dict(m) for m in messages]
    overlay = build_style_overlay(style, overrides)
    if not overlay:
        return msgs
    for i in range(len(msgs) - 1, -1, -1):
        if str(msgs[i].get("role") or "") == "system":
            content = str(msgs[i].get("content") or "")
            if "[output_style=" in content:
                return msgs
            msgs[i]["content"] = content.rstrip() + "\n\n" + overlay
            return msgs
    msgs.insert(0, {"role": "system", "content": overlay})
    return msgs


def apply_project_style_meta(
    project: MutableMapping[str, Any],
    *,
    output_style: Optional[str] = None,
    overrides: Optional[Mapping[str, Any]] = None,
) -> None:
    """Persist style preference on project dict (factory / session)."""
    if output_style is not None:
        project["output_style"] = resolve_output_style({"output_style": output_style})
    if overrides is not None:
        project["output_style_overrides"] = whitelist_overrides(
            {"output_style_overrides": overrides}
        )
    project.setdefault("metadata", {})
    if isinstance(project["metadata"], dict):
        project["metadata"]["output_style"] = project.get("output_style", STYLE_DEFAULT)
        project["metadata"]["output_style_version"] = STYLE_VERSION
        project["metadata"]["output_style_hash"] = skill_body_hash()


# ── A3a: style telemetry (no A/B split) ──────────────────────────────────────

_EVENTS_MAX = 500
_EVENTS_FILENAME = "output_style_events.json"


def output_style_events_path() -> Path:
    home = Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat"))
    return home / "wiki" / _EVENTS_FILENAME


def estimate_reply_tokens(text: str) -> int:
    """Rough token estimate for telemetry (not billing-grade)."""
    s = str(text or "")
    if not s:
        return 0
    return max(1, len(s) // 4)


def infer_followups(messages: Optional[Sequence[Mapping[str, Any]]] = None) -> int:
    """Count user turns after the first (proxy for follow-up pressure)."""
    if not messages:
        return 0
    user_n = sum(1 for m in messages if str(m.get("role") or "") == "user")
    return max(0, user_n - 1)


def record_output_style_event(
    *,
    style: str,
    project_id: str = "",
    session_id: str = "",
    source: str = "",
    tokens: Optional[int] = None,
    followups: Optional[int] = None,
    first_pass_ok: Optional[bool] = None,
    experiment_id: str = "",
    arm: str = "",
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """A3a: append one style telemetry row (queryable JSON).

    A3b: optional ``experiment_id`` / ``arm`` for split attribution (still no topology change).
    """
    import json
    import time

    resolved = resolve_output_style({"output_style": style})
    row: Dict[str, Any] = {
        "ts": time.time(),
        "style": resolved,
        "style_version": STYLE_VERSION if resolved == STYLE_ADHD else "",
        "style_hash": skill_body_hash() if resolved == STYLE_ADHD else "",
        "project_id": str(project_id or "")[:128],
        "session_id": str(session_id or "")[:128],
        "source": str(source or "")[:64],
        "tokens": int(tokens) if tokens is not None else None,
        "followups": int(followups) if followups is not None else None,
        "first_pass_ok": first_pass_ok,
        "experiment_id": str(experiment_id or "")[:64],
        "arm": str(arm or "")[:32],
    }
    if extra:
        # Keep payload small; string-coerce unknown keys
        slim = {str(k)[:32]: str(v)[:120] for k, v in list(extra.items())[:8]}
        if slim:
            row["extra"] = slim

    path = output_style_events_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        samples: List[Any] = []
        if path.is_file():
            try:
                samples = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(samples, list):
                    samples = []
            except Exception:
                samples = []
        samples.append(row)
        if len(samples) > _EVENTS_MAX:
            samples = samples[-_EVENTS_MAX:]
        path.write_text(json.dumps(samples, ensure_ascii=False), encoding="utf-8")
    except Exception:
        logger.debug("record_output_style_event failed", exc_info=True)
    return row


def query_output_style_events(
    *,
    limit: int = 50,
    style: Optional[str] = None,
    project_id: Optional[str] = None,
    experiment_id: Optional[str] = None,
    arm: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """A3a/A3b: read recent style telemetry (newest last)."""
    import json

    path = output_style_events_path()
    if not path.is_file():
        return []
    try:
        samples = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(samples, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in samples:
        if not isinstance(row, Mapping):
            continue
        if style is not None and str(row.get("style") or "") != str(style):
            continue
        if project_id is not None and str(row.get("project_id") or "") != str(project_id):
            continue
        if experiment_id is not None and str(row.get("experiment_id") or "") != str(
            experiment_id
        ):
            continue
        if arm is not None and str(row.get("arm") or "") != str(arm):
            continue
        out.append(dict(row))
    lim = max(1, min(int(limit or 50), _EVENTS_MAX))
    return out[-lim:]


# ── A3b: sticky A/B assignment (opt-in; default off) ─────────────────────────

EXPERIMENT_ID_DEFAULT = "output_style_v1"
ARM_CONTROL = "control"  # default style
ARM_TREATMENT = "treatment"  # adhd style


def get_output_style_experiment_pct(
    source: Optional[Mapping[str, Any]] = None,
) -> int:
    """ADHD arm percentage 0–100. Env default 0 (experiment off)."""
    if source:
        raw = source.get("output_style_experiment_pct")
        if raw in (None, ""):
            meta = source.get("metadata")
            if isinstance(meta, Mapping):
                raw = meta.get("output_style_experiment_pct")
        if raw not in (None, ""):
            try:
                return max(0, min(100, int(raw)))
            except (TypeError, ValueError):
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
    env = os.getenv("AIPLAT_OUTPUT_STYLE_EXPERIMENT_PCT", "0")
    try:
        return max(0, min(100, int(env)))
    except (TypeError, ValueError):
        return 0


def style_experiment_bucket(sticky_id: str) -> int:
    """Stable 0–99 bucket from sticky id (project/session)."""
    import hashlib

    key = str(sticky_id or "anon").encode("utf-8")
    digest = hashlib.sha256(key).hexdigest()
    return int(digest[:8], 16) % 100


def _user_locked_style(project: Mapping[str, Any]) -> bool:
    if project.get("output_style_user_set") in (True, 1, "1", "true", "True"):
        return True
    meta = project.get("metadata")
    if isinstance(meta, Mapping) and meta.get("output_style_user_set") in (
        True,
        1,
        "1",
        "true",
        "True",
    ):
        return True
    return False


def assign_output_style_experiment(
    project: MutableMapping[str, Any],
    *,
    sticky_id: str = "",
    adhd_pct: Optional[int] = None,
    experiment_id: str = EXPERIMENT_ID_DEFAULT,
) -> Dict[str, Any]:
    """A3b: sticky default|adhd arm. Explicit user style wins; pct=0 → no split.

    Persists ``output_style_arm`` / ``output_style_experiment_id`` on the project.
    Does not rewrite style when user locked or experiment disabled.
    """
    exp_id = str(
        project.get("output_style_experiment_id")
        or experiment_id
        or EXPERIMENT_ID_DEFAULT
    )[:64]
    pct = int(adhd_pct) if adhd_pct is not None else get_output_style_experiment_pct(project)

    # Already assigned — sticky
    existing_arm = str(project.get("output_style_arm") or "").strip().lower()
    if existing_arm in (ARM_CONTROL, ARM_TREATMENT, "a", "b"):
        if existing_arm == "a":
            existing_arm = ARM_CONTROL
        elif existing_arm == "b":
            existing_arm = ARM_TREATMENT
        style = STYLE_ADHD if existing_arm == ARM_TREATMENT else STYLE_DEFAULT
        if not _user_locked_style(project):
            project["output_style"] = style
        project["output_style_arm"] = existing_arm
        project["output_style_experiment_id"] = exp_id
        apply_project_style_meta(project, output_style=project.get("output_style"))
        return {
            "assigned": False,
            "sticky": True,
            "arm": existing_arm,
            "style": resolve_output_style(project),
            "experiment_id": exp_id,
            "pct": pct,
        }

    if _user_locked_style(project) or pct <= 0:
        style = resolve_output_style(project)
        return {
            "assigned": False,
            "sticky": False,
            "arm": "",
            "style": style,
            "experiment_id": "",
            "pct": pct,
        }

    sid = str(sticky_id or project.get("id") or project.get("project_id") or "anon")
    bucket = style_experiment_bucket(sid)
    arm = ARM_TREATMENT if bucket < pct else ARM_CONTROL
    style = STYLE_ADHD if arm == ARM_TREATMENT else STYLE_DEFAULT
    project["output_style"] = style
    project["output_style_arm"] = arm
    project["output_style_experiment_id"] = exp_id
    project["output_style_bucket"] = bucket
    apply_project_style_meta(project, output_style=style)
    return {
        "assigned": True,
        "sticky": True,
        "arm": arm,
        "style": style,
        "experiment_id": exp_id,
        "pct": pct,
        "bucket": bucket,
    }


def compare_output_style_arms(
    *,
    experiment_id: str = EXPERIMENT_ID_DEFAULT,
    limit: int = 500,
) -> Dict[str, Any]:
    """A3b: contrast table from telemetry (tokens / followups / first_pass_ok)."""
    rows = query_output_style_events(limit=limit, experiment_id=experiment_id)
    # Also include rows tagged by style when experiment_id empty on older events
    if not rows and experiment_id:
        rows = [
            r
            for r in query_output_style_events(limit=limit)
            if str(r.get("experiment_id") or "") in ("", experiment_id)
        ]

    def _agg(subset: List[Dict[str, Any]]) -> Dict[str, Any]:
        n = len(subset)
        if n == 0:
            return {
                "n": 0,
                "avg_tokens": None,
                "avg_followups": None,
                "first_pass_rate": None,
            }
        toks = [int(r["tokens"]) for r in subset if r.get("tokens") is not None]
        fups = [int(r["followups"]) for r in subset if r.get("followups") is not None]
        fps = [r for r in subset if isinstance(r.get("first_pass_ok"), bool)]
        ok = sum(1 for r in fps if r.get("first_pass_ok"))
        return {
            "n": n,
            "avg_tokens": (sum(toks) / len(toks)) if toks else None,
            "avg_followups": (sum(fups) / len(fups)) if fups else None,
            "first_pass_rate": (ok / len(fps)) if fps else None,
        }

    by_arm: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        a = str(r.get("arm") or "") or (
            ARM_TREATMENT if r.get("style") == STYLE_ADHD else ARM_CONTROL
        )
        by_arm.setdefault(a, []).append(r)

    arms = {k: _agg(v) for k, v in by_arm.items()}
    return {
        "experiment_id": experiment_id,
        "total": len(rows),
        "arms": arms,
    }
