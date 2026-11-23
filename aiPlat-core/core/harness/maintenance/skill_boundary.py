"""Executable skill boundaries: skip_when and untrusted-skill content gate.

skip_when is a phrase list. If the current task already states that phrase,
the skill is not run. Scanning is for skills imported from outside the tree.

ContentGate (Asset Content Gate v0): heuristic scan of SKILL.md + nearby text.
SecureScan remains package-structure only; this module is the single content path
(合流 scan_skill_dir / scan_untrusted_skill_text). Non-goals: LLM-as-judge,
complete prompt-injection prevention.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

_NEGATION = re.compile(
    r"不要|没有|并非|不是|并未|别再|勿|without|\bnot\b|\bno\b|don't|do not",
    re.I,
)

# ContentGate severity — block refuse-install; degrade install but not schedulable; warn visible only.
GATE_BLOCK = "block"
GATE_DEGRADE = "degrade"
GATE_WARN = "warn"
_GATE_RANK = {GATE_WARN: 1, GATE_DEGRADE: 2, GATE_BLOCK: 3}

# (pattern, rule_id, severity). Extra phrases from AIPLAT_CONTENT_GATE_EXTRA (comma-separated → degrade).
_HOSTILE_RULES: Tuple[Tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.I), "prompt_injection", GATE_BLOCK),
    (re.compile(r"(?:curl|wget)[^\n]{0,160}\|\s*(?:sh|bash)\b", re.I), "supply_chain", GATE_BLOCK),
    (re.compile(r"(?:curl|wget)[^\n]{0,160}&&\s*(?:sh|bash)\b", re.I), "supply_chain", GATE_BLOCK),
    (re.compile(r"\$\(\s*(?:curl|wget)\b", re.I), "supply_chain", GATE_BLOCK),
    (
        re.compile(
            r"base64\.b64decode\([\s\S]{0,240}\)\s*[\);]?\s*(?:exec|eval)\s*\(",
            re.I,
        ),
        "tool_abuse",
        GATE_BLOCK,
    ),
    (re.compile(r"(?:api[_-]?key|secret|token)[^\n]{0,80}https?://", re.I), "exfil", GATE_BLOCK),
    # Soft instruction / tool-abuse heuristics (honest: not semantic-complete).
    (
        re.compile(
            r"(?:send|upload|exfiltrat\w*|post)\s+(?:all\s+)?(?:secrets?|credentials?|api[_-]?keys?|tokens?|"
            r"env(?:ironment)?\s*vars?|\.env)\b",
            re.I,
        ),
        "credential_exfil_instruction",
        GATE_DEGRADE,
    ),
    (
        re.compile(
            r"(?:dump|exfiltrat\w*|harvest)\s+(?:all\s+)?(?:files?|data|secrets?)\b.{0,80}"
            r"(?:http|webhook|pastebin|discord|telegram)",
            re.I,
        ),
        "batch_exfil_instruction",
        GATE_DEGRADE,
    ),
    (
        re.compile(
            r"(?:use|call|invoke)\s+(?:the\s+)?(?:terminal|shell|bash|exec)\b.{0,120}"
            r"(?:secret|credential|api[_-]?key|password|\.env)",
            re.I,
        ),
        "high_risk_tool_cooccurrence",
        GATE_DEGRADE,
    ),
    (
        re.compile(
            r"(?:override|bypass|disable)\s+(?:all\s+)?(?:safety|policy|guardrail|permission)s?\b",
            re.I,
        ),
        "policy_bypass_instruction",
        GATE_WARN,
    ),
    (
        re.compile(r"jailbreak|DAN\s+mode|developer\s+mode\s+enabled", re.I),
        "jailbreak_phrase",
        GATE_WARN,
    ),
)

# Backward-compat alias used by older imports / docs.
_HOSTILE = tuple((pat, rid) for pat, rid, _sev in _HOSTILE_RULES)


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

    Args:
        skill: Skill object with metadata / _config.
        params: Invocation params (task/query/prompt fields scanned).
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


def _extra_degrade_patterns() -> List[Tuple[re.Pattern[str], str, str]]:
    """Optional operator wordlist via AIPLAT_CONTENT_GATE_EXTRA (comma-separated phrases)."""
    raw = str(os.environ.get("AIPLAT_CONTENT_GATE_EXTRA") or "").strip()
    if not raw:
        return []
    out: List[Tuple[re.Pattern[str], str, str]] = []
    for part in raw.split(","):
        phrase = part.strip()
        if len(phrase) < 4:
            continue
        try:
            out.append((re.compile(re.escape(phrase), re.I), "content_gate_extra", GATE_DEGRADE))
        except re.error:
            continue
    return out


def content_gate_findings(text: str) -> List[Dict[str, Any]]:
    """Heuristic ContentGate findings for untrusted skill text.

    Args:
        text: Concatenated skill tree text (SKILL.md + nearby scripts).

    Returns:
        List of finding dicts with rule_id, severity, line, message.
    """
    body = str(text or "")
    findings: List[Dict[str, Any]] = []
    rules = list(_HOSTILE_RULES) + _extra_degrade_patterns()
    for pattern, rule_id, severity in rules:
        match = pattern.search(body)
        if not match:
            continue
        line = body[: match.start()].count("\n") + 1
        findings.append(
            {
                "rule_id": rule_id,
                "severity": severity,
                "line": line,
                "message": f"{rule_id} ({severity})",
                "code": f"content_gate_{rule_id}",
            }
        )
    return findings


def content_gate_level(findings: List[Dict[str, Any]]) -> Optional[str]:
    """Return the highest severity among findings, or None if empty.

    Args:
        findings: Output of content_gate_findings.
    """
    best: Optional[str] = None
    best_rank = 0
    for item in findings or []:
        sev = str(item.get("severity") or "")
        rank = _GATE_RANK.get(sev, 0)
        if rank > best_rank:
            best_rank = rank
            best = sev
    return best


def apply_content_gate_to_compat(compat: Dict[str, Any], scan: Dict[str, Any]) -> Dict[str, Any]:
    """Merge ContentGate scan into a skill COMPAT dict (single content standard).

    Args:
        compat: Mutable compat payload from compute_skill_compat.
        scan: Result of scan_skill_dir / scan_untrusted_skill_text.

    Returns:
        The same compat dict after mutation.
    """
    if not isinstance(compat, dict):
        return compat
    findings = list(scan.get("findings") or []) if isinstance(scan, dict) else []
    level = content_gate_level(findings) if findings else (
        GATE_BLOCK if isinstance(scan, dict) and scan.get("blocked") else None
    )
    issues = list(compat.get("issues") or [])
    for finding in findings:
        sev = str(finding.get("severity") or GATE_WARN)
        issues.append(
            {
                "code": str(finding.get("code") or f"content_gate_{finding.get('rule_id') or 'hit'}"),
                "severity": "error" if sev == GATE_BLOCK else ("warning" if sev == GATE_DEGRADE else "info"),
                "message": str(finding.get("message") or finding.get("rule_id") or "content_gate"),
                "gate": sev,
            }
        )
    if level == GATE_BLOCK:
        compat["tier"] = "blocked"
        compat["schedulable"] = False
        compat["ui_state"] = "不能用"
        upgrade = dict(compat.get("upgrade") or {})
        upgrade["recommended"] = "content_gate_blocked"
        compat["upgrade"] = upgrade
    elif level == GATE_DEGRADE:
        # Installable but not default-schedulable（还差几步）.
        compat["schedulable"] = False
        if str(compat.get("tier") or "") == "blocked":
            pass
        else:
            compat["ui_state"] = "还差几步"
        upgrade = dict(compat.get("upgrade") or {})
        upgrade["recommended"] = "review_content_gate"
        compat["upgrade"] = upgrade
        issues.append(
            {
                "code": "content_gate_degrade",
                "severity": "warning",
                "message": "content gate degrade: not default-schedulable (heuristic; not semantic-complete)",
                "gate": GATE_DEGRADE,
            }
        )
    compat["issues"] = issues
    if level:
        compat["content_gate"] = {"level": level, "finding_count": len(findings)}
    return compat


def scan_skill_dir(skill_id: str, skill_md: Any) -> Dict[str, Any]:
    """Scan the skill directory before enable or install (ContentGate + SARIF).

    Args:
        skill_id: Skill ID.
        skill_md: Path to SKILL.md.
    """
    from pathlib import Path

    path = Path(str(skill_md)) if skill_md else None
    if path is None or not path.is_file():
        return {
            "blocked": False,
            "gate_level": None,
            "findings": [],
            "skill": skill_id or "",
            "sarif": {"runs": [{"results": []}]},
        }
    return scan_untrusted_skill_text(skill_id, _skill_tree_text(path))


def scan_untrusted_skill_text(name: str, text: str) -> Dict[str, Any]:
    """Static ContentGate. blocked=True only for block-severity hits.

    Args:
        name: Skill name for SARIF messages.
        text: Skill tree text to scan.

    Returns:
        Dict with blocked, gate_level, findings, skill, sarif.
    """
    findings = content_gate_findings(text)
    level = content_gate_level(findings)
    results = []
    for finding in findings:
        results.append(
            {
                "ruleId": finding["rule_id"],
                "level": "error" if finding["severity"] == GATE_BLOCK else (
                    "warning" if finding["severity"] == GATE_DEGRADE else "note"
                ),
                "message": {
                    "text": f"{finding['rule_id']} in skill {name or 'skill'} [{finding['severity']}]"
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "region": {"startLine": int(finding.get("line") or 1)},
                        }
                    }
                ],
                "properties": {"gate": finding["severity"]},
            }
        )
    return {
        "blocked": level == GATE_BLOCK,
        "gate_level": level,
        "findings": findings,
        "skill": name or "",
        "sarif": {
            "version": "2.1.0",
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [
                {
                    "tool": {"driver": {"name": "AssetContentGate"}},
                    "results": results,
                }
            ],
        },
    }
