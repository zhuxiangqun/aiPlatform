"""
Multimodal KB PoC (Phase B)

目标：
- 用“真实扫描 PDF”打通最小闭环：渲染页图 → OCR（带 bbox）→ 抽取候选数值 → 基于问题做简单读数 → 返回 citations（页码+bbox）
- 该模块是 PoC：强调可运行与可观测，不追求最终精度/完备性。
"""

from .ingest import ingest_scanned_pdf
from .query import answer_question

__all__ = ["ingest_scanned_pdf", "answer_question"]

