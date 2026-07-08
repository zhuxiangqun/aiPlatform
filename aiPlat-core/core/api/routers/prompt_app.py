"""Prompt App Templates API — user-facing prompt templates organized by category."""
from __future__ import annotations
import json
import json as _json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.syscalls.llm import sys_llm_generate
from core.schemas_prompt_app import (
    PromptAppTemplateCreate, PromptAppTemplateUpdate,
    PromptPreviewRequest, PromptPreviewTextRequest, PromptOptimizeRequest,
    PromptRunRequest,
    PromptCategoryCreate,
    PromptAppInstanceCreate, PromptAppInstanceUpdate,
)

router = APIRouter()
_log = logging.getLogger("aiplat.prompt_app")


async def _record_changeset(store, name: str, target_id: str, status: str = "success", args: dict = None, result: dict = None):
    try:
        from core.governance.changeset import record_changeset
        await record_changeset(
            store=store, name=name, target_type="prompt_app_template", target_id=target_id,
            status=status, args=args or {}, result=result, user_id="admin",
        )
    except Exception:
        _log.warning("变更集记录失败: name=%s target_id=%s", name, target_id, exc_info=True)


def _verify_template_signature(template_id: str) -> Optional[bool]:
    """Best-effort signature verification for prompt app templates."""
    try:
        from core.management.prompt_app_manager import PromptAppManager
        from core.security.skill_signature_gate import get_trusted_skill_pubkeys_map
        import asyncio
        mgr = PromptAppManager()
        tpl = mgr.get(template_id)
        if not tpl: return None
        prov = dict(tpl.metadata.get("provenance", {}))
        if not prov.get("signature"): return None
        rt = get_kernel_runtime()
        store = getattr(rt, "execution_store", None) if rt else None
        import concurrent.futures as _cf
        with _cf.ThreadPoolExecutor(max_workers=1) as _pool:
            trusted = _pool.submit(asyncio.run, get_trusted_skill_pubkeys_map(store)).result(timeout=10) if store else {}
        result = mgr.compute_signature_verification(tpl, trusted)
        return result.get("signature_verified")
    except Exception:
        return None


def _store():
    rt = get_kernel_runtime()
    return getattr(rt, "execution_store", None) if rt else None


def _new_id(prefix: str = "pt") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ── Template CRUD ──────────────────────────────────────────────────

@router.get("/prompts/app/templates", response_model=Dict[str, Any])
async def list_templates(category: str = "", status: str = "",
                         limit: int = 100, offset: int = 0):
    try:
        store = _store()
        if not store:
            raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
        return await store.list_prompt_app_templates(
            limit=limit, offset=offset, category=category, status=status)
    except HTTPException:
        raise
    except Exception as e:
        _log.exception("list_templates failed")
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.post("/prompts/app/templates", response_model=Dict[str, Any])
async def create_template(req: PromptAppTemplateCreate):
    try:
        store = _store()
        if not store:
            raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
        result = await store.upsert_prompt_app_template(
            template_id=req.template_id,
            name=req.name,
            category=req.category,
            tags=_json.dumps(req.tags, ensure_ascii=False),
            system_prompt=req.system_prompt,
            user_prompt=req.user_prompt,
            assistant_prompt=req.assistant_prompt,
            variables=_json.dumps(req.variables, ensure_ascii=False),
        )
        await _record_changeset(store, "create_prompt_app_template", req.template_id, args={"name": req.name, "category": req.category})
        _verify_template_signature(req.template_id)  # best-effort signature check
        return result
    except HTTPException:
        raise
    except Exception as e:
        _log.exception("create_template failed")
        raise HTTPException(status_code=500, detail=str(e)[:300])


@router.get("/prompts/app/templates/{template_id}", response_model=Dict[str, Any])
async def get_template(template_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    tpl = await store.get_prompt_app_template(template_id=template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return tpl


@router.put("/prompts/app/templates/{template_id}", response_model=Dict[str, Any])
async def update_template(template_id: str, req: PromptAppTemplateUpdate):
    try:
        store = _store()
        if not store:
            raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
        existing = await store.get_prompt_app_template(template_id=template_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Template not found")
        return await store.upsert_prompt_app_template(
            template_id=template_id,
            name=req.name or existing.get("name", ""),
            category=req.category or existing.get("category", ""),
            tags=_json.dumps(req.tags, ensure_ascii=False) if req.tags is not None else existing.get("tags", "[]"),
            system_prompt=req.system_prompt if req.system_prompt is not None else existing.get("system_prompt", ""),
            user_prompt=req.user_prompt if req.user_prompt is not None else existing.get("user_prompt", ""),
            assistant_prompt=req.assistant_prompt if req.assistant_prompt is not None else existing.get("assistant_prompt", ""),
            variables=_json.dumps(req.variables, ensure_ascii=False) if req.variables is not None else existing.get("variables", "[]"),
            status=req.status or existing.get("status", "draft"),
        )
    except HTTPException:
        raise
    except Exception as e:
        _log.error(f"Update template failed: {e}")
        raise HTTPException(status_code=500, detail=f"Update template failed: {str(e)[:300]}")


@router.post("/prompts/app/templates/{template_id}/publish", response_model=Dict[str, Any])
async def publish_template(template_id: str):
    """Publish a prompt app template with signature verification."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    tpl = await store.get_prompt_app_template(template_id=template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    # Signature verification gate (best-effort)
    verified = _verify_template_signature(template_id)
    if verified is False:
        raise HTTPException(status_code=403, detail="Template signature verification failed — must be signed before publish")

    await store.upsert_prompt_app_template(
        template_id=template_id, name=tpl.get("name", ""), category=tpl.get("category", ""),
        tags=tpl.get("tags", "[]"), system_prompt=tpl.get("system_prompt", ""),
        user_prompt=tpl.get("user_prompt", ""), assistant_prompt=tpl.get("assistant_prompt", ""),
        variables=tpl.get("variables", "[]"),
    )
    # Update status to published via raw update
    try:
        await store.db.execute("UPDATE prompt_app_templates SET status='published', updated_at=? WHERE template_id=?", (time.time(), template_id))
        await store.db.commit()
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    await _record_changeset(store, "publish_prompt_app_template", template_id, args={"status": "published"})
    return {"status": "published", "template_id": template_id}


@router.delete("/prompts/app/templates/{template_id}", response_model=Dict[str, Any])
async def delete_template(template_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    ok = await store.delete_prompt_app_template(template_id=template_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "deleted"}


@router.post("/prompts/app/templates/{template_id}/copy", response_model=Dict[str, Any])
async def copy_template(template_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    existing = await store.get_prompt_app_template(template_id=template_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")
    new_id = f"{template_id}-copy-{_new_id('')}"
    return await store.upsert_prompt_app_template(
        template_id=new_id,
        name=existing.get("name", "") + " (副本)",
        category=existing.get("category", ""),
        tags=existing.get("tags", "[]"),
        system_prompt=existing.get("system_prompt", ""),
        user_prompt=existing.get("user_prompt", ""),
        assistant_prompt=existing.get("assistant_prompt", ""),
        variables=existing.get("variables", "[]"),
        status="draft",
    )


# ── Preview ────────────────────────────────────────────────────────

@router.post("/prompts/app/templates/{template_id}/preview", response_model=Dict[str, Any])
async def preview_template(template_id: str, req: PromptPreviewRequest):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    tpl = await store.get_prompt_app_template(template_id=template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    # Assemble prompt from template + variables
    sp = tpl.get("system_prompt", "")
    up = tpl.get("user_prompt", "")
    ap = tpl.get("assistant_prompt", "")

    for k, v in req.variables.items():
        ph = "${" + k + "}"
        up = up.replace(ph, str(v))

    try:
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        model_name = req.model or best_model_for_purpose("default")
        model = create_selected_adapter(model_name=model_name)
        messages = []
        if sp:
            messages.append({"role": "system", "content": sp})
        messages.append({"role": "user", "content": up})
        if ap:
            messages.append({"role": "assistant", "content": ap})
        resp = await sys_llm_generate(model, messages)
        output = resp.content if hasattr(resp, 'content') else str(resp)
        return {"output": str(output)[:4000], "model": model_name}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Preview failed: {str(e)[:200]}")


# ── Preview Text (raw prompt, no template_id needed) ─────────────

@router.post("/prompts/app/preview-text", response_model=Dict[str, Any])
async def preview_text(req: PromptPreviewTextRequest):
    sp = req.system_prompt or ""
    up = req.user_prompt or ""
    if not up:
        raise HTTPException(status_code=400, detail="user_prompt is required")

    for k, v in req.variables.items():
        up = up.replace("$" + "{" + k + "}", str(v))

    try:
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        model_name = req.model or best_model_for_purpose("default")
        model = create_selected_adapter(model_name=model_name)
        messages = []
        if sp:
            messages.append({"role": "system", "content": sp})
        messages.append({"role": "user", "content": up})
        resp = await sys_llm_generate(model, messages)
        output = resp.content if hasattr(resp, 'content') else str(resp)
        return {"output": str(output)[:4000], "model": model_name}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Preview text failed: {str(e)[:200]}")


# ── Run (template or instance → LLM output) ──────────────────────

@router.post("/prompts/app/run", response_model=Dict[str, Any])
async def run_prompt(req: PromptRunRequest):
    """Run a template or instance: render variables → LLM → return output."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    sp = up = ""
    if req.instance_id:
        inst = await store.get_prompt_app_instance(instance_id=req.instance_id)
        if not inst:
            raise HTTPException(status_code=404, detail="Instance not found")
        sp = inst.get("system_prompt", "")
        up = inst.get("user_prompt", "")
    elif req.template_id:
        tpl = await store.get_prompt_app_template(template_id=req.template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Template not found")
        sp = tpl.get("system_prompt", "")
        up = tpl.get("user_prompt", "")
    else:
        raise HTTPException(status_code=400, detail="template_id or instance_id required")

    for k, v in req.variables.items():
        up = up.replace("$" + "{" + k + "}", str(v))

    try:
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        model_name = req.model or best_model_for_purpose("default")
        model = create_selected_adapter(model_name=model_name)
        messages = []
        if sp:
            messages.append({"role": "system", "content": sp})
        messages.append({"role": "user", "content": up})
        resp = await sys_llm_generate(model, messages)
        output = resp.content if hasattr(resp, 'content') else str(resp)
        return {"output": str(output)[:4000], "model": model_name}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Run failed: {str(e)[:200]}")


# ── Optimize ───────────────────────────────────────────────────────

@router.post("/prompts/app/optimize", response_model=Dict[str, Any])
async def optimize_prompt(req: PromptOptimizeRequest):
    """AI-optimize a prompt: returns improved version with suggestions."""
    prompt_text = req.prompt
    try:
        store = _store()
        tpl = None
        if req.template_id and store:
            tpl = await store.get_prompt_app_template(template_id=req.template_id)
        if tpl and not prompt_text:
            prompt_text = tpl.get("user_prompt", "")

        if not prompt_text:
            raise HTTPException(status_code=400, detail="No prompt text to optimize")

        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        from core.harness.utils.prompt_loader import _async_prompt_resolve
        model_name = req.model or best_model_for_purpose("default")
        model = create_selected_adapter(model_name=model_name)

        optimize_prompt_text = f"""你是 Prompt 优化专家。分析以下 prompt 并提出优化建议。

原始 Prompt：
{prompt_text[:3000]}

请输出 JSON：
{{
  "optimized": "优化后的 prompt 文本",
  "changes": ["改动1说明", "改动2说明"],
  "score": 8
}}

只输出 JSON，不要其他内容。"""

        resp = await sys_llm_generate(model, [
            {"role": "system", "content": await _async_prompt_resolve("prompt-optimize-system-role")},
            {"role": "user", "content": optimize_prompt_text},
        ], config=None)

        content = resp.content if hasattr(resp, 'content') else str(resp)
        import re
        match = re.search(r'\{[\s\S]*\}', content.strip())
        result = {}
        if match:
            try:
                result = _json.loads(match.group(0))
            except Exception:
                result = {"optimized": content[:2000], "changes": [], "score": 0}

        return {
            "original": prompt_text[:2000],
            "optimized": result.get("optimized", "")[:2000],
            "changes": result.get("changes", []),
            "score": result.get("score", 0),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Optimize failed: {str(e)[:200]}")


# ── Categories ─────────────────────────────────────────────────────

@router.get("/prompts/app/categories", response_model=Dict[str, Any])
async def list_categories():
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_prompt_app_categories()


@router.post("/prompts/app/categories", response_model=Dict[str, Any])
async def create_category(req: PromptCategoryCreate):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    await store.upsert_prompt_app_category(
        name=req.name, display_order=req.display_order,
        icon=req.icon, parent=req.parent)
    return {"status": "created"}


@router.delete("/prompts/app/categories/{name}", response_model=Dict[str, Any])
async def delete_category(name: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    # Check if any templates use this category
    result = await store.list_prompt_app_templates(limit=1, category=name)
    if result.get("total", 0) > 0:
        raise HTTPException(status_code=409, detail="Cannot delete category with existing templates")
    await store.delete_prompt_app_category(name=name)
    return {"status": "deleted"}


# ── Seed ───────────────────────────────────────────────────────────

_APP_DEFAULTS = [
    # System behavior (19)
    ("graph-ask", "NL→图查询", "", "", "你是代码库专家。用户问：${question}\n\n你可以使用以下工具：...\n\n返回严格JSON（无markdown）。", "只返回JSON，不要任何其他内容。", ""),
    ("graph-ask-translate", "查询→自然语言", "", "", "用户问：${question}\n系统查询结果：${results_text}\n\n请用3-5句中文回答。", "用中文简洁回答。", ""),
    ("graph-system-role", "图查询系统角色", "", "", "", "你是代码库专家。只输出JSON。", ""),
    ("graph-architect-role", "架构师角色", "", "", "", "你是代码库架构师。", ""),
    ("graph-chat-stream", "代码专家(SSE)", "", "", "You are a codebase expert.\nCode context: ${context}\n\nQuestion: ${question}\nAnswer concisely in Chinese.", "", ""),
    ("agent-auto-fill", "Agent自动配置", "", "agent,配置,AI", "你是AI平台配置专家。从可用技能列表中挑选最匹配的2-3个skill填入JSON的skills数组（技能名必须与列表完全一致）。只输出JSON。", "你是一个AI平台配置专家。用户正在创建一个新的AI Agent：\n\n名称：${name}\n描述：${description}\n${role_section}\n\n可用技能列表：\n${skills_catalog}\n\n从以上列表挑2-3个最匹配的技能名填入JSON。输出JSON：{\"agent_type\":\"...\",\"skills\":[\"技能1\",\"技能2\"],\"memory_config\":{},\"reasoning\":\"...\"}", ""),
    ("agent-role-definition", "角色定义生成", "", "", "你是AI角色定义专家。名称：${name}\n描述：${description}\n\n生成结构化角色定义JSON。", "只输出JSON。", ""),
    ("agent-role-system", "角色定义系统角色", "", "", "", "你是AI角色定义专家。只输出JSON。", ""),
    ("agent-auto-fill-batch", "批量Agent配置", "", "", "你是AI平台配置专家。为${count}个Agent推荐配置。\n${agent_list}\n\n输出JSON。", "只输出JSON。", ""),
    ("eval-metrics-design", "评估指标设计", "", "", "你是评估指标设计专家。Agent：${name}(${agent_type})\n描述：${description}\n历史：${history}\n\n设计3-5个评分维度JSON。", "只输出JSON数组。", ""),
    ("eval-metrics-system", "指标系统角色", "", "", "", "你是评估指标设计专家。只输出JSON数组。", ""),
    ("kb-qa", "知识库问答", "", "公文", "你是知识库问答助手。基于提供的文档准确简洁回答问题。\n\n场景：${scenario}\n文档：${documents}\n\n问题：${question}\n\n直接中文回答。", "", ""),
    ("kb-doc-qa", "文档问答", "", "公文", "你是文档问答助手。仅基于给定片段回答，不编造。\n\n片段：${passages}\n\n问题：${question}\n\n纯文本答案。", "", ""),
    ("kb-doc-writer", "文档写作", "", "公文", "你是文档写作助手。按用户要求生成知识库文档。\n\n标题：${title}\n要求：${prompt}", "直接输出文档。", ""),
    ("kb-planner", "KB任务规划", "", "公文", "你是任务规划器。将任务拆解为2-5个步骤。\n\n可用：retrieve(查询词)\n\n任务：${task}", "", ""),
    ("kb-retrieval-assistant", "KB检索助手", "", "", "", "You are a knowledge retrieval assistant. Answer based on provided context.", ""),
    ("doc-summarizer", "文档总结", "", "公文", "你是文档总结助手。仅基于候选句生成总结。\n${sentences}\n\n输出JSON：{summary, points}。", "输出JSON。", ""),
    ("agent-fallback", "Agent回退", "", "", "", "You are ${agent_name}. Respond helpfully.", ""),
    ("conversational-default", "默认对话", "", "", "", "You are a helpful assistant.", ""),
    # User-visible (15)
    ("invitation-letter", "邀请函", "公文", "正式,商务,邀请", "你是专业的公文写作助手，风格正式、简洁、礼貌。", "生成邀请函：\n收件人：${recipient}\n事件：${event}\n日期：${date}\n地点：${location}\n发件人：${sender}", "直接输出邀请函正文。"),
    ("recommendation-letter", "推荐信", "公文", "正式,商务,推荐", "你是专业的公文写作助手。", "生成推荐信：\n推荐人：${recommender}\n被推荐人：${candidate}\n推荐原因：${reason}\n日期：${date}", "直接输出推荐信正文。"),
    ("notice", "通知公告", "公文", "正式,通知", "你是公文写作助手。", "生成通知：\n标题：${title}\n内容：${content}\n日期：${date}", "直接输出通知正文。"),
    ("meeting-minutes", "会议纪要", "公文", "正式,会议", "你是公文写作助手。", "生成会议纪要：\n会议主题：${topic}\n参会人：${attendees}\n讨论要点：${points}\n决议：${decisions}", "直接输出会议纪要正文。"),
    ("interior-design", "室内设计", "图像", "设计,室内,现代", "你是室内设计图像生成助手。", "Interior Design: ${style}, ${room_type}, ${lighting}, ${color_scheme}, ${furniture_style}", "Negative: low quality, blurry, distorted"),
    ("art-illustration", "艺术插图", "图像", "艺术,插图,手绘", "你是艺术插图生成助手。", "Art illustration: ${style}, ${subject}, ${color_palette}, ${mood}", "Negative: low quality, artifacts, signature"),
    ("photo-realistic", "照片写实", "图像", "照片,写实,摄影", "你是照片写实生成助手。", "Photo-realistic: ${subject}, ${environment}, ${lighting}, ${camera}, ${style}", "Negative: cartoon, sketch, low quality"),
    ("3d-character", "3D角色", "图像", "3D,角色,设计", "你是3D角色生成助手。", "3D character: ${character_type}, ${style}, ${environment}, ${pose}, ${details}", "Negative: low poly, deformed, low quality"),
    ("course-outline", "课件大纲", "教育", "教育,课程,大纲", "你是教育课件设计助手。", "生成课件大纲：\n课程：${course_name}\n目标学员：${audience}\n课时：${duration}\n目标：${objectives}", "直接输出大纲结构。"),
    ("exam-question", "试题生成", "教育", "教育,考试,试题", "你是试题生成助手。", "生成试题：\n学科：${subject}\n难度：${difficulty}\n题型：${question_type}\n数量：${count}\n知识点：${topics}", "直接输出试题。"),
    ("thesis-abstract", "论文摘要", "教育", "教育,论文,学术", "你是学术写作助手。", "生成论文摘要：\n标题：${title}\n关键词：${keywords}\n研究背景：${background}\n方法：${method}\n结论：${conclusion}", "直接输出摘要。"),
    ("article-polish", "文章润色", "创作", "创作,润色,文案", "你是文章润色助手。", "润色以下文本：\n原文：${original}\n风格：${style}\n长度要求：${length}", "直接输出润色后文本。"),
    ("poetry", "诗歌生成", "创作", "创作,诗歌,文学", "你是诗歌创作助手。", "创作诗歌：\n主题：${theme}\n风格：${style}\n格式：${format}", "直接输出诗歌。"),
    ("code-comment", "代码注释", "技术", "技术,编程,注释", "你是代码注释助手。", "为以下代码添加注释：\n语言：${language}\n代码：${code}\n风格：${comment_style}", "直接输出带注释的代码。"),
    ("tech-proposal", "技术方案", "技术", "技术,方案,文档", "你是技术方案撰写助手。", "撰写技术方案：\n项目：${project}\n需求：${requirements}\n技术栈：${tech_stack}\n架构：${architecture}", "直接输出方案文档。"),
]


_EXAMPLES = {
    "invitation-letter": "输入：recipient=张总, event=年会, date=2026-06-01, location=北京饭店, sender=李经理\n输出：尊敬的张总：诚邀您参加于2026年6月1日在北京饭店举行的年会晚宴。期待您的光临。此致 李经理",
    "recommendation-letter": "输入：recommender=王教授, candidate=李明, reason=优秀研究能力, date=2025-12-01\n输出：尊敬的评审委员会：我很荣幸推荐李明同学。李明在研究生期间展现了出色的研究能力...",
    "notice": "输入：title=放假通知, content=春节放假安排, date=2025-01-20\n输出：放假通知：根据国家法定节假日规定，春节放假时间为...",
    "course-outline": "输入：course_name=Python入门, audience=零基础学员, duration=4周, objectives=掌握Python基础语法\n输出：第一周：Python简介与环境搭建；第二周：变量、数据类型与运算符...",
    "meeting-minutes": "输入：topic=产品评审会, attendees=张总,李经理,王工, points=讨论了V2版本需求, decisions=Q3上线\n输出：会议纪要：产品评审会。参会人：张总、李经理、王工。讨论要点：V2版本需求。决议：Q3上线。",
    "interior-design": "输入：style=现代简约, room_type=客厅, lighting=自然光, color_scheme=浅色系, furniture_style=北欧\n输出：Interior Design: modern minimalist living room, natural lighting, light colors, Nordic furniture style, large windows, plants",
    "code-comment": "输入：language=Python, code=def add(a,b):\n    return a+b, comment_style=中文\n输出：# 计算两个数的和\n# 参数: a - 第一个加数, b - 第二个加数  \n# 返回: 两数之和\ndef add(a, b):\n    return a + b",
}

_CONSTRAINTS = {
    "invitation-letter": "· 日期使用yyyy年mm月dd日格式\n· 不使用昵称\n· 不添加RSVP信息",
    "interior-design": "· 正向Prompt使用英文\n· 包含style/room_type/lighting关键词",
    "code-comment": "· 保留原代码不变\n· 注释使用中文\n· 不添加文件头注释",
}


@router.post("/prompts/app/seed", response_model=Dict[str, Any])
async def seed_app_templates():
    """Import 34 default app templates (idempotent)."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    seeded, skipped = [], []
    # Seed scenario tags first
    try:
        await seed_scenario_tags()
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    for tid, name, cat, tags, sp, up, ap in _APP_DEFAULTS:
        try:
            existing = await store.get_prompt_app_template(template_id=tid)
            if existing:
                skipped.append(tid)
                continue
            vars_list = []
            import re as _re
            all_text = sp + up + ap
            for m in _re.findall(r'\$\{(\w+)\}', all_text):
                if m not in [v.get("name") for v in vars_list]:
                    vars_list.append({"name": m, "type": "text", "description": ""})
            scenario_tags = _TEMPLATE_SCENARIOS.get(tid, [])
            await store.upsert_prompt_app_template(
                template_id=tid, name=name, category=cat,
                tags=_json.dumps([t.strip() for t in tags.split(",") if t.strip()], ensure_ascii=False),
                system_prompt=sp, user_prompt=up, assistant_prompt=ap,
                variables=_json.dumps(vars_list, ensure_ascii=False),
                examples=_EXAMPLES.get(tid, ""),
                constraints=_CONSTRAINTS.get(tid, ""),
                scenario_tags=_json.dumps(scenario_tags, ensure_ascii=False),
                status="published",
            )
            seeded.append(tid)
        except Exception:
            skipped.append(tid)
    return {"seeded": seeded, "skipped": skipped, "total": len(seeded) + len(skipped)}


# ── Scenario Tags ──────────────────────────────────────────────────

_SCENARIO_TAGS = [
    ("使用场景", "商务沟通", "", 1),
    ("使用场景", "内部管理", "", 2),
    ("使用场景", "教学辅助", "", 3),
    ("使用场景", "创意写作", "", 4),
    ("使用场景", "技术文档", "", 5),
    ("子场景", "正式邀请", "商务沟通", 1),
    ("子场景", "人才推荐", "商务沟通", 2),
    ("子场景", "信息发布", "内部管理", 1),
    ("子场景", "会议记录", "内部管理", 2),
    ("子场景", "课件制作", "教学辅助", 1),
    ("子场景", "试题生成", "教学辅助", 2),
    ("子场景", "学术写作", "教学辅助", 3),
    ("子场景", "文案润色", "创意写作", 1),
    ("子场景", "诗歌创作", "创意写作", 2),
    ("子场景", "代码注释", "技术文档", 1),
    ("子场景", "方案撰写", "技术文档", 2),
    ("对象", "外部客户", "", 1),
    ("对象", "评审机构", "", 2),
    ("对象", "全员", "", 3),
    ("对象", "参会者", "", 4),
    ("对象", "学生", "", 5),
    ("对象", "读者", "", 6),
    ("对象", "开发者", "", 7),
    ("语气", "正式礼貌", "", 1),
    ("语气", "正式直接", "", 2),
    ("语气", "客观记录", "", 3),
    ("语气", "教学引导", "", 4),
    ("语气", "创意自由", "", 5),
    ("语气", "技术准确", "", 6),
]

_TEMPLATE_SCENARIOS = {
    "invitation-letter": ["正式邀请", "外部客户", "正式礼貌"],
    "recommendation-letter": ["人才推荐", "评审机构", "正式直接"],
    "notice": ["信息发布", "全员", "正式直接"],
    "meeting-minutes": ["会议记录", "参会者", "客观记录"],
    "course-outline": ["课件制作", "学生", "教学引导"],
    "exam-question": ["试题生成", "学生", "教学引导"],
    "thesis-abstract": ["学术写作", "评审机构", "客观记录"],
    "article-polish": ["文案润色", "读者", "创意自由"],
    "poetry": ["诗歌创作", "读者", "创意自由"],
    "code-comment": ["代码注释", "开发者", "技术准确"],
    "tech-proposal": ["方案撰写", "开发者", "技术准确"],
    "interior-design": ["创意写作", "外部客户", "创意自由"],
    "art-illustration": ["创意写作", "外部客户", "创意自由"],
    "photo-realistic": ["创意写作", "外部客户", "创意自由"],
    "3d-character": ["创意写作", "外部客户", "创意自由"],
}


@router.get("/prompts/app/scenario-tags", response_model=Dict[str, Any])
async def list_scenario_tags():
    """Return all scenario tags, grouped by category."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503)
    await store.init()
    import sqlite3, anyio
    db_path = store._config.db_path
    def _sync():
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA busy_timeout=3000"); conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM prompt_scenario_tags ORDER BY display_order;").fetchall()
            result = {}
            for r in rows:
                cat = r["category"]
                if cat not in result:
                    result[cat] = []
                result[cat].append({"name": r["name"], "parent": r["parent"]})
            return result
        finally:
            conn.close()
    return await anyio.to_thread.run_sync(_sync)


@router.post("/prompts/app/scenario-tags/seed", response_model=Dict[str, Any])
async def seed_scenario_tags():
    """Seed scenario tags (idempotent)."""
    store = _store()
    if not store:
        raise HTTPException(status_code=503)
    await store.init()
    import sqlite3, anyio, time as _t
    db_path = store._config.db_path
    now = _t.time()
    def _sync():
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA busy_timeout=3000")
        try:
            for cat, name, parent, order in _SCENARIO_TAGS:
                conn.execute(
                    "INSERT OR IGNORE INTO prompt_scenario_tags(name,category,parent,display_order,created_at) VALUES(?,?,?,?,?);",
                    (name, cat, parent, order, now)
                )
            conn.commit()
        finally:
            conn.close()
    await anyio.to_thread.run_sync(_sync)
    return {"status": "seeded", "count": len(_SCENARIO_TAGS)}


# ── Instance CRUD ──────────────────────────────────────────────────

@router.get("/prompts/app/instances", response_model=Dict[str, Any])
async def list_instances(limit: int = 100, offset: int = 0):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_prompt_app_instances(limit=limit, offset=offset)


@router.post("/prompts/app/instances", response_model=Dict[str, Any])
async def create_instance(req: PromptAppInstanceCreate):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    tpl = await store.get_prompt_app_template(template_id=req.source_template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Source template not found")
    inst_id = f"inst-{uuid.uuid4().hex[:8]}"
    return await store.upsert_prompt_app_instance(
        instance_id=inst_id, name=req.name or f"{tpl.get('name', '')} (实例)",
        source_template_id=req.source_template_id,
        system_prompt=tpl.get("system_prompt", ""),
        user_prompt=tpl.get("user_prompt", ""),
        assistant_prompt=tpl.get("assistant_prompt", ""),
        variables=tpl.get("variables", "[]"),
    )


@router.put("/prompts/app/instances/{instance_id}", response_model=Dict[str, Any])
async def update_instance(instance_id: str, req: PromptAppInstanceUpdate):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    existing = await store.get_prompt_app_instance(instance_id=instance_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Instance not found")
    return await store.upsert_prompt_app_instance(
        instance_id=instance_id,
        name=req.name or existing.get("name", ""),
        source_template_id=existing.get("source_template_id", ""),
        system_prompt=req.system_prompt if req.system_prompt is not None else existing.get("system_prompt", ""),
        user_prompt=req.user_prompt if req.user_prompt is not None else existing.get("user_prompt", ""),
        assistant_prompt=req.assistant_prompt if req.assistant_prompt is not None else existing.get("assistant_prompt", ""),
        variables=_json.dumps(req.variables, ensure_ascii=False) if req.variables is not None else existing.get("variables", "[]"),
        status=req.status or existing.get("status", "draft"),
    )


@router.delete("/prompts/app/instances/{instance_id}", response_model=Dict[str, Any])
async def delete_instance(instance_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    await store.delete_prompt_app_instance(instance_id=instance_id)
    return {"status": "deleted"}


@router.post("/prompts/app/templates/{template_id}/sign", response_model=Dict[str, Any])
async def sign_prompt_app_template(template_id: str, req: Dict[str, Any]):
    """Sign a prompt app template directory with Ed25519 key. Writes TEMPLATE.manifest.json."""
    private_key = str(req.get("private_key") or "").strip()
    private_key = private_key.replace("\\n", "\n")  # normalize escaped newlines from frontend
    if not private_key:
        raise HTTPException(status_code=400, detail="private_key is required")

    try:
        from core.management.prompt_app_manager import PromptAppManager
        mgr = PromptAppManager()
    except Exception:
        raise HTTPException(status_code=503, detail="PromptAppManager not available")

    tpl = mgr.get(template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="template not found")

    try:
        from core.harness.infrastructure.crypto.signature import sign_skill as sign_tpl

        tmpl_dir = Path(tpl.metadata.get("filesystem", {}).get("template_dir") or "")
        if not tmpl_dir or not tmpl_dir.exists():
            raise HTTPException(status_code=500, detail="Template directory not found")

        mgr._enrich_provenance_and_integrity(tpl.metadata, template_dir=tmpl_dir)
        integ = tpl.metadata.get("integrity", {})
        bundle_sha256 = integ.get("bundle_sha256", "")
        if not bundle_sha256:
            raise HTTPException(status_code=500, detail="Could not compute bundle_sha256")

        version = req.get("version") or tpl.version or "0.1.0"
        signature = sign_tpl(private_key=private_key, skill_id=template_id, version=str(version), bundle_sha256=bundle_sha256)

        manifest_path = tmpl_dir / "TEMPLATE.manifest.json"
        manifest = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                _log.warning("无法解析 manifest JSON: %s", manifest_path, exc_info=True)
        manifest["signature"] = signature
        manifest["version"] = str(version)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        mgr._enrich_provenance_and_integrity(tpl.metadata, template_dir=tmpl_dir)

    except HTTPException: raise
    except ValueError as e: raise HTTPException(status_code=400, detail=f"Invalid private key: {str(e)}")
    except Exception as e: raise HTTPException(status_code=500, detail=f"Signing failed: {str(e)}")

    return {"status": "signed", "bundle_sha256": bundle_sha256, "version": str(version), "signature": signature}
