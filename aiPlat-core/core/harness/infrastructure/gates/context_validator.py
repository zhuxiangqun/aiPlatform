"""
ContextValidator — pre-context quality validation.

Runs BEFORE ContextGate.assemble(): dedup, staleness check, conflict detection.
Reduces token waste before it reaches the model.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    deduplicated: List[Dict[str, Any]] = field(default_factory=list)
    removed_count: int = 0
    stale_warnings: List[str] = field(default_factory=list)
    conflict_markers: List[Dict[str, Any]] = field(default_factory=list)
    quality_score: int = 100
    token_saved: int = 0


class ContextValidator:
    """
    Pre-context validation: dedup, staleness, conflict detection.
    
    Three checks:
      1. Dedup — SHA-256 exact match + near-duplicate (Jaccard > 0.95) removal
      2. Staleness — messages > 24h old with code/version references
      3. Conflict — contradictory fact assertions detected
    """

    _STALE_THRESHOLD_S: float = 86400.0  # 24 hours
    _CODE_VERSION_PATTERNS: Tuple[re.Pattern, ...] = (
        re.compile(r'(?:using|version|upgrade|migrate).*\d+\.\d+', re.I),
        re.compile(r'(?:import|from)\s+\S+', re.I),
        re.compile(r'(?:file|path|directory).*[./]', re.I),
    )
    _DUPE_JACCARD_THRESHOLD: float = 0.95

    def validate(
        self,
        messages: List[Dict[str, Any]],
        *,
        memory_context: Optional[List[Dict[str, Any]]] = None,
        validate_staleness: bool = True,
        validate_conflicts: bool = True,
    ) -> ValidationResult:
        """
        Validate and deduplicate context messages.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            memory_context: Optional memory messages to check for staleness
            validate_staleness: Enable staleness check
            validate_conflicts: Enable conflict detection
        """
        all_messages = (memory_context or []) + (messages or [])
        result = ValidationResult()
        if not all_messages:
            return result

        # 1. Deduplication
        result.deduplicated, result.removed_count = self._dedup(all_messages)
        tok_saved = self._estimate_tokens_removed(all_messages, result.deduplicated)
        result.token_saved = tok_saved

        # 2. Staleness check
        if validate_staleness:
            result.stale_warnings = self._check_staleness(result.deduplicated)

        # 3. Conflict detection
        if validate_conflicts:
            result.conflict_markers = self._detect_conflicts(result.deduplicated)

        # Quality score
        max_score = 100
        score = max_score
        if result.removed_count > 0:
            score -= min(10, result.removed_count * 2)
        if result.stale_warnings:
            score -= min(15, len(result.stale_warnings) * 5)
        if result.conflict_markers:
            score -= min(15, len(result.conflict_markers) * 5)
        result.quality_score = max(0, score)

        if score < 50:
            log.warning("Low context quality: score=%d dupes=%d stale=%d conflicts=%d",
                       score, result.removed_count, len(result.stale_warnings), len(result.conflict_markers))

        return result

    def _hash_content(self, content: str) -> str:
        """Normalize and hash message content."""
        return hashlib.md5(content.strip().lower().encode()).hexdigest()

    def _jaccard(self, a: str, b: str) -> float:
        """Jaccard similarity on tokenized text."""
        sa = set(a.lower().split())
        sb = set(b.lower().split())
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    def _dedup(self, messages: List[Dict]) -> Tuple[List[Dict], int]:
        """Remove exact and near-duplicate messages."""
        seen: Dict[str, int] = {}  # hash → index
        result: List[Dict] = []
        removed = 0

        for i, msg in enumerate(messages):
            content = str(msg.get("content", ""))
            if not content.strip():
                result.append(msg)
                continue

            h = self._hash_content(content)

            # Exact match
            if h in seen:
                removed += 1
                continue

            # Near-duplicate check against recent messages
            is_dupe = False
            for j, prev in enumerate(result[-5:]):  # check last 5
                prev_content = str(prev.get("content", ""))
                if self._jaccard(content, prev_content) > self._DUPE_JACCARD_THRESHOLD:
                    is_dupe = True
                    removed += 1
                    break

            if not is_dupe:
                seen[h] = i
                result.append(msg)

        return result, removed

    def _check_staleness(self, messages: List[Dict]) -> List[str]:
        """Detect stale information (code/version refs that may be outdated)."""
        warnings = []
        now = time.time()

        for i, msg in enumerate(messages):
            ts = msg.get("timestamp", 0.0) or 0.0
            if ts <= 0:
                continue
            age = now - ts
            if age < self._STALE_THRESHOLD_S:
                continue

            content = str(msg.get("content", ""))
            for pattern in self._CODE_VERSION_PATTERNS:
                if pattern.search(content):
                    age_days = age / 86400
                    warnings.append(
                        f"Message #{i+1} ({age_days:.0f}d old): "
                        f"contains code/version ref may be outdated — "
                        f"'{str(pattern.search(content).group())[:60]}'"
                    )
                    break

        return warnings

    def _detect_conflicts(self, messages: List[Dict]) -> List[Dict[str, Any]]:
        """Detect contradictory fact assertions in context."""
        conflicts = []
        version_pattern = re.compile(r'(?:version|v)\s*(\d+\.\d+(?:\.\d+)?)', re.I)
        library_pattern = re.compile(r'(?:using|with)\s+([\w-]+)\s+(?:v?)(\d+\.\d+)', re.I)

        versions: Dict[str, Dict] = {}  # lib_name → {version, message_index}
        
        for i, msg in enumerate(messages):
            content = str(msg.get("content", ""))
            for m in library_pattern.finditer(content):
                lib = m.group(1).lower()
                ver = m.group(2)
                if lib in versions and versions[lib]["version"] != ver:
                    conflicts.append({
                        "key": lib,
                        "values": [versions[lib]["version"], ver],
                        "indices": [versions[lib]["index"], i],
                        "detail": f"'{lib}' version conflict: {versions[lib]['version']} vs {ver}",
                    })
                versions[lib] = {"version": ver, "index": i}

        return conflicts

    def _estimate_tokens_removed(self, original: List[Dict], deduplicated: List[Dict]) -> int:
        """Estimate tokens saved by deduplication (rough: chars/4)."""
        orig_chars = sum(len(str(m.get("content", ""))) for m in original)
        dedup_chars = sum(len(str(m.get("content", ""))) for m in deduplicated)
        return (orig_chars - dedup_chars) // 4


_validator: Optional[ContextValidator] = None


def get_context_validator() -> ContextValidator:
    global _validator
    if _validator is None:
        _validator = ContextValidator()
    return _validator


__all__ = ["ContextValidator", "ValidationResult", "get_context_validator"]
