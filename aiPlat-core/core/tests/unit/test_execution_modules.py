"""Tests for skills/executor.py + debate.py + renderer.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "aiPlat-core"))


class TestSkillsExecutor:
    def test_import(self):
        from core.apps.skills.executor import SkillExecutor
        assert SkillExecutor is not None

    def test_import_fork(self):
        from core.apps.skills.executor import SkillExecutor
        assert SkillExecutor is not None


class TestDebate:
    def test_import(self):
        from core.harness.execution.debate import DebateState
        assert DebateState is not None


class TestRenderer:
    def test_import(self):
        from core.harness.execution.renderer import render_stage_output
        assert callable(render_stage_output)


class TestPromptAssembler:
    def test_import(self):
        from core.harness.assembly.prompt_assembler import MessageFormatter, PromptAssemblyResult
        assert MessageFormatter is not None
        assert PromptAssemblyResult is not None
