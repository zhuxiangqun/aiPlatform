"""
CLAUDE.md loader / scanner for project-level AI guidelines.

This module enables enforcing "project-level contract" (CLAUDE.md) inside the
aiPlat execution chain (server-side), not just in IDEs.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


_INJECTION_PATTERNS = [
    (re.compile(r"ignore\s+(previous|all|above|prior)\s+instructions", re.I), "prompt_injection"),
    (re.compile(r"do\s+not\s+tell\s+the\s+user", re.I), "deception_hide"),
    (re.compile(r"system\s+prompt\s+override", re.I), "sys_prompt_override"),
    # common exfil / jailbreak wording
    (re.compile(r"(exfiltrate|leak|steal)\s+(secrets?|keys?|tokens?)", re.I), "exfiltration_attempt"),
    (re.compile(r"(upload|send)\s+.*(to|into)\s+https?://", re.I), "url_exfiltration"),
    (re.compile(r"BEGIN\s+PRIVATE\s+KEY", re.I), "embedded_private_key"),
    (re.compile(r"api[_-]?key\s*[:=]", re.I), "secret_mention"),
    # encoding/obfuscation hints
    (re.compile(r"base64\s*[:=]|-----BEGIN", re.I), "encoding_or_pem"),
    (re.compile(r"\b[a-f0-9]{32,}\b", re.I), "suspicious_hex_blob"),
]

_INVISIBLE_CHARS = {
    "\u200b",
    "\u200c",
    "\u200d",
    "\u2060",
    "\ufeff",
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
}


@dataclass
class ClaudeMdDecision:
    action: str  # none|warn|truncate|block|approval_required
    policy: str
    findings: List[str]
    path: str
    sha256: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "action": self.action,
            "policy": self.policy,
            "findings": list(self.findings or []),
            "path": self.path,
            "sha256": self.sha256,
        }


def _scan(text: str, *, path: str) -> Tuple[str, ClaudeMdDecision]:
    """
    Scan CLAUDE.md content for injection-like patterns.

    Policy via env AIPLAT_CLAUDE_MD_POLICY:
      - warn (default): keep content, record findings
      - truncate: redact suspicious patterns, keep rest
      - block: drop content
      - approval_required: drop content and mark as approval_required (best-effort)
    """
    policy = os.getenv("AIPLAT_CLAUDE_MD_POLICY", "warn").strip().lower() or "warn"
    if policy not in {"block", "warn", "truncate", "approval_required"}:
        policy = "warn"

    findings: List[str] = []
    for ch in _INVISIBLE_CHARS:
        if ch in text:
            findings.append(f"invisible_unicode_U+{ord(ch):04X}")

    matched: List[Tuple[re.Pattern, str]] = []
    for pat, reason in _INJECTION_PATTERNS:
        try:
            if pat.search(text):
                findings.append(reason)
                matched.append((pat, reason))
        except Exception:
            continue

    sha = hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None
    d = ClaudeMdDecision(action="none", policy=policy, findings=findings, path=path, sha256=sha)
    if not findings:
        return text, d

    if policy == "warn":
        d.action = "warn"
        return text, d

    if policy == "truncate":
        redacted = text
        for pat, _reason in matched:
            try:
                redacted = pat.sub("[REDACTED]", redacted)
            except Exception:
                continue
        d.action = "truncate"
        d.sha256 = hashlib.sha256(redacted.encode("utf-8")).hexdigest() if redacted else None
        return redacted, d

    if policy == "approval_required":
        d.action = "approval_required"
        return "", d

    d.action = "block"
    return "", d


def load_claude_md(repo_root: str) -> Tuple[str, Optional[str], ClaudeMdDecision]:
    """
    Load CLAUDE.md from repo root (best-effort).
    Returns: (content, used_path, decision)
    """
    root = Path(str(repo_root)).expanduser()
    p = root / "CLAUDE.md"
    if not p.is_file():
        return "", None, ClaudeMdDecision(action="none", policy=os.getenv("AIPLAT_CLAUDE_MD_POLICY", "warn"), findings=[], path=str(p))
    try:
        text = p.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        text = ""
    if not text:
        return "", str(p), ClaudeMdDecision(action="none", policy=os.getenv("AIPLAT_CLAUDE_MD_POLICY", "warn"), findings=[], path=str(p))
    scanned, decision = _scan(text, path=str(p))
    return scanned, str(p), decision


def load_claude_md_file(file_path: str) -> Tuple[str, Optional[str], ClaudeMdDecision]:
    """
    Load and scan a CLAUDE.md by explicit file path.
    Returns: (content, used_path, decision)
    """
    p = Path(str(file_path)).expanduser()
    if p.is_dir():
        p = p / "CLAUDE.md"
    if not p.is_file():
        return "", None, ClaudeMdDecision(action="none", policy=os.getenv("AIPLAT_CLAUDE_MD_POLICY", "warn"), findings=[], path=str(p))
    try:
        text = p.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        text = ""
    if not text:
        return "", str(p), ClaudeMdDecision(action="none", policy=os.getenv("AIPLAT_CLAUDE_MD_POLICY", "warn"), findings=[], path=str(p))
    scanned, decision = _scan(text, path=str(p))
    return scanned, str(p), decision


def find_nearest_claude_md_root(path: str) -> Optional[str]:
    """
    Given a file or directory path, walk up parents to find a directory
    containing CLAUDE.md. Returns that directory path, or None.
    """
    try:
        p = Path(str(path)).expanduser()
        # If looks like a file, start from parent
        if p.suffix:
            cur = p.parent
        else:
            cur = p
        cur = cur.resolve()
        for d in [cur] + list(cur.parents):
            try:
                if (d / "CLAUDE.md").is_file():
                    return str(d)
            except Exception:
                continue
    except Exception:
        return None
    return None


def infer_claude_md_files_from_text(text: str, *, workspace_root: Optional[str] = None) -> List[str]:
    """
    Infer relevant CLAUDE.md files from free-form text (task/user message).

    Heuristics:
    - absolute paths: /.../aiPlat-core/... or /.../aiPlat-management/...
    - relative paths mentioning repo folders: aiPlat-core/... or aiPlat-management/...
    - bare repo hints: "aiPlat-core" / "aiPlat-management"
    """
    t = str(text or "")
    if not t.strip():
        return []

    # Resolve workspace root if not provided (best-effort).
    if not workspace_root:
        try:
            here = Path(__file__).resolve()  # .../aiPlat-core/core/harness/context/claude_md.py
            core_repo_root = here.parents[3]  # .../aiPlat-core
            workspace_root = str(core_repo_root.parent)
        except Exception:
            workspace_root = None

    cand: List[str] = []
    # Repo path-like hints
    for m in re.findall(r"(aiPlat-(?:core|management)/[A-Za-z0-9_\-./]+)", t):
        cand.append(str(m))
    # Absolute path hints (very permissive: any /.../suffix with these repo names)
    for m in re.findall(r"(/[^\\s'\"`]+aiPlat-(?:core|management)/[^\\s'\"`]+)", t):
        cand.append(str(m))

    # Bare repo name hints
    if "aiplat-core" in t.lower() or "aiplat core" in t.lower() or "aiPlat-core" in t:
        cand.append("aiPlat-core")
    if "aiplat-management" in t.lower() or "aiplat management" in t.lower() or "aiPlat-management" in t:
        cand.append("aiPlat-management")

    # Normalize to absolute paths when possible
    abs_paths: List[str] = []
    for p in cand:
        p0 = str(p or "").strip()
        if not p0:
            continue
        if p0.startswith("/"):
            abs_paths.append(p0)
        elif workspace_root:
            abs_paths.append(str(Path(str(workspace_root)) / p0))

    # Map to nearest CLAUDE.md roots
    roots: List[str] = []
    for p in abs_paths:
        r = find_nearest_claude_md_root(p)
        if r:
            roots.append(r)

    roots = list(dict.fromkeys(roots))
    files: List[str] = []
    for r in roots:
        try:
            fp = str(Path(r) / "CLAUDE.md")
            if Path(fp).is_file():
                files.append(fp)
        except Exception:
            continue
    return list(dict.fromkeys(files))
