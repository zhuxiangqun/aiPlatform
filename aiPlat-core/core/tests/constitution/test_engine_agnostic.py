"""Engine layer agnostic constraints — must pass on every commit."""
import pytest
from pathlib import Path

ENGINE_DIR = Path(__file__).parent.parent.parent.parent / "core" / "harness" / "execution"
EXCLUDE = {'__pycache__', 'test_', '__init__.py', 'prompt_loader'}


def _files():
    return [f for f in ENGINE_DIR.rglob("*.py") if all(e not in str(f) for e in EXCLUDE)]


def test_no_chinese_prompts_in_engine():
    """Engine must not contain hardcoded Chinese prompts."""
    violations = []
    for f in _files():
        for lineno, line in enumerate(f.read_text().split("\n"), 1):
            s = line.strip()
            if any(k in s for k in ["你是", "你是一个", "请将", "请基于"]):
                if not s.startswith("#") and "_sync_resolve" not in s:
                    violations.append(f"{f.name}:{lineno}: {s[:80]}")
    assert not violations, (
        f"{len(violations)} hardcoded Chinese prompts found. "
        f"Move to prompt_loader.py:\n" + "\n".join(violations[:15])
    )


def test_no_artifact_key_tuples_in_engine():
    """Engine must not hardcode artifact key tuples."""
    violations = []
    for f in _files():
        for lineno, line in enumerate(f.read_text().split("\n"), 1):
            s = line.strip()
            if all(k in s for k in ('"architecture"', '"code"')):
                if not s.startswith("#"):
                    violations.append(f"{f.name}:{lineno}: {s[:80]}")
    assert not violations, (
        f"{len(violations)} hardcoded artifact keys found. "
        f"Use config.stages iteration:\n" + "\n".join(violations[:10])
    )


def test_no_skill_names_in_pipeline_engine():
    """Pipeline engine must not reference specific skill names."""
    f = ENGINE_DIR / "pipeline_engine.py"
    if not f.exists():
        pytest.skip("pipeline_engine.py not found")
    violations = []
    for lineno, line in enumerate(f.read_text().split("\n"), 1):
        s = line.strip()
        for term in ['"architecture_design"', '"code_generation"', '"test_case_generation"']:
            if term in s and not s.startswith("#") and "skill_name" not in s:
                violations.append(f"pipeline_engine.py:{lineno}: {s[:80]}")
    assert not violations, (
        f"{len(violations)} hardcoded skill names in pipeline engine. "
        f"Use stage.skill_name from config:\n" + "\n".join(violations[:10])
    )


def test_skill_dispatch_exists():
    """_dispatch_execute must have skill_name dispatch path."""
    f = ENGINE_DIR / "pipeline_engine.py"
    source = f.read_text()
    assert "skill_name" in source, "_dispatch_execute missing skill_name check"
    assert "_run_stage_skill" in source, "pipeline_engine.py missing _run_stage_skill method"
