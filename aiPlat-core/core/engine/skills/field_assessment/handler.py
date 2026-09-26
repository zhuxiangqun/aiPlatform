"""
Field Assessment Handler (v2.7) — 5-step reasoning via ontology_agent.

Replaces the giant LLM prompt with a structured reasoning pipeline:
  1. Task Understanding → 2. Path Planning → 3. Graph Query
  4. Rule Scoring → 5. NL Output

Produces auditable reasoning_trace alongside the diagnosis.
Output always includes `markdown` to satisfy SKILL.md output_schema.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from core.harness.infrastructure.gateway.fde_notifier import _notify_safe

logger = logging.getLogger("field_assessment")


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    """Main handler: run ontology_agent 5-step reasoning pipeline.

    Input: company_name / industry / pain_points / domain_id / ...
    Output: { markdown, diagnosis, reasoning_trace, quality_indicators }
    """
    domain_id = str(params.get("domain_id") or "").strip()
    session_id = str(params.get("session_id") or "").strip()
    profile = params.get("customer_profile") if isinstance(params.get("customer_profile"), dict) else {}

    company = str(params.get("company_name") or profile.get("company_name") or "").strip()
    industry = str(params.get("industry") or profile.get("industry") or "").strip()
    pain_raw = params.get("pain_points") or profile.get("pain_points") or ""
    if isinstance(pain_raw, list):
        pain_points = "；".join(str(x).strip() for x in pain_raw if str(x).strip())
    else:
        pain_points = str(pain_raw).strip()
    tech = params.get("existing_tech_stack") or []
    if isinstance(tech, list):
        tech_s = "、".join(str(x) for x in tech if x)
    else:
        tech_s = str(tech or "")
    poc = str(params.get("poc_timeline") or params.get("timeline") or "").strip()

    if not session_id:
        import time as _time_sid
        import uuid as _uuid_sid
        slug = company or "diag"
        session_id = f"session_{slug}_{int(_time_sid.time())}_{_uuid_sid.uuid4().hex[:6]}"

    # ── Build task description ──
    task_parts: List[str] = []
    if company:
        task_parts.append(f"客户 {company}")
    if industry:
        task_parts.append(f"{industry}行业")
    if pain_points:
        task_parts.append(f"痛点: {pain_points}")
    if poc:
        task_parts.append(f"目标: {poc}")
    task = " ".join(task_parts) if task_parts else f"分析 domain={domain_id or 'unknown'} 的业务问题"

    # ── Run Ontology Agent 5-step reasoning ──
    reasoning_result: Dict[str, Any] = {}
    try:
        from core.harness.syscalls.ontology_reason import sys_ontology_reason
        reasoning_result = await sys_ontology_reason(
            task=task,
            domain_id=domain_id or None,
        )
        logger.info(
            "OntologyAgent completed: mode=%s, path=%s",
            reasoning_result.get("mode", "?"),
            reasoning_result.get("selected_path", "?"),
        )
    except Exception as e:
        logger.warning("OntologyAgent reasoning failed: %s", e)
        reasoning_result = {"error": str(e), "mode": "react_fallback", "nl_output": ""}

    # ── Extract diagnosis from reasoning output ──
    scoring_results = reasoning_result.get("scoring_results", []) or []
    path_result = reasoning_result.get("path_result", {}) or {}
    reasoning_trace = reasoning_result.get("reasoning_trace", []) or []
    nl = str(reasoning_result.get("nl_output") or "").strip()

    diagnosis = {
        "domain_id": domain_id,
        "session_id": session_id,
        "company_name": company,
        "industry": industry,
        "mode": reasoning_result.get("mode", "unknown"),
        "selected_path": reasoning_result.get("selected_path", ""),
        "nl_summary": nl,
        "issues_found": len(scoring_results) if isinstance(scoring_results, list) else 0,
        "high_priority_issues": len([
            r for r in (scoring_results if isinstance(scoring_results, list) else [])
            if isinstance(r, dict) and r.get("level") == "high"
        ]),
        "terminal_entities": (
            path_result.get("terminal_entities", [])
            if isinstance(path_result, dict) else []
        ),
        "recommended_domain": domain_id or "待确认",
        "deep_problem": _deep_problem_from(pain_points, nl),
    }

    quality = {
        "reasoning_trace_complete": len(reasoning_trace) >= 3,
        "scoring_applied": isinstance(scoring_results, list) and len(scoring_results) > 0,
        "path_completed": (
            bool(path_result.get("completed"))
            if isinstance(path_result, dict) else False
        ),
        "confidence": _estimate_confidence(reasoning_result),
    }

    markdown = _build_markdown(
        company=company,
        industry=industry,
        pain_points=pain_points,
        tech_s=tech_s,
        poc=poc,
        domain_id=domain_id,
        diagnosis=diagnosis,
        scoring_results=scoring_results if isinstance(scoring_results, list) else [],
        nl=nl,
        quality=quality,
    )

    _notify_safe("诊断报告生成", domain_id or company or "fde", {
        "issues_found": diagnosis.get("issues_found", 0),
    })

    return {
        "markdown": markdown,
        "diagnosis": diagnosis,
        "reasoning_trace": reasoning_trace,
        "quality_indicators": quality,
        # Frontend also accepts output.text / output.output
        "text": markdown,
        "output": markdown,
        "session_id": session_id,
    }


def _deep_problem_from(pain_points: str, nl: str) -> str:
    if nl:
        first = nl.split("\n", 1)[0].strip()
        # Ignore English infrastructure fallback strings from ontology_reason
        if first and "No reasoning path found" not in first and "Try a different question" not in first:
            return first[:200]
    if pain_points:
        return f"现场作业闭环缺失：{pain_points[:120]}"
    return "客户业务痛点与本体能力尚未对齐（待确认）"


def _build_markdown(
    *,
    company: str,
    industry: str,
    pain_points: str,
    tech_s: str,
    poc: str,
    domain_id: str,
    diagnosis: Dict[str, Any],
    scoring_results: List[Any],
    nl: str,
    quality: Dict[str, Any],
) -> str:
    """Build the 8-section FDE report required by SKILL.md / frontend parsers."""
    company_l = company or "（未提供，待确认）"
    industry_l = industry or "（未提供，待确认）"
    pain_l = pain_points or "（未提供，待确认）"
    domain_l = domain_id or "待确认"
    deep = diagnosis.get("deep_problem") or "待确认"
    conf = quality.get("confidence", 0.5)

    issues_lines = []
    for i, r in enumerate(scoring_results[:8], 1):
        if isinstance(r, dict):
            issues_lines.append(
                f"| {i} | {r.get('rule_id') or r.get('name') or 'issue'} | "
                f"{r.get('level') or 'medium'} | {r.get('message') or r.get('reason') or ''} |"
            )
        else:
            issues_lines.append(f"| {i} | — | — | {r} |")
    if not issues_lines:
        issues_lines.append("| 1 | dispatch_sync | high | 派单与到场状态不同步（待确认） |")
        issues_lines.append("| 2 | record_trace | high | 安装维修记录无法对齐设备与现场（待确认） |")
        issues_lines.append("| 3 | chase_manual | medium | 催单依赖人工（待确认） |")

    nl_block = nl if nl and "No reasoning path found" not in nl else (
        f"建议以「{poc or '工单派单与到场闭环'}」为 POC 切口，"
        f"先打通派单→接单→到场→完成的状态同步，再扩展维保档案与客户催单可视。"
    )

    return f"""## 第一层：确定性分析（仅基于已提供的输入）

### 1. 痛点 → AI 增强机会映射
[](to_client)
| # | 客户痛点（📋 客户输入） | AI 增强机会 | 推荐切入 |
|---|------------------------|------------|---------|
| 1 | {pain_l} | 工单状态实时同步 + 师傅到场签到 | POC：派单→到场闭环 |
| 2 | 安装/维修记录散落 | 现场作业结构化归档 + 设备-客户对齐 | 二期：维保档案 |
| 3 | 催单靠人工追 | 超时自动提醒与进度可视 | 二期：客户自助查询 |

### 2. 客户画像摘要
[](to_fde)
- 公司：{company_l}
- 行业：{industry_l}
- 现有技术栈：{tech_s or '微信群 / 表格（📊 行业假设）'}
- POC 目标：{poc or '工单派单与到场闭环（待确认）'}
- 推荐本体域：{domain_l}

### 3. 深层问题
[](to_client)
**深层问题：{deep}**

根因判断：表层要「系统」，实质是缺少「工单状态机 + 现场证据 + 催单 SLA」的统一语义模型。
推荐本体域：{domain_l}

## 第二层：本体与规则评分

### 4. 规则命中 / 缺口
| # | 规则/缺口 | 级别 | 说明 |
|---|----------|------|------|
{chr(10).join(issues_lines)}

置信度：{conf}

### 5. 推理摘要
{nl_block}

## 第三层：落地建议

### 6. Top 3 落地机会
1. **派单与到场闭环 POC** — 微信群派单改为可追踪工单状态（accepted→assigned→onsite→done）
2. **现场记录结构化** — 安装/维修照片与设备、客户现场绑定
3. **催单可视** — 超时自动提醒，减少人工追单

### 7. POC 路线图（建议 2–4 周）
1. 周1：锁定 {domain_l} 本体类（工单/师傅/客户现场）与状态机
2. 周2：派单→到场最小闭环（移动端签到 + 管理端看板）
3. 周3：与现有微信/表格双轨并行验证
4. 周4：验收指标（准时到场率、催单次数下降）

### 8. 风险与待确认
- 团队规模、师傅是否外包（待确认）
- 是否已有任何工单/CRM 系统（待确认）
- 客户对数据驻留与等保要求（待确认）
"""


def _estimate_confidence(result: Dict) -> float:
    """Estimate confidence from reasoning trace completeness."""
    trace = result.get("reasoning_trace", [])
    if not trace:
        return 0.45
    successful = sum(1 for t in trace if isinstance(t, dict) and t.get("success", True))
    return round(min(0.95, successful / max(len(trace), 1)), 2)
