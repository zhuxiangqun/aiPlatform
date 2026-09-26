"""FDE assess/dialog clarify turn — core service (MemoryManager + optional Agent).

Platform `/fde/assess/dialog` is a thin HTTP proxy over `run_clarify_turn`.
Conversational memory uses sys_llm_generate(session_id=…) → MemoryManager.
Structured field cache only fills company/industry/pain gaps between turns.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_INDUSTRY_KEYWORDS = [
    "政务", "医疗", "金融", "制造", "零售", "教育", "物流", "农业",
    "能源", "交通", "地产", "保险", "通信", "互联网", "软件", "游戏",
    "安装服务", "安装", "维保", "售后服务", "现场服务",
]
_COMPANY_SUFFIXES = ["公司", "集团", "有限公司", "科技", "有限责任公司"]
_CORE_DIALOG_GAPS = ("公司名称", "行业", "痛点")
_PAIN_POINT_KEYWORDS = [
    "痛点", "问题", "困难", "效率低", "不准确", "人工", "手动", "无法",
    "串标", "围标", "检测", "检索", "识别", "分析", "预测", "优化",
    "不同步", "催单", "派单", "对不上",
]
_FINISH_COMMANDS = {"结束澄清", "结束", "finish", "done", "生成报告", "生成诊断"}
_DIALOG_FALLBACK_OPTS = ["是", "否", "部分是", "其他"]
_DIALOG_DEFAULT_MSG = "请提供更多关于客户业务的信息。"

# Structured field cache only — NOT a substitute for MemoryManager conversation memory.
_DIALOG_CONTEXT_MEMORY: Dict[str, Dict[str, str]] = {}
_pending_qs_cache: Dict[str, list] = {}


@dataclass
class ClarifyTurnInput:
    turn: int = 1
    answer: str = ""
    session_id: str = ""
    report_text: str = ""
    dialog_id: str = ""
    history: List[Dict[str, str]] = field(default_factory=list)
    industry: str = ""
    company_name: str = ""
    pain_points: str = ""
    team_size: str = ""
    budget: str = ""
    existing_tech_stack: str = ""
    internal_data_sources: str = ""
    external_data_sources: str = ""
    compliance_requirements: str = ""
    poc_timeline: str = ""
    production_timeline: str = ""
    domain_id: str = ""
    run_diagnosis: bool = False


def simple_extract_fields(answer: str, context: dict) -> dict:
    """Keyword/label-based extraction when LLM is unavailable or as a first pass."""
    updated: Dict[str, str] = {}
    a = answer.strip()
    if not a:
        return updated

    import re as _re

    def _set(field_name: str, value: str) -> None:
        if not value or context.get(field_name) or updated.get(field_name):
            return
        val = value.strip(" ，,。；;.\n\t")
        if not val:
            return
        if field_name == "pain_points":
            val = val[:400]
        if len(val) >= 1:
            updated[field_name] = val

    m = _re.search(r'(?:客户|公司|企业|厂商)(?:名称)?\s*[：:是叫为]\s*([^\s，,。；;\n/]{2,40})', a)
    if m:
        _set("company_name", m.group(1))
    m = _re.search(r'行业\s*[：:是为]\s*([^\s，,。；;\n/]{2,40})', a)
    if m:
        _set("industry", m.group(1))
    m = _re.search(
        r'痛点\s*[：:]\s*(.+?)(?=(?:\n|希望|域\s*[：:]|团队|技术栈|预算|POC|poc|$))',
        a, _re.DOTALL | _re.IGNORECASE,
    )
    if m:
        _set("pain_points", m.group(1))
    m = _re.search(r'(?:团队规模|人数|规模)\s*[：:是为]\s*([^\s，,。；;\n]{1,40})', a)
    if m:
        _set("team_size", m.group(1))
    m = _re.search(r'(?:技术栈|现有技术|系统)\s*[：:是为]\s*([^\n，,。；;]{2,80})', a)
    if m:
        _set("existing_tech_stack", m.group(1))
    m = _re.search(r'预算\s*[：:是为]\s*([^\s，,。；;\n]{1,40})', a)
    if m:
        _set("budget", m.group(1))
    m = _re.search(r'(?:域|本体域|domain(?:_id)?)\s*[：:=]\s*([a-zA-Z][\w\-]{1,64})', a, _re.IGNORECASE)
    if m:
        _set("domain_id", m.group(1))

    for kw in _INDUSTRY_KEYWORDS:
        if kw in a and not context.get("industry") and not updated.get("industry"):
            updated["industry"] = kw
            break

    has_company = any(p in a for p in _COMPANY_SUFFIXES)
    if has_company and not context.get("company_name") and not updated.get("company_name"):
        m = _re.search(r'(?:叫|是|为)\s*([^\s，,。.叫是为]{2,20})(?:\s*(?:公司|集团|有限公司|科技))?', a)
        if not m:
            m = _re.search(r'([^\s，,。.叫是为]{2,20})\s*(?:公司|集团|有限公司|科技)', a)
        if m:
            name = m.group(1).strip("，,。. ")
            if len(name) >= 2 and name not in ("我们", "这个", "那个", "一家", "一个"):
                updated["company_name"] = name
        if not updated.get("company_name"):
            for sent in a.replace("，", "。").split("。"):
                if any(p in sent for p in _COMPANY_SUFFIXES):
                    cs = sent.strip()
                    for p in _COMPANY_SUFFIXES:
                        if p in cs:
                            name = cs[:cs.index(p)].strip()
                            if len(name) >= 2:
                                updated["company_name"] = name[:40]
                                break
                    break

    m = _re.search(r'(\d+)[\s~到至-]*(\d*)\s*(?:人|个?人|员工|团队)', a)
    if m and not context.get("team_size") and not updated.get("team_size"):
        if m.group(2):
            updated["team_size"] = f'{m.group(1)}-{m.group(2)}人'
        else:
            updated["team_size"] = f'{m.group(1)}人'

    m = _re.search(r'(\d+)\s*(?:万|k|w)\s*(?:预算|元|块|以内|左右)?', a, _re.IGNORECASE)
    if m and not context.get("budget") and not updated.get("budget"):
        updated["budget"] = f'{m.group(1)}万'

    if (
        any(kw in a for kw in _PAIN_POINT_KEYWORDS)
        and not context.get("pain_points")
        and not updated.get("pain_points")
    ):
        updated["pain_points"] = a[:200]

    tech_kw = [
        "Java", "Python", "Go", "MySQL", "PostgreSQL", "Oracle", "Docker",
        "K8s", "Kubernetes", "React", "Vue", "Angular", "Spring", "Flask",
        "ERP", "OA", "CRM", "Hadoop", "Spark", "云服务", "私有云", "公有云",
        "微信", "Excel", "表格",
    ]
    if not context.get("existing_tech_stack") and not updated.get("existing_tech_stack"):
        found = [kw for kw in tech_kw if kw.lower() in a.lower()]
        if found:
            updated["existing_tech_stack"] = ", ".join(found[:5])

    if "等保" in a and not context.get("compliance_requirements"):
        updated["compliance_requirements"] = "等保"

    return updated


def prioritize_gaps(gaps: list) -> list:
    if not gaps:
        return []
    core = [g for g in _CORE_DIALOG_GAPS if g in gaps]
    rest = [g for g in gaps if g not in _CORE_DIALOG_GAPS]
    return core + rest


def _rotate_default_question(gaps: list, pending_qs: list, turn: int) -> str:
    from core.harness.utils.prompt_loader import _sync_resolve

    if pending_qs and turn <= len(pending_qs):
        return _sync_resolve("fde-dialog-pending-q", question=pending_qs[turn - 1])
    ordered = prioritize_gaps(gaps)
    if ordered:
        g = ordered[(turn - 1) % len(ordered)]
        return _sync_resolve("fde-dialog-gap-q", gap=g)
    return _DIALOG_DEFAULT_MSG


def _pending_questions_from_report(rpt: str) -> list:
    import re as _re_pq
    text = (rpt or "").strip()
    if len(text) < 40 and "待确认" not in text:
        return []
    qs: list = []
    seen = set()

    def _add(raw: str) -> None:
        q = (raw or "").strip().lstrip("-*•、").strip()
        if not q or len(q) < 4:
            return
        q = q.replace("（待确认）", "").replace("(待确认)", "").strip(" ：:")
        if not q:
            return
        if not (q.endswith("？") or q.endswith("?")):
            q = f"请确认：{q}？"
        key = q.lower()
        if key in seen:
            return
        seen.add(key)
        qs.append(q)

    m = _re_pq.search(r"###\s*8[^\n]*\n([\s\S]*?)(?=\n##\s|\Z)", text)
    block = m.group(1) if m else ""
    src = block if block.strip() else text
    for line in src.splitlines():
        s = line.strip()
        if not s:
            continue
        if "待确认" in s:
            _add(s)
        elif s.startswith(("-", "*", "•")) and ("是否" in s or "？" in s or "?" in s):
            _add(s)
        elif block and s.startswith(("-", "*", "•")):
            _add(s)

    if not qs:
        for line in text.splitlines():
            if "待确认" in line:
                _add(line)

    return qs[:8]


async def _extract_pending_questions(session_id: str = "", report_text: str = "") -> list:
    cache_key = (session_id or "") + "::" + str(hash((report_text or "")[:2000]))
    if cache_key in _pending_qs_cache:
        return _pending_qs_cache[cache_key]

    rpt = (report_text or "").strip()
    questions = _pending_questions_from_report(rpt) if rpt else []

    if not questions and session_id:
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            fd = GraphIndex.load("fde-delivery")
            for _nid, node in list(fd._nodes.items()):
                if getattr(node, "class_name", "") == "SessionMeta" and getattr(node, "entity_id", "") == session_id:
                    try:
                        md = json.loads(node.entity_name)
                    except Exception:
                        md = {}
                    stored = md.get("report_text", "") or md.get("pain_points", "")
                    questions = _pending_questions_from_report(stored)
                    break
        except Exception:
            logger.debug("pending SessionMeta lookup failed", exc_info=True)

    if not questions and len(rpt) >= 200:
        try:
            from core.harness.syscalls.llm import sys_llm_generate
            from core.harness.utils.model_injection import best_model_for_purpose
            extract_prompt = (
                f'从以下诊断报告中提取所有需要客户确认的问题，以JSON返回。\n\n'
                f'报告内容:\n{rpt[:8000]}\n\n'
                f'返回格式: {{"questions": ["完整的问题文本1", "完整的问题文本2", ...]}}\n'
                f'把「（待确认）」条目改写成完整问句。仅返回JSON，无其他文字。'
            )
            model_name = best_model_for_purpose(
                "skill_execution",
                messages=[{"role": "user", "content": extract_prompt[:500]}],
            )
            if model_name:
                resp = await sys_llm_generate(
                    None, [{"role": "user", "content": extract_prompt}],
                    model_name=model_name, max_tokens=300, temperature=0.1,
                )
                content = str(getattr(resp, "content", "") or "{}")
                content = content.replace("```json", "").replace("```", "").strip()
                result = json.loads(content)
                raw_qs = result.get("questions", []) if isinstance(result, dict) else []
                questions = [
                    q.strip() for q in raw_qs
                    if isinstance(q, str) and len(q.strip()) > 8
                ][:8]
        except Exception:
            logger.debug("pending LLM extract failed", exc_info=True)

    _pending_qs_cache[cache_key] = questions
    return questions


def _format_dialog_history(history: list, limit: int = 12) -> str:
    if not history:
        return "（无）"
    lines = []
    for h in list(history)[-limit:]:
        if not isinstance(h, dict):
            continue
        role = str(h.get("role") or "").strip()
        content = str(h.get("content") or "").strip()
        if not content:
            continue
        label = "用户" if role == "user" else ("助手" if role == "assistant" else role or "消息")
        lines.append(f"{label}: {content[:400]}")
    return "\n".join(lines) if lines else "（无）"


def _dialog_memory_key(req: ClarifyTurnInput) -> str:
    for cand in (req.dialog_id or "", req.session_id or "", (req.company_name or "").strip()):
        k = str(cand).strip()
        if k:
            return k[:120]
    return ""


def _merge_dialog_memory(key: str, context: dict) -> dict:
    """Fill empty structured slots from prior turns; then persist non-empty values."""
    if not key:
        return context
    prev = _DIALOG_CONTEXT_MEMORY.get(key) or {}
    for k, v in prev.items():
        if k in context and v and not (context.get(k) or "").strip():
            context[k] = v
    _DIALOG_CONTEXT_MEMORY[key] = {
        k: str(v).strip()
        for k, v in context.items()
        if isinstance(v, str) and str(v).strip()
    }
    if len(_DIALOG_CONTEXT_MEMORY) > 200:
        for old in list(_DIALOG_CONTEXT_MEMORY.keys())[:50]:
            _DIALOG_CONTEXT_MEMORY.pop(old, None)
    return context


def _context_ack_prefix(context: dict) -> str:
    name = (context.get("company_name") or "").strip()
    industry = (context.get("industry") or "").strip()
    if name and industry:
        return f"已了解「{name}」（{industry}）。"
    if name:
        return f"已了解「{name}」。"
    if industry:
        return f"已了解行业「{industry}」。"
    return ""


async def run_clarify_turn(req: ClarifyTurnInput) -> Dict[str, Any]:
    """One clarify turn. Returns dialog payload (without FdeStatusResponse wrapper)."""
    from core.apps.skills.registry import _compute_readiness
    from core.apps.fde.service.agent import run_fde_agent_one_shot
    from core.harness.syscalls.llm import sys_llm_generate
    from core.harness.utils.model_injection import best_model_for_purpose
    from core.harness.utils.prompt_loader import _sync_resolve

    mem_key = _dialog_memory_key(req)

    trigger_diagnosis = req.answer.strip() in ("运行诊断", "开始诊断", "run diagnosis")
    if trigger_diagnosis or req.run_diagnosis:
        agent_result = await run_fde_agent_one_shot(
            agent_id="fde_solution_architect",
            skill_filter=["field_assessment"],
            user_message=(
                f"客户名称：{req.company_name}\n行业：{req.industry}\n"
                f"痛点：{req.pain_points}\n团队规模：{req.team_size}\n"
                f"技术栈：{req.existing_tech_stack}\n"
                f"数据源：内部-{req.internal_data_sources} 外部-{req.external_data_sources}\n"
                f"合规要求：{req.compliance_requirements}"
            ),
            extra_context={
                "company_name": req.company_name,
                "industry": req.industry,
                "pain_points": req.pain_points,
                "domain_id": req.domain_id,
            },
            session_id=mem_key or None,
        )
        if agent_result and agent_result.get("success"):
            return {
                "turn": req.turn + 1,
                "diagnosis": agent_result["output"],
                "fully_ready": True,
                "core_ready": True,
                "finished": True,
                "agent_used": agent_result["agent_id"],
                "skills_used": agent_result["skills_used"],
                "gaps": [],
                "readiness": 100,
                "question": "好的，正在根据已收集信息生成诊断报告……",
                "options": [],
                "context": {
                    "company_name": req.company_name,
                    "industry": req.industry,
                    "pain_points": req.pain_points,
                    "team_size": req.team_size,
                    "budget": req.budget,
                    "existing_tech_stack": req.existing_tech_stack,
                    "internal_data_sources": req.internal_data_sources,
                    "external_data_sources": req.external_data_sources,
                    "compliance_requirements": req.compliance_requirements,
                    "poc_timeline": req.poc_timeline,
                    "production_timeline": req.production_timeline,
                    "domain_id": req.domain_id,
                },
            }

    model_name = best_model_for_purpose("skill_execution")
    llm_available = model_name is not None

    turn = req.turn
    context = {
        "company_name": (req.company_name or "").strip(),
        "industry": (req.industry or "").strip(),
        "pain_points": (req.pain_points or "").strip(),
        "team_size": (req.team_size or "").strip(),
        "budget": (req.budget or "").strip(),
        "existing_tech_stack": (req.existing_tech_stack or "").strip(),
        "internal_data_sources": (req.internal_data_sources or "").strip(),
        "external_data_sources": (req.external_data_sources or "").strip(),
        "compliance_requirements": (req.compliance_requirements or "").strip(),
        "poc_timeline": (req.poc_timeline or "").strip(),
        "production_timeline": (req.production_timeline or "").strip(),
        "domain_id": (req.domain_id or "").strip(),
    }
    context = _merge_dialog_memory(mem_key, context)
    history_text = _format_dialog_history(req.history or [])

    if turn > 1 and (req.answer or "").strip():
        kw_extracted = simple_extract_fields(req.answer, context)
        for k, v in kw_extracted.items():
            if v and k in context:
                context[k] = v
        if llm_available:
            try:
                extract_prompt = _sync_resolve(
                    "fde-field-extract",
                    answer=req.answer,
                    context_json=json.dumps(context, ensure_ascii=False),
                    history_text=history_text,
                )
                resp = await sys_llm_generate(
                    None, [{"role": "user", "content": extract_prompt}],
                    model_name=model_name, max_tokens=150, temperature=0.1,
                    session_id=mem_key or None,
                    trace_context={"skip_claude_md": True},
                )
                content_raw = str(getattr(resp, "content", "") or "")
                try:
                    extracted = json.loads(content_raw)
                    for k, v in extracted.items():
                        if v and isinstance(v, str) and k in context:
                            context[k] = str(v).strip()
                except Exception as e:
                    logger.warning("dialog extract JSON parse failed: %s raw=%s", e, content_raw[:120])
            except Exception as e:
                logger.warning("dialog extract LLM call failed: %s", e)
        context = _merge_dialog_memory(mem_key, context)

    score, gaps = _compute_readiness(context)
    gaps = prioritize_gaps(gaps)
    core_ready = score >= 40 and not any(g in gaps for g in ["公司名称", "行业", "痛点"])
    fully_ready = score >= 80

    answer_norm = req.answer.strip().lower() if turn > 1 else ""
    finished = answer_norm in _FINISH_COMMANDS
    user_requested_report = answer_norm in ("生成报告", "生成诊断")

    pending_qs = await _extract_pending_questions(
        session_id=req.session_id or "",
        report_text=req.report_text or "",
    )
    report_followup = bool(pending_qs) or bool((req.report_text or "").strip())

    question, options = "", []
    if user_requested_report and (core_ready or fully_ready or score >= 40):
        # Prefer Agent + field_assessment with stable session; UI still submits skill execute
        agent_result = await run_fde_agent_one_shot(
            agent_id="fde_solution_architect",
            skill_filter=["field_assessment"],
            user_message=(
                f"客户名称：{context.get('company_name')}\n行业：{context.get('industry')}\n"
                f"痛点：{context.get('pain_points')}\n团队规模：{context.get('team_size')}\n"
                f"技术栈：{context.get('existing_tech_stack')}\n域：{context.get('domain_id')}\n"
                f"请基于以上画像生成现场诊断报告。"
            ),
            extra_context=dict(context),
            session_id=mem_key or None,
        )
        finished = True
        question = "好的，正在根据已收集信息生成诊断报告……"
        options = []
        out: Dict[str, Any] = {
            "turn": turn + 1,
            "readiness": score,
            "question": question,
            "options": options,
            "fully_ready": fully_ready,
            "core_ready": core_ready,
            "finished": finished,
            "gaps": gaps,
            "context": context,
        }
        if agent_result and agent_result.get("success"):
            out["diagnosis"] = agent_result["output"]
            out["agent_used"] = agent_result["agent_id"]
            out["skills_used"] = agent_result["skills_used"]
        context = _merge_dialog_memory(mem_key, context)
        out["context"] = context
        return out

    if finished or (fully_ready and not gaps and not pending_qs and not report_followup):
        question = "所有信息已收集完毕。请回复「生成报告」来生成完整的FDE交付手册。"
        options = ["生成报告", "继续补充"]
        finished = True
    elif pending_qs:
        idx = max(0, (turn - 1) % len(pending_qs)) if turn >= 1 else 0
        if turn > len(pending_qs) and req.answer.strip():
            finished = True
            question = "报告待确认项已澄清完毕。可关闭对话框，在报告下方「待确认问题反馈」中汇总后点「更新诊断」。"
            options = ["结束澄清", "继续补充"]
        else:
            q = pending_qs[idx]
            question = f"【报告待确认 {idx + 1}/{len(pending_qs)}】{q}"
            options = ["是", "否", "部分是", "暂不确定"]
    elif report_followup and not pending_qs:
        finished = True
        question = "未从报告中解析到待确认项。可直接在报告下方反馈区补充后点「更新诊断」，或继续补充客户画像。"
        options = ["结束澄清", "继续补充"]
    elif core_ready:
        question = "基础信息已充分，可以生成初步诊断报告。建议继续提供更多信息以获得完整的交付手册。请回复「生成报告」，或继续提供信息。"
        options = ["生成报告", "继续补充"]
    else:
        if not llm_available:
            if gaps:
                g = gaps[(turn - 1) % len(gaps)]
                ack = _context_ack_prefix(context)
                question = f"{ack}请提供「{g}」的相关信息。"
                options = []
            else:
                finished = True
                question = "所有信息已收集完毕。请回复「生成报告」来生成完整的FDE交付手册。"
                options = ["生成报告", "继续补充"]
        else:
            try:
                extra = f"\n诊断报告中的待确认问题: {pending_qs}" if pending_qs else ""
                has_pending = "true" if pending_qs else "false"
                gen_prompt = _sync_resolve(
                    "fde-dialog-generation",
                    context_json=json.dumps(context, ensure_ascii=False),
                    history_text=history_text,
                    gaps=str(gaps),
                    has_pending=has_pending,
                    pending_extra=extra,
                )
                resp = await sys_llm_generate(
                    None, [{"role": "user", "content": gen_prompt}],
                    model_name=model_name, max_tokens=200, temperature=0.3,
                    session_id=mem_key or None,
                    trace_context={"skip_claude_md": True},
                )
                try:
                    result = json.loads(str(getattr(resp, "content", "") or "{}"))
                    if result.get("action") == "generate":
                        finished = True
                        question = "所有信息已收集完毕。请回复「生成报告」来生成完整的FDE交付手册。"
                        options = ["生成报告", "继续补充"]
                    else:
                        question = result.get("question", _rotate_default_question(gaps, pending_qs, turn))
                        options = result.get("options", [])
                except Exception as e:
                    logger.warning("dialog gen JSON parse failed: %s", e)
                    question = _rotate_default_question(gaps, pending_qs, turn)
                    options = []
            except Exception as e:
                logger.warning("dialog gen LLM call failed: %s", e)
                question = _rotate_default_question(gaps, pending_qs, turn)
                options = []

    context = _merge_dialog_memory(mem_key, context)
    return {
        "turn": turn + 1,
        "readiness": score,
        "question": question,
        "options": options,
        "fully_ready": fully_ready,
        "core_ready": core_ready,
        "finished": finished,
        "gaps": gaps,
        "context": context,
    }
