#!/usr/bin/env python3
"""Build aiPlat product PPTs (honest current-state).

1) Agent  — mirrors StarAgent 2.0 chapter skeleton
2) Ontology — mirrors 星邺本体平台介绍 v1.0
3) Combo — mirrors 星邺汇捷-本体+超级智能体分享0622

Style mirrors aiPlat-本体平台产品介绍-现状版.pptx.
Content is aiPlat code truth; never copy Xingye marketing metrics.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Pt

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "product-pptx"
OUT_AGENT = OUT_DIR / "aiPlat-Agent智能体平台产品介绍-现状版.pptx"
OUT_ONTO = OUT_DIR / "aiPlat-本体平台产品介绍-对标星邺结构-现状版.pptx"
OUT_COMBO = OUT_DIR / "aiPlat-本体+Agent合册产品介绍-现状版.pptx"

# Slide size ≈ widescreen 13.33" × 7.5"
W, H = 12191695, 6858000
MARGIN = 384048

C_BG = RGBColor(0x0F, 0x14, 0x1A)
C_CARD = RGBColor(0x1A, 0x22, 0x2C)
C_CARD2 = RGBColor(0x22, 0x2C, 0x38)
C_ACCENT = RGBColor(0x3B, 0x82, 0xF6)
C_ACCENT2 = RGBColor(0x14, 0xB8, 0xA6)
C_WARN = RGBColor(0xF5, 0x9E, 0x0B)
C_TEXT = RGBColor(0xE5, 0xE7, 0xEB)
C_MUTED = RGBColor(0x9C, 0xA3, 0xAF)
C_FOOT = RGBColor(0x6B, 0x72, 0x80)
C_LINE = RGBColor(0x2A, 0x34, 0x40)
C_TOP = RGBColor(0x3B, 0x82, 0xF6)
C_OK = RGBColor(0x22, 0xC5, 0x5E)
C_PARTIAL = RGBColor(0xF5, 0x9E, 0x0B)
C_MISS = RGBColor(0xF8, 0x71, 0x71)


def matrix_page(
    prs,
    *,
    section: str,
    title: str,
    subtitle: str,
    rows: list,
    series: str,
    total: int,
    page: int,
):
    """Traffic-light status matrix. rows: (capability, status, note)
    status: done | partial | missing
    """
    slide = blank_slide(prs)
    _section_label(slide, section)
    _title(slide, title)
    _subtitle(slide, subtitle)

    # legend
    legend = [("已做 / 长板", C_OK), ("部分", C_PARTIAL), ("未做", C_MISS)]
    lx = MARGIN
    for lab, col in legend:
        dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, lx, 1280000, 140000, 140000)
        _fill(dot, col)
        _textbox(slide, lx + 180000, 1260000, 1400000, 200000, lab, size=11, color=C_MUTED)
        lx += 2000000

    # header bar
    top0 = 1550000
    hdr = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, MARGIN, top0, W - 2 * MARGIN, 320000)
    _fill(hdr, C_CARD2)
    _textbox(slide, MARGIN + 120000, top0 + 60000, 2800000, 220000, "能力项", size=12, bold=True, color=C_WHITE)
    _textbox(slide, MARGIN + 3000000, top0 + 60000, 1400000, 220000, "状态", size=12, bold=True, color=C_WHITE)
    _textbox(slide, MARGIN + 4600000, top0 + 60000, 6400000, 220000, "一句话边界", size=12, bold=True, color=C_WHITE)

    status_label = {"done": "已做", "partial": "部分", "missing": "未做"}
    status_color = {"done": C_OK, "partial": C_PARTIAL, "missing": C_MISS}

    usable = (H - 420000) - (top0 + 320000)
    row_h = min(420000, max(280000, usable // max(1, len(rows))))
    for i, (name, status, note) in enumerate(rows):
        y = top0 + 320000 + i * row_h
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, MARGIN, y, W - 2 * MARGIN, row_h - 40000)
        _fill(bg, C_CARD if i % 2 == 0 else C_CARD2)
        dot = slide.shapes.add_shape(MSO_SHAPE.OVAL, MARGIN + 3000000, y + 120000, 160000, 160000)
        _fill(dot, status_color.get(status, C_MUTED))
        _textbox(slide, MARGIN + 120000, y + 80000, 2800000, 280000, name, size=13, bold=True, color=C_WHITE)
        _textbox(
            slide,
            MARGIN + 3220000,
            y + 80000,
            1200000,
            280000,
            status_label.get(status, status),
            size=13,
            bold=True,
            color=status_color.get(status, C_MUTED),
        )
        _textbox(slide, MARGIN + 4600000, y + 80000, 6400000, 280000, note, size=12, color=C_MUTED)

    _footer(slide, page, total, series)


C_WHITE = RGBColor(0xFF, 0xFF, 0xFF)


def _set_run(p, text, size=14, bold=False, color=C_TEXT, font="Microsoft YaHei"):
    p.clear()
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font
    return run


def _fill(shape, color):
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def _textbox(slide, left, top, width, height, text, *, size=14, bold=False, color=C_TEXT, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    _set_run(p, text, size=size, bold=bold, color=color)
    return box


def _card(slide, left, top, width, height, title, body, *, title_size=15, body_size=12):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    _fill(shape, C_CARD)
    shape.adjustments[0] = 0.08
    _textbox(slide, left + 120000, top + 100000, width - 240000, 320000, title, size=title_size, bold=True, color=C_WHITE)
    _textbox(slide, left + 120000, top + 420000, width - 240000, height - 560000, body, size=body_size, color=C_MUTED)


def _footer(slide, page: int, total: int, series: str):
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, H - 347472, W, 347472)
    _fill(bar, RGBColor(0x12, 0x18, 0x20))
    _textbox(slide, MARGIN, H - 310000, 8200000, 256032, f"现状说明  ·  不是愿景承诺  ·  {series}", size=11, color=C_FOOT)
    _textbox(slide, W - 1800000, H - 310000, 1500000, 256032, f"{page} / {total}", size=11, color=C_FOOT, align=PP_ALIGN.RIGHT)


def _top_bar(slide):
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, 73152)
    _fill(bar, C_TOP)


def _bg(slide):
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H)
    _fill(bg, C_BG)


def _section_label(slide, label: str):
    _textbox(slide, MARGIN, 164592, 7315200, 256032, label, size=12, bold=True, color=C_ACCENT2)


def _title(slide, text: str):
    _textbox(slide, MARGIN, 384048, 11338560, 438912, text, size=26, bold=True, color=C_WHITE)


def _subtitle(slide, text: str, top=932688):
    _textbox(slide, MARGIN, top, 11338560, 320040, text, size=14, color=C_MUTED)


def new_deck() -> Presentation:
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H
    return prs


def blank_slide(prs: Presentation):
    layout = prs.slide_layouts[6]  # blank
    slide = prs.slides.add_slide(layout)
    _bg(slide)
    _top_bar(slide)
    return slide


def cover(prs, *, brand: str, title: str, lines: list[str], note: str, series: str, total: int):
    slide = blank_slide(prs)
    accent = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, 164592, H)
    _fill(accent, C_ACCENT)
    _textbox(slide, 640080, 1234440, 10058400, 329184, "现状说明  ·  不是数字员工组织", size=14, color=C_MUTED)
    _textbox(slide, 640080, 1691640, 10058400, 640080, brand, size=44, bold=True, color=C_WHITE)
    _textbox(slide, 640080, 2377440, 10058400, 548640, title, size=28, bold=True, color=C_ACCENT2)
    body = "\n".join(lines)
    _textbox(slide, 640080, 3200400, 9601200, 1400000, body, size=16, color=C_TEXT)
    _textbox(slide, 640080, 5852160, 10058400, 365760, note, size=12, color=C_FOOT)
    _footer(slide, 1, total, series)


def toc(prs, items: list, series: str, total: int, page: int, *, subtitle: Optional[str] = None):
    slide = blank_slide(prs)
    _section_label(slide, "CONTENTS")
    _title(slide, "目录")
    _subtitle(
        slide,
        subtitle
        or "章节按企业级平台通用架构分层；正文只写 aiPlat 已落地事实",
    )
    cols = 2
    per = (len(items) + cols - 1) // cols
    for i, (num, name) in enumerate(items):
        col = i // per
        row = i % per
        left = MARGIN + col * 5600000
        top = 1500000 + row * 520000
        _textbox(slide, left, top, 800000, 400000, num, size=18, bold=True, color=C_ACCENT)
        _textbox(slide, left + 900000, top, 4200000, 400000, name, size=16, color=C_TEXT)
    _footer(slide, page, total, series)


def part(prs, part_no: str, title: str, sub: str, series: str, total: int, page: int):
    slide = blank_slide(prs)
    _textbox(slide, MARGIN, 2200000, 11338560, 500000, part_no, size=18, bold=True, color=C_ACCENT2)
    _textbox(slide, MARGIN, 2800000, 11338560, 700000, title, size=36, bold=True, color=C_WHITE)
    _textbox(slide, MARGIN, 3600000, 11338560, 500000, sub, size=16, color=C_MUTED)
    _footer(slide, page, total, series)


def cards_page(
    prs,
    *,
    section: str,
    title: str,
    subtitle: str,
    cards: list[tuple[str, str]],
    series: str,
    total: int,
    page: int,
    cols: int = 3,
):
    slide = blank_slide(prs)
    _section_label(slide, section)
    _title(slide, title)
    _subtitle(slide, subtitle)
    n = len(cards)
    rows = (n + cols - 1) // cols
    gap = 180000
    usable_w = W - 2 * MARGIN
    usable_h = H - 1500000 - 450000
    cw = (usable_w - gap * (cols - 1)) // cols
    ch = (usable_h - gap * (rows - 1)) // rows
    for i, (t, b) in enumerate(cards):
        r, c = divmod(i, cols)
        if rows == 1:
            r, c = 0, i
            cw = (usable_w - gap * (n - 1)) // n
            ch = min(ch, 2200000)
        left = MARGIN + c * (cw + gap)
        top = 1400000 + r * (ch + gap)
        _card(slide, left, top, cw, ch, t, b)
    _footer(slide, page, total, series)


def bullets_page(
    prs,
    *,
    section: str,
    title: str,
    subtitle: str,
    left_title: str,
    left_items: list[str],
    right_title: str,
    right_items: list[str],
    series: str,
    total: int,
    page: int,
):
    slide = blank_slide(prs)
    _section_label(slide, section)
    _title(slide, title)
    _subtitle(slide, subtitle)
    half = (W - 2 * MARGIN - 180000) // 2
    for col, (ht, items) in enumerate(((left_title, left_items), (right_title, right_items))):
        left = MARGIN + col * (half + 180000)
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, 1400000, half, 4600000)
        _fill(shape, C_CARD)
        shape.adjustments[0] = 0.06
        _textbox(slide, left + 140000, 1520000, half - 280000, 360000, ht, size=16, bold=True, color=C_WHITE)
        y = 2000000
        for it in items:
            _textbox(slide, left + 140000, y, half - 280000, 520000, "·  " + it, size=13, color=C_MUTED)
            y += 520000
    _footer(slide, page, total, series)


def closing(prs, *, line: str, points: list[str], series: str, total: int, page: int):
    slide = blank_slide(prs)
    accent = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, 164592, H)
    _fill(accent, C_ACCENT)
    _textbox(slide, 640080, 640080, 10058400, 365760, "对外只说这一句", size=14, color=C_MUTED)
    _textbox(slide, 640080, 1280160, 10789920, 1600000, line, size=20, bold=True, color=C_WHITE)
    y = 3200400
    for p in points:
        _textbox(slide, 640080, y, 10789920, 450000, p, size=14, color=C_MUTED)
        y += 500000
    _textbox(slide, 640080, 5760720, 10058400, 365760, "对内对齐、销售现状页、新员工入职用本页。愿景图不当现状。", size=12, color=C_FOOT)
    _footer(slide, page, total, series)


# ─────────────────────────── Agent deck ───────────────────────────

def build_agent() -> Path:
    series = "aiPlat Agent"
    total = 18
    prs = new_deck()

    cover(
        prs,
        brand="aiPlat",
        title="Agent 智能体平台 · 现状版",
        lines=[
            "控制台驱动的智能体装配、执行与治理。",
            "同一执行核：ReAct / Pipeline / Skill / Syscall。",
            "人批闸门在中心。舰队默认拒绝。客户尚未签收数字员工组织。",
        ],
        note="章节对标 StarAgent 2.0；结论只写仓库已落地能力，不搬对方宣传指标。",
        series=series,
        total=total,
    )
    toc(
        prs,
        [
            ("01", "愿景与定位"),
            ("02", "问题与一句话定位"),
            ("03", "能力面 · 全生命周期"),
            ("04", "执行核与记忆"),
            ("05", "应用工厂"),
            ("06", "治理与架构"),
            ("07", "场景与触达"),
            ("08", "对外收口句"),
        ],
        series,
        total,
        2,
    )
    part(prs, "PART I", "愿景与定位", "为什么配置、执行、治理要放在同一个控制台里", series, total, 3)

    cards_page(
        prs,
        section="02  问题",
        title="从「能聊」到「能用、能管、能落地」",
        subtitle="企业部署智能体时反复撞见的四类问题 · aiPlat 的答法",
        cards=[
            ("能聊不能用", "没有受控工具与动作硬门，对话停在建议。aiPlat：Skill / Syscall / Action 合同，越界否决可审计。"),
            ("能用不能管", "提示词散落、权限叠床架屋。aiPlat：PolicyGate 单次判定；管理端五组菜单按任务流收口。"),
            ("能管不能复现", "一次成功复制不了。aiPlat：Pipeline 阶段配置 + 编码宪法默认注入；运行可回看。"),
            ("能复现不能守界", "自动写规则、自动上架技能。aiPlat：提案不是规则；能力市场是注册库，人批后才上架。"),
        ],
        series=series,
        total=total,
        page=4,
        cols=2,
    )

    cards_page(
        prs,
        section="03  定位",
        title="配置治理 + 受控执行，一体化控制台",
        subtitle="不是群聊里的数字员工团队。是人在控制台里驱动受控执行。",
        cards=[
            ("管理控制台", "五组菜单：仪表盘、知识双轨、应用工厂、诊断治理、平台设置。组织试点与价值看板在仪表盘。"),
            ("执行核", "ReActLoop · PipelineEngine · Skill 执行真实性（handler/prompt 显式声明）。同一 syscall 面。"),
            ("人批闸门", "抽取草稿、仲裁单、提案、HITL、飞书确认、岗位开跑。批准不自动写活本体。"),
        ],
        series=series,
        total=total,
        page=5,
        cols=3,
    )

    part(prs, "PART II", "能力与体验", "装配 · 对话 · 编排 · 触达 · 沉淀 —— 同一执行核", series, total, 6)

    cards_page(
        prs,
        section="04  能力面",
        title="六大产品面，覆盖 Agent 生命周期",
        subtitle="对标 StarAgent「六大产品面」结构；名称按 aiPlat 实装",
        cards=[
            ("1  装配", "AGENT.md + required_skills；Builder / 应用工厂生成应用；注册到消息总线身份层。"),
            ("2  对话与执行", "ReAct Reason→Act→Observe；材料问答 CRAG；跳过宪法须显式声明。"),
            ("3  编排", "Pipeline 阶段配置驱动；handoff / skill_routing；禁止无门控 peer execute。"),
            ("4  工具扩展", "Skill（handler/prompt）+ MCP 接入；Syscall 是最后手段（成本阶梯）。"),
            ("5  记忆与上下文", "Working / Episodic / Semantic / TaskSkill；ContextBus 分层注入。"),
            ("6  沉淀", "案例 overlay、TaskSkill 晶体化、提案入队；默认不自动 apply、不自动上架。"),
        ],
        series=series,
        total=total,
        page=7,
        cols=3,
    )

    bullets_page(
        prs,
        section="05  执行核",
        title="核心体验：可追踪的执行，不是黑盒聊天",
        subtitle="业务与技术共享同一条运行记录",
        left_title="已落地",
        left_items=[
            "ReActLoop + Hook / 压缩 / 记忆",
            "Pipeline 阶段失败策略可配置",
            "Skill execution_type 强制声明",
            "运行事件、诊断对比、审查（autoreview）",
            "OrgRun 五步回放：缺步写「未发生」",
        ],
        right_title="明确不做 / 未宣称",
        right_items=[
            "不是群聊为中心的数字员工团队",
            "舰队多 Agent 默认拒绝；放行≠已产品化 spawn",
            "不说「感知到执行」已自主闭环",
            "不说决策准确率已到某百分比",
            "不说出错已自动变成规则或技能",
        ],
        series=series,
        total=total,
        page=8,
    )

    cards_page(
        prs,
        section="06  应用工厂",
        title="AI 应用工厂：制造者，不是岗位员工",
        subtitle="工厂生成应用生命周期在；它不是 7×24 研发数字员工",
        cards=[
            ("项目与流水线", "Builder 项目、Pipeline 观察与启动、产物链接。生成物走平台既有路径，不平行造引擎。"),
            ("Agent / Skill / 工具", "工作区能力注册；Skill 市场是注册库。H5 只组装已有草稿，人批后才登记，不写 SKILL.md。"),
            ("评测与守护", "Eval 门、conformance、运行时治理 sidecar；质量总线横切，不各自一套评分。"),
        ],
        series=series,
        total=total,
        page=9,
        cols=3,
    )

    part(prs, "PART III", "治理与架构", "管得住 · 审得了 · 扩得开 —— 且不拆闸门", series, total, 10)

    cards_page(
        prs,
        section="07  治理",
        title="企业级治理：管得住，审得了，扩得开",
        subtitle="管理台已有的关键门禁 · 不是口号清单",
        cards=[
            ("PolicyGate 单次权限", "同一请求只判一次。身份来自请求头角色；请求体自报审批人无效。"),
            ("编码宪法", "karpathy_v1 全局默认注入。Skill 可声明豁免，默认强制。"),
            ("本体与配置二分", "Evolve=配置键观测窗；本体=提案+分级审批。活 YAML 直写拒绝。"),
            ("审计与回放", "ActionStore / 运行事件 / Org 回放 / 证据包导出。用量只记账，不计费。"),
            ("待批提效（H1–H4）", "inbox + 快照只读；提案可见 Diff。试点页可扫沙箱队列；live 拒绝。沙箱/live 通过率只读对照，不是灰度。批准与写活本体仍须人批。"),
            ("安全边界", "admin MFA、SSRF/路径守卫、架构守卫 CI。接口白名单默认关。"),
        ],
        series=series,
        total=total,
        page=11,
        cols=3,
    )

    cards_page(
        prs,
        section="08  架构",
        title="分层架构：管理端 → 平台 → 内核 → 基础设施",
        subtitle="导入方向单向。平台经 CoreFacade 访问 core。",
        cards=[
            ("管理端", "React 控制台。五组菜单。组织试点 /org/pilot。"),
            ("平台 apps", "org / fde / builder / kb / governance。HTTP 在 platform，业务逻辑在 core/apps。"),
            ("Harness 内核", "执行、记忆、知识、syscall、PolicyGate。禁止硬编码业务角色名。"),
            ("Infra", "模型目录唯一权威。LLM/Embedding/Rerank/Audio 适配器。"),
        ],
        series=series,
        total=total,
        page=12,
        cols=2,
    )

    part(prs, "PART IV", "功能与场景", "能讲清楚的落地竖切；不讲未测量的准确率", series, total, 13)

    cards_page(
        prs,
        section="09  场景",
        title="四条可讲的场景竖切",
        subtitle="有的写有；没有的写没有。不搬星邺效果数字。",
        cards=[
            ("材料问答", "Wiki / 向量检索 + CRAG 回退。知识库不替代本体拍板。"),
            ("FDE 交付", "诊断→证据→交付流水线→HITL→Evolve 观测窗。工作台多 Tab 已接线。"),
            ("it-ops 组织试点", "飞书确认后开跑、周报三 KPI、沙箱可扫队列、基线可填写、证据包导出。不是签收。"),
            ("应用工厂生成", "生成 Agent 走 Pipeline + handoff；消息总线是身份层，不是无门控互调。"),
        ],
        series=series,
        total=total,
        page=14,
        cols=2,
    )

    cards_page(
        prs,
        section="10  技能与渠道",
        title="技能生态 + 渠道触达",
        subtitle="扩展面在；自动化上架与多入站渠道不在现状承诺里",
        cards=[
            ("Skill", "workspace / engine Skill；execution_type 强制；handler 缺失报错不装假。"),
            ("MCP", "可接入 MCP Server；核心能力不靠平行实现。"),
            ("飞书入站", "签名、重放、身份映射。人确认才跑。企微只出站。"),
            ("第二入站渠道", "未开。不称多端数字员工已铺开。"),
        ],
        series=series,
        total=total,
        page=15,
        cols=2,
    )

    bullets_page(
        prs,
        section="11  对照",
        title="与 StarAgent 叙事同维对照（诚实）",
        subtitle="学结构，不抄宣传",
        left_title="结构上对齐",
        left_items=[
            "工作台 + 管理台一体",
            "生命周期：装配→执行→触达→沉淀",
            "治理专章：权限、审计、扩展",
            "技能 / 工具扩展面",
            "多端触达作为专章（我们写清边界）",
        ],
        right_title="aiPlat 差异 / 克制",
        right_items=[
            "中心是控制台+人批闸门，不是群聊团队",
            "数字员工 = 竖切试点，不是已签收组织",
            "舰队默认拒绝",
            "提案/案例默认不自动变规则或技能",
            "用量可审计，不计费、无 SKU 价目",
        ],
        series=series,
        total=total,
        page=16,
    )

    cards_page(
        prs,
        section="12  管理面",
        title="管理后台：按任务流的五组，不是工具堆砌",
        subtitle="菜单是治理入口，不是功能广告",
        cards=[
            ("仪表盘", "概览、组织试点、告警、治理、价值看板"),
            ("知识", "业务本体权威轨 · 知识库检索轨"),
            ("AI 应用工厂", "项目、流水线、Agent/Skill/工具工作区"),
            ("诊断与治理", "链路、对比、审查、修复、FDE 工作台"),
            ("平台设置", "模型、节点、安全、审计、渠道"),
            ("权限收口", "按角色可见；admin 须 MFA 才能建 API Key"),
        ],
        series=series,
        total=total,
        page=17,
        cols=3,
    )

    closing(
        prs,
        line=(
            "aiPlat Agent 当前是控制台驱动的智能体装配与受控执行平台。"
            "同一执行核可跑 ReAct / Pipeline / Skill；人批闸门未拆。"
            "客户尚未签收数字员工组织。"
        ),
        points=[
            "不是「人 + 数字员工团队」，是人在控制台里驱动受控执行。",
            "能力市场是注册库。提案不是规则。舰队默认拒绝。",
            "即便案例已沉淀、提案已入队，也不说出错已变成规则或技能。",
        ],
        series=series,
        total=total,
        page=18,
    )

    prs.save(str(OUT_AGENT))
    return OUT_AGENT


# ─────────────────────────── Ontology deck ───────────────────────────

def build_ontology() -> Path:
    series = "aiPlat 本体"
    total = 18
    prs = new_deck()

    cover(
        prs,
        brand="aiPlat",
        title="本体平台 · 现状版（对标星邺结构）",
        lines=[
            "卖的不是知识图谱广告，是可配置的业务世界 + 可执行边界。",
            "说明书（域 YAML）+ 真实层（GraphIndex）+ Action 硬门。",
            "it-ops 竖切可验收。客户尚未签收。不是运行时 OWL 产品。",
        ],
        note="章节对标《星邺汇捷本体平台介绍 v1.0》；禁止把对方宣传指标写成 aiPlat 已实现。",
        series=series,
        total=total,
    )
    toc(
        prs,
        [
            ("01", "我们如何理解本体"),
            ("02", "为什么要有这一层"),
            ("03", "方案分层对照"),
            ("04", "特色能力（诚实版）"),
            ("05", "实施与竖切"),
            ("06", "场景"),
            ("07", "非目标清单"),
            ("08", "对外收口句"),
        ],
        series,
        total,
        2,
    )

    cards_page(
        prs,
        section="01  理解",
        title="我们对本体的理解",
        subtitle="借鉴 Palantir 可执行本体；不宣称运行时 OWL 全家桶已上线",
        cards=[
            ("是什么", "领域客观世界的说明书 + 运行中的真实层。对象、属性、关系、状态、动作写在一处。"),
            ("不是什么", "不是今晚某条告警的自动生成器。不是 HermiT/Pellet 已嵌入生产推理。"),
            ("价值怎么落地", "统一词表、动作硬门、变更人批、否决可审计。Agent 越界会被系统挡住。"),
        ],
        series=series,
        total=total,
        page=3,
        cols=3,
    )

    cards_page(
        prs,
        section="02  为什么",
        title="为什么要有这一层",
        subtitle="企业缺的不是再一个聊天窗口",
        cards=[
            ("数据各说各话", "域本体声明对象、状态、动作。试点主线是 it-ops。"),
            ("知识是碎片", "知识库帮助查文档；不替代业务权威。双轨：业务本体 | 知识库。"),
            ("模型不懂边界", "Action / PolicyGate 硬门。越界否决可审计。"),
            ("决策靠人补洞", "一条线可回放、可人批、可有限回滚。客户还没签收。"),
        ],
        series=series,
        total=total,
        page=4,
        cols=2,
    )

    cards_page(
        prs,
        section="03  分层",
        title="星邺分层 ↔ aiPlat 工程落点",
        subtitle="同维对照，成熟度按代码，不按愿景",
        cards=[
            ("OntoStar ↔ 本体底座", "域 YAML + GraphIndex + ActionRegistry + 提案门（VersionedOntologyStore）"),
            ("AIStar ↔ 智能体平台", "infra 模型目录 + Skill/Syscall + ReAct/Pipeline"),
            ("SuperStar ↔ 编排验证", "Pipeline + FDE + Eval；验证=硬门/审计，不是营销「超级智能体已闭环」"),
            ("数字员工 ↔ 竖切", "it-ops / lock-service / data-gov 等场景线；不是全域数字员工组织已签收"),
            ("适配层", "路径 A 提案改说明书 · B webhook/表映射写图 · C 模板种图"),
            ("知识库轨", "向量 / Wiki / Vault：检索轨，不替代本体拍板"),
        ],
        series=series,
        total=total,
        page=5,
        cols=3,
    )

    part(prs, "PART 特色能力", "特色能力（诚实版）", "结构对标星邺六大特色；每条写清做到哪、没做到哪", series, total, 6)

    cards_page(
        prs,
        section="04  建模闸门",
        title="建模是带闸门的环，不是自动写上",
        subtitle="对标「多种建模方式」——我们强调人批，不报补齐率",
        cards=[
            ("文档/表抽取", "出草稿。确认之前不写活 YAML，也不直接写跨域边。"),
            ("仲裁", "相似度高也只出单。人点合并，才写对齐（须快照才能撤）。"),
            ("提案", "重复失败可聚合。未批不写入，也不自动变技能。"),
            ("写入唯一路", "人批后走 apply_proposal 等既有路径。批准动作本身不改活本体。"),
        ],
        series=series,
        total=total,
        page=7,
        cols=2,
    )

    cards_page(
        prs,
        section="05  权限与动作",
        title="权限与动作：硬门优先",
        subtitle="对标「本体权限」——实例 ACL + Action 合同，不是营销三级已封死",
        cards=[
            ("Action 硬门", "未进合同的调用不能借对话绕过。L1 硬门 > L2 prompt 软约束。"),
            ("ABox ACL", "viewer / analyst / admin。属性可脱敏。"),
            ("批准只判一次", "PolicyGate。身份来自请求头。空身份拒绝。"),
            ("还没宣称的", "不说对象/属性/实例三级已按营销案例全封死。"),
        ],
        series=series,
        total=total,
        page=8,
        cols=2,
    )

    cards_page(
        prs,
        section="06  推理与学习",
        title="推理建议 ≠ 已确认事实；学习 ≠ 自动改规则",
        subtitle="对标「自动推理 / 在线学习」——我们写清边界",
        cards=[
            ("走图 / GraphRAG", "实体路由→子图→定向检索。路径是证据。"),
            ("GraphInference", "建议层。落图须 assert 或提案。can_execute 可为否。"),
            ("案例 overlay", "OrgRun / 工具失败可记案例。反复低收益的注入时降权；可移入冷库只供审计，不删除。不改 TBox。"),
            ("edge 提案", "K5 可入队；开关打开时拒绝启动。默认不自动 apply。"),
        ],
        series=series,
        total=total,
        page=9,
        cols=2,
    )

    cards_page(
        prs,
        section="07  API 与入轨",
        title="对外能力与三条入轨",
        subtitle="对标「对外 API」——意图链有工程落点，不抄六步广告词",
        cards=[
            ("路径 A", "提案改说明书（活 YAML）。直写拒绝（F2）。"),
            ("路径 B", "webhook / JSON / 表·CSV 映射写真实层。白名单主机。"),
            ("路径 C", "已有说明书→模板或手动种图（教学/演示）。"),
            ("检索 API", "DomainRouter + 融合检索；业务对象权威在图，不在 Wiki。"),
        ],
        series=series,
        total=total,
        page=10,
        cols=2,
    )

    part(prs, "PART 实施", "实施与竖切", "业务本体定义边界；智能体遵守边界。一条线先验收。", series, total, 11)

    cards_page(
        prs,
        section="08  竖切",
        title="it-ops 试点：现在能拿出来验收的生产关系",
        subtitle="不是运维数字员工已经到岗",
        cards=[
            ("岗位", "告警试点岗：技能、接口、渠道、数据域写在岗位上。"),
            ("入口", "飞书入站确认；控制台岗位开跑；侧边栏组织试点。"),
            ("一周能看", "运行次数、三 KPI、待批快照、证据包、可审计收益（有基线才算人时）。"),
            ("能撤 / 不能撤", "已生效可退上一版；带快照对齐可撤。没留底旧对齐不能一键撤。"),
        ],
        series=series,
        total=total,
        page=12,
        cols=2,
    )

    cards_page(
        prs,
        section="09  场景 · 治理",
        title="场景：数据治理 —— 能抽取，不能报补齐率",
        subtitle="对标星邺数据治理页。不写 50%→95%、8000 天→5 天。",
        cards=[
            ("有的", "抽取、待审、跨域候选、双轨知识、确认后变更信号。"),
            ("没有的", "不声称元数据补齐率或人天压缩比。本仓库未测量那些数。"),
            ("边界", "平台能力在。不等于已替客户做完治理项目。"),
        ],
        series=series,
        total=total,
        page=13,
        cols=3,
    )

    cards_page(
        prs,
        section="10  场景 · 故障",
        title="场景：故障诊断 —— 走图 + 人批，不是超级智能体已闭环",
        subtitle="对标星邺故障诊断叙事；工程落点是 it-ops 竖切",
        cards=[
            ("做了", "告警/服务/主机等类型；分诊与根因动作合同；OrgRun + HITL；回放。"),
            ("没做", "不声称 200 节点告警已自动根因闭环；不声称决策准确率。"),
            ("闸门", "推理路径是证据。人批才写状态与边。"),
        ],
        series=series,
        total=total,
        page=14,
        cols=3,
    )

    cards_page(
        prs,
        section="11  场景 · 问答与取数",
        title="知识问答与取数",
        subtitle="检索在，权威不在检索里；取数先白名单",
        cards=[
            ("问答", "知识库解决「材料在哪」。动手与拍板回到域类、状态、动作。"),
            ("取数", "接口先登记。未登记主机拒绝。结果可回看，用量记账不计费。"),
            ("价值翻译", "试点页可填写租户基线。有基线才显示节省人时；无基线只显示平台 KPI。"),
        ],
        series=series,
        total=total,
        page=15,
        cols=3,
    )

    bullets_page(
        prs,
        section="12  非目标",
        title="禁止当成现状说的话",
        subtitle="与 ONTOLOGY_NARRATIVE 一致",
        left_title="禁止表述",
        left_items=[
            "完整企业本体已建成",
            "OWL / SPARQL 级推理已上线",
            "HermiT 已融合进运行时",
            "全域统一语义 / L5 已签收",
            "推理建议已自动确认为业务事实",
            "出错已变成规则；技能已自动上架",
        ],
        right_title="可以说",
        right_items=[
            "Palantir 式可执行本体内核在建设中",
            "YAML + 图 + Action 是运行时权威",
            "OWL 可作导出与离线审稿",
            "it-ops 单线可回放、可人批、可有限回滚；apply 另写 JSON diff",
            "证据可导出；客户尚未签收",
            "提效不放权（H0–H5；H4 沙箱开、live 拒）",
        ],
        series=series,
        total=total,
        page=16,
    )

    cards_page(
        prs,
        section="13  UI",
        title="管理端入口",
        subtitle="权威轨与检索轨分开，避免两张皮",
        cards=[
            ("业务本体", "/knowledge/business — 工厂 / 域 / 编辑器"),
            ("知识库", "/knowledge/library — 向量 / Wiki / 文档"),
            ("组织试点", "/org/pilot — 扫队列、填基线（可先试算）、装模板、记值班/回滚演练、签收准备度八闸门卡片（如何核/跳转）+剧本可导出。无注入不报命中率。不是签收。"),
            ("FDE 工作台", "诊断与治理组 — 抽取 / 仲裁 / 交付"),
        ],
        series=series,
        total=total,
        page=17,
        cols=2,
    )

    closing(
        prs,
        line=(
            "aiPlat 本体当前是控制台驱动的可执行语义底座："
            "说明书 + 真实层 + Action 硬门。"
            "it-ops 试点可回放、可人批、可有限回滚；沙箱可扫队列，基线可自助填写。第二域模板只给骨架，不是零配置开箱。"
            "客户尚未签收。还不是数字员工组织，也不是运行时 OWL 产品。"
        ),
        points=[
            "双轨：业务本体权威 · 知识库检索。知识库不替代拍板。",
            "提案不是规则。材料包与证据包就绪都不等于签字。",
            "五组菜单保留。不称超级组织，不称 L5 已签收。",
        ],
        series=series,
        total=total,
        page=18,
    )

    prs.save(str(OUT_ONTO))
    return OUT_ONTO


# ─────────────────── Combo: Ontology + Agent ───────────────────

def build_combo() -> Path:
    """Joint narrative: ontology + agent. Internal deck may cite competitor skeleton."""
    series = "aiPlat 本体+Agent"
    total = 16
    prs = new_deck()

    cover(
        prs,
        brand="aiPlat",
        title="本体 + Agent · 合册现状版",
        lines=[
            "对标星邺「本体+超级智能体」分享结构（内部对齐用）。",
            "一层语义底座，一层受控执行；交点是人批闸门。",
            "it-ops 竖切可联调。不称超级组织，客户尚未签收。",
        ],
        note="内部版可保留竞对骨架对照；对外版请用同名「对外版」文件。正文只写 aiPlat 已落地。",
        series=series,
        total=total,
    )
    toc(
        prs,
        [
            ("01", "时代命题与卡位"),
            ("02", "四层引擎对照"),
            ("03", "八项能力：做成 / 未做"),
            ("04", "受控提效：到底省什么"),
            ("05", "人机关系与研发形态"),
            ("06", "六项技术突破（诚实）"),
            ("07", "本体 ↔ Agent 双向"),
            ("08", "竖切实践与收口"),
        ],
        series,
        total,
        2,
        subtitle="内部对齐：可对照业界「本体+智能体」分享骨架；正文是代码事实",
    )

    cards_page(
        prs,
        section="01  命题",
        title="软件在变，最难的那块砖是什么？",
        subtitle="把卡位落在可执行语义 + 闸门，而不是口号式 Agent 化",
        cards=[
            ("时代叙事", "应用层价值在上升，企业要把「能聊」变成「能用、能管、能落地」。这是方向，不是已完成态。"),
            ("错误卡位", "只堆对话入口、只堆模型、只堆知识库检索——缺统一业务对象与动作边界，Agent 仍会越界。"),
            ("aiPlat 卡位", "域 YAML 说明书 + GraphIndex 真实层 + Action/PolicyGate 硬门 + ReAct/Pipeline 执行核。"),
        ],
        series=series,
        total=total,
        page=3,
        cols=3,
    )

    cards_page(
        prs,
        section="02  引擎",
        title="四层引擎：渠道 → Agent → 本体 → 业务系统",
        subtitle="企业级通用分层；名称按 aiPlat 实装改写",
        cards=[
            ("① 渠道入口", "飞书入站（签名/重放/映射），人确认才跑。企微只出站。不是多渠数字员工已铺开。"),
            ("② Agent 执行", "ReAct / Pipeline / Skill / Syscall。应用工厂可装配。舰队默认拒绝。"),
            ("③ 本体语义", "对象/属性/关系/状态/动作/接口。业务本体权威轨；知识库是检索轨。"),
            ("④ 业务系统", "Interface 白名单 + Path B webhook/表映射。默认关 live；未登记主机拒绝。"),
        ],
        series=series,
        total=total,
        page=4,
        cols=2,
    )

    matrix_page(
        prs,
        section="03  八项能力",
        title="八项能力 · 做成 / 未做分开写",
        subtitle="勾选状态以代码为准。绿=已做，黄=部分，红=未做。",
        rows=[
            ("1 多角色并行", "missing", "舰队默认拒绝。沙箱可记多角色交接，不 spawn。单次 OrgRun，不是并行数字员工。"),
            ("2 持续学习", "partial", "案例与提案入队。提案不是规则；默认不自动 apply。"),
            ("3 Skill 市场", "partial", "注册库在。H5 只组装已有草稿；人批后才登记。失败回放可标缺口，先 Diff 预览再采纳进提案，不写活 YAML。"),
            ("4 任务主动工作", "partial", "飞书确认后跑、岗位开跑。白名单事件只沙箱预演，不进 live。不是 7×24 主动伙伴。"),
            ("5 企业可管可控", "done", "PolicyGate、回放、审计、证据包、用量记账不计费。"),
            ("6 渠道灵活接入", "partial", "飞书入站已开。第二入站渠道未开。企微只出站。"),
            ("7 代码研发模式", "partial", "工厂在。不是 7×24 研发数字员工岗位。"),
            ("8 接入本体语义", "done", "竖切已接 DomainRouter / 图 / Action。知识库不替代拍板。"),
        ],
        series=series,
        total=total,
        page=5,
    )

    cards_page(
        prs,
        section="04  受控提效",
        title="在受控前提下，我们到底帮你省了什么？",
        subtitle="不承诺「减少 90% 工作量」。把治理翻译成可感知的业务成本下降。",
        cards=[
            ("审计与复盘成本", "把散落在聊天里的故障排查，变成可回放的 traces。缺步标明「未发生」，不补假链路。"),
            ("合规与越界风险", "未进合同的调用不能借对话绕过。就算对话里被诱导，越界查询也会在系统层被拦住，并留下审计。"),
            ("例外才进人批", "常规流水线跑到闸门；人只批抽取确认、仲裁、提案和例外。沙箱里可扫一遍队列，生产 live 仍须人批。"),
            ("签收准备成本", "证据包一键导出，审计材料不用从聊天里翻。封面声明不是签字，材料齐不等于客户已签收。"),
            ("价值可读性", "客户可自己填历史工时基线，平台按公式算节省人时。没填基线就不编数字，只显示平台指标。"),
            ("明确不省的", "不省掉人批本身。失败可标缺口、连续失败只提示提案，都不写活本体。模板不是零配置开箱。真签收另宣布。"),
        ],
        series=series,
        total=total,
        page=6,
        cols=3,
    )

    bullets_page(
        prs,
        section="05  人机关系",
        title="人机关系：指挥官在控制台，不是群聊超级组织",
        subtitle="角色转型方向可讲，现状成熟度克制",
        left_title="常见愿景三层",
        left_items=[
            "指挥层：定目标、审规则、核异常、批策略",
            "执行层：多角色 Agent 团队并行",
            "接入层：ERP/CRM 等存量系统",
            "口号：从超级个体到超级组织",
        ],
        right_title="aiPlat 现状怎么落",
        right_items=[
            "指挥：人在五组菜单里批、开跑、导出证据",
            "执行：单线受控运行；舰队默认拒绝",
            "接入：白名单 Interface；live 默认关",
            "不称超级组织 / L5 已签收",
        ],
        series=series,
        total=total,
        page=7,
    )

    cards_page(
        prs,
        section="06  研发形态",
        title="研发变革：工厂协同，不是本机 IDE 被取代的幻觉",
        subtitle="人提目标与边界，Agent 在闸门内执行可审计步骤",
        cards=[
            ("传统", "人在 IDE 里完成全部编码与联调。"),
            ("方向", "人提目标与边界，Agent/Pipeline 在闸门内执行可审计步骤。"),
            ("aiPlat", "应用工厂 + 编码宪法 + autoreview + Eval 门。生成物走平台路径，不平行造引擎。"),
            ("边界", "工厂不是 7×24 研发员工岗位。放行舰队 ≠ 已产品化多 Agent spawn。"),
        ],
        series=series,
        total=total,
        page=8,
        cols=2,
    )

    part(
        prs,
        "PART 技术",
        "六项技术突破（诚实映射）",
        "冷启动 → 演化 → 可信；每块写清做到哪",
        series,
        total,
        9,
    )

    matrix_page(
        prs,
        section="07  六项突破",
        title="建模 · 融合 · 推理 · Harness · 学习 · 安全",
        subtitle="冷启动到可信底座。状态只标工程边界，不标愿景完成度。",
        rows=[
            ("01 自动化建模", "partial", "抽取出草稿。确认前不写活 YAML、不写跨域边。不报补齐率。"),
            ("02 动态本体融合", "partial", "仲裁 + 提案。带快照才可撤。冲突靠人批。"),
            ("03 本体推理", "partial", "走图与推理是证据/建议。落图须 assert 或提案。非 OWL 运行时。"),
            ("04 Harness 工程", "done", "Action / PolicyGate。HITL、Eval、回放。上下文分层注入。"),
            ("05 持续学习", "partial", "案例、TaskSkill、edge 提案。默认不自动改 TBox、不上架。"),
            ("06 智能体安全", "done", "岗位、沙箱 IO、审计、admin MFA、架构守卫。"),
        ],
        series=series,
        total=total,
        page=10,
    )

    bullets_page(
        prs,
        section="08  双向",
        title="本体如何喂 Agent · Agent 如何反哺本体",
        subtitle="合册核心交点：语义进执行，执行回语义——都过人批",
        left_title="本体 → Agent",
        left_items=[
            "DomainRouter 选域",
            "GraphIndex 查对象与状态",
            "Action 合同约束可调动作",
            "Interface 白名单约束取数",
            "ContextBus / 检索注入任务上下文",
            "知识库只助查文档，不替代拍板",
        ],
        right_title="Agent → 本体",
        right_items=[
            "抽取草稿待确认",
            "OrgRun / 工具失败 → 案例 overlay",
            "重复失败 → edge 提案入队",
            "待批快照 + H4 队列自动通过（沙箱开、live 拒）",
            "人批后才 apply / 写边",
            "证据包导出供签收准备（≠已签收）",
        ],
        series=series,
        total=total,
        page=11,
    )

    cards_page(
        prs,
        section="09  实践",
        title="应用实践：用 aiPlat 竖切讲",
        subtitle="可验证的线；不搬外部客户成效数字",
        cards=[
            ("it-ops 告警分诊", "本体类型 + OrgRun + 飞书确认 + 周报 KPI + 有限回滚 + 证据包。"),
            ("FDE 交付闭环", "诊断→证据→流水线 HITL→Evolve 观测窗。工作台多 Tab 已接线。"),
            ("材料问答", "知识库检索 + CRAG。结论若要动手，回到域动作硬门。"),
            ("应用工厂生成", "生成 Agent 走 Pipeline/handoff；消息总线是身份层，不是无门控互调。"),
        ],
        series=series,
        total=total,
        page=12,
        cols=2,
    )

    cards_page(
        prs,
        section="10  治理交点",
        title="合册治理：两边共用闸门，不各建一套",
        subtitle="管得住两边，才谈得上「引擎」",
        cards=[
            ("写入唯一路", "活 YAML 只经提案 apply；Agent 批准动作本身不改说明书。"),
            ("执行唯一核", "ReAct/Pipeline/Skill 共享 syscall 与 PolicyGate。"),
            ("观测唯一账", "回放、用量、证据包、价值翻译（有基线才算人时）。"),
            ("明确不做", "H4 在 live 拒绝；H5 不自动上架；第二入站、打开 m4_claim —— 未宣布。"),
        ],
        series=series,
        total=total,
        page=13,
        cols=2,
    )

    cards_page(
        prs,
        section="11  资料关系",
        title="三份资料怎么分工",
        subtitle="单独讲 Agent、单独讲本体、合册讲交点",
        cards=[
            ("Agent 册", "装配、执行核、工厂、治理、渠道。读者：平台/应用负责人。"),
            ("本体册", "说明书、真实层、入轨、非目标、竖切场景。读者：业务架构/数据负责人。"),
            ("合册（本份）", "四层引擎、八项做成/未做、受控提效、双向反哺。读者：决策层 30 分钟对齐。"),
            ("现状图/竖切册", "另有「现状版」含现状图与验收话术，可与合册并用。"),
        ],
        series=series,
        total=total,
        page=14,
        cols=2,
    )

    bullets_page(
        prs,
        section="12  合作口径",
        title="对外合作可组合，但不预支签收",
        subtitle="阶段可组合，话术不透支",
        left_title="可谈的组合",
        left_items=[
            "平台授权：控制台 + 执行核 + 本体底座",
            "专家咨询：域建模与闸门设计",
            "应用落地：单线竖切（如 it-ops）联调",
            "材料包/证据包：签收准备，不是已签字",
        ],
        right_title="进场前说清",
        right_items=[
            "先一条线，不承诺全域数字员工",
            "人批闸门不拆",
            "live IO 默认关，白名单另立",
            "效果数字以客户环境实测为准",
        ],
        series=series,
        total=total,
        page=15,
    )

    closing(
        prs,
        line=(
            "aiPlat 当前是「本体语义底座 + 受控 Agent 执行」合在同一控制台的引擎："
            "渠道进、Agent 跑、本体定界、系统白名单出。"
            "it-ops 竖切可联调。交点是人批闸门。"
            "不称超级组织，客户尚未签收。"
        ),
        points=[
            "八项能力里：可控可观测是长板；多角色并行与自动变规则是未做。",
            "受控提效：可回放、可审计、例外人批、证据可导出——不是全自动免责。",
            "本体喂 Agent，Agent 反哺案例/提案——写入仍走人批。成熟度以本仓库代码为准。",
        ],
        series=series,
        total=total,
        page=16,
    )

    prs.save(str(OUT_COMBO))
    return OUT_COMBO


_EXTERNAL_REPLACEMENTS = [
    ("对标星邺「本体+超级智能体」分享结构（内部对齐用）。", "按企业级「语义底座 + 受控智能体」通用分层讲述。"),
    ("对标星邺「本体+超级智能体」分享结构。", "按企业级「语义底座 + 受控智能体」通用分层讲述。"),
    ("内部版可保留竞对骨架对照；对外版请用同名「对外版」文件。正文只写 aiPlat 已落地。", "对外现状版。正文只写 aiPlat 已落地事实，不引用竞对名称。"),
    ("章节对标《星邺汇捷-本体+超级智能体分享0622》；正文只写 aiPlat 已落地，不搬对方客户成效数字。", "按企业级平台通用架构分层；正文只写 aiPlat 已落地事实。"),
    ("内部对齐：可对照业界「本体+智能体」分享骨架；正文是代码事实", "按企业级平台通用架构分层；正文是代码事实"),
    ("章节骨架对标星邺产品介绍；正文只写 aiPlat 已落地事实", "按企业级平台通用架构分层；正文只写 aiPlat 已落地事实"),
    ("章节对标 StarAgent 2.0；结论只写仓库已落地能力，不搬对方宣传指标。", "按企业级智能体平台通用章节讲述；结论只写仓库已落地能力。"),
    ("对标 StarAgent「六大产品面」结构；名称按 aiPlat 实装", "按智能体全生命周期六面讲述；名称按 aiPlat 实装"),
    ("与 StarAgent 叙事同维对照（诚实）", "与常见企业级智能体叙事同维对照（诚实）"),
    ("学结构，不抄宣传", "学通用结构，不抄宣传指标"),
    ("本体平台 · 现状版（对标星邺结构）", "本体平台 · 现状版"),
    ("章节对标《星邺汇捷本体平台介绍 v1.0》；禁止把对方宣传指标写成 aiPlat 已实现。", "按企业级本体平台通用章节讲述；禁止把未验证宣传指标写成已实现。"),
    ("星邺分层 ↔ aiPlat 工程落点", "业界常见分层 ↔ aiPlat 工程落点"),
    ("同维对照，成熟度按代码，不按愿景", "同维对照，成熟度按代码，不按愿景"),
    ("结构对标星邺六大特色；每条写清做到哪、没做到哪", "按企业级本体六类能力写清做到哪、没做到哪"),
    ("对标星邺数据治理页。不写 50%→95%、8000 天→5 天。", "数据治理场景。不写未在本仓库测量的补齐率与人天数字。"),
    ("对标星邺故障诊断叙事；工程落点是 it-ops 竖切", "故障诊断场景；工程落点是 it-ops 竖切"),
    ("与星邺分享同维对话；成熟度以本仓库代码与契约为准。", "成熟度以本仓库代码与契约为准。"),
    ("对标「星智引擎」分层；名称按 aiPlat 实装改写", "企业级四层引擎；名称按 aiPlat 实装改写"),
    ("对标分享「战略定位」——我们把卡位落在可执行语义 + 闸门，而不是口号式 Agent 化", "把卡位落在可执行语义 + 闸门，而不是口号式 Agent 化"),
    ("对标「新一代数字员工」八项 · 做成 / 未做分开写", "八项能力 · 做成 / 未做分开写"),
    ("学对方清单结构；不把愿景勾成已交付", "清单结构清晰；不把愿景勾成已交付"),
    ("不称对标 Cursor 的 7×24 研发数字员工已上岗。", "不称 7×24 研发数字员工已上岗。"),
    ("清单结构可对标业界「数字员工」叙事；勾选状态以代码为准", "勾选状态以代码为准"),
    ("有的写有；没有的写没有。不搬星邺效果数字。", "有的写有；没有的写没有。不写未在本仓库测量的宣传指标。"),
    ("章节对标 StarAgent 2.0；结论只写仓库已落地能力，不搬对方宣传指标。", "按企业级智能体平台通用章节讲述；结论只写仓库已落地能力。"),
    ("对标 StarAgent「六大产品面」结构；名称按 aiPlat 实装", "按智能体全生命周期六面讲述；名称按 aiPlat 实装"),
    ("与 StarAgent 叙事同维对照（诚实）", "与常见企业级智能体叙事同维对照（诚实）"),
]


def _replace_in_textframe(tf, mapping: list) -> bool:
    full = tf.text or ""
    new_full = full
    for old, repl in mapping:
        if old in new_full:
            new_full = new_full.replace(old, repl)
    if new_full == full:
        return False
    # rewrite frame as single block in first paragraph
    paras = list(tf.paragraphs)
    if not paras:
        return False
    p0 = paras[0]
    if p0.runs:
        p0.runs[0].text = new_full
        for r in p0.runs[1:]:
            r.text = ""
    else:
        p0.text = new_full
    for p in paras[1:]:
        for r in p.runs:
            r.text = ""
        if not p.runs:
            p.text = ""
    return True


def export_external(src: Path, dst: Path) -> Path:
    """Clone deck and scrub competitor-facing wording for customer handout."""
    import shutil

    shutil.copy2(src, dst)
    prs = Presentation(str(dst))
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                _replace_in_textframe(shape.text_frame, _EXTERNAL_REPLACEMENTS)
    # assert no vertical-slice typo (坚+切 mis-typed)
    bad = "坚" + "切"
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame and bad in shape.text_frame.text:
                raise SystemExit(f"typo {bad} found in {dst}")
    prs.save(str(dst))
    return dst


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    a = build_agent()
    o = build_ontology()
    c = build_combo()
    print("wrote", a)
    print("wrote", o)
    print("wrote", c)

    # external handouts (no competitor names in customer-facing copy)
    exteriors = [
        (a, OUT_DIR / "aiPlat-Agent智能体平台产品介绍-现状版-对外版.pptx"),
        (o, OUT_DIR / "aiPlat-本体平台产品介绍-现状版-对外版.pptx"),
        (c, OUT_DIR / "aiPlat-本体+Agent合册产品介绍-现状版-对外版.pptx"),
    ]
    for src, dst in exteriors:
        export_external(src, dst)
        print("wrote", dst)


if __name__ == "__main__":
    main()
