"""Markdown PRD → dict (pipeline materialize; kernel-owned, no platform import).

Handles the standard pm_agent layout (## 项目名称 / ### FR-00N / ## 决策).
Builder keeps a richer parser for chat edge-cases; both must stay compatible.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List


def parse_prd_markdown(reply: str) -> Dict[str, Any]:
    """Parse structured Markdown PRD into a dict."""
    text = str(reply or "").replace("<!-- PRD_READY -->", "").strip()
    named = list(re.finditer(r"(?m)^##\s*项目名称", text))
    if named:
        text = text[named[-1].start() :].strip()

    prd: Dict[str, Any] = {}
    m_title = re.search(r"(?m)^##\s*项目名称[：:]\s*(.+)$", text)
    if m_title:
        prd["title"] = m_title.group(1).strip()

    sections = _split_sections(text)
    bg = (sections.get("项目背景") or sections.get("背景") or "").strip()
    if bg:
        prd["description"] = bg

    func = ""
    for key, body in sections.items():
        if "功能需求" in key:
            func = body
            break
    frs = _parse_frs(func)
    if frs:
        prd["functional_requirements"] = frs

    stories_body = ""
    for key, body in sections.items():
        if "用户故事" in key or "User Stor" in key:
            stories_body = body
            break
    us = _parse_user_stories(stories_body)
    if us:
        prd["user_stories"] = us

    decisions_body = (
        sections.get("决策")
        or sections.get("产品决策")
        or sections.get("Decisions")
        or ""
    ).strip()
    if decisions_body:
        dec = _parse_decisions(decisions_body)
        if dec:
            prd["decisions"] = dec

    oq_body = (
        sections.get("待确认问题")
        or sections.get("开放问题")
        or sections.get("Open Questions")
        or ""
    ).strip()
    oqs: List[str] = []
    for line in oq_body.splitlines():
        lm = re.match(r"^\s*(?:\d+\.|[-*])\s*(.+)$", line)
        if lm:
            t = lm.group(1).strip()
            if t not in ("（无）", "(无)", "无", "N/A", "None"):
                oqs.append(t)
    prd["open_questions"] = oqs

    scope = (sections.get("范围") or sections.get("Scope") or "").strip()
    if scope:
        prd["scope"] = scope
        try:
            from core.harness.execution.prd_quality_gate import normalize_constraints

            prd = normalize_constraints(prd)
        except Exception:
            pass  # noqa: cleanup-best-effort

    return prd


def _split_sections(clean: str) -> Dict[str, str]:
    known = re.compile(
        r"^(项目背景|背景|功能需求|核心功能需求|用户故事|决策|产品决策|"
        r"待确认问题|开放问题|范围|Scope|Background|Decisions|Open Questions)$"
    )
    sections: Dict[str, str] = {}
    current = ""
    for line in (clean or "").split("\n"):
        m = re.match(r"^(#{2,3})\s+(.+)$", line)
        if m:
            raw = m.group(2).strip()
            bare = re.sub(r"[：:].*$", "", raw).strip()
            if re.match(r"^项目名称\b", raw):
                current = ""
                continue
            if known.match(bare) or "功能需求" in bare or "用户故事" in bare:
                current = bare
                sections[current] = ""
                continue
        if current:
            sections[current] += line + "\n"
    return sections


def _clean_decision_value(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return s
    m = re.search(r"`([a-zA-Z][\w]*)`", s)
    if m:
        return m.group(1)
    s = s.strip("`").strip()
    if re.search(r"[≤≥<>×x\d\u4e00-\u9fff/]", s) and not re.match(
        r"^[a-z][a-z0-9_]*$", s
    ):
        return re.split(r"[（(]", s, maxsplit=1)[0].strip() or s
    m = re.match(r"^([a-zA-Z][\w]*)", s)
    if m:
        rest = s[m.end() :].lstrip()
        if not rest or rest[0] in "（(—–-：:":
            return m.group(1)
        if re.search(r"[≤≥<>×\d\u4e00-\u9fff]", rest):
            return s
        return m.group(1)
    return s


def _parse_decisions(body: str) -> Dict[str, Any]:
    dec: Dict[str, Any] = {}
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(
            r"^\s*[-*]?\s*`?([a-zA-Z_][\w]*)`?\s*[：:=]\s*(.+?)\s*$",
            s,
        )
        if m:
            dec[m.group(1).strip()] = _clean_decision_value(m.group(2))
    return dec


def _parse_frs(func_section: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not (func_section or "").strip():
        return items
    starts = list(
        re.finditer(r"(?m)^###\s*(FR[-\s]?\d+)\s*[:：]\s*(.+)$", func_section)
    )
    if not starts:
        return items
    for i, m in enumerate(starts):
        fr_id = re.sub(r"\s+", "", m.group(1).upper().replace(" ", "-"))
        if not fr_id.startswith("FR-"):
            fr_id = fr_id.replace("FR", "FR-", 1)
        name = (m.group(2) or "").strip()
        end = starts[i + 1].start() if i + 1 < len(starts) else len(func_section)
        body = func_section[m.end() : end]
        desc_m = re.search(r"(?:\*\*)?(?:描述|功能描述)(?:\*\*)?[：:]\s*(.+)", body)
        pri_m = re.search(r"(?:\*\*)?优先级(?:\*\*)?[：:]\s*(\S+)", body)
        acs = re.findall(r"AC\d+[：:]\s*(.+)", body)
        if not acs:
            ac_block = re.search(
                r"验收标准[：:]?\s*\n((?:\s*[-*]\s+.+\n?)+)", body
            )
            if ac_block:
                acs = re.findall(r"[-*]\s+(.+)", ac_block.group(1))
        fr: Dict[str, Any] = {
            "id": fr_id,
            "name": name,
            "description": desc_m.group(1).strip() if desc_m else "",
            "acceptance_criteria": [a.strip() for a in acs],
        }
        if pri_m:
            fr["priority"] = pri_m.group(1).strip()
        items.append(fr)
    return items


def _parse_user_stories(body: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not (body or "").strip():
        return items
    for us_match in re.finditer(
        r"###\s*(.+?)\n(.*?)(?=\n###|\n##|\Z)", body, re.DOTALL
    ):
        head = us_match.group(1).strip()
        us_body = us_match.group(2)
        us_id, us_text = head, head
        if ":" in head:
            us_id, us_text = head.split(":", 1)
        elif "：" in head:
            us_id, us_text = head.split("：", 1)
        us_id, us_text = us_id.strip(), us_text.strip()
        rel = re.search(r"(?:\*\*)?关联功能(?:\*\*)?[：:]\s*(.+)", us_body)
        if not rel:
            rel = re.search(r"(?:\*\*)?关联需求(?:\*\*)?[：:]\s*(.+)", us_body)
        pri = re.search(r"(?:\*\*)?优先级(?:\*\*)?[：:]\s*(\S+)", us_body)
        story_m = re.search(r"(?:\*\*)?故事(?:\*\*)?[：:]\s*(.+)", us_body)
        story: Dict[str, Any] = {
            "id": us_id,
            "story": (story_m.group(1).strip() if story_m else us_text),
            "description": (story_m.group(1).strip() if story_m else us_text),
        }
        if rel:
            story["related_fr"] = [
                p.strip()
                for p in re.split(r"[,，、\s]+", rel.group(1))
                if p.strip()
            ]
        if pri:
            story["priority"] = pri.group(1).strip()
        items.append(story)
    return items
