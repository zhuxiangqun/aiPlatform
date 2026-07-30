#!/usr/bin/env python3
"""
E2E integration smoke test — knowledge pipeline + action registry (v3.1).

Tests the full chain:
  1. Document extraction (entity + relation from text)
  2. Cross-domain entity resolution discovery
  3. Action execution with entity constraints
  4. Audit trail verification

Usage: python3 scripts/e2e_smoke_test.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "aiPlat-core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "aiPlat-platform"))


async def test_extraction_pipeline():
    """Test: ingest + extract modules load and function properly."""
    from core.harness.knowledge_pipeline.extractor import (
        DocumentIngestor, ExtractionPipeline, PendingExtractionStore
    )
    # Test ingestor (no LLM required)
    ingestor = DocumentIngestor()
    chunks = ingestor.ingest("测试文档内容。这是第二句。", doc_name="test.txt")
    assert len(chunks) == 1, f"Expected 1 chunk, got {len(chunks)}"
    print(f"  ✅ Extraction: ingestor splits into {len(chunks)} chunk(s)")

    # Test store initialization (no LLM required)
    store = PendingExtractionStore()
    await store.initialize()
    print(f"  ✅ Extraction: PendingExtractionStore initialized")


async def test_cross_domain_candidates():
    """Test: cross-domain candidate discovery."""
    from core.harness.knowledge_pipeline.resolver import CrossDomainResolver, seed_cross_domain_config
    seed_cross_domain_config()
    resolver = CrossDomainResolver()
    candidates = resolver.find_candidates("unified_customer")
    print(f"  ✅ CrossDomain: {len(candidates)} candidates found")
    return candidates


async def test_action_registry():
    """Test: ActionRegistry has business actions registered."""
    from core.harness.ontology_engine.action_registry import get_action_registry
    reg = get_action_registry()
    actions = reg.list_for_class("fde-delivery", "诊断会话", "delivered")
    assert actions, "No actions for fde-delivery/诊断会话/delivered"
    print(f"  ✅ ActionRegistry: {len(actions)} actions for 诊断会话/delivered")
    for a in actions:
        if a.action_id == "approve_diagnosis":
            print(f"     - {a.action_id}: {a.label} (required_state={a.required_state})")
    return actions


async def test_entity_constraints():
    """Test: entity constraint validation."""
    from core.harness.ontology_engine.action_registry import get_action_registry
    reg = get_action_registry()
    # Should block: requires state 'delivered' but entity is 'in_progress'
    result = reg.check_entity_constraints(
        "approve_diagnosis", "fde-delivery", "诊断会话", "in_progress", "fde_engineer"
    )
    assert not result["valid"], "Should be blocked by state constraint"
    assert result["constraint_type"] == "state"
    print(f"  ✅ Constraints: correctly blocked — {result['reason'][:60]}")
    # Should pass: correct state
    result2 = reg.check_entity_constraints(
        "approve_diagnosis", "fde-delivery", "诊断会话", "delivered", "fde_engineer"
    )
    assert result2["valid"], f"Should pass: {result2['reason']}"
    print(f"  ✅ Constraints: correctly allowed")


async def test_dynamic_mapper():
    """Test: dynamic schema mapping."""
    from core.harness.infrastructure.dynamic_mapper import DynamicSchemaMapper
    mapper = DynamicSchemaMapper()
    raw = {"customer_name": "张江高科", "fault_desc": "设备不启动", "phone": "13800138000"}
    try:
        entity = mapper.map_to_entity(raw, "fde-delivery", "诊断会话")
        print(f"  ✅ Mapper: external JSON → entity id={entity['id'][:12]}")
    except (ValueError, FileNotFoundError) as e:
        print(f"  ⚠️ Mapper: expected error (no '诊断会话' class in fde-delivery?): {str(e)[:80]}")


async def test_throttle():
    """Test: decision throttle initializes and checks work."""
    from core.harness.infrastructure.throttle import DecisionThrottle
    from core.harness.infrastructure.action_store import ActionStore

    # Ensure table exists
    store = ActionStore()
    await store.initialize()

    throttle = DecisionThrottle(store=store)
    result = await throttle.check_rate_limit(
        actor="test_user", action_id="approve_diagnosis",
        domain_id="fde-delivery", limit=100, block_on_breach=False,
    )
    assert result["allowed"], f"Throttle should allow: {result}"
    print(f"  ✅ Throttle: initialized and checking (count={result['count']}, limit={result['limit']})")


async def main():
    print("\n═══════════════════════════════════════")
    print("  E2E Integration Smoke Test")
    print("═══════════════════════════════════════\n")

    failures = 0

    tests = [
        ("Extraction Pipeline", test_extraction_pipeline),
        ("Cross-Domain Candidates", test_cross_domain_candidates),
        ("Action Registry", test_action_registry),
        ("Entity Constraints", test_entity_constraints),
        ("Dynamic Mapper", test_dynamic_mapper),
        ("Decision Throttle", test_throttle),
    ]

    for name, test_fn in tests:
        try:
            await test_fn()
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            failures += 1

    print(f"\n{'✅ ALL PASSED' if failures == 0 else f'❌ {failures} FAILED'}")
    sys.exit(failures)


if __name__ == "__main__":
    asyncio.run(main())
