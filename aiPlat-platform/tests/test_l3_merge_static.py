"""Static tests for L3 incremental merge wiring (plan-app-factory-l3).

Verifies: schema fields, merge endpoints, prompt constants, engine UNCHANGED
handling, and the merge_engine module having a production caller.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BUILDER_ROUTER = ROOT / "aiPlat-platform" / "api" / "routers" / "builder.py"
BUILDER_SERVICE = ROOT / "aiPlat-platform" / "builder" / "builder_project_service.py"
MERGE_ENGINE = ROOT / "aiPlat-platform" / "builder" / "merge_engine.py"
SCHEMAS = ROOT / "aiPlat-core" / "core" / "schemas_builder.py"
PIPELINE_ENGINE = ROOT / "aiPlat-core" / "core" / "harness" / "execution" / "pipeline_engine.py"


class TestL3Schema:
    def test_merge_strategy_field(self):
        content = SCHEMAS.read_text()
        assert "merge_strategy: str = \"full_rewrite\"" in content
        assert "merge_review_required: bool = False" in content


class TestL3Endpoints:
    def test_merge_endpoints(self):
        content = BUILDER_ROUTER.read_text()
        assert "merge-preview" in content
        assert "merge-apply" in content
        assert "merge-previews" in content


class TestL3Prompt:
    def test_increment_prompt_constant(self):
        content = BUILDER_SERVICE.read_text()
        assert "_L3_INCREMENT_PROMPT" in content
        assert "增量修改" in content
        assert "逐字节一致" in content
        assert "UNCHANGED" in content

    def test_rebuild_selects_prompt_by_strategy(self):
        content = BUILDER_SERVICE.read_text()
        assert "_merge_strategy" in content
        assert "_L3_INCREMENT_PROMPT if _merge_strategy == \"incremental_merge\"" in content


class TestL3MergeService:
    def test_methods_exist(self):
        content = BUILDER_SERVICE.read_text()
        for m in ("async def merge_preview", "async def list_merge_previews",
                  "async def merge_apply", "def _parse_file_blocks"):
            assert m in content, f"missing {m}"

    def test_merge_engine_has_caller(self):
        content = BUILDER_SERVICE.read_text()
        assert "from builder.merge_engine import" in content


class TestL3EngineUnchanged:
    def test_unchanged_marker_stripped(self):
        content = PIPELINE_ENGINE.read_text()
        assert "UNCHANGED" in content
        assert "_re.sub(r'^#{2,4}\\s*UNCHANGED:" in content


class TestL3P0Patches:
    """L3 评审 P0 暗坑补丁（原子审批/哈希锁/AST 阻断）。"""

    def test_atomic_gate_message(self):
        content = BUILDER_SERVICE.read_text()
        assert "必须审批全部文件（原子化）" in content
        assert "atomic_approval_required" in content

    def test_atomic_gate_in_engine(self):
        content = MERGE_ENGINE.read_text()
        assert "P0-01 atomic gate" in content
        assert "missing_approval" in content

    def test_snapshot_functions(self):
        content = MERGE_ENGINE.read_text()
        assert "def snapshot_affected_files" in content
        assert "def verify_snapshot" in content

    def test_rebuild_takes_snapshot(self):
        content = BUILDER_SERVICE.read_text()
        assert "pre_gen_snapshot" in content
        assert "snapshot_affected_files" in content

    def test_concurrent_modification_code(self):
        content = BUILDER_SERVICE.read_text()
        assert "concurrent_modification" in content
        assert "生成期间已被外部修改" in content

    def test_analyze_impact_endpoint(self):
        content = BUILDER_ROUTER.read_text()
        assert "analyze-impact" in content

    def test_hunk_categorization(self):
        content = MERGE_ENGINE.read_text()
        assert "def _categorize_hunk" in content
        assert "formatting" in content and "logic" in content
