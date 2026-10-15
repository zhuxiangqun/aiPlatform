"""OpenWorker-inspired P3: session write provenance → hard floor on exec."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.harness.infrastructure.gates.approval_gate import (
    ApprovalSeverity,
    ApprovalVerdict,
    get_approval_gate,
    reset_approval_gate,
)
from core.harness.infrastructure.gates.session_write_provenance import (
    _reset_session_write_provenance,
    extract_executable_paths,
    get_session_write_provenance,
    provenance_forces_hard_floor,
    record_session_write,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_approval_gate()
    _reset_session_write_provenance()
    yield
    reset_approval_gate()
    _reset_session_write_provenance()
    for k in (
        "AIPLAT_APPROVAL_GATE_DISABLED",
        "AIPLAT_HARD_FLOOR_DISABLED",
        "AIPLAT_APPROVALS_DISABLED",
    ):
        os.environ.pop(k, None)


class TestExtractExecutablePaths:
    def test_python_script_arg(self):
        paths = extract_executable_paths("python3 /tmp/setup.py")
        assert any(p.endswith("setup.py") for p in paths)

    def test_relative_script(self):
        paths = extract_executable_paths("./bootstrap.sh")
        assert "./bootstrap.sh" in paths or any("bootstrap" in p for p in paths)

    def test_bare_py_token(self):
        paths = extract_executable_paths("setup.py")
        assert "setup.py" in paths

    def test_harmless_ls(self):
        assert extract_executable_paths("ls -la /tmp") == []


class TestSessionWriteStore:
    def test_record_and_lookup(self, tmp_path):
        target = tmp_path / "agent_wrote.py"
        target.write_text("print(1)\n", encoding="utf-8")
        record_session_write(str(target), session_id="s1")
        store = get_session_write_provenance()
        rec = store.lookup("s1", str(target))
        assert rec is not None
        assert rec.origin == "written"
        assert rec.step == 1

    def test_provenance_forces_floor_after_write(self, tmp_path):
        target = tmp_path / "evil.py"
        target.write_text("import os\n", encoding="utf-8")
        record_session_write(str(target), session_id="s2")
        hit = provenance_forces_hard_floor(
            session_id="s2",
            command=f"python3 {target}",
        )
        assert hit is not None
        assert hit.path == os.path.realpath(str(target))

    def test_no_floor_without_prior_write(self, tmp_path):
        target = tmp_path / "preexist.py"
        target.write_text("x=1\n", encoding="utf-8")
        # Not recorded — no floor
        hit = provenance_forces_hard_floor(
            session_id="s3",
            command=f"python3 {target}",
        )
        assert hit is None

    def test_session_isolation(self, tmp_path):
        target = tmp_path / "iso.py"
        target.write_text("pass\n", encoding="utf-8")
        record_session_write(str(target), session_id="alpha")
        assert provenance_forces_hard_floor(
            session_id="beta", command=f"python3 {target}",
        ) is None
        assert provenance_forces_hard_floor(
            session_id="alpha", command=f"python3 {target}",
        ) is not None


class TestApprovalGateProvenance:
    def test_exec_after_write_is_hard_floor(self, tmp_path):
        target = tmp_path / "payload.py"
        target.write_text("print('x')\n", encoding="utf-8")
        record_session_write(str(target), session_id="gate-sess")
        gate = get_approval_gate()
        result = gate.check(
            "shell_exec",
            {
                "command": f"python3 {target}",
                "_session_id": "gate-sess",
            },
            session_id="gate-sess",
            auto_approve=True,
        )
        assert result.verdict == ApprovalVerdict.ASK
        assert result.hard_floor is True
        assert result.severity == ApprovalSeverity.CRITICAL
        assert result.rule_id == "session_write_provenance"

    def test_hard_floor_survives_approvals_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AIPLAT_APPROVALS_DISABLED", "1")
        target = tmp_path / "payload2.py"
        target.write_text("print(2)\n", encoding="utf-8")
        record_session_write(str(target), session_id="dis-sess")
        gate = get_approval_gate()
        result = gate.check(
            "code_execution",
            {"code": f"python3 {target}", "_session_id": "dis-sess"},
            session_id="dis-sess",
            auto_approve=True,
        )
        assert result.verdict == ApprovalVerdict.ASK
        assert result.hard_floor is True

    def test_unrelated_command_no_provenance_floor(self, tmp_path):
        target = tmp_path / "other.py"
        target.write_text("pass\n", encoding="utf-8")
        record_session_write(str(target), session_id="ok-sess")
        gate = get_approval_gate()
        floor = gate.check_hard_floor(
            "shell_exec",
            {"command": "echo hello"},
            session_id="ok-sess",
        )
        # echo may still hit shell_exec catalogue CRITICAL — but not provenance rule
        assert floor.rule_id != "session_write_provenance"
        assert "session-written" not in (floor.message or "")
        assert "session-downloaded" not in (floor.message or "")

    def test_relative_path_match_after_write(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "rel_run.py"
        target.write_text("print(0)\n", encoding="utf-8")
        record_session_write(str(target), session_id="rel-sess")
        hit = provenance_forces_hard_floor(
            session_id="rel-sess",
            command="python3 rel_run.py",
        )
        assert hit is not None

    def test_known_paths_listed_after_write(self, tmp_path):
        target = tmp_path / "listed.py"
        target.write_text("pass\n", encoding="utf-8")
        record_session_write(str(target), session_id="facade-prov")
        paths = get_session_write_provenance().known_paths("facade-prov")
        assert any(p.endswith("listed.py") for p in paths)
