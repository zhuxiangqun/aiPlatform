"""
draw.io 图表生成器 — LLM 直接输出 draw.io XML，零外部依赖

核心思路: DeepSeek/ChatGPT 等 LLM 在训练数据中见过 draw.io XML 格式。
给定结构化 Prompt，可以直接输出规范的 mxGraphModel XML。
前端用 draw.io 开源 viewer (viewer.diagrams.net) 渲染，完全本地化。

用法:
  from core.harness.syscalls.drawio_gen import generate_diagram
  xml = await generate_diagram("用户登录 + MFA 验证流程图")
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import re as _re
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Prompt ──────────────────────────────────────────────────────────

DRAWIO_PROMPT = """你是 draw.io 图表专家。根据用户描述生成规范的 draw.io XML。

## 输出格式
<mxfile host="app.diagrams.net" agent="ai">
  <diagram name="图表" id="diagram1">
    <mxGraphModel dx="1422" dy="794" grid="1" gridSize="10">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <!-- 你的节点和连线 -->
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>

## 节点样式
- 流程节点: rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;
- 判断/条件: shape=rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;
- 用户/角色: shape=umlActor;verticalLabelPosition=bottom;html=1;fillColor=#e1d5e7;strokeColor=#9673a6;
- 数据库: shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;fillColor=#d5e8d4;strokeColor=#82b366;
- 外部/云: shape=cloud;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;
- 开始/结束: rounded=1;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;fontStyle=1;

连线: edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=classic;

## 规则
- 节点id用英文+数字，source/target引用id
- 间距: 水平160, 垂直100, 节点120x60, 起始x=100 y=100
- 只输出XML，不要markdown包裹，不要解释
- 每个图至少3个节点2条线

用户需求: {description}"""

MODIFY_PROMPT = """修改以下 draw.io XML 满足新需求。保持风格，只改必要部分。

原XML:
{xml}

新需求: {description}

只输出修改后的完整XML。"""


# ── Core ────────────────────────────────────────────────────────────

async def generate_diagram(
    description: str,
    context_xml: Optional[str] = None,
) -> str:
    u"""根据描述生成或修改 draw.io XML。

    Args:
        description: 图表需求描述
        context_xml: 已有XML(修改模式)

    Returns:
        draw.io XML 字符串
    """
    from core.harness.syscalls.llm import sys_llm_generate
    from core.harness.utils.model_injection import best_model_for_purpose

    if context_xml:
        prompt = MODIFY_PROMPT.format(xml=context_xml[:5000], description=description)
    else:
        prompt = DRAWIO_PROMPT.format(description=description)

    try:
        result = await sys_llm_generate(
            None, [{"role": "user", "content": prompt}],
            model_name=best_model_for_purpose("chat"),
            max_tokens=3000,
        )
        content = getattr(result, 'content', '') or str(result)
    except Exception as e:
        logger.warning("Diagram generation failed: %s", e)
        return _fallback_diagram(description)

    xml = _clean_xml(content)
    if not _validate_xml(xml):
        xml = _fallback_diagram(description)

    return xml


def _clean_xml(text: str) -> str:
    u"""Strip markdown fences and extract XML."""
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl > 0:
            t = t[first_nl:].strip()
    if t.endswith("```"):
        t = t[:-3].strip()

    start = t.find("<mxfile")
    if start == -1:
        start = t.find("<mxGraphModel")
    if start > 0:
        t = t[start:]
    return t


def _validate_xml(xml: str) -> bool:
    return bool(xml) and "<root>" in xml and '<mxCell id="0"' in xml


def _fallback_diagram(description: str) -> str:
    u"""Generate minimal valid diagram when LLM output fails."""
    import xml.etree.ElementTree as ET
    from xml.dom import minidom

    mxfile = ET.Element("mxfile", {"host": "app.diagrams.net", "agent": "ai"})
    diag = ET.SubElement(mxfile, "diagram", {"name": description[:40], "id": "d1"})
    model = ET.SubElement(diag, "mxGraphModel", {"dx": "800", "dy": "400", "grid": "1", "gridSize": "10"})
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
    n = ET.SubElement(root, "mxCell", {"id": "n1", "value": description[:60], "vertex": "1", "parent": "1",
        "style": "rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;"})
    ET.SubElement(n, "mxGeometry", {"x": "100", "y": "100", "width": "120", "height": "60", "as": "geometry"})

    rough = ET.tostring(mxfile, encoding="utf-8")
    return minidom.parseString(rough).toprettyxml(indent="  ")


# ── Storage ─────────────────────────────────────────────────────────

_DIAGRAMS_DIR = Path(_os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))) / "diagrams"


def save_diagram(xml: str, diagram_id: Optional[str] = None) -> str:
    _DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    did = diagram_id or _uuid.uuid4().hex[:8]
    (_DIAGRAMS_DIR / f"{did}.xml").write_text(xml, encoding="utf-8")
    return did


def load_diagram(diagram_id: str) -> Optional[str]:
    path = _DIAGRAMS_DIR / f"{diagram_id}.xml"
    return path.read_text(encoding="utf-8") if path.exists() else None


def list_diagrams() -> List[Dict[str, Any]]:
    result = []
    for fp in sorted(_DIAGRAMS_DIR.glob("*.xml"), key=lambda f: f.stat().st_mtime, reverse=True):
        s = fp.stat()
        result.append({"id": fp.stem, "name": fp.stem, "size": s.st_size,
                       "modified": datetime.fromtimestamp(s.st_mtime, timezone.utc).isoformat()})
    return result


def delete_diagram(diagram_id: str) -> bool:
    path = _DIAGRAMS_DIR / f"{diagram_id}.xml"
    if path.exists():
        path.unlink()
        return True
    return False


def sys_drawio_generate(description: str, modify_id: str = "") -> Dict[str, Any]:
    u"""Syscall: generate or modify a draw.io diagram.

    Returns {diagram_id, viewer_url, xml_preview}.
    """
    import asyncio
    context = load_diagram(modify_id) if modify_id else None
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # Already in async context — use thread pool
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            xml = pool.submit(asyncio.run, generate_diagram(description, context)).result()
    else:
        xml = asyncio.run(generate_diagram(description, context))
    did = save_diagram(xml)
    return {"diagram_id": did, "viewer_url": f"/diagrams/viewer/{did}", "xml_preview": xml[:500]}
