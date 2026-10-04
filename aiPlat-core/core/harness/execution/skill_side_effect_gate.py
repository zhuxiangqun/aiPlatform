"""Refuse prompt-only skills that declare mutating side effects.

A prompt skill may emit text. Write/network/exec require a realizer:
handler.py, hybrid handler, or a dedicated python_class (not LLM GenericSkill).
No skill-name or agent-id matching.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.harness.interfaces import SkillResult

MUTATING_EFFECT_TYPES = frozenset(
    {
        "write",
        "delete",
        "exec",
        "execute",
        "shell",
        "subprocess",
        "command",
        "network",
        "http",
        "https",
        "upload",
        "rpc",
    }
)
TEXTUAL_EFFECT_TYPES = frozenset(
    {"", "read", "emit", "llm", "generate", "none", "llm:generate"}
)
MUTATING_PERMISSION_MARKERS = (
    "fs:write",
    "fs:delete",
    "file:write",
    "file:delete",
    "wiki:write",
    "kb:write",
    "kb:ingest",
    "net:",
    "network",
    "http:",
    "https:",
    "upload",
    "browser",
    "tool:shell",
    "tool:bash",
    "tool:run_command",
    "tool:browser",
    "code:execute",
)
_MUTATING_RESOURCE_MARKERS = (
    "filesystem:write",
    "fs:write",
    "upload",
    "browser:",
    "http://",
    "https://",
    "object-storage",
    "s3:",
)
_LLM_GENERIC_CLASSES = frozenset(
    {
        "_GenericSkill",
        "TextGenerationSkill",
        "CodeGenerationSkill",
        "DataAnalysisSkill",
        "BaseSkill",
    }
)
ERROR_CODE = "SIDE_EFFECT_UNREALIZED"
# Empty effects/permissions still count as mutation when SOP/schema says so
# (workspace skills often omit effects). Do not match "write code" / "## FILE".
_SOP_MUTATE_MARKERS = (
    "\u5bf9\u8c61\u5b58\u50a8",  # object storage (zh)
    "\u4e0a\u4f20\u6587\u4ef6\u5230",  # upload file to (zh)
    "\u4e0a\u4f20\u5230\u5bf9\u8c61",  # upload to object (zh)
    "\u751f\u6210\u64ad\u653e\u94fe\u63a5",  # generate playback URL (zh)
    "object storage",
    "put_object",
    "multipart upload",
)
_OUTPUT_MUTATE_KEYS = frozenset(
    {
        "play_url",
        "playback_url",
        "upload_url",
        "cdn_url",
        "object_key",
        "oss_url",
        "s3_url",
    }
)


def _cfg_and_meta(skill: Any) -> Tuple[Any, Dict[str, Any]]:
    if isinstance(skill, dict):
        md = skill.get("metadata") if isinstance(skill.get("metadata"), dict) else {}
        return skill, md
    cfg = getattr(skill, "_config", None) or getattr(skill, "config", None)
    meta: Dict[str, Any] = {}
    if cfg is not None:
        raw = getattr(cfg, "metadata", None)
        if isinstance(raw, dict):
            meta = raw
    if not meta:
        raw = getattr(skill, "metadata", None)
        if isinstance(raw, dict):
            meta = raw
    return cfg, meta


def _execution_type(skill: Any) -> str:
    cfg, meta = _cfg_and_meta(skill)
    for src in (skill, cfg, meta):
        if src is None:
            continue
        if isinstance(src, dict):
            v = src.get("execution_type")
        else:
            v = getattr(src, "execution_type", None)
        if v:
            return str(v).strip().lower()
    return str(meta.get("execution_type") or "").strip().lower()


def _effects(skill: Any) -> List[Dict[str, Any]]:
    cfg, meta = _cfg_and_meta(skill)
    raw = None
    if isinstance(skill, dict):
        raw = skill.get("effects")
    if raw is None and cfg is not None:
        raw = getattr(cfg, "effects", None) if not isinstance(cfg, dict) else cfg.get("effects")
    if raw is None:
        raw = meta.get("effects")
    if not isinstance(raw, list):
        return []
    return [e for e in raw if isinstance(e, dict)]


def _permissions(skill: Any) -> List[str]:
    cfg, meta = _cfg_and_meta(skill)
    raw: Any = None
    if isinstance(skill, dict):
        raw = skill.get("permissions")
    if raw is None and cfg is not None and not isinstance(cfg, dict):
        raw = getattr(cfg, "permissions", None)
        if isinstance(raw, dict):
            raw = None
    if raw is None:
        raw = meta.get("permissions")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    return []


def _skill_dir(skill: Any) -> str:
    _, meta = _cfg_and_meta(skill)
    fs = meta.get("filesystem") if isinstance(meta.get("filesystem"), dict) else {}
    sd = str(fs.get("skill_dir") or "").strip()
    if sd:
        return sd
    md_path = str(fs.get("skill_md") or meta.get("skill_path") or "").strip()
    if md_path:
        return os.path.dirname(md_path)
    if isinstance(skill, dict):
        loc = str(skill.get("skill_dir") or skill.get("path") or "").strip()
        if loc:
            return loc if os.path.isdir(loc) else os.path.dirname(loc)
    return ""


def handler_exists(skill: Any) -> bool:
    sd = _skill_dir(skill)
    if sd and os.path.isfile(os.path.join(sd, "handler.py")):
        return True
    _, meta = _cfg_and_meta(skill)
    hp = str(meta.get("handler_path") or "").strip()
    return bool(hp and os.path.isfile(hp))


def is_mutating_effect(effect: Dict[str, Any]) -> bool:
    t = str(effect.get("type") or "").strip().lower()
    resources = effect.get("resources") or []
    blob = " ".join(str(r).lower() for r in resources)
    if any(m in blob for m in _MUTATING_RESOURCE_MARKERS):
        return True
    if "filesystem" in blob and ("write" in blob or t not in ("read", "emit")):
        return True
    if t in TEXTUAL_EFFECT_TYPES or t.startswith("llm"):
        return False
    if t in MUTATING_EFFECT_TYPES or t in ("both", "mutate"):
        return True
    return False


def _mutating_permissions(perms: Sequence[str]) -> List[str]:
    hit = []
    for p in perms:
        pl = str(p).strip().lower()
        if any(m in pl for m in MUTATING_PERMISSION_MARKERS):
            hit.append(pl)
    return hit


def _class_is_llm_generic(skill: Any) -> bool:
    if isinstance(skill, dict):
        return True
    return type(skill).__name__ in _LLM_GENERIC_CLASSES


def _output_keys(skill: Any) -> List[str]:
    cfg, meta = _cfg_and_meta(skill)
    schema: Any = None
    if isinstance(skill, dict):
        schema = skill.get("output_schema") or skill.get("output")
    if schema is None and cfg is not None:
        schema = getattr(cfg, "output_schema", None) if not isinstance(cfg, dict) else cfg.get("output_schema")
    if schema is None:
        schema = meta.get("output_schema")
    keys: List[str] = []
    if isinstance(schema, dict):
        props = schema.get("properties") if isinstance(schema.get("properties"), dict) else None
        src = props if props else schema
        keys.extend(str(k) for k in src.keys() if str(k).strip() and not str(k).startswith("$"))
    elif isinstance(schema, list):
        for item in schema:
            if isinstance(item, dict) and item.get("name"):
                keys.append(str(item.get("name")))
    return [k.strip().lower() for k in keys]


def _has_file_typed_input(skill: Any) -> bool:
    cfg, meta = _cfg_and_meta(skill)
    blobs: List[Any] = []
    if isinstance(skill, dict):
        blobs.extend([skill.get("input_schema"), skill.get("input")])
    if cfg is not None:
        blobs.append(getattr(cfg, "input_schema", None) if not isinstance(cfg, dict) else cfg.get("input_schema"))
    blobs.append(meta.get("input_schema"))
    for schema in blobs:
        if isinstance(schema, dict):
            for v in schema.values():
                if isinstance(v, dict) and str(v.get("type") or "").lower() in ("file", "binary", "bytes"):
                    return True
            props = schema.get("properties")
            if isinstance(props, dict):
                for v in props.values():
                    if isinstance(v, dict) and str(v.get("type") or "").lower() in ("file", "binary", "bytes"):
                        return True
        if isinstance(schema, list):
            for item in schema:
                if isinstance(item, dict) and str(item.get("type") or "").lower() in ("file", "binary", "bytes"):
                    return True
    return False


def _sop_text(skill: Any) -> str:
    cfg, meta = _cfg_and_meta(skill)
    parts: List[str] = []
    if isinstance(skill, dict):
        for k in ("description", "sop", "body"):
            v = skill.get(k)
            if v:
                parts.append(str(v))
    desc = getattr(cfg, "description", None) if cfg is not None and not isinstance(cfg, dict) else None
    if desc:
        parts.append(str(desc))
    for k in ("sop_markdown", "body", "description"):
        v = meta.get(k)
        if v:
            parts.append(str(v))
    sd = _skill_dir(skill)
    if sd:
        md = os.path.join(sd, "SKILL.md")
        if os.path.isfile(md):
            try:
                parts.append(open(md, encoding="utf-8").read())
            except OSError:
                pass  # noqa: cleanup-best-effort
    return "\n".join(parts)


def _sop_or_schema_implies_mutation(skill: Any) -> bool:
    """True only with direct evidence of upload/object-store I/O, not code emit."""
    keys = set(_output_keys(skill))
    if keys & _OUTPUT_MUTATE_KEYS:
        return True
    blob = _sop_text(skill).lower()
    if any(m.lower() in blob for m in _SOP_MUTATE_MARKERS):
        return True
    if _has_file_typed_input(skill) and ("\u4e0a\u4f20" in _sop_text(skill) or "upload" in blob):
        return True
    return False


def unrealized_side_effect_reason(skill: Any) -> Optional[str]:
    """None if execution may proceed; otherwise a human-readable refusal."""
    et = _execution_type(skill) or "prompt"
    has_handler = handler_exists(skill)
    if et in ("handler", "hybrid") and has_handler:
        return None
    if et == "python_class" and not _class_is_llm_generic(skill):
        return None
    if has_handler and et in ("handler", "hybrid", "python_class"):
        return None

    effects = _effects(skill)
    mutating = [e for e in effects if is_mutating_effect(e)]
    perm_hits = _mutating_permissions(_permissions(skill))
    inferred = False
    if not mutating and not perm_hits:
        # Explicit emit/read means text-only; do not override with SOP keywords.
        if effects:
            return None
        inferred = _sop_or_schema_implies_mutation(skill)
        if not inferred:
            return None

    kinds = sorted(
        {str(e.get("type") or "write").strip().lower() for e in mutating} | set(perm_hits)
    )
    if inferred and not kinds:
        kinds = ["inferred:upload"]
    return (
        f"{ERROR_CODE}: skill declares mutating effects/permissions {kinds} "
        f"but execution_type={et} has no handler.py. Prompt-only skills may emit text "
        "(effects type: emit|read|llm). Add handler.py with execution_type: handler, "
        "or drop write/network/exec claims."
    )


def skill_descriptor_from_md_path(path: str) -> Optional[Dict[str, Any]]:
    """Parse SKILL.md frontmatter into the dict shape the side-effect gate accepts."""
    p = str(path or "").strip()
    if not p or not os.path.isfile(p):
        return None
    try:
        raw = open(p, encoding="utf-8").read()
    except OSError:
        return None
    if not raw.startswith("---"):
        return None
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        import yaml

        fm = yaml.safe_load(parts[1])
    except Exception:
        return None
    if not isinstance(fm, dict):
        return None
    blob = dict(fm)
    blob["body"] = parts[2]
    blob["skill_dir"] = os.path.dirname(p)
    meta = blob.get("metadata") if isinstance(blob.get("metadata"), dict) else {}
    fs = dict(meta.get("filesystem") or {}) if isinstance(meta.get("filesystem"), dict) else {}
    fs.setdefault("skill_dir", blob["skill_dir"])
    fs.setdefault("skill_md", p)
    meta = dict(meta)
    meta["filesystem"] = fs
    blob["metadata"] = meta
    return blob


def skill_result_if_unrealized_side_effects(skill: Any) -> Optional[SkillResult]:
    reason = unrealized_side_effect_reason(skill)
    if not reason:
        return None
    return SkillResult(
        success=False,
        error=reason,
        error_type=ERROR_CODE,
        recovery_hint=(
            "Use a handler or bound tool that actually performs the side effect; "
            "or change effects to emit if the skill only produces text."
        ),
        metadata={"error_code": ERROR_CODE},
    )
