"""Tests for L2 import-existing-code implementation (plan-app-factory-l2-import-repo.md).

Static analysis — verifies endpoints, security helpers, intent validation and
config-driver wiring exist. Dynamic behavior (zip-slip, manifest scan) is covered
in test_l2_import_helpers.py.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BUILDER_ROUTER = ROOT / "aiPlat-platform" / "api" / "routers" / "builder.py"
BUILDER_SERVICE = ROOT / "aiPlat-platform" / "builder" / "builder_project_service.py"
SCHEMAS_BUILDER = ROOT / "aiPlat-core" / "core" / "schemas_builder.py"
PIPELINE_EXEC = ROOT / "aiPlat-core" / "core" / "api" / "routers" / "pipeline_execution.py"
PIPELINE_ENGINE = ROOT / "aiPlat-core" / "core" / "harness" / "execution" / "pipeline_engine.py"
PIPELINE_EVAL = ROOT / "aiPlat-core" / "core" / "harness" / "execution" / "pipeline_eval.py"


class TestL2RouterEndpoints:
    """L2 API endpoints registered on the builder router."""

    def test_import_repo_endpoint(self):
        content = BUILDER_ROUTER.read_text()
        assert "/projects/{project_id}/import-repo" in content
        assert "UploadFile" in content and "existing_path" in content

    def test_imported_files_endpoint(self):
        assert "/projects/{project_id}/imported-files" in BUILDER_ROUTER.read_text()

    def test_import_stats_endpoint(self):
        assert "/import-stats" in BUILDER_ROUTER.read_text()


class TestL2ServiceSecurity:
    """Security helpers (§3.3/§3.5/§3.6): zip-slip, whitelist, sensitive-file skip."""

    def test_safe_extract_zip_exists(self):
        tree = ast.parse(BUILDER_SERVICE.read_text())
        names = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef,))]
        assert "_safe_extract_zip" in names
        assert "_scan_imported" in names
        assert "_detect_tests" in names
        assert "_detect_missing_deps" in names

    def test_zip_slip_guard_present(self):
        content = BUILDER_SERVICE.read_text()
        assert "zip-slip" in content or "路径越界" in content
        assert "startswith(_root_abs" in content  # resolved-path prefix check

    def test_sensitive_file_skip_regex(self):
        content = BUILDER_SERVICE.read_text()
        assert "_L2_SENSITIVE_RE" in content
        assert ".env" in content and ".pem" in content

    def test_size_limits_present(self):
        content = BUILDER_SERVICE.read_text()
        assert "_L2_IMPORT_MAX_ZIP_BYTES" in content
        assert "_L2_IMPORT_MAX_FILES" in content
        assert "_L2_IMPORT_MAX_FILE_BYTES" in content

    def test_existing_path_whitelist(self):
        content = BUILDER_SERVICE.read_text()
        assert "AIPLAT_HOME" in content and "白名单" in content


class TestL2IntentValidation:
    """modify_files {path, intent} binding — empty intent rejected (§3.2/§4)."""

    def test_update_prd_validates_intent(self):
        content = BUILDER_SERVICE.read_text()
        assert "modify_files" in content
        assert "必须填写修改意图" in content

    def test_behavior_prompt_exists(self):
        content = BUILDER_SERVICE.read_text()
        assert "重写而非合并" in content
        assert "modify_files" in content

    def test_rebuild_passes_imported_repo(self):
        content = BUILDER_SERVICE.read_text()
        assert 'config["imported_repo"]' in content
        assert 'config["skip_pytest_gate"]' in content


class TestL2CoreWiring:
    """Core-side wiring: schema field, state pass-through, engine injection, skip gate."""

    def test_stage_config_field(self):
        content = SCHEMAS_BUILDER.read_text()
        assert "inject_imported_context: bool = False" in content

    def test_state_pass_through(self):
        content = PIPELINE_EXEC.read_text()
        assert '"imported_repo": config.get("imported_repo")' in content
        assert '"skip_pytest_gate": bool(config.get("skip_pytest_gate"' in content

    def test_engine_injection(self):
        content = PIPELINE_ENGINE.read_text()
        assert "inject_imported_context" in content
        assert "imported existing code" in content
        assert "behavior_prompt" in content

    def test_skip_gate_in_engine(self):
        content = PIPELINE_ENGINE.read_text()
        assert "skip_pytest_gate" in content
        # P1-7 收敛（2026-08-25）：落盘收敛到共享 _apply_skip_pytest_gate（pipeline_eval.py），
        # 引擎侧保留入口判断 + 调用点
        assert "_apply_skip_pytest_gate" in content

    def test_skip_gate_in_eval(self):
        content = PIPELINE_EVAL.read_text()
        assert "skip_pytest_gate" in content
        assert "pytest_gate_skipped" in content
        assert "APPROVED_SKIPPED" in content  # 唯一落盘实现（共享 helper）


class TestL2DeployWarnings:
    """Build-Log regenerated warning + skip reason (§3.9 条件 2)."""

    @staticmethod
    def _builder_sources() -> str:
        """P1-14 God Class 拆分后：BuilderProjectService 的方法分布在主类 + L2L5/Deploy Mixin，
        语义断言改为拼接三文件（方法均经 MRO 可达 BuilderProjectService）。"""
        return (
            BUILDER_SERVICE.read_text()
            + "\n" + (ROOT / "aiPlat-platform" / "builder" / "builder_l2l5_mixin.py").read_text()
            + "\n" + (ROOT / "aiPlat-platform" / "builder" / "builder_deploy_mixin.py").read_text()
        )

    def test_regenerated_warnings(self):
        content = self._builder_sources()
        assert "regenerated_warnings" in content
        assert "has been regenerated" in content
        assert "review diff manually" in content

    def test_skip_reason_on_deploy(self):
        content = self._builder_sources()
        assert "_skip_pytest_gate" in content
        assert "user skipped pytest gate" in content
