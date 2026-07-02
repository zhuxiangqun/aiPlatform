"""
Auto-fixer loop — repairs P2 (low-risk) issues.

checkpoint: git stash push -u before each round
rollback:   git stash pop on scope violation or error
circular:   uses dependency injection (review_callback) — no import from handler
"""

import logging
import re

from core.harness.syscalls import sys_tool_call
from core.harness.utils.model_injection import best_model_for_purpose
from core.harness.syscalls.llm import sys_llm_generate
from core.engine.skills.autoreview.review_report import ReviewReport
from core.engine.skills.autoreview.scope_governor import ScopeGovernor

_log = logging.getLogger("autoreview.fixer")

FIX_SYSTEM_PROMPT = (
    "Generate ONLY the exact code patch to apply. "
    "Output the OLD code block followed by the NEW code block, each wrapped in ```.\n"
    "Example:\n"
    "```python\nold_code_line\n```\n"
    "```python\nnew_code_line\n```"
)


async def auto_fix_loop(
    report: ReviewReport,
    governor: ScopeGovernor,
    diff_refresh_fn,
    review_callback,      # ← injected by handler.py (avoids circular import)
    max_rounds: int = 2,
) -> ReviewReport:
    """Auto-fix P2 issues with git stash checkpoint + rollback."""
    for round_num in range(max_rounds):
        fixes = report.fixable_p2_issues()
        if not fixes:
            break

        # checkpoint — include untracked files
        await sys_tool_call(
            "git",
            {"args": ["stash", "push", "-u", "-m", f"autoreview_checkpoint_r{round_num + 1}"]},
        )

        try:
            for fix in fixes:
                try:
                    patch_resp = await sys_llm_generate(
                        best_model_for_purpose("code_gen"),
                        [
                            {"role": "system", "content": FIX_SYSTEM_PROMPT},
                            {
                                "role": "user",
                                "content": (
                                    f"Fix this issue in {fix.file}:{fix.line}:\n"
                                    f"{fix.description}\n\n"
                                    f"Fix suggestion: {fix.fix_suggestion}\n\n"
                                    "Output ONLY old/new code blocks."
                                ),
                            },
                        ],
                    )
                    patch = _parse_patch(str(patch_resp))
                    if patch.get("old") is not None and patch.get("new") is not None:
                        await sys_tool_call(
                            "file_edit",
                            {
                                "path": fix.file,
                                "old": patch["old"],
                                "new": patch["new"],
                            },
                        )
                        report.auto_fixed_count += 1
                        fix.additions = len(patch["new"].split("\n"))
                        fix.deletions = len(patch["old"].split("\n"))
                except Exception as e:
                    _log.warning("Fix failed for %s:%d: %s", fix.file, fix.line, e)

            # re-review
            diff = diff_refresh_fn()
            report = await review_callback(diff, "style")

            # scope governor check
            if not governor.check(report):
                await sys_tool_call("git", {"args": ["stash", "pop"]})
                return report.mark_abandoned("Scope Governor rejected fix round")

        except Exception as e:
            await sys_tool_call("git", {"args": ["stash", "pop"]})
            return report.mark_abandoned(f"Auto-fix error: {e}")

    return report


def _parse_patch(llm_output: str) -> dict:
    """Extract old/new code blocks from LLM output. Handles any language tag."""
    blocks = re.findall(r'```(?:\w+)?\s*\n(.*?)\n```', llm_output, re.DOTALL)
    if len(blocks) >= 2:
        return {"old": blocks[0].strip(), "new": blocks[1].strip()}
    if len(blocks) == 1:
        return {"old": "", "new": blocks[0].strip()}
    return {}
