"""Regression: extraction parse + domain class filter must not drop entities."""
from __future__ import annotations

import asyncio

from core.harness.knowledge_pipeline.extractor import EntityExtractor, ExtractedEntity


def test_parse_response_accepts_domain_class_types():
    ex = EntityExtractor()
    raw = """一些思考……
```json
{
  "entities": [
    {"name": "LM-200", "class_type": "设备型号", "attributes": {}, "evidence": "门锁 LM-200"},
    {"name": "张三", "class_type": "安装师傅", "attributes": {}, "evidence": "师傅张三"}
  ],
  "relations": [
    {"source": "张三", "type": "负责", "target": "LM-200", "evidence": "负责安装"}
  ],
  "overall_confidence": 0.9
}
```
"""
    allowed = {"设备型号", "安装师傅", "安装工单", "客户现场", "故障类型", "维修记录"}
    parsed = ex._parse_response(raw, "doc", 0, allowed_class_types=allowed)
    assert len(parsed["entities"]) == 2
    assert {e.class_type for e in parsed["entities"]} == {"设备型号", "安装师傅"}
    assert len(parsed["relations"]) == 1


def test_extract_filter_keeps_extracted_entity_objects():
    """Historical bug: filter used e.get() on ExtractedEntity → AttributeError → 0 entities."""
    ex = EntityExtractor()
    allowed = {"设备型号", "安装师傅", "维修记录"}

    async def fake_llm(_prompt: str) -> str:
        return (
            '{"entities":[{"name":"LM-200","class_type":"设备型号","attributes":{},'
            '"evidence":"x"},{"name":"未知角色","class_type":"组织","attributes":{},'
            '"evidence":"y"}],"relations":[],"overall_confidence":0.8}'
        )

    ex._call_llm = fake_llm  # type: ignore[method-assign]
    ex._effective_class_types = lambda _domain: allowed  # type: ignore[method-assign]

    parsed = asyncio.get_event_loop().run_until_complete(
        ex.extract({"text": "门锁 LM-200", "doc_name": "t", "offset": 0}, domain_id="lock-service")
    )
    assert len(parsed["entities"]) == 2
    assert all(isinstance(e, ExtractedEntity) for e in parsed["entities"])
    # 域外类型 remap 到域内默认，而不是丢弃
    types = {e.class_type for e in parsed["entities"]}
    assert "设备型号" in types
    assert "组织" not in types
    assert all(e.class_type in allowed for e in parsed["entities"])


def test_route_status_pending_not_auto_accept():
    from core.harness.knowledge_pipeline.extractor import ExtractionPipeline

    pipe = ExtractionPipeline()
    assert pipe._route_status(0.95, entity_count=3) == "pending"
    assert pipe._route_status(0.95, entity_count=0) == "rejected"
    assert pipe._route_status(0.4, entity_count=2) == "rejected"
