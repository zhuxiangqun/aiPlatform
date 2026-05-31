"""Lint rule: conflict pair detection (Jaccard-based routing overlap)."""

import re
from typing import Any, Dict, List

from core.management.skill_linter_base import LintIssue, LintRule


def _norm_text(s: str) -> str:
    s0 = str(s or "").strip().lower()
    s0 = re.sub(r"[\s\-._/]+", " ", s0)
    s0 = re.sub(r"[^\w\u4e00-\u9fff ]+", "", s0)
    return s0.strip()


class ConflictPairCheck(LintRule):
    code = "conflict_pair_high_overlap"
    level = "warning"
    category = "trigger"

    def check(self, skill: Any) -> List[LintIssue]:
        sid = str(getattr(skill, "id", "") or (skill.get("id") if isinstance(skill, dict) else "") or "").strip()
        meta = self._get_meta(skill)
        confs = meta.get("_conflicts") if isinstance(meta.get("_conflicts"), list) else []
        if not confs:
            return []
        try:
            top = confs[0] if isinstance(confs[0], dict) else None
            j = float((top or {}).get("jaccard") or 0.0) if top else 0.0
            ov = (top or {}).get("overlap_tokens") if isinstance((top or {}).get("overlap_tokens"), list) else []
            if j >= 0.35 and len(ov) >= 3:
                a = (top.get("skill_a") or {}) if isinstance(top.get("skill_a"), dict) else {}
                b = (top.get("skill_b") or {}) if isinstance(top.get("skill_b"), dict) else {}
                other = b if str(a.get("skill_id") or "") == sid else a
                return [LintIssue(
                    level=self.level, code=self.code,
                    message=f"路由冲突：与 {other.get('name') or other.get('skill_id')} 的 token 重合偏高（jaccard={j:.2f}）。建议做冲突对定向消歧（negative_triggers/constraints/减少泛化 triggers）。",
                    location="observability.lint_conflicts",
                )]
        except Exception:
            pass
        return []

    @staticmethod
    def _get_meta(skill: Any) -> dict:
        meta = getattr(skill, "metadata", None) if not isinstance(skill, dict) else skill.get("metadata")
        return meta if isinstance(meta, dict) else {}
