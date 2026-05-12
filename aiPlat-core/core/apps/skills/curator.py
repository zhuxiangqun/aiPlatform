"""
Skill Curator — autonomous skill lifecycle management.

Implements the Hermes-style curator pattern: inactivity-triggered background
review that auto-transitions lifecycle states (active→stale→archived) and
optionally consolidates similar skills under umbrella parents.

Design: strictly separated from EvolutionEngine (version management). Curator
handles "should this skill still exist?", EvolutionEngine handles "how to create
the next version?".
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class SkillLifecycle(Enum):
    """Skill lifecycle state (curator-managed, not version-managed)."""
    ACTIVE = "active"       # In regular use
    STALE = "stale"         # Not used for stale_after_days
    ARCHIVED = "archived"   # Consolidated into umbrella or deprecated


@dataclass
class CuratorConfig:
    """Configuration for the skill curator."""
    interval_hours: float = 168.0       # Check every 7 days (default)
    min_idle_hours: float = 2.0          # Agent must be idle this long before running
    stale_after_days: int = 30           # Mark as STALE after this many days inactive
    archive_after_days: int = 90         # Move to ARCHIVED after this many days stale
    dry_run: bool = False                # Preview mode: read-only, never mutates
    max_merge_candidates: int = 5        # Max similar skills to consider for umbrella
    state_file: str = "curator_state.json"


@dataclass
class CuratorRunReport:
    """Report from a single curator run."""
    run_at: float
    active_count: int
    stale_count: int
    archived_count: int
    merged: List[str] = field(default_factory=list)
    promoted: List[str] = field(default_factory=list)
    dry_run: bool = False
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class SkillCurator:
    """Autonomous skill lifecycle curator.

    Usage:
        curator = SkillCurator(skill_dir=Path("~/.aiplat/skills"))
        report = await curator.run_if_idle()
        if report:
            print(f"Processed {report.stale_count} stale, "
                  f"{report.archived_count} archived")
    """

    def __init__(self, skill_dir: Optional[Path] = None, config: Optional[CuratorConfig] = None):
        self._skill_dir = skill_dir or Path(
            os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat"))
        ) / "skills"
        self._config = config or CuratorConfig()
        self._state: Dict = {}

    # ── Public API ──────────────────────────────────────────────────────

    async def run_if_idle(self) -> Optional[CuratorRunReport]:
        """Run curator if the conditions are met (idle + interval elapsed)."""
        self._load_state()
        last_run = self._state.get("last_run_at", 0)
        elapsed_hours = (time.time() - last_run) / 3600

        if elapsed_hours < self._config.interval_hours:
            return None

        # Check agent idle (best-effort via state file)
        last_activity = self._state.get("last_activity_at", time.time())
        idle_hours = (time.time() - last_activity) / 3600
        if idle_hours < self._config.min_idle_hours:
            return None

        started = time.time()
        report = await self._run()
        report.duration_seconds = round(time.time() - started, 2)
        report.dry_run = self._config.dry_run

        self._state["last_run_at"] = time.time()
        self._state["run_count"] = self._state.get("run_count", 0) + 1
        self._persist_state()
        return report

    def record_call(self, skill_id: str) -> None:
        """Record a skill invocation for frequency tracking and curator lifecycle."""
        if self._config.dry_run:
            return
        entry = self._skill_dir / skill_id
        if not entry.exists():
            return
        state_file = entry / ".curator_state.json"
        data = {}
        if state_file.exists():
            try:
                with open(state_file, "r") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        data["call_count"] = data.get("call_count", 0) + 1
        data["last_activity_at"] = time.time()
        data["lifecycle"] = "active"  # call → automatic promotion to active
        try:
            with open(state_file, "w") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    # ── Public API ──────────────────────────────────────────────────────

    async def _run(self) -> CuratorRunReport:
        report = CuratorRunReport(run_at=time.time(), active_count=0, stale_count=0, archived_count=0)
        if not self._skill_dir.exists():
            return report

        skills = self._list_skills()
        if not skills:
            return report

        now = time.time()

        for skill_id, meta in skills.items():
            state = meta.get("lifecycle", "active")
            last_used = meta.get("last_activity_at", 0)
            days_since = (now - last_used) / 86400
            call_count = meta.get("call_count", 0)
            pinned = meta.get("pinned", False)

            # Builtin protection: never transition engine/builtin skills
            if meta.get("scope") == "engine" or meta.get("builtin") or meta.get("bundled"):
                report.active_count += 1
                continue

            # Pinned protection: pinned skills never transition to stale/archived
            if pinned:
                report.active_count += 1
                continue

            # High-frequency override: frequently called skills stay active
            if call_count >= 10 and days_since < 60:
                report.active_count += 1
                continue

            # Time-based auto-transitions
            if state == "active" and days_since > self._config.archive_after_days:
                self._transition(skill_id, SkillLifecycle.ARCHIVED, reason=f"inactive {days_since:.0f}d")
                report.archived_count += 1
            elif state == "active" and days_since > self._config.stale_after_days:
                self._transition(skill_id, SkillLifecycle.STALE, reason=f"inactive {days_since:.0f}d")
                report.stale_count += 1
            elif state == "stale" and days_since > self._config.archive_after_days:
                self._transition(skill_id, SkillLifecycle.ARCHIVED, reason=f"stale for {days_since:.0f}d")
                report.archived_count += 1
            else:
                report.active_count += 1

        # Smart merging: group similar stale skills into umbrella parents
        merged = await self._merge_similar(skills)
        report.merged = merged

        # Template promotion: high-frequency skills → reusable templates
        promoted = self._promote_to_template(skills)
        report.promoted = promoted

        return report

    # ── Smart Merge & Template ───────────────────────────────────────────

    async def _merge_similar(self, skills: Dict[str, Dict]) -> List[str]:
        """Merge similar stale/archived skills into umbrella parents."""
        if self._config.dry_run:
            return []
        merged = []
        stale_ids = [sid for sid, m in skills.items()
                     if m.get("lifecycle") in ("stale", "archived") and not m.get("pinned")]
        for i in range(len(stale_ids)):
            for j in range(i + 1, min(i + self._config.max_merge_candidates + 1, len(stale_ids))):
                a, b = stale_ids[i], stale_ids[j]
                if self._names_similar(a, b):
                    umbrella = self._longest_common_prefix(a, b) or f"merged_{a[:8]}_{b[:8]}"
                    # Create umbrella directory
                    umbrella_dir = self._skill_dir / umbrella
                    if not umbrella_dir.exists():
                        umbrella_dir.mkdir(parents=True, exist_ok=True)
                        state_file = umbrella_dir / ".curator_state.json"
                        data = {"lifecycle": "active", "call_count": 0,
                                "umbrella_parent": True, "children": [a, b],
                                "merged_at": time.time()}
                        try:
                            with open(state_file, "w") as f:
                                json.dump(data, f, indent=2)
                        except OSError:
                            pass
                    # Mark children as archived
                    for child in (a, b):
                        self._transition(child, SkillLifecycle.ARCHIVED,
                                        reason=f"merged into umbrella '{umbrella}'")
                    merged.append(f"{a}+{b}={umbrella}")
        return merged

    def _promote_to_template(self, skills: Dict[str, Dict]) -> List[str]:
        """Promote high-frequency skills to reusable templates."""
        if self._config.dry_run:
            return []
        promoted = []
        for skill_id, meta in skills.items():
            if meta.get("call_count", 0) >= 20 and not meta.get("pinned") and not meta.get("template"):
                entry = self._skill_dir / skill_id
                state_file = entry / ".curator_state.json"
                data = {"template": True, "promoted_at": time.time()}
                if state_file.exists():
                    try:
                        with open(state_file, "r") as f:
                            data.update(json.load(f))
                    except (json.JSONDecodeError, OSError):
                        pass
                data["template"] = True
                data["promoted_at"] = time.time()
                try:
                    with open(state_file, "w") as f:
                        json.dump(data, f, indent=2)
                except OSError:
                    pass
                promoted.append(skill_id)
        return promoted

    @staticmethod
    def _names_similar(a: str, b: str) -> bool:
        """Check if two skill names are similar enough to merge."""
        shorter = min(a, b, key=len)
        longer = a if shorter == b else b
        # Simple prefix matching or character overlap
        if shorter and longer.startswith(shorter[:max(len(shorter) // 2, 3)]):
            return True
        common = sum(1 for c in shorter if c in longer)
        return common / max(len(shorter), 1) > 0.5

    @staticmethod
    def _longest_common_prefix(a: str, b: str) -> str:
        """Find the longest common prefix for umbrella naming."""
        prefix = []
        for ca, cb in zip(a, b):
            if ca == cb:
                prefix.append(ca)
            else:
                break
        result = "".join(prefix).rstrip("_")
        return result if len(result) >= 3 else ""

    # ── Helpers ─────────────────────────────────────────────────────────

    def _list_skills(self) -> Dict[str, Dict]:
        """List all skills with their curator metadata."""
        result = {}
        for entry in self._skill_dir.iterdir():
            if not entry.is_dir():
                continue
            state_file = entry / ".curator_state.json"
            meta = {"lifecycle": "active", "last_activity_at": 0}
            if state_file.exists():
                try:
                    with open(state_file, "r") as f:
                        stored = json.load(f)
                    meta.update(stored)
                except (json.JSONDecodeError, OSError):
                    pass
            # Fallback: use directory mtime as last activity
            if not meta.get("last_activity_at"):
                try:
                    meta["last_activity_at"] = os.path.getmtime(entry)
                except OSError:
                    meta["last_activity_at"] = 0
            result[entry.name] = meta
        return result

    def _transition(self, skill_id: str, target: SkillLifecycle, reason: str = ""):
        if self._config.dry_run:
            return
        entry = self._skill_dir / skill_id
        if not entry.exists():
            return

        if target == SkillLifecycle.ARCHIVED:
            self._archive_to_dir(skill_id)
        state_file = entry / ".curator_state.json"
        data = {"lifecycle": target.value, "transition_reason": reason, "transition_at": time.time()}
        if state_file.exists():
            try:
                with open(state_file, "r") as f:
                    data.update(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass
        try:
            with open(state_file, "w") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def _archive_to_dir(self, skill_id: str) -> bool:
        """Move a skill directory to .archive/ for reversible archival."""
        import shutil
        entry = self._skill_dir / skill_id
        if not entry.exists():
            return False
        archive_root = self._skill_dir / ".archive"
        archive_root.mkdir(parents=True, exist_ok=True)
        target = archive_root / skill_id
        if target.exists():
            import shutil
            shutil.rmtree(target)
        shutil.move(str(entry), str(target))
        return True

    def restore_from_archive(self, skill_id: str) -> bool:
        """Restore an archived skill back to the active directory."""
        import shutil
        archive_root = self._skill_dir / ".archive"
        archived = archive_root / skill_id
        if not archived.exists():
            return False
        target = self._skill_dir / skill_id
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(archived), str(target))
        state_file = target / ".curator_state.json"
        data = {"lifecycle": "active", "restored_at": time.time()}
        try:
            with open(state_file, "w") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass
        return True

    def _load_state(self):
        path = Path(self._config.state_file)
        if path.exists():
            try:
                with open(path, "r") as f:
                    self._state = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

    def _persist_state(self):
        path = Path(self._config.state_file)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(self._state, f, indent=2)
        except OSError:
            pass


def get_skill_curator(skill_dir: Optional[Path] = None) -> SkillCurator:
    """Get a curator for the given skill directory."""
    return SkillCurator(skill_dir=skill_dir)
