"""Domain prompts — migrated from harness/utils/prompt_loader.py per CLAUDE.md §17."""

from core.harness.utils.prompt_loader import _register as register_prompt

def register_fde_prompts():
    """Register 7 domain-specific prompts for fde module."""
    prompts = {
        "fde-ask-system": """你是AI落地诊断专家。以下是客户画像相关的领域上下文。

${context}

${evidence_block}
请基于以上上下文回答用户问题。回答时优先引用证据溯源中的信息。要求：简洁（300字内），引用具体来源。""",
        "fde-field-extract": """从以下回答中提取客户信息字段，以JSON返回。
回答: "${answer}"
当前已知: ${context_json}
提取规则: company_name(公司名), industry(行业), pain_points(痛点), team_size(人数), budget(预算)
例如用户说"我们南京明图，做政务系统集成的，大概50人" → {"company_name":"南京明图","industry":"政务","team_size":"50"}
仅返回JSON，无其他文字。""",
        "fde-dialog-generation": """你是FDE诊断澄清助手。
客户已知: ${context_json}
缺失维度: ${gaps}
有待确认问题: ${has_pending}${pending_extra}

操作规则(按优先级):
1. 如果有"待确认问题": 逐一追问，完成后再判断信息充分性 → {"action":"ask","question":"...","options":[...]}
2. 如果缺失基础信息(公司名/行业/痛点): 优先追问 → {"action":"ask","question":"...","options":[...]}
3. 基础信息全+无待确认问题 → {"action":"generate"}

要求: 问题有行业上下文。options最多4个，留一个"其他"。
仅返回JSON，无其他文字。""",
        "fde-dialog-gap-q": "请提供「${gap}」的相关信息。",
        "fde-dialog-pending-q": "请确认以下问题：${question}",
        "fde-infer-industry-system": "你是企业行业分类助手。只返回JSON。",
        "fde-infer-industry-user": """根据以下企业信息判断行业分类，选择最匹配的一个：

企业名称：${company_name}
业务描述：${description}

可选行业：manufacturing(制造), installation(安装服务), finance(金融), retail(零售), healthcare(医疗), education(教育), logistics(物流), government(政务), technology(科技), general(通用)

只返回JSON，不要其他文字：{"industry": "industry_key", "confidence": 0.0-1.0, "reason": "一句话理由"}""",
    }
    for pid, content in prompts.items():
        register_prompt(pid, content, category="fde")