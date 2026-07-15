"""Tests for P0-2: structured tool/skill error diagnostics (Hermes Layer 2).

Covers:
  - recovery_hint_for() maps every FailoverReason to a non-empty hint
  - ToolResult / SkillResult carry the new structured error fields
  - _enrich_tool_error() no-ops on success / pre-classified results
  - _enrich_tool_error() populates error_type + recovery_hint on failure
  - _enrich_tool_error() extracts exit_code / stderr from dict output
"""

import pytest
import sys

sys.path.insert(0, "aiPlat-core")

from core.harness.interfaces.tool import ToolResult
from core.harness.interfaces.skill import SkillResult
from core.harness.infrastructure.gates.error_translator import (
    recovery_hint_for,
    FailoverReason,
)
from core.harness.syscalls.tool import _enrich_tool_error


class TestRecoveryHintMap:
    def test_every_reason_has_hint(self):
        for reason in FailoverReason:
            hint = recovery_hint_for(reason)
            assert isinstance(hint, str) and len(hint) > 0, f"{reason} has no hint"

    def test_unknown_fallback(self):
        # An unmapped-style call still returns the unknown hint
        assert recovery_hint_for(FailoverReason.unknown)


class TestStructuredFields:
    def test_toolresult_has_new_fields(self):
        r = ToolResult(success=False, error="boom")
        assert r.error_type is None
        assert r.exit_code is None
        assert r.stderr is None
        assert r.recovery_hint is None

    def test_skillresult_has_new_fields(self):
        r = SkillResult(success=False, error="boom")
        assert r.error_type is None
        assert r.recovery_hint is None


class TestEnrichToolError:
    def test_noop_on_success(self):
        r = ToolResult(success=True, output="ok")
        out = _enrich_tool_error(r)
        assert out.error_type is None
        assert out.recovery_hint is None

    def test_noop_when_already_classified(self):
        r = ToolResult(success=False, error="x", error_type="timeout",
                       recovery_hint="preset")
        out = _enrich_tool_error(r)
        assert out.error_type == "timeout"
        assert out.recovery_hint == "preset"

    def test_populates_on_failure(self):
        r = ToolResult(success=False, error="connection timed out")
        out = _enrich_tool_error(r)
        assert out.error_type == FailoverReason.timeout.value
        assert out.recovery_hint and len(out.recovery_hint) > 0

    def test_rate_limit_classification(self):
        r = ToolResult(success=False, error="429 rate limit exceeded")
        out = _enrich_tool_error(r)
        assert out.error_type == FailoverReason.rate_limit.value

    def test_unknown_error_still_gets_hint(self):
        r = ToolResult(success=False, error="some weird tool failure xyz")
        out = _enrich_tool_error(r)
        assert out.error_type == FailoverReason.unknown.value
        assert out.recovery_hint  # generic hint present

    def test_extracts_exit_code_and_stderr_from_dict_output(self):
        r = ToolResult(
            success=False,
            error="command failed",
            output={"exit_code": 126, "stderr": "permission denied"},
        )
        out = _enrich_tool_error(r)
        assert out.exit_code == 126
        assert out.stderr == "permission denied"
        assert out.error_type is not None

    def test_handles_returncode_alias(self):
        r = ToolResult(
            success=False,
            error="failed",
            output={"returncode": 2, "stderr": "no such file"},
        )
        out = _enrich_tool_error(r)
        assert out.exit_code == 2

    def test_never_raises_on_non_toolresult(self):
        # dict has no .success → treated as success (no attr) → returned unchanged
        assert _enrich_tool_error({"foo": "bar"}) == {"foo": "bar"}
        assert _enrich_tool_error(None) is None
