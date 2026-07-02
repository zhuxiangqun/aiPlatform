"""
Scope Governor — prevents review fixes from expanding into refactoring.

Stop conditions (any one triggers):
  1. Modified files outside baseline
  2. Net line increase > 50% of baseline (100% for P0 security fixes)
  3. Two fix rounds without convergence
"""

from dataclasses import dataclass, field
from core.engine.skills.autoreview.review_report import ReviewReport


@dataclass
class ScopeGovernor:
    initial_files: set
    initial_lines: int
    fix_rounds: int = field(default=0)
    prev_issue_count: int = field(default=0)

    def check(self, report: ReviewReport) -> bool:
        self.fix_rounds += 1

        # 1. File boundary
        new_files = set(report.all_files()) - self.initial_files
        if new_files:
            report.add_scope_violation(
                f"Modified files outside baseline: {new_files}"
            )
            return False

        # 2. Net line increase
        net_increase = sum(
            i.additions - i.deletions
            for i in report.issues
            if i.fix_suggestion
        )
        multiplier = 2.0 if report.p0_count > 0 else 1.0
        threshold = self.initial_lines * 0.5 * multiplier
        if net_increase > threshold:
            report.add_scope_violation(
                f"Net increase ({net_increase}) exceeds threshold ({threshold:.0f}) "
                f"from baseline {self.initial_lines} lines"
            )
            return False

        # 3. Convergence
        if self.fix_rounds >= 2 and report.issue_count >= self.prev_issue_count:
            report.add_scope_violation(
                "Two fix rounds without convergence"
            )
            return False

        self.prev_issue_count = report.issue_count
        return True
