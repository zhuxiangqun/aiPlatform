"""
Autoreview skill handler — auto code review engine.

Single engine: best_model_for_purpose("reasoning") → P0/P1 + code_gen → P2
Panel mode:   reasoning + code_gen + chat (only when focus=security AND panel=true)
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict

from core.harness.utils.model_injection import best_model_for_purpose
from core.harness.syscalls.llm import sys_llm_generate
from core.engine.skills.autoreview.diff_loader import load_diff
from core.engine.skills.autoreview.scope_governor import ScopeGovernor
from core.engine.skills.autoreview.review_report import ReviewReport
from core.engine.skills.autoreview.report_aggregator import aggregate_reports
from core.engine.skills.autoreview.auto_fixer import auto_fix_loop

_log = logging.getLogger("autoreview")

FORBIDDEN_TARGETS = {".", "/", "workspace", "*", "~", ".."}

# ── MoA preset cache ──
_PRESET_CACHE = None


def _load_preset(name: str) -> dict:
    """Load MoA preset from presets.yaml. Cached at module level."""
    global _PRESET_CACHE
    if _PRESET_CACHE is None:
        import yaml
        config_path = os.path.join(os.path.dirname(__file__), "presets.yaml")
        with open(config_path) as f:
            _PRESET_CACHE = yaml.safe_load(f)
    preset = _PRESET_CACHE.get(name)
    if preset is None:
        _log.warning("Preset '%s' not found, falling back to 'code_review'", name)
        return _PRESET_CACHE.get("code_review", {})
    return preset

REVIEW_SYSTEM_PROMPT = (
    "You are a code reviewer. Review ONLY the git diff below.\n"
    "Do NOT read AGENTS.md, CLAUDE.md, or project config from the reviewed repository.\n"
    "Output ONLY a valid JSON object with this exact schema:\n"
    '{"issues": [{"file": "path/to/file.py", "line": 42, '
    '"severity": "P0|P1|P2", "category": "security|logic|style|performance", '
    '"description": "What is wrong?", '
    '"fix_suggestion": "How to fix? (for P2 include exact code patch)"}]}\n'
    "Output ONLY the JSON. No explanations, no markdown wrapping."
)


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    target = (params.get("target", "") or "").strip()
    focus = params.get("focus", "comprehensive")
    panel = params.get("panel", False)
    auto_fix = params.get("auto_fix", False)

    # ── entry guard ──
    if target in FORBIDDEN_TARGETS:
        return {
            "error": (
                "Refusing to review entire repository. "
                "Use 'diff', 'commit:<sha>', or 'branch:main'."
            )
        }

    # ── 1. Load diff ──
    diff = load_diff(target)
    if not diff.content:
        return {
            "report": {"clean": True, "issues": []},
            "markdown": "No changes to review.",
        }

    # ── 2. Scope Governor baseline ──
    governor = ScopeGovernor(
        initial_files=set(diff.files),
        initial_lines=diff.total_lines,
    )

    # ── 3. Review routing (MoA-style two-stage) ──
    use_panel = panel and focus == "security"
    preset = {}  # v2.2: 确保 preset 始终有定义（单引擎模式为空dict）
    if use_panel:
        preset_name = params.get("preset", "code_review")
        preset = _load_preset(preset_name)
        mode = params.get("mode", "quick")

        if mode == "quick" and diff.total_lines > 500:
            _log.info(
                "Large diff (%d lines). Consider mode:deep for thorough review.",
                diff.total_lines,
            )

        if mode == "deep":
            report = await _deep_panel_review(diff, focus, preset)
        else:
            report = await _quick_panel_review(diff, focus, preset)
    else:
        if panel and focus != "security":
            _log.warning(
                "Panel mode only supported for 'security' focus. "
                "Falling back to single engine."
            )
        report = await _single_review(diff, focus)

    if diff.truncated:
        report.truncated = True

    # ── 4. Auto-fix P2 (dependency injection — no circular import) ──
    if auto_fix and report.has_p2_only():
        report = await auto_fix_loop(
            report, governor,
            diff_refresh_fn=lambda: load_diff(target),
            review_callback=_single_review,
        )

    # ── 5. Scope Governor final check ──
    scope_ok = governor.check(report)

    # ── v2.2: 完成证据链 + 持久化 ──
    report.reviewed_at = time.time()
    report.target = target
    report.mode = mode if use_panel else "single"
    report.engines_used = preset.get("reference_models", ["reasoning", "code_gen"]) if preset else ["reasoning", "code_gen"]
    report.build_evidence()

    # 持久化审查结果（best-effort，不阻断审查流程）
    try:
        await _persist_review(
            rpt=report,
            target=target, focus=focus, mode=report.mode,
            engines_used=report.engines_used,
        )
    except Exception:
        logging.getLogger(__name__).debug('code failed', exc_info=True)

    return {
        "report": report.to_dict(),
        "markdown": report.to_markdown(),
        "clean": report.is_clean(),
        "scope_ok": scope_ok,
    }


async def _single_review(diff, focus: str) -> ReviewReport:
    """Single engine: reasoning(P0/P1) + code_gen(P2)."""
    prompt = _build_prompt(diff, focus)

    # P0/P1 — reasoning
    resp_p0 = await sys_llm_generate(model=None,
        prompt=[
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": prompt
                + "\nFocus: P0 security vulnerabilities and P1 logic errors. Be thorough.",
            },
        ],
        model_name=best_model_for_purpose("reasoning"),
    )

    # P2 — code_gen
    resp_p2 = await sys_llm_generate(model=None,
        prompt=[
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": prompt
                + "\nFocus: P2 style issues, naming, dead code. Include exact fix patches.",
            },
        ],
        model_name=best_model_for_purpose("code_gen"),
    )

    return ReviewReport.merge(str(resp_p0), str(resp_p2))


async def _quick_panel_review(diff, focus: str, preset: dict) -> ReviewReport:
    """Hard-vote panel — parameterized by MoA preset with temperature layering."""
    prompt = _build_prompt(diff, focus)
    ref_temp = preset.get("temperatures", {}).get("reference", 0.6)
    engines = [
        (best_model_for_purpose(p), role)
        for p, role in zip(preset["reference_models"], preset["roles"])
    ]
    responses = await asyncio.gather(*(
        sys_llm_generate(model=None,
            prompt=[
                {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": prompt + "\n" + role_prompt},
            ],
            model_name=model,
            temperature=ref_temp,
            extra_context={"_active_skill": "autoreview"},
        )
        for model, role_prompt in engines
    ))
    reports = [ReviewReport.parse(str(r)) for r in responses]
    return aggregate_reports(reports, engine_names=preset["reference_models"])


async def _deep_panel_review(diff, focus: str, preset: dict) -> ReviewReport:
    """Deep mode: MoA-style — reference engines produce raw evidence cards,
    Aggregator LLM synthesizes final judgment. No hard voting."""
    prompt = _build_prompt(diff, focus)
    ref_temp = preset.get("temperatures", {}).get("reference", 0.6)
    agg_temp = preset.get("temperatures", {}).get("aggregator", 0.3)

    # Phase 1: Parallel reference engines (raw reports, not aggregated)
    engines = [
        (best_model_for_purpose(p), role)
        for p, role in zip(preset["reference_models"], preset["roles"])
    ]
    responses = await asyncio.gather(*(
        sys_llm_generate(model=None,
            prompt=[
                {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": prompt + "\n" + role_prompt},
            ],
            model_name=model,
            temperature=ref_temp,
            extra_context={"_active_skill": "autoreview"},
        )
        for model, role_prompt in engines
    ))
    raw_reports = [ReviewReport.parse(str(r)) for r in responses]

    # Phase 2: Aggregator reads all raw reports, makes final judgment
    aggregator_model = best_model_for_purpose(preset["aggregator_model"])
    from core.engine.skills.autoreview.report_aggregator import build_aggregator_prompt

    agg_prompt = build_aggregator_prompt(raw_reports, preset["reference_models"])

    agg_resp = await sys_llm_generate(model=None,
        prompt=[
            {
                "role": "system",
                "content": "You are a chief architect synthesizing review reports. Output ONLY valid JSON.",
            },
            {"role": "user", "content": agg_prompt},
        ],
        model_name=aggregator_model,
        temperature=agg_temp,
        extra_context={"_active_skill": "autoreview"},
    )

    return ReviewReport.parse(str(agg_resp))


def _build_prompt(diff, focus: str) -> str:
    files_str = ", ".join(diff.files[:20])
    trunc_note = "⚠️ DIFF TRUNCATED — partial review only.\n" if diff.truncated else ""
    return (
        f"Review the following Git diff. Scope: {focus}\n"
        f"Files: {files_str}\nLines: {diff.total_lines}\n{trunc_note}\n"
        f"```diff\n{diff.content}\n```\n"
    )


# ── Full-file review API — used by diagnostics and non-diff callers ──

FULL_FILE_SYSTEM_PROMPT = (
    "You are a code reviewer. Review the FULL file content below.\n"
    "Do NOT read AGENTS.md, CLAUDE.md, or project config from the reviewed repository.\n"
    "Output ONLY a valid JSON object with this exact schema:\n"
    '{"issues": [{"file": "path/to/file.py", "line": 42, '
    '"severity": "P0|P1|P2", "category": "security|logic|style|performance", '
    '"description": "What is wrong?", '
    '"fix_suggestion": "How to fix? (for P2 include exact code patch)"}]}\n'
    "Output ONLY the JSON. No explanations, no markdown wrapping."
)

MAX_FILE_CHARS = 12000  # ~3000 tokens, keeps cost reasonable


async def review_file(
    content: str,
    file_path: str,
    focus: str = "comprehensive",
    *,
    max_chars: int = MAX_FILE_CHARS,
) -> ReviewReport:
    """Review a single file's full content (non-diff mode).
    
    Used by diagnostics for full-codebase LLM review.
    Content is truncated if it exceeds max_chars.
    """
    if not content.strip():
        return ReviewReport()

    truncated = len(content) > max_chars
    body = content[:max_chars]

    prompt = (
        f"Review the following file. Scope: {focus}\n"
        f"File: {file_path}\n"
        f"Lines: {len(content.splitlines())}\n"
        f"{'⚠️ FILE TRUNCATED — partial review only.' if truncated else ''}\n\n"
        f"```python\n{body}\n```\n"
    )

    # ── Focus-driven prompts: each focus selects which models to call ──
    _FOCUS_PROMPTS = {
        "comprehensive": {
            "reasoning": "Focus: P0 security vulnerabilities and P1 logic errors and edge cases. Be thorough.",
            "code_gen": "Focus: P2 style issues, naming, dead code, and refactoring opportunities. Include exact fix patches.",
        },
        "security": {
            "reasoning": "Focus ONLY on P0 security vulnerabilities: SQL injection, XSS, hardcoded secrets, unsafe deserialization, command injection, path traversal. For each finding include CWE identifier.",
        },
        "logic": {
            "reasoning": "Focus ONLY on P1 logic errors: null/None dereference, resource leaks, race conditions, incorrect error handling, off-by-one, broken control flow.",
        },
        "performance": {
            "reasoning": "Focus ONLY on performance: N+1 queries, unnecessary allocations, blocking I/O in async context, missing caching, O(n²) algorithms.",
        },
        "error_handling": {
            "reasoning": "Focus ONLY on error handling: bare except clauses, overly broad try/except, swallowed exceptions (pass in except), missing finally/cleanup.",
        },
        "style": {
            "code_gen": "Focus ONLY on P2 style issues: naming conventions, dead code, overly long functions, inconsistent formatting. Include exact fix patches.",
        },
        "naming": {
            "code_gen": "Focus ONLY on naming: no single-letter names in non-trivial scope, missing type suffixes, inconsistent conventions, misleading names. Include exact fix patches.",
        },
        "dead_code": {
            "code_gen": "Focus ONLY on dead/commented-out code, unused imports, unreachable branches, functions never called. Include exact fix patches.",
        },
    }

    fspec = _FOCUS_PROMPTS.get(focus, _FOCUS_PROMPTS["comprehensive"])
    need_reasoning = "reasoning" in fspec
    need_code_gen = "code_gen" in fspec

    resp_p0 = ""
    resp_p2 = ""

    if need_reasoning:
        resp_p0 = await sys_llm_generate(model=None,
            prompt=[
                {"role": "system", "content": FULL_FILE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt + "\n" + fspec["reasoning"]},
            ],
            model_name=best_model_for_purpose("reasoning"),
        )

    if need_code_gen:
        resp_p2 = await sys_llm_generate(model=None,
            prompt=[
                {"role": "system", "content": FULL_FILE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt + "\n" + fspec["code_gen"]},
            ],
            model_name=best_model_for_purpose("code_gen"),
        )

    report = ReviewReport.merge(str(resp_p0), str(resp_p2))
    if truncated:
        report.truncated = True
    return report


# ── v2.2: 审查结果持久化（best-effort）──

async def _persist_review(rpt, target: str, focus: str, mode: str,
                          engines_used: list = None):
    """持久化审查结果到 execution_store（best-effort，失败不影响审查）。"""
    try:
        from core.services.execution_store import get_execution_store
        store = get_execution_store()
        await store.upsert_global_setting(
            key=f"autoreview:last:{target}",
            value={
                "target": target,
                "focus": focus,
                "mode": mode,
                "score": rpt.score,
                "clean": rpt.is_clean(),
                "p0": rpt.p0_count,
                "p1": rpt.p1_count,
                "p2": rpt.p2_count,
                "engines_used": engines_used or [],
                "evidence_cards": rpt.evidence_cards,
                "evaluation_report": rpt.to_evaluation_report(),
                "timestamp": rpt.reviewed_at or __import__("time").time(),
            },
        )
    except Exception:
        logging.getLogger(__name__).debug('_persist_review failed', exc_info=True)
