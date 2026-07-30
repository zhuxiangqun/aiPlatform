"""

Skill Curator — periodic skill lifecycle manager (Hermes Agent style).



Reviews all skills every 7 days:

  - 30 days no execution → stale (decayed_at)

  - 90 days no execution → archived (enabled=False)

  - Overlapping skills (>70% name similarity) → merge suggestions



callers: background scheduler (_scheduler_loop), GET /system/curate-skills

"""



from __future__ import annotations



import json

import logging

import os as _os

import time as _time_curator

from typing import Any, Dict, List, Optional



logger = logging.getLogger(__name__)



_CURATOR_STATE = _os.path.expanduser("~/.aiplat/curator_state.json")





def _should_curate() -> bool:

    """Check if 7 days have passed since last curation."""

    now = int(_time_curator.time())

    try:

        if _os.path.exists(_CURATOR_STATE):

            with open(_CURATOR_STATE) as f:

                last = json.load(f).get("last_curation_ts", 0)

            delta = now - last

            if delta < 7 * 86400:

                logger.debug("SkillCurator skipped: last run %d seconds ago", delta)

                return False

    except Exception:

        logging.getLogger(__name__).debug('_should_curate failed', exc_info=True)
    return True





def _save_curation_ts():

    try:

        _os.makedirs(_os.path.dirname(_CURATOR_STATE), exist_ok=True)

        with open(_CURATOR_STATE, "w") as f:

            json.dump({"last_curation_ts": int(_time_curator.time())}, f)

    except Exception:

        logging.getLogger(__name__).debug('_save_curation_ts failed', exc_info=True)




def _token_overlap(a: str, b: str) -> float:

    ta = set(a.lower().replace("_", " ").split())

    tb = set(b.lower().replace("_", " ").split())

    union = len(ta | tb)

    return len(ta & tb) / union if union > 0 else 0.0





def _common_prefix(a: str, b: str) -> str:

    parts_a = a.split("_")

    parts_b = b.split("_")

    common = [pa for pa, pb in zip(parts_a, parts_b) if pa == pb]

    return "_".join(common) + "_umbrella" if common else "merged_skill"





class SkillCurator:

    """Periodic skill lifecycle manager."""



    STALE_DAYS = 30

    ARCHIVE_DAYS = 90

    MERGE_SIMILARITY = 0.7



    def curate(self) -> Dict[str, Any]:

        if not _should_curate():

            return {"skipped": True, "reason": "Last curation < 7 days ago"}



        from core.apps.skills.registry import SkillRegistry



        sr = SkillRegistry()

        now = int(_time_curator.time())

        stale_cutoff = now - self.STALE_DAYS * 86400

        archive_cutoff = now - self.ARCHIVE_DAYS * 86400



        actions = {"stale": [], "archived": [], "merge_suggestions": [], "reviewed": 0}



        active_skills = [

            (name, stats) for name, stats in sr._binding_stats.items()

            if stats.total_executions > 0 and sr._enabled.get(name, True)

        ]



        # ── 1. Stale/Archive detection ──

        for name, stats in active_skills:

            actions["reviewed"] += 1

            last_ts = getattr(stats, 'last_executed_at', 0) or 0

            if last_ts == 0:

                continue

            if last_ts < archive_cutoff:

                sr._enabled[name] = False

                actions["archived"].append({

                    "skill": name, "last_executed": last_ts,

                    "reason": f"last activity {self.ARCHIVE_DAYS}+ days ago",

                })

            elif last_ts < stale_cutoff:

                stats.decayed_at = now

                actions["stale"].append({

                    "skill": name, "last_executed": last_ts,

                    "reason": f"last activity {self.STALE_DAYS}+ days ago",

                })



        # ── 2. Merge suggestions ──

        names = [name for name, _ in active_skills]

        for i, a in enumerate(names):

            for b in names[i + 1:]:

                overlap = _token_overlap(a, b)

                if overlap >= self.MERGE_SIMILARITY:

                    actions["merge_suggestions"].append({

                        "skill_a": a, "skill_b": b,

                        "overlap": round(overlap, 2),

                        "umbrella": _common_prefix(a, b),

                    })



        _save_curation_ts()

        logger.info(

            "SkillCurator: reviewed %d — %d stale, %d archived, %d merge",

            actions["reviewed"], len(actions["stale"]),

            len(actions["archived"]), len(actions["merge_suggestions"])

        )

        return actions

