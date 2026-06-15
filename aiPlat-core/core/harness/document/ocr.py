"""
Image OCR — Tesseract / PaddleOCR model inference for image-to-text.
Uses InfraOCRAdapter for unified model loading through infra.
Legacy direct pytesseract fallback retained for backward compat.

Configuration:
  AIPLAT_VIDEO_OCR_LANG — language (eng+chi_sim, chi_sim, eng, default: eng+chi_sim)
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List


def ocr_keyframes(frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Prefer InfraOCRAdapter
    try:
        from core.harness.infrastructure.base_model_adapter import create_adapter
        adapter = create_adapter("ocr")
        return adapter.ocr_frames(frames)
    except Exception:
        pass

    # Legacy pytesseract direct load (fallback)
    try:
        from PIL import Image
        import pytesseract  # type: ignore  # noqa: F401
    except Exception:
        return []

    lang = str(os.getenv("AIPLAT_VIDEO_OCR_LANG", "eng+chi_sim") or "eng+chi_sim")
    out: List[Dict[str, Any]] = []
    for fr in frames:
        p = str(fr.get("local_path") or "")
        if not p:
            continue
        try:
            with Image.open(p) as img:
                text = pytesseract.image_to_string(img, lang=lang)
        except Exception:
            continue
        text = " ".join(str(text or "").split()).strip()
        if len(text) < 6:
            continue
        useful = len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", text))
        symbol = len(re.findall(r"[^A-Za-z0-9\u4e00-\u9fff\s]", text))
        quality = (useful / max(1, len(text))) - (symbol / max(1, len(text))) * 0.7
        if useful < max(6, len(text) // 4) or quality < 0.28:
            continue
        out.append({"time_ms": int(fr.get("time_ms") or 0), "text": text[:4000]})
    return out


async def vlm_describe_image(image_path: str, image_type: str = "auto") -> str:
    """Use VLM to generate structured description of image content.

    Args:
        image_path: Path to the image file (PNG/JPG)
        image_type: "chart" | "architecture" | "flowchart" | "table" | "auto"

    Returns:
        Structured text description suitable for embedding and search.
    """
    import base64
    try:
        with open(image_path, 'rb') as f:
            image_b64 = base64.b64encode(f.read()).decode()
    except Exception:
        return ""

    prompts = {
        "chart": "分析这张图表：提取图表类型、X/Y轴含义、关键数据趋势和极值点。输出中文。",
        "architecture": "分析这张架构图：提取所有组件名称、连接关系、数据流向。输出中文。",
        "flowchart": "分析这张流程图：提取每个步骤、决策节点和分支条件。输出中文。",
        "table": "分析这张表格：提取表头、关键数据行和汇总信息。输出中文。",
        "auto": "分析这张图片的内容：提取其中包含的关键信息、结构和关系。输出中文。",
    }

    try:
        from core.harness.syscalls.llm import sys_llm_generate
        prompt_text = prompts.get(image_type, prompts["auto"])
        resp = await sys_llm_generate(
            prompt=[
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    {"type": "text", "text": prompt_text},
                ]}
            ],
            model=None,
            temperature=0.1,
            max_tokens=800,
        )
        text = str(resp) if resp else ""
        return text[:2000]
    except Exception:
        return ""


__all__ = ["ocr_keyframes", "vlm_describe_image"]
