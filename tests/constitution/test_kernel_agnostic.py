"""
Architecture Constitution Tests: Kernel Agnostic (core MUST be application-unaware)

Enforces CLAUDE.md §5.29 and root CLAUDE.md §8:
    aiPlat-core (Harness kernel) MUST NOT contain any application-specific knowledge.

These tests verify that:
1. No hardcoded business role names in the harness/engine
2. No hardcoded business phase names used for behavior branching
3. No hardcoded artifact keys (state.get("prd"), state.get("architecture"), etc.)
4. No agent-id string matching for behavior branching
5. No hardcoded scoring dimensions (functionality, product_depth, etc.)
6. No business SOP prompt text embedded in engine code
7. No channel adapter logic (Slack, Telegram, etc.)

Transitional code: Code marked with "DEPRECATED: migrate to <target_layer>"
or gated behind a feature flag with clear migration plan is allowed as
transitional debt. Each such case must have a corresponding Phase in the
optimization plan.
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def _find_py_files(dir_path: str) -> List[Path]:
    dir_full = WORKSPACE_ROOT / dir_path
    if not dir_full.exists():
        return []
    files = []
    for root, dirs, filenames in os.walk(str(dir_full)):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".pytest_cache")]
        for f in filenames:
            if f.endswith(".py"):
                files.append(Path(root) / f)
    return files


def _grep_files(files: List[Path], pattern: str) -> List[Tuple[Path, int, str]]:
    compiled = re.compile(pattern)
    hits = []
    for fp in files:
        try:
            for i, line in enumerate(fp.read_text(encoding="utf-8", errors="ignore").split("\n"), 1):
                if compiled.search(line):
                    hits.append((fp, i, line.strip()))
        except Exception:
            pass
    return hits


def _has_transitional_marker(fp: Path) -> bool:
    """Check if a file has an approved transitional marker (DEPRECATED comment
    with clear migration plan, or feature flag guard with documented path)."""
    try:
        text = fp.read_text(encoding="utf-8", errors="ignore")[:4096]
    except Exception:
        return False
    markers = [
        r'DEPRECATED:.*migrate\s+to\s+',
        r'# NOTE:.*should move to.*layer',
    ]
    for m in markers:
        if re.search(m, text, re.IGNORECASE):
            return True
    return False


# ============================================================================
# Category 1: Hardcoded Business Role Names
# ============================================================================


class TestNoHardcodedBusinessRoleNames:
    """Harness/engine MUST NOT contain hardcoded role names like 'architect', 'pm_agent'."""

    FORBIDDEN_PATTERNS = [
        # Exact string literals of business roles (not in comments, not in test files)
        (r'"pm_agent"', "Hardcoded 'pm_agent' role name"),
        (r'"architect_agent"', "Hardcoded 'architect_agent' role name"),
        (r'"programmer_agent"', "Hardcoded 'programmer_agent' role name"),
        (r'"qa_agent"', "Hardcoded 'qa_agent' role name"),
        (r'"frontend_engineer"', "Hardcoded 'frontend_engineer' role name"),
        (r'"backend_engineer"', "Hardcoded 'backend_engineer' role name"),
        (r'"product_manager"', "Hardcoded 'product_manager' role name"),
        (r'"system_architect"', "Hardcoded 'system_architect' role name"),
    ]

    # Files exempt from these checks (docstrings, schemas, integration, configs)
    EXEMPT_PATTERNS = [
        r"schemas_builder\.py$",     # Schema definitions
        r"agent_insight_service\.py$", # Metrics layer (allowed exception)
        r"integration\.py$",         # Integration layer
        r"multi_agent\.py$",         # Multi-agent coordinator
        r"prompt_configs\.py$",      # Prompt configuration
        r"tests/",                   # All test files
        r"docs/",                    # Documentation
    ]

    def test_no_business_role_names_in_harness(self):
        files = _find_py_files("aiPlat-core/core/harness")
        for pattern, desc in self.FORBIDDEN_PATTERNS:
            hits = _grep_files(files, pattern)
            filtered = []
            for f, l, s in hits:
                if any(re.search(e, str(f)) for e in self.EXEMPT_PATTERNS):
                    continue
                if "# fallback" in s.lower() or "# legacy" in s.lower():
                    continue
                filtered.append((f, l, s))
            assert not filtered, (
                f"Harness MUST NOT contain hardcoded role names. "
                f"Pattern [{pattern}] ({desc}) found {len(filtered)} times:\n"
                + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
            )

    def test_no_business_role_names_in_engine(self):
        files = _find_py_files("aiPlat-core/core/harness/execution")
        for pattern, desc in self.FORBIDDEN_PATTERNS:
            hits = _grep_files(files, pattern)
            filtered = []
            for f, l, s in hits:
                if any(re.search(e, str(f)) for e in self.EXEMPT_PATTERNS):
                    continue
                if "# fallback" in s.lower() or "# legacy" in s.lower():
                    continue
                filtered.append((f, l, s))
            assert not filtered, (
                f"Engine MUST NOT contain hardcoded role names. "
                f"Pattern [{pattern}] found {len(filtered)} times:\n"
                + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
            )


# ============================================================================
# Category 2: Hardcoded Artifact Keys
# ============================================================================


class TestNoHardcodedArtifactKeys:
    """Harness MUST NOT hardcode artifact keys like 'prd', 'architecture', 'test_report'."""

    FORBIDDEN_ARTIFACT_KEYS = [
        (r'state\.get\("prd"\)', "Hardcoded artifact key 'prd'"),
        (r'state\.get\("architecture"\)', "Hardcoded artifact key 'architecture'"),
        (r'state\.get\("code"\)', "Hardcoded artifact key 'code'"),
        (r'state\.get\("test_report"\)', "Hardcoded artifact key 'test_report'"),
        (r'state\.get\("test_plan"\)', "Hardcoded artifact key 'test_plan'"),
        (r'state\["prd"\]', "Hardcoded artifact key 'prd' (bracket access)"),
        (r'state\["architecture"\]', "Hardcoded artifact key 'architecture' (bracket access)"),
        (r'state\["code"\]', "Hardcoded artifact key 'code' (bracket access)"),
        (r'state\["test_report"\]', "Hardcoded artifact key 'test_report' (bracket access)"),
    ]

    def test_no_hardcoded_artifact_keys_in_harness(self):
        files = _find_py_files("aiPlat-core/core/harness")
        # Exempt test files, schemas, integration
        exempt = re.compile(r"(tests/|schemas_|integration\.py|builder_|prompt_configs\.py)")
        for pattern, desc in self.FORBIDDEN_ARTIFACT_KEYS:
            hits = _grep_files(files, pattern)
            filtered = [(f, l, s) for f, l, s in hits if not exempt.search(str(f))]
            assert not filtered, (
                f"Harness MUST NOT hardcode artifact keys. Use stage.output_artifact / stage.test_result_key. "
                f"Pattern [{desc}] found {len(filtered)} times:\n"
                + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
            )


# ============================================================================
# Category 3: Phase String Matching for Behavior Branching
# ============================================================================


class TestNoPhaseStringBranching:
    """Harness MUST NOT branch on business phase names."""

    def test_no_phase_string_branching(self):
        files = _find_py_files("aiPlat-core/core/harness")
        # Check for "if phase == 'awaiting_*'" patterns
        pattern = r"(if.*phase\s*[=!]=.*['\"]|if.*['\"]\s*in\s*phase)"
        hits = _grep_files(files, pattern)

        exempt = re.compile(r"(tests/|schemas_|integration\.py)")
        filtered = [(f, l, s) for f, l, s in hits if not exempt.search(str(f))]

        assert not filtered, (
            f"Harness MUST NOT branch on business phase strings. Use stage config fields. "
            f"Found {len(filtered)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
        )


# ============================================================================
# Category 4: Agent ID String Matching for Behavior
# ============================================================================


class TestNoAgentIdStringBranching:
    """Harness MUST NOT branch on agent_id strings."""

    def test_no_agent_id_string_branching(self):
        files = _find_py_files("aiPlat-core/core/harness/execution")
        # Only catch comparisons to HARDCODED string literals (business role names),
        # not data-driven comparisons (target_agent from LLM output, config-driven matching).
        # Forbidden: agent_id == "architect_agent"  /  'architect' in agent_id
        # Allowed: s.agent_id == target_agent (where target_agent comes from data)
        pattern = r'(agent_id\s*[=!]=\s*["\']|["\']\s*in\s+agent_id)'
        hits = _grep_files(files, pattern)
        exempt = re.compile(r"(tests/|schemas_|integration\.py)")
        filtered = [(f, l, s) for f, l, s in hits if not exempt.search(str(f))]
        assert not filtered, (
            f"Engine MUST NOT branch on hardcoded agent_id strings. "
            f"Data-driven matching (agent_id == variable_from_data) is allowed. "
            f"Found {len(filtered)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
        )


# ============================================================================
# Category 5: Hardcoded Scoring Dimensions
# ============================================================================


class TestNoHardcodedScoringDimensions:
    """Evaluation code MUST NOT hardcode scoring dimension names and weights."""

    SCORING_PATTERNS = [
        (r'"functionality"', "Hardcoded scoring dimension 'functionality'"),
        (r'"product_depth"', "Hardcoded scoring dimension 'product_depth'"),
        (r'"design_ux"', "Hardcoded scoring dimension 'design_ux'"),
        (r'"code_architecture"', "Hardcoded scoring dimension 'code_architecture'"),
        (r'functionality_min', "Hardcoded scoring field 'functionality_min'"),
        (r'score_functionality', "Hardcoded scoring field 'score_functionality'"),
        (r'score_product_depth', "Hardcoded scoring field 'score_product_depth'"),
        (r'score_design_ux', "Hardcoded scoring field 'score_design_ux'"),
        (r'score_code_architecture', "Hardcoded scoring field 'score_code_architecture'"),
    ]

    def test_no_hardcoded_scoring_dimensions_in_evaluation(self):
        files = _find_py_files("aiPlat-core/core/harness/evaluation")
        exempt = re.compile(r"schemas_builder\.py|dimensions\.py|tests/")
        for pattern, desc in self.SCORING_PATTERNS:
            hits = _grep_files(files, pattern)
            filtered = [(f, l, s) for f, l, s in hits if not exempt.search(str(f))]
            assert not filtered, (
                f"Evaluation MUST use stage.scoring_dimensions, not hardcoded dimensions. "
                f"Pattern [{desc}] found {len(filtered)} times:\n"
                + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
            )

    def test_no_hardcoded_scoring_dimensions_in_schemas(self):
        files = [_f for _f in _find_py_files("aiPlat-core/core") if "schemas_builder" in str(_f)]
        exempt = re.compile(r"tests/")
        for pattern, desc in self.SCORING_PATTERNS:
            hits = _grep_files(files, pattern)
            filtered = [(f, l, s) for f, l, s in hits if not exempt.search(str(f))]
            assert not filtered, (
                f"Schema MUST use generic Dict fields, not hardcoded scoring field names. "
                f"Pattern [{desc}] found {len(filtered)} times:\n"
                + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
            )


# ============================================================================
# Category 6: Business SOP Prompt Text in Engine
# ============================================================================


class TestNoBusinessSOPInEngine:
    """Engine MUST NOT contain business SOP prompts — those belong in AGENT.md."""

    BUSINESS_PROMPT_MARKERS = [
        r'"You are a strict (software )?(QA evaluator|quality check expert|evaluator)',
        r'"你是一个严格的\s*(QA|质量检查|评估)',
        r'"Evaluate based on requirements, code, and test results',
    ]

    def test_no_business_prompt_in_engine(self):
        files = _find_py_files("aiPlat-core/core/harness/execution")
        exempt = re.compile(r"tests/|prompt_configs\.py")
        for pattern in self.BUSINESS_PROMPT_MARKERS:
            hits = _grep_files(files, pattern)
            filtered = [(f, l, s) for f, l, s in hits if not exempt.search(str(f))]
            assert not filtered, (
                f"Engine MUST NOT embed business evaluation prompts. "
                f"Move to AGENT.md or PipelineStageConfig fields. "
                f"Pattern found {len(filtered)} times:\n"
                + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
            )


# ============================================================================
# Category 7: Channel Adapter Logic in Core
# ============================================================================


class TestNoChannelAdaptersInCore:
    """Core MUST NOT contain channel-specific adapter logic (Slack, Telegram, etc.)."""

    def test_no_slack_handlers_in_core(self):
        files = _find_py_files("aiPlat-core/core")
        exempt = re.compile(r"(tests/|__pycache__|generated/)")
        patterns = [
            (r"slack.*signature|verify_slack|slack_command|slack_events|app_mention",
             "Slack channel adapter logic"),
            (r"url_verification.*challenge|event_callback|bot_id",
             "Slack Events API handler logic"),
            (r"response_url", "Slack response_url delivery logic"),
        ]
        for pattern, desc in patterns:
            hits = _grep_files(files, pattern)
            filtered = [(f, l, s) for f, l, s in hits
                        if not exempt.search(str(f)) and not _has_transitional_marker(f)]
            assert not filtered, (
                f"Core MUST NOT contain channel adapter logic ({desc}). "
                f"Move to aiPlat-app/channels/. Found {len(filtered)} violations:\n"
                + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
            )


# ============================================================================
# Category 8: Quota Enforcement in Core Execution Path
# ============================================================================


class TestNoQuotaEnforcementInCore:
    """Core execution path MUST NOT enforce tenant quotas — that's platform's job.
    Transitional: code behind AIPLAT_ENABLE_SYSCALL_QUOTA flag with documented
    migration plan is allowed as known architectural debt (Phase 2)."""

    def test_no_quota_check_in_harness_syscalls(self):
        files = _find_py_files("aiPlat-core/core/harness/syscalls")
        pattern = r"tenant_quota|quota_exceeded|daily.*limit|quota.*check"
        exempt = re.compile(r"tests/")
        hits = _grep_files(files, pattern)
        filtered = [(f, l, s) for f, l, s in hits
                    if not exempt.search(str(f)) and not _has_transitional_marker(f)]
        assert not filtered, (
            f"Harness syscalls MUST NOT enforce tenant quotas directly. "
            f"Quota management belongs in platform layer. "
            f"Found {len(filtered)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
        )

    def test_no_tenant_quotas_table_in_core(self):
        files = _find_py_files("aiPlat-core/core")
        pattern = r"tenant_quotas"
        exempt = re.compile(r"tests/")
        hits = _grep_files(files, pattern)
        filtered = [(f, l, s) for f, l, s in hits
                    if not exempt.search(str(f)) and not _has_transitional_marker(f)]
        assert not filtered, (
            f"Core MUST NOT manage tenant_quotas table directly. "
            f"Quota management belongs in platform layer. "
            f"Found {len(filtered)} violations:\n"
            + "\n".join(f"  {p}:{l}: {s}" for p, l, s in filtered[:10])
        )
