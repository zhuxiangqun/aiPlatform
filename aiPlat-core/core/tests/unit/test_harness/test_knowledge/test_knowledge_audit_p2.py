"""知识管理审计 REAL 项修复测试（2026-08-25）。

覆盖：
- P2-1 quality gate 真正降级：gate 失败 + deep research 启用 → web fallback 并入结果；
  gate 失败但 deep research 关闭 → 仅打标记（向后兼容）；gate 通过 → 不降级
- P2-3 EXTRACTION_PROMPT 注册 prompt_loader：模板可解析 + 变量替换；_build_prompt 回退模块常量
- Q3 VALID_CLASS_TYPES 配置驱动：无域/未知域回退默认集；有域时读域本体类清单
- P2-4 DomainRouter 重复行清理：_t1_label_match/_t2_embed_score 共享助手行为与旧逻辑一致
- Q3 ABox TBox：_map_to_domain_class 映射；_add_data_validated 校验 prop
"""

import os
import sys
import tempfile
from unittest.mock import patch, AsyncMock

sys.path.insert(0, ".")

import pytest


def _fresh_home():
    tmp = tempfile.mkdtemp()
    os.environ["AIPLAT_HOME"] = tmp
    return tmp


class TestQualityGateDegradation:
    """P2-1：quality gate 从'只打标记'升级为'真正降级'。"""

    def _make_retriever(self, gate_enabled=True):
        from core.harness.knowledge.retriever import KnowledgeRetriever
        r = KnowledgeRetriever(quality_gate_enabled=gate_enabled, quality_threshold=0.9)
        return r

    def _fake_results(self, n=3, text="低相关内容"):
        from core.harness.knowledge.types import (
            KnowledgeEntry, KnowledgeResult, KnowledgeType, KnowledgeSource, KnowledgeMetadata)
        out = []
        for i in range(n):
            entry = KnowledgeEntry(id=f"r{i}", type=KnowledgeType.FACT, content=text,
                                   metadata=KnowledgeMetadata(source=KnowledgeSource.DATABASE))
            out.append(KnowledgeResult(entry=entry, score=0.5))
        return out

    @pytest.mark.asyncio
    async def test_gate_fail_deep_research_off_only_tags(self):
        """gate 失败但 AIPLAT_DEEP_RESEARCH_ENABLED 未启用 → 仅打标记，不降级（向后兼容）。"""
        _fresh_home()
        r = self._make_retriever()
        # 替换 retrieve 为低质量结果（query 与内容无关 → gate fail）
        async def fake_retrieve(kq):
            return self._fake_results()
        r._retriever.retrieve = fake_retrieve
        results = await r.search("completely unrelated query zzqq")
        assert len(results) == 3  # 无 web 并入
        assert all(hasattr(x, "metadata") and getattr(x, "metadata", None)
                   and x.metadata.get("_quality_gate") == "switch_to_web_search"
                   for x in results)

    @pytest.mark.asyncio
    async def test_gate_fail_deep_research_on_appends_web(self):
        """gate 失败 + deep research 启用 → web fallback 并入结果（真正降级）。"""
        _fresh_home()
        os.environ["AIPLAT_DEEP_RESEARCH_ENABLED"] = "true"
        r = self._make_retriever()
        async def fake_retrieve(kq):
            return self._fake_results()
        r._retriever.retrieve = fake_retrieve
        fake_web = [{"title": "WebDoc", "url": "https://example.com/1",
                     "snippet": "web snippet"}]
        with patch("core.harness.syscalls.retrieval_crag._ddg_search",
                   AsyncMock(return_value=fake_web)):
            results = await r.search("completely unrelated query zzqq")
        assert len(results) > 3  # 有 web 并入
        web_res = [x for x in results if x.source_category == "web_fallback"]
        assert len(web_res) == 1
        assert "https://example.com/1" in web_res[0].source_page
        del os.environ["AIPLAT_DEEP_RESEARCH_ENABLED"]

    @pytest.mark.asyncio
    async def test_gate_pass_no_degradation(self):
        """gate 通过（高相关且 ≥3 chunks）→ 不降级，不触发 web。"""
        _fresh_home()
        os.environ["AIPLAT_DEEP_RESEARCH_ENABLED"] = "true"
        r = self._make_retriever()
        async def fake_retrieve(kq):
            from core.harness.knowledge.types import (
                KnowledgeEntry, KnowledgeResult, KnowledgeType, KnowledgeSource, KnowledgeMetadata)
            text = "完全匹配查询词汇的高相关文档内容"
            return [KnowledgeResult(entry=KnowledgeEntry(id=f"ok{i}", type=KnowledgeType.FACT,
                                                        content=text,
                                                        metadata=KnowledgeMetadata(source=KnowledgeSource.DATABASE)),
                                    score=0.9) for i in range(3)]
        r._retriever.retrieve = fake_retrieve
        with patch("core.harness.syscalls.retrieval_crag._ddg_search",
                   AsyncMock(return_value=[{"title": "x", "url": "u", "snippet": "s"}])) as m:
            results = await r.search("完全匹配查询词汇")
        m.assert_not_awaited()
        assert len(results) == 3  # 无 web 并入
        del os.environ["AIPLAT_DEEP_RESEARCH_ENABLED"]


class TestExtractionPromptRegistered:
    """P2-3：EXTRACTION_PROMPT 注册进 prompt_loader + Q3 VALID_CLASS_TYPES 配置驱动。"""

    def test_prompt_registered_in_loader(self):
        _fresh_home()
        from core.harness.knowledge_pipeline.extractor import EntityExtractor  # noqa: F401  # 触发注册
        from core.harness.utils.prompt_loader import list_templates, _sync_resolve
        templates = [t[0] for t in list_templates()]
        assert "knowledge-extraction" in templates
        resolved = _sync_resolve("knowledge-extraction", chunk_text="测试内容")
        assert "测试内容" in resolved

    def test_build_prompt_fallback(self):
        from core.harness.knowledge_pipeline.extractor import EntityExtractor
        ex = EntityExtractor()
        p = ex._build_prompt("hello world", "人物, 组织")
        assert "hello world" in p

    def test_class_types_config_driven_fallback(self):
        from core.harness.knowledge_pipeline.extractor import EntityExtractor
        ex = EntityExtractor()
        # 无域/未知域 → 回退默认集
        assert ex._effective_class_types("") == ex.VALID_CLASS_TYPES
        assert ex._effective_class_types("no_such_domain_xyz") == ex.VALID_CLASS_TYPES
        # 已知域 → 读域本体（用现有域 supply-chain 的任意断言：集合非空且包含默认集元素或域特有类）
        typed = ex._effective_class_types("supply-chain")
        assert typed, "supply-chain domain should expose class types"


class TestDomainRouterDedup:
    """P2-4：T1/T2 共享助手（重复行清理后行为一致）。"""

    def test_helpers_exist_and_return_expected(self):
        from core.harness.knowledge.domain_router import DomainRouter
        r = DomainRouter()
        assert callable(r._t1_label_match)
        assert callable(r._t2_embed_score)
        # 空索引 → T1 None；未知域 → T2 None
        assert r._t1_label_match("anything") is None or isinstance(r._t1_label_match("anything"), str)
        s = r._t2_embed_score("anything", "no_such_domain")
        assert s is None or isinstance(s, float)

    def test_suggest_and_cost_consistent(self):
        from core.harness.knowledge.domain_router import DomainRouter
        r = DomainRouter()
        r._ensure_built()
        doms = r.list_domains()
        if len(doms) > 1:
            sugg = r.suggest("supply chain procurement", top_k=3)
            assert isinstance(sugg, list) and len(sugg) <= 3
            cost = r.per_domain_cost("supply chain procurement")
            assert isinstance(cost, dict)
            assert "t3_calls_needed" in cost or "per_domain" in cost


class TestAboxTBox:
    """Q3：ABox 类归属映射域 TBox + data property 校验。"""

    def test_domain_class_labels_none_fallback(self):
        from core.harness.knowledge import knowledge_abox_builder as kab
        assert kab._domain_class_labels("") is None
        assert kab._domain_class_labels("no_such_domain_xyz") is None
        assert kab._map_to_domain_class("entities", "") == ""

    def test_add_data_validated_skips_ghost_props(self):
        from core.harness.knowledge import knowledge_abox_builder as kab

        class FakeOnto:
            def __init__(self):
                self.triples = []

        o = FakeOnto()
        kab._add_data_validated(o, "s", "title", "v", None)          # 无域 → 写
        assert len(o.triples) == 1
        kab._add_data_validated(o, "s", "ghost_prop", "v", {"title"})  # 域无此 prop → 跳过
        assert len(o.triples) == 1
        kab._add_data_validated(o, "s", "title", "v2", {"title"})     # 域有 prop → 写
        assert len(o.triples) == 2
