"""Routing purpose ContextVar → sys_llm_generate args.purpose resolution."""
from __future__ import annotations


def test_peek_routing_purpose_from_selection_log_stamp():
    from core.harness.utils.model_injection import (
        _log_model_selection,
        _ROUTING_PURPOSE,
        peek_routing_purpose,
    )

    token = _ROUTING_PURPOSE.set(None)
    try:
        _log_model_selection("chat", "demo-model", entry="best_model_for_purpose")
        assert peek_routing_purpose() == "chat"
        _log_model_selection(
            "create_adapter", "demo-model", entry="create_selected_adapter"
        )
        # create_adapter must not overwrite routing purpose
        assert peek_routing_purpose() == "chat"
    finally:
        _ROUTING_PURPOSE.reset(token)


def test_resolve_llm_purpose_peeks_contextvar():
    from core.harness.syscalls.llm import _resolve_llm_purpose
    from core.harness.utils.model_injection import _ROUTING_PURPOSE, _stamp_routing_purpose

    token = _ROUTING_PURPOSE.set(None)
    try:
        assert _resolve_llm_purpose() is None
        _stamp_routing_purpose("code_gen", "best_model_for_purpose")
        assert _resolve_llm_purpose() == "code_gen"
        assert _resolve_llm_purpose(purpose="clarify") == "clarify"
    finally:
        _ROUTING_PURPOSE.reset(token)


def test_skill_nested_trace_sets_purpose():
    from core.harness.utils.execute_session import skill_nested_llm_trace_context

    tc = skill_nested_llm_trace_context(source="code_generation")
    assert tc.get("purpose") == "code_gen"
    tc2 = skill_nested_llm_trace_context(source="skill_base")
    assert tc2.get("purpose") == "skill_execution"
    tc3 = skill_nested_llm_trace_context(source="skill_base", purpose="doc_llm")
    assert tc3.get("purpose") == "doc_llm"


def test_resolve_llm_purpose_from_source_map():
    from core.harness.syscalls.llm import _resolve_llm_purpose
    from core.harness.utils.model_injection import _ROUTING_PURPOSE

    token = _ROUTING_PURPOSE.set(None)
    try:
        assert _resolve_llm_purpose(trace_context={"source": "query_rewriter"}) == "doc_llm"
        assert _resolve_llm_purpose(trace_context={"source": "moa_executor"}) == "reasoning"
        assert _resolve_llm_purpose(trace_context={"source": "fde_ask"}) == "skill_execution"
        assert _resolve_llm_purpose(trace_context={"source": "workflow_plan_stage"}) == "reasoning"
        assert _resolve_llm_purpose(trace_context={"source": "skill_foo"}) == "skill_execution"
    finally:
        _ROUTING_PURPOSE.reset(token)
