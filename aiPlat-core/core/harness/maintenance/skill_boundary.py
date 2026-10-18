"""Executable skill boundaries: skip_when and untrusted-skill scan.

skip_when is a phrase list. If the current task already states that phrase,
the skill is not run. Scanning is for skills imported from outside the tree.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_NEGATION = re.compile(
    r"不要|没有|并非|不是|并未|别再|勿|without|\bnot\b|\bno\b|don't|do not",
    re.I,
)


def _phrase_affirmed(blob: str, phrase: str) -> bool:
    """True when some occurrence is not in a short negated window."""
    start = 0
    while True:
        idx = blob.find(phrase, start)
        if idx < 0:
            return False
        window = blob[max(0, idx - 12) : idx]
        if not _NEGATION.search(window):
            return True
        start = idx + len(phrase)


_HOSTILE = (
    (re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.I), "prompt_injection"),
    (re.compile(r"(?:curl|wget)[^\n]{0,160}\|\s*(?:sh|bash)\b", re.I), "supply_chain"),
    (re.compile(r"(?:curl|wget)[^\n]{0,160}&&\s*(?:sh|bash)\b", re.I), "supply_chain"),
    (re.compile(r"\$\(\s*(?:curl|wget)\b", re.I), "supply_chain"),
    (
        re.compile(
            r"base64\.b64decode\([\s\S]{0,240}\)\s*[\);]?\s*(?:exec|eval)\s*\(",
            re.I,
        ),
        "tool_abuse",
    ),
    (re.compile(r"(?:api[_-]?key|secret|token)[^\n]{0,80}https?://", re.I), "exfil"),
)


def _skip_phrases(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = re.split(r"[\n;；]", raw)
    elif isinstance(raw, list):
        parts = [str(item) for item in raw]
    else:
        return []
    out = []
    for part in parts:
        text = str(part or "").strip()
        if len(text) >= 4:
            out.append(text)
    return out


def _task_blob(params: Any) -> str:
    if not isinstance(params, dict):
        return str(params or "")
    chunks = []
    for key in ("task", "query", "prompt", "instruction", "user_task", "content"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            chunks.append(value.strip())
    return "\n".join(chunks)


def skill_skip_reason(skill: Any, params: Any) -> Optional[str]:
    """Return a skip reason when the task already matches skip_when.

    Callers must treat a non-None reason as skip (success=False), not success.
    """
    config = getattr(skill, "_config", None)
    meta = getattr(config, "metadata", None) if config is not None else None
    if not isinstance(meta, dict):
        meta = getattr(skill, "metadata", None)
    if not isinstance(meta, dict):
        return None
    phrases = _skip_phrases(
        meta.get("skip_conditions")
        or meta.get("skip_when")
        or meta.get("when_not_to_use")
        or meta.get("When NOT to Use")
    )
    blob = _task_blob(params)
    if not phrases or not blob:
        return None
    for phrase in phrases:
        if _phrase_affirmed(blob, phrase):
            return f"skip_when matched: {phrase[:120]}"
    return None


_SCAN_SUFFIXES = {
    ".md",
    ".py",
    ".sh",
    ".bash",
    ".zsh",
    ".js",
    ".mjs",
    ".ts",
    ".ps1",
    ".bat",
    ".cmd",
    ".json",
}
# Only skip VCS/cache trees — do NOT skip all dotdirs (`.hidden/run.sh` was a bypass).
_SKIP_SCAN_DIRS = {"node_modules", "__pycache__", ".git"}


def _scan_candidate(path: Any) -> bool:
    """Known text suffixes, plus extensionless scripts that start with a shebang."""
    suffix = str(getattr(path, "suffix", "") or "").lower()
    if suffix in _SCAN_SUFFIXES:
        return True
    if suffix:
        return False
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:80]
    except OSError:
        return False
    return head.startswith("#!")


def _skill_tree_text(skill_md: Any) -> str:
    """SKILL.md plus nearby text files. Payload often sits in scripts/, not the frontmatter."""
    from pathlib import Path

    path = Path(str(skill_md)) if skill_md else None
    if path is None or not path.is_file():
        return ""
    root = path.parent
    ranked: list = []
    rest: list = []
    for candidate in root.rglob("*"):
        if not candidate.is_file() or candidate == path:
            continue
        rel_parts = candidate.relative_to(root).parts
        if any(part in _SKIP_SCAN_DIRS for part in rel_parts):
            continue
        if not _scan_candidate(candidate):
            continue
        try:
            if candidate.stat().st_size > 200_000:
                continue
        except OSError:
            continue
        if rel_parts and (
            rel_parts[0] in {"scripts", "bin", "hooks"} or rel_parts[0].startswith(".")
        ):
            ranked.append(candidate)
        else:
            rest.append(candidate)
    files = [path, *ranked, *rest][:80]
    chunks = []
    for item in files:
        try:
            chunks.append(item.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(chunks)


def scan_skill_dir(skill_id: str, skill_md: Any) -> Dict[str, Any]:
    """Scan the skill directory before enable or install."""
    from pathlib import Path

    path = Path(str(skill_md)) if skill_md else None
    if path is None or not path.is_file():
        return {
            "blocked": False,
            "skill": skill_id or "",
            "sarif": {"runs": [{"results": []}]},
        }
    return scan_untrusted_skill_text(skill_id, _skill_tree_text(path))


def scan_untrusted_skill_text(name: str, text: str) -> Dict[str, Any]:
    """Static scan. Blocked when a hostile pattern matches. SARIF-shaped results."""
    body = str(text or "")
    results = []
    for pattern, rule_id in _HOSTILE:
        match = pattern.search(body)
        if not match:
            continue
        line = body[: match.start()].count("\n") + 1
        results.append(
            {
                "ruleId": rule_id,
                "level": "error",
                "message": {"text": f"{rule_id} in skill {name or 'skill'}"},
                "locations": [
                    {
                        "physicalLocation": {
                            "region": {"startLine": line},
                        }
                    }
                ],
            }
        )
    return {
        "blocked": bool(results),
        "skill": name or "",
        "sarif": {
            "version": "2.1.0",
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [
                {
                    "tool": {"driver": {"name": "aiplat-skill-scan"}},
                    "results": results,
                }
            ],
        },
    }
