"""
KB Integration router — Slack/IM webhook endpoints for knowledge base Q&A.
"""
from __future__ import annotations

import urllib.parse
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from api.schemas_response import StatusResponse

router = APIRouter(prefix="/platform", tags=["kb-integration"])


def _parse_form_body(raw: bytes) -> Dict[str, str]:
    form = urllib.parse.parse_qs(raw.decode("utf-8"), keep_blank_values=True)

    def _one(key: str) -> str:
        vals = form.get(key)
        return str(vals[0]) if vals else ""

    return {
        "text": _one("text"),
        "channel_id": _one("channel_id"),
        "user_id": _one("user_id"),
        "team_id": _one("team_id"),
    }


@router.post("/kb/slack/query", response_model=StatusResponse)
async def kb_slack_query(request: Request):
    """Slack slash-command webhook: answer KB questions from Slack.

    Requires a valid Slack signing secret (``AIPLAT_SLACK_SIGNING_SECRET``)
    unless ``AIPLAT_CHANNEL_ALLOW_UNSIGNED=1`` is set for local development.
    """
    raw = await request.body()
    try:
        from auth.slack_signature import require_slack_request

        require_slack_request(dict(request.headers), raw)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    question = ""
    doc_ids = None
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        import json

        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return {"response_type": "ephemeral", "text": "无法解析问题"}
        if not isinstance(data, dict):
            return {"response_type": "ephemeral", "text": "无法解析问题"}
        question = str(data.get("text") or data.get("question") or "").strip()
        doc_ids = data.get("doc_ids")
    else:
        form = _parse_form_body(raw)
        question = form.get("text", "").strip()

    if not question:
        return {"response_type": "ephemeral", "text": "请输入问题，例如 `/kb 什么是RAG`"}

    try:
        # W4: canonical Q&A path = CRAG (kb_qa_retrieve), not raw kb_retrieve
        from core.api.facades.service_facade import llm_generate
        from core.api.facades.kb_facade import kb_qa_retrieve

        doc_content, citations = await kb_qa_retrieve(
            question, doc_ids=doc_ids, top_k=3, tenant_id="system",
        )

        from core.api.core_facade import _sync_resolve as _async_prompt_resolve  # v2.5: canonical path (sync wrapper for async)
        from core.api.core_facade import best_model_for_purpose  # v2.5: canonical path
        sp = await _async_prompt_resolve("kb-qa", scenario="widget", documents=doc_content or "", question=question)
        resp = await llm_generate(
            None,
            [{"role": "user", "content": sp}],
            model_name=best_model_for_purpose("chat"), temperature=0.3, max_tokens=1000,
        )
        answer = getattr(resp, "content", "") or str(resp)
        sources = [
            {"doc_id": c.get("doc_id") or c.get("source", ""), "text": (c.get("text") or "")[:200]}
            for c in (citations or [])[:3]
        ]
        return {"answer": answer.strip(), "sources": sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kb/widget/embed.js", response_model=StatusResponse)
async def kb_widget_js():
    """Minimal embeddable JS widget for aiPlat KB.

    Answers are written with ``textContent`` (not ``innerHTML``) so LLM/HTML
    payloads cannot execute in the host page.
    """
    js = """
(function() {
  function esc(s) {
    var t = document.createElement('span');
    t.textContent = String(s == null ? '' : s);
    return t.innerHTML;
  }
  var d = document, s = d.createElement('div');
  s.innerHTML = '<div style="max-width:600px;margin:20px auto;font-family:sans-serif;border:1px solid #e0e0e0;border-radius:12px;padding:20px">'
    + '<h3>📚 AI 知识库问答</h3>'
    + '<input id="aiplat-kb-input" placeholder="输入问题..." style="width:100%;padding:10px;border:1px solid #ddd;border-radius:8px;margin:10px 0">'
    + '<button id="aiplat-kb-ask" style="background:#6366f1;color:white;border:none;padding:8px 20px;border-radius:8px;cursor:pointer">提问</button>'
    + '<div id="aiplat-kb-answer" style="margin-top:15px;padding:15px;background:#f5f5f5;border-radius:8px;display:none"></div></div>';
  var target = d.getElementById('aiplat-kb') || d.body;
  target.appendChild(s);
  d.getElementById('aiplat-kb-ask').onclick = async function() {
    var q = d.getElementById('aiplat-kb-input').value, ans = d.getElementById('aiplat-kb-answer');
    if (!q) return;
    ans.style.display = 'block';
    ans.textContent = '思考中...';
    try {
      var r = await fetch('/api/platform/kb/widget/query', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q:q})});
      var j = await r.json();
      ans.innerHTML = '<strong>回答：</strong><br>' + esc(j.answer || '未找到答案');
    } catch(e) { ans.textContent = '查询失败: ' + (e && e.message ? e.message : String(e)); }
  };
})();
"""
    return Response(content=js, media_type="application/javascript")
