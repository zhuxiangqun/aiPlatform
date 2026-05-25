from __future__ import annotations

from pathlib import Path
from typing import List, Optional


def render_pdf_to_images(pdf_path: str, *, out_dir: str, dpi: int = 200, max_pages: Optional[int] = None) -> List[str]:
    """
    将 PDF 渲染为按页图片（PNG）。
    - 优先使用 PyMuPDF(fitz)；若不可用可再扩展 pypdfium2。
    """
    out = []
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)

    # --- PyMuPDF ---
    try:
        import fitz  # type: ignore

        doc = fitz.open(pdf_path)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        n = doc.page_count
        if max_pages is not None:
            n = min(n, int(max_pages))
        for i in range(n):
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            fp = p / f"page_{i:04d}.png"
            pix.save(str(fp))
            out.append(str(fp))
        return out
    except Exception:
        pass

    # --- pypdfium2 fallback (optional) ---
    try:
        import pypdfium2 as pdfium  # type: ignore

        pdf = pdfium.PdfDocument(pdf_path)
        n = len(pdf)
        if max_pages is not None:
            n = min(n, int(max_pages))
        for i in range(n):
            page = pdf.get_page(i)
            pil_image = page.render(scale=dpi / 72.0).to_pil()
            fp = p / f"page_{i:04d}.png"
            pil_image.save(fp)
            out.append(str(fp))
        return out
    except Exception as e:
        raise RuntimeError(
            "PDF 渲染失败：缺少依赖。请安装 PyMuPDF 或 pypdfium2。\n"
            "推荐：pip install pymupdf --break-system-packages\n"
            "或：pip install pypdfium2 --break-system-packages"
        ) from e

