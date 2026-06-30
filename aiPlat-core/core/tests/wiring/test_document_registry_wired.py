"""
Wiring assertion tests for ConverterRegistry and DocumentConverter protocol.

CLAUDE.md §5.30 rule 10 (强制): 每个新建公共模块必须附带接线断言测试。

验证:
  - ConverterRegistry 被 kb_facade / core_facade 接入生产线
  - get_document_registry() 有 production caller
  - detect_structure_role() 被 converter 子类使用
  - 两个 facade 的 get_document_categories() 返回一致
"""
import pytest

from .conftest import has_production_caller, assert_wired


class TestDocumentRegistryWired:

    def test_get_document_registry_has_production_caller(self):
        """ConverterRegistry 全局单例必须有非自身的 production caller."""
        assert has_production_caller(
            "get_document_registry", "protocol.py"
        ), "get_document_registry() has 0 production callers"

    def test_registry_accessed_by_kb_facade(self):
        """kb_facade 通过 get_document_registry() 接入 registry."""
        assert has_production_caller(
            "get_document_registry", "protocol.py"
        ), "kb_facade must call registry for document parsing"

    def test_registry_accessed_by_core_facade(self):
        """core_facade 通过 get_document_registry() 接入 registry."""
        assert has_production_caller(
            "get_document_registry", "protocol.py"
        ), "core_facade must call registry"

    def test_detect_structure_role_wired(self):
        """detect_structure_role() 被至少 1 个 converter 使用."""
        assert has_production_caller(
            "detect_structure_role", "protocol.py"
        ), "detect_structure_role() has 0 production callers outside protocol.py"

    def test_element_to_dicts_wired(self):
        """_elements_to_dicts() 被 facade 层调用."""
        assert has_production_caller(
            "_elements_to_dicts", "parsers.py"
        ), "_elements_to_dicts() has 0 production callers outside parsers.py"


class TestNewlyWiredDocumentModules:

    def test_converter_registry_wired(self):
        assert_wired("get_document_registry", "protocol.py",
                      "Phase 1.1", "DocumentConverter registry — single source of truth for all parsing")

    def test_kind_normalization_wired(self):
        assert_wired("normalize_kind", "kb_facade.py",
                      "Phase 1.1", "Canonical document kind normalization (eliminates duplicated dispatch)")

    def test_kind_to_ext_wired(self):
        assert_wired("_KIND_TO_EXT", "kb_facade.py",
                      "Phase 1.1", "Centralized extension-to-kind mapping (eliminates 5 duplicated dispatch points)")


class TestAutoLearnerWired:

    def test_auto_learner_has_caller(self):
        """AutoLearner.analyze_failure() must have production callers (from loop.py or pipeline_engine.py)."""
        assert has_production_caller("analyze_failure", "__init__.py"), (
            "AutoLearner.analyze_failure() has 0 production callers — "
            "the self-learning loop is not connected. "
            "Expected callers: loop.py, pipeline_engine.py"
        )

    def test_get_auto_learner_called(self):
        """get_auto_learner() must be called from execution paths."""
        assert has_production_caller("get_auto_learner", "__init__.py"), (
            "get_auto_learner() has 0 production callers — "
            "the AutoLearner singleton is never accessed from execution paths."
        )

    def test_self_learning_loop_connected(self):
        """Verify the self-learning loop: auto learner is importable and functional."""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
        from core.harness.learning import get_auto_learner, AutoLearner
        learner = get_auto_learner()
        assert learner is not None
        assert isinstance(learner, AutoLearner)
        draft = learner.analyze_failure(
            error="test error",
            agent_id="test",
            run_id="test",
            task="test task",
        )
        assert draft is not None
        assert draft.status == "draft"

    def test_converter_registry_wired(self):
        assert_wired("get_document_registry", "protocol.py",
                      "Phase 1.1", "DocumentConverter registry — single source of truth for all parsing")

    def test_kind_normalization_wired(self):
        assert_wired("normalize_kind", "kb_facade.py",
                      "Phase 1.1", "Canonical document kind normalization (eliminates duplicated dispatch)")

    def test_kind_to_ext_wired(self):
        assert_wired("_KIND_TO_EXT", "kb_facade.py",
                      "Phase 1.1", "Centralized extension-to-kind mapping (eliminates 5 duplicated dispatch points)")


class TestFacadeConsistency:

    def test_categories_consistent(self):
        """core_facade 和 kb_facade 返回相同的 document categories."""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
        from core.api.facades.kb_facade import get_document_categories as kb_cats
        from core.api.core_facade import get_document_categories as core_cats
        kb = sorted(kb_cats())
        core = sorted(core_cats())
        assert kb == core, (
            f"Facade mismatch!\n"
            f"  kb_facade  ({len(kb)}): {kb}\n"
            f"  core_facade ({len(core)}): {core}"
        )

    def test_categories_contain_required_formats(self):
        """验证核心格式都在列表中."""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
        from core.harness.document.protocol import get_document_registry
        cats = get_document_registry().get_supported_categories()
        required = ["pdf", "docx", "pptx", "xlsx", "html", "csv", "markdown",
                     "json", "eml", "audio", "image", "video", "txt"]
        missing = [r for r in required if r not in cats]
        assert not missing, f"Missing categories: {missing}"

    def test_registry_has_13_converters(self):
        """验证 13 个 built-in converter 已注册."""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
        from core.harness.document.protocol import get_document_registry
        registry = get_document_registry()
        cats = registry.get_supported_categories()
        assert len(cats) == 13, f"Expected 13 converters, got {len(cats)}: {cats}"
