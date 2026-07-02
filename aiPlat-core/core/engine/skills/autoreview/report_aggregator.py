"""
Multi-engine result aggregation — line-anchor + voting.

Dedup: (file, line, severity) triple exact match → merge
Vote:  3 engines agree → P0, 2 agree → P1, 1 alone → P2 (source-labeled)
Complexity: O(n log n), no embedding matrix ops.
"""

from collections import defaultdict
from typing import Dict, List
from core.engine.skills.autoreview.review_report import ReviewReport, ReviewIssue


def aggregate_reports(
    reports: List[ReviewReport],
    engine_names: List[str],
) -> ReviewReport:
    """Vote-aggregate three engine reports into a single panel report."""
    all_issues = []
    for i, eng in enumerate(engine_names):
        for issue in reports[i].issues:
            issue.engine = eng
            issue.engines = [eng]
            all_issues.append(issue)

    groups: Dict[tuple, list] = defaultdict(list)
    for issue in all_issues:
        key = (issue.file, issue.line, issue.severity)
        groups[key].append(issue)

    common = []
    unique: Dict[str, list] = {eng: [] for eng in engine_names}

    for _key, issues in groups.items():
        eng_count = len(set(i.engine for i in issues))
        if eng_count >= 3:
            merged = _merge(issues, "P0")
            common.append(merged)
        elif eng_count == 2:
            merged = _merge(issues, "P1")
            common.append(merged)
        else:
            for issue in issues:
                issue.severity = "P2"
                unique[issue.engine].append(issue)

    report = ReviewReport()
    report.common_findings = common
    report.unique_findings = unique
    report.issues = common + [i for items in unique.values() for i in items]
    return report


def _merge(issues: List[ReviewIssue], final_severity: str) -> ReviewIssue:
    """Merge same-key issues. First issue provides detail, severity is final vote."""
    merged = issues[0]
    merged.severity = final_severity
    merged.engines = sorted(set(i.engine for i in issues))
    merged.engine = "+".join(merged.engines)
    return merged


# ── MoA Deep Mode: Aggregator LLM prompt + evidence card builder ──

AGGREGATOR_PROMPT = """You are a chief architect. Below are review reports from multiple engines.

Your task:
1. **CONSENSUS UPGRADE**: If >=2 reports flag the same file:line:issue, upgrade to P0.
2. **CONFLICT ARBITRATION**: If reports disagree on severity, pick the safer (more conservative) level.
3. **DEDUP**: If reports describe the same root cause differently, merge into one issue citing all engines.

Output ONLY a valid JSON object:
{{"issues": [{{"file": "...", "line": 0, "severity": "P0|P1|P2", "category": "...", "description": "...", "fix_suggestion": "...", "engines": ["A","B"]}}]}}
{reports}
"""


def build_aggregator_prompt(raw_reports, engine_names) -> str:
    """Build Aggregator prompt from 2-3 engine reports, handling variable engine count."""
    report_sections = []
    for name, report in zip(engine_names, raw_reports):
        report_sections.append(f"--- Engine: {name} ---\n{compact_report(report)}")
    return AGGREGATOR_PROMPT.format(reports="\n\n".join(report_sections))


def compact_report(report) -> str:
    """Compress a ReviewReport to compact evidence cards (<300 tokens total).
    
    Each issue is summarized in one line: [severity] file:line (category) description.
    If no issues found, returns a clear empty marker to avoid prompt format damage.
    """
    if not report.issues:
        return "No issues found in this review."

    cards = []
    for issue in report.issues:
        cards.append(
            f"  [{issue.severity}] {issue.file}:{issue.line} ({issue.category})\n"
            f"    {issue.description[:80]}"
        )
    return "\n".join(cards)
