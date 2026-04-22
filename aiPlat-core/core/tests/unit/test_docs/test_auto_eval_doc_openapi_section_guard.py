from __future__ import annotations

from pathlib import Path


def _extract_between(text: str, begin: str, end: str) -> str:
    if begin not in text or end not in text:
        return ""
    a = text.split(begin, 1)[1]
    b = a.split(end, 1)[0]
    return b.strip() + "\n"


def test_auto_eval_doc_openapi_section_guard():
    """
    最终形态：文档的 API 段落不手写，必须与 openapi-eval.snapshot.json 自动生成结果一致。

    修复方式：
      1) python -m core.tools.export_eval_openapi > docs/design/evaluation/openapi-eval.snapshot.json
      2) python -m core.tools.sync_eval_docs
    """

    from core.tools.sync_eval_docs import render_openapi_section

    repo_root = Path(__file__).resolve().parents[4]
    doc_path = repo_root / "docs" / "design" / "evaluation" / "auto-eval-and-regression.md"
    snap_path = repo_root / "docs" / "design" / "evaluation" / "openapi-eval.snapshot.json"
    assert doc_path.exists()
    assert snap_path.exists()

    doc = doc_path.read_text(encoding="utf-8", errors="ignore")
    begin = "<!-- OPENAPI_EVAL_BEGIN -->"
    end = "<!-- OPENAPI_EVAL_END -->"
    actual = _extract_between(doc, begin, end)

    import json

    snap = json.loads(snap_path.read_text(encoding="utf-8", errors="ignore"))
    expected = render_openapi_section(snap).strip() + "\n"

    assert actual.strip() == expected.strip()

