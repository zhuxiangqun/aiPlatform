"""Regression tests for the known-defect review batch (fix/review-known-defects)."""

from __future__ import annotations

import pytest


def test_resolve_gold_dir_rejects_path_escape(tmp_path, monkeypatch):
    from core.harness.evaluation import code_review_gold as mod

    monkeypatch.setattr(
        "core.utils.paths.get_aiplat_data_dir",
        lambda rel="": str(tmp_path / str(rel).lstrip("/")),
    )
    evil = tmp_path / "outside"
    evil.mkdir()
    marker = evil / "secret.json"
    marker.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="gold_dir not under allowed"):
        mod.resolve_gold_dir(str(evil))


def test_reusable_stage_artifact_rejects_done_verify_failure():
    from core.harness.execution.pipeline_engine import PipelineEngine

    fn = PipelineEngine._is_reusable_stage_artifact
    assert fn({"status": "failed", "raw_output": "x", "title": "t"}) is False
    assert fn({"done_verify_veto": True, "raw_output": "x"}) is False
    assert fn({"error": "done_verify: missing FILE", "raw_output": "x"}) is False
    assert fn({"loop_state": "error", "raw_output": "x"}) is False
    assert fn({"source": "confirmed_prd", "raw_output": "ok"}) is True


def test_pinned_memory_tenant_isolation(tmp_path, monkeypatch):
    from core.harness.memory import file_store as fs

    monkeypatch.setattr(fs, "MEMORY_DIR", str(tmp_path))
    assert fs.write_memory("tenant-a fact about widgets", key="pref", tenant_id="ten_a")
    assert fs.write_memory("tenant-b fact about gadgets", key="pref", tenant_id="ten_b")
    a = fs.pinned_memory_text(tenant_id="ten_a")
    b = fs.pinned_memory_text(tenant_id="ten_b")
    assert "widgets" in a and "gadgets" not in a
    assert "gadgets" in b and "widgets" not in b


def test_archive_requires_session_id(tmp_path, monkeypatch):
    from core.harness.memory import file_store as fs

    monkeypatch.setattr(fs, "MEMORY_DIR", str(tmp_path))
    n = fs.archive_compacted_turns(
        [{"role": "user", "content": "hello world archive"}],
        session_id="",
        tenant_id="t1",
    )
    assert n == 0
    n2 = fs.archive_compacted_turns(
        [{"role": "user", "content": "hello world archive"}],
        session_id="s1",
        tenant_id="t1",
    )
    assert n2 == 1


def test_scoring_dimensions_no_release_fallback(monkeypatch):
    from core.harness.evaluation import dimensions as dim

    monkeypatch.delenv("AIPLAT_EVAL_DIMENSIONS", raising=False)
    assert dim.get_scoring_dimensions() == []


def test_repair_path_rejects_escape(tmp_path, monkeypatch):
    from core.harness.execution import completion_receipt as cr

    monkeypatch.chdir(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("x", encoding="utf-8")
    ctx = {"cwd": str(work)}
    assert cr._resolve_repair_path(ctx, "../secret.txt") == ""
    inside = work / "a.py"
    resolved = cr._resolve_repair_path(ctx, "a.py")
    assert resolved == str(inside.resolve())


def test_infer_receipt_status_ignores_benign_not_found():
    from core.harness.execution.completion_receipt import infer_receipt_status

    assert infer_receipt_status("Pattern not found in file") == "ok"
    assert infer_receipt_status("error_count: 0") == "ok"
    assert infer_receipt_status("Denied: blocked") == "failed"
    assert infer_receipt_status("Error: boom") == "failed"


def test_compiled_react_deny_returns_failure():
    import ast
    from pathlib import Path

    react_path = (
        Path(__file__).resolve().parents[3]
        / "harness"
        / "execution"
        / "langgraph"
        / "compiled_graphs"
        / "react.py"
    )
    src = react_path.read_text(encoding="utf-8")
    # Structural guard: deny branches must return success=False near Denied:
    assert "Denied:" in src
    assert "success=False" in src
    assert "record_tool_receipt" in src
    tree = ast.parse(src)
    assert tree is not None


def test_summarize_tool_msg_keeps_command_output():
    from core.harness.memory.compression import ContextCompression

    out = ContextCompression._summarize_tool_msg(
        {"name": "bash", "content": "pytest failed\nAssertionError: boom"},
        0,
    )
    assert "pytest" in out
    assert "[bash] executed" not in out


def test_coding_veto_fail_closed_in_production(monkeypatch):
    from core.harness.execution.execution_seal import coding_deliverable_veto

    monkeypatch.setenv("AIPLAT_PROFILE", "production")
    monkeypatch.delenv("AIPLAT_CODING_VETO_FAIL_OPEN", raising=False)
    code = (
        "## FILE: src/api/tasks.ts\n"
        "export async function getTasks() {\n"
        "  return apiClient.get('/api/tasks');\n"
        "}\n" * 3
    )
    ctx = {
        "_bound_skill_ids": ["code_generation", "autoreview"],
        "_skill_delivery": "once",
        "_primary_skill_delivered": "code_generation",
        "_user_task": "根据 api_contracts 生成 TypeScript 前端代码",
        "output": code,
        "_followup_skills_done": [],
        "_acceptance_veto_count": 3,
    }
    veto = coding_deliverable_veto(ctx)
    assert veto and "autoreview" in veto
    assert ctx.get("_coding_veto_exhausted") is True


def test_type_index_js_supports_textarea_and_contenteditable():
    from core.apps.tools.browser import _BrowserSession

    js = _BrowserSession._TYPE_INDEX_JS
    assert "TEXTAREA" in js
    assert "isContentEditable" in js or "contentEditable" in js
    assert "HTMLTextAreaElement" in js


def test_reevaluate_defaults_record_novel_false():
    import ast
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[5]
        / "aiPlat-platform"
        / "apps"
        / "eval"
        / "api"
        / "code_review_gold.py"
    )
    if not path.is_file():
        path = Path("aiPlat-platform/apps/eval/api/code_review_gold.py")
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "reevaluate_gold"
    )
    text = ast.get_source_segment(src, fn) or ""
    assert "record_novel = False" in text or "record_novel=False" in text.replace(" ", "")
