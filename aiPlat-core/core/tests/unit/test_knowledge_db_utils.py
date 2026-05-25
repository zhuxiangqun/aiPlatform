"""Tests for knowledge/db.py + knowledge/utils.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "aiPlat-core"))

import pytest


class TestKnowledgeDB:
    def test_get_knowledge_db_exists(self):
        from core.harness.knowledge.db import get_knowledge_db
        assert callable(get_knowledge_db)

    def test_set_knowledge_db_exists(self):
        from core.harness.knowledge.db import set_knowledge_db
        assert callable(set_knowledge_db)


class TestKnowledgeUtils:
    def test_extract_keywords(self):
        from core.harness.knowledge.utils import extract_keywords
        kw = extract_keywords("核心 要点 总结")
        assert isinstance(kw, list)

    def test_score_text(self):
        from core.harness.knowledge.utils import score_text
        score = score_text("这是一个测试文本", ["测试", "文本"])
        assert isinstance(score, (int, float))
        assert score >= 0

    def test_text_quality_score(self):
        from core.harness.knowledge.utils import text_quality_score
        score = text_quality_score("hello world")
        assert isinstance(score, (int, float))

    def test_is_low_quality_video_ocr(self):
        from core.harness.knowledge.utils import is_low_quality_video_ocr
        result = is_low_quality_video_ocr("正常文本内容")
        assert isinstance(result, bool)

    def test_element_source(self):
        from core.harness.knowledge.utils import element_source
        src = element_source({"page_idx": 1, "type": "text"})
        assert isinstance(src, str)
