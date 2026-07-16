"""
KB Integration router — Slack/IM webhook endpoints for knowledge base Q&A.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/platform", tags=["kb-integration"])


@router.post("/kb/slack/query", response_model=Dict[str, Any])
async def kb_slack_query(request: Request):
    """Slack slash-command webhook: answer KB questions from Slack.

    Accepts Slack's application/x-www-form-urlencoded body:
      - text: the user's question
      - channel_id, user_id, team_id (for future auth)
    Returns in_channel response with KB answer.
    """
    try:
        body = await request.form()
        question = str(body.get("text") or "").strip()
        if not question:
            return {"response_type": "ephemeral", "text": "请输入问题，例如 `/kb 什么是RAG`"}
    except Exception:
        try:
            data = await request.json()
            question = str(data.get("text") or data.get("question") or "").strip()
        except Exception:
            return {"response_type": "ephemeral", "text": "无法解析问题"}

    try:
        # Retrieve from KB
        from core.api.facades.service_facade import llm_generate
        from core.api.facades.kb_facade import kb_retrieve

        doc_ids = data.get("doc_ids") or ["doc_test_001", "doc_test_002", "doc_test_003"]
        results = kb_retrieve(query=question, doc_ids=doc_ids, top_k=3)
        doc_content = "\n\n---\n\n".join(r["text"][:500] for r in results[:3]) if results else ""

        from core.api.core_facade import _sync_resolve as _async_prompt_resolve  # v2.5: canonical path (sync wrapper for async)
        from core.api.core_facade import best_model_for_purpose  # v2.5: canonical path
        sp = await _async_prompt_resolve("kb-qa", scenario="widget", documents=doc_content, question=question)
        resp = await llm_generate(
            None,
            [{"role": "user", "content": sp}],
            model_name=best_model_for_purpose("chat"), temperature=0.3, max_tokens=1000,
        )
        answer = getattr(resp, "content", "") or str(resp)
        return {"answer": answer.strip(), "sources": [{"doc_id": r["doc_id"], "text": r["text"][:200]} for r in results[:3]]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kb/widget/embed.js", response_model=Dict[str, Any])
async def kb_widget_js():
    """Minimal embeddable JS widget for aiPlat KB."""
    from fastapi.responses import Response
    js = """
(function() {
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
    ans.style.display = 'block'; ans.innerHTML = '思考中...';
    try {
      var r = await fetch('/api/platform/kb/widget/query', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q:q})});
      var j = await r.json();
      ans.innerHTML = '<strong>回答：</strong><br>' + (j.answer || '未找到答案');
    } catch(e) { ans.innerHTML = '查询失败: ' + e.message; }
  };
})();
"""
    return Response(content=js, media_type="application/javascript")
