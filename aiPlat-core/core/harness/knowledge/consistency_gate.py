"""
Cross-Stage Consistency Gate — detect contradictions between FDE diagnosis sections.

Scans a generated diagnosis report for common failure patterns:
  1. Data maturity (§2) is low but §6-§7 recommends high-ML solutions
  2. Deployment (§3) is on-premise but §6 recommends SaaS
  3. Pain point count (§1) is low but §5 recommends large team
  4. Compliance (§4) requires 信创 but §6 recommends non-domestic components

callers: field-assessment skill post-generation check (registry.py)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


def check_cross_stage_consistency(report_text: str) -> List[Dict[str, Any]]:
    """Scan a diagnosis report for cross-section contradictions.

    Returns a list of warnings, each with:
        rule, section, message, severity (warning/error)
    """
    warnings: List[Dict[str, Any]] = []
    if not report_text or not isinstance(report_text, str):
        return warnings

    # ── Extract section content ranges ──
    sections = _extract_sections(report_text)

    # ── Rule 1: Low data maturity + high-ML recommendation ──
    warnings.extend(_check_data_vs_model(sections))

    # ── Rule 2: On-premise deployment + SaaS recommendation ──
    warnings.extend(_check_deploy_vs_saas(sections))

    # ── Rule 3: Few pain points + large team ──
    warnings.extend(_check_scope_vs_team(sections))

    # ── Rule 4: 信创 requirement + non-domestic components ──
    warnings.extend(_check_xinchuang_vs_components(sections))

    # ── Rule 5: POC timeline too aggressive for scope ──
    warnings.extend(_check_poc_vs_scope(sections))

    return warnings


def _extract_sections(text: str) -> Dict[str, str]:
    """Extract rough section boundaries from markdown report."""
    sections: Dict[str, str] = {}
    pattern = re.compile(r'^###?\s+(\d+[.\d]*)\s+(.+)$', re.MULTILINE)
    matches = list(pattern.finditer(text))

    for i, m in enumerate(matches):
        sec_id = m.group(1)
        sec_title = m.group(2)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        key = f"{sec_id} {sec_title}"
        sections[key] = text[start:end]

    return sections


def _join_section_range(sections: Dict[str, str], *prefixes: str) -> str:
    """Join content from multiple section prefixes."""
    parts = []
    for key, content in sections.items():
        for prefix in prefixes:
            if key.startswith(prefix):
                parts.append(content)
                break
    return "\n".join(parts)


# ── Individual rule checks ──────────────────────────────────────────

def _check_data_vs_model(sections: Dict[str, str]) -> List[Dict[str, Any]]:
    """§2 data maturity low → §6 high-ML recommendation."""
    warnings = []
    data_text = _join_section_range(sections, "2.", "2 ")
    rec_text = _join_section_range(sections, "6.", "6 ", "5.", "5 ")

    data_low = bool(re.search(
        r'(成熟度等级.*?(低|1|2|无|缺失|未采集|纸))|(数据.*?(缺失|不足|质量差|不完善))',
        data_text
    ))
    rec_high = bool(re.search(
        r'(大模型|深度学习|LLM|transformer|bert|gpt|fine.?tun|预训练|neural|神经网络)',
        rec_text, re.IGNORECASE
    ))

    if data_low and rec_high:
        warnings.append({
            "rule": "data_vs_model",
            "section": "§2 ↔ §6",
            "message": "§2 数据成熟度偏低，但 §6 推荐了需大量标注数据的高阶ML方案。建议：增加数据采集阶段或替换为规则/小样本方案。",
            "severity": "error",
        })
    return warnings


def _check_deploy_vs_saas(sections: Dict[str, str]) -> List[Dict[str, Any]]:
    """§3 on-premise → §6 SaaS recommendation."""
    warnings = []
    deploy_text = _join_section_range(sections, "3.", "3 ")
    rec_text = _join_section_range(sections, "6.", "6 ", "7.", "7 ")

    on_prem = bool(re.search(
        r'(私有化|自建|本地部署|on.?prem|内网|政务云|专用机房|离线)',
        deploy_text, re.IGNORECASE
    ))
    saas_rec = bool(re.search(
        r'(SaaS|云端部署|公有云|阿里云官网|腾讯云官网|AWS|Azure|云服务|API调用)',
        rec_text, re.IGNORECASE
    ))

    if on_prem and saas_rec:
        warnings.append({
            "rule": "deploy_vs_saas",
            "section": "§3 ↔ §6/§7",
            "message": "§3 要求私有化/本地部署，但 §6/§7 推荐了SaaS/公有云方案。建议：替换为信创私有化方案或混合云架构。",
            "severity": "warning",
        })
    return warnings


def _check_scope_vs_team(sections: Dict[str, str]) -> List[Dict[str, Any]]:
    """§1 few pain points → §5 large team."""
    warnings = []
    scope_text = _join_section_range(sections, "1.", "1 ")
    team_text = _join_section_range(sections, "5.", "5 ")  # top 3 recs often in §5

    # Count pain point rows (markdown table rows with non-empty cells)
    pain_rows = len(re.findall(r'^\|.*\|.*\|.*\|.*\|.*\|', scope_text, re.MULTILINE))
    large_team = bool(re.search(
        r'(\d{2,}\s*人|团队.*(8|9|\d{2})|大型团队|多人协作)',
        team_text
    ))

    if pain_rows <= 2 and large_team:
        warnings.append({
            "rule": "scope_vs_team",
            "section": "§1 ↔ §5",
            "message": f"§1 仅识别 {pain_rows} 个痛点，但 §5 推荐较大团队规模。建议：缩小POC团队或补充更多痛点分析。",
            "severity": "warning",
        })
    return warnings


def _check_xinchuang_vs_components(sections: Dict[str, str]) -> List[Dict[str, Any]]:
    """§4 信创 requirement → §6 non-domestic components."""
    warnings = []
    compliance_text = _join_section_range(sections, "4.", "4 ")
    rec_text = _join_section_range(sections, "6.", "6 ", "6.1", "6.2")

    xinchuang = bool(re.search(
        r'信创|国产化|自主可控|国产替代|安全可控',
        compliance_text
    ))
    non_domestic = bool(re.search(
        r'(NVIDIA|nvidia|CUDA|cuda|OpenAI|openai|GPT\b|Anthropic|Google Cloud|AWS)',
        rec_text
    ))

    if xinchuang and non_domestic:
        warnings.append({
            "rule": "xinchuang_vs_components",
            "section": "§4 ↔ §6",
            "message": "§4 要求信创/国产化，但 §6 推荐了非国产组件。建议：替换为国产替代方案（昇腾/寒武纪/达梦/人大金仓等）。",
            "severity": "error",
        })
    return warnings


def _check_poc_vs_scope(sections: Dict[str, str]) -> List[Dict[str, Any]]:
    """§7 POC timeline ~1 month but scope is large."""
    warnings = []
    scope_text = _join_section_range(sections, "1.", "1 ")
    poc_text = _join_section_range(sections, "7.", "7 ")

    pain_count = len([r for r in scope_text.split("\n") if r.strip().startswith("|") and "|" in r[1:]])
    rapid_poc = bool(re.search(
        r'(1\s*个?月|3[0 ]天|POC.*1.*月|试点.*1.*月)',
        poc_text
    ))

    if pain_count >= 5 and rapid_poc:
        warnings.append({
            "rule": "poc_vs_scope",
            "section": "§1 ↔ §7",
            "message": f"§1 识别了 {pain_count} 个痛点，但 §7 POC 周期仅 1 个月。建议：POC 聚焦1-2个核心痛点或延长至3个月。",
            "severity": "warning",
        })
    return warnings
