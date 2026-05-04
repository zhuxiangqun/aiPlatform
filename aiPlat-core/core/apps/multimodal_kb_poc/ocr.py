from __future__ import annotations

from typing import List, Literal, Optional
import threading

from .types import BBox, OCRToken


def _bbox_from_poly(poly) -> BBox:
    xs = [int(p[0]) for p in poly]
    ys = [int(p[1]) for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


# Cache PaddleOCR instances so we don't re-load models per page.
# Loading models repeatedly is extremely slow and looks like the job is "stuck".
_PADDLE_OCR_LOCK = threading.RLock()
_PADDLE_OCR_CACHE: dict[str, object] = {}


def _get_paddle_ocr(*, lang: str) -> object:
    """
    Return a cached PaddleOCR instance.
    Keyed by ocr_lang ('ch'/'en').
    """
    with _PADDLE_OCR_LOCK:
        if lang in _PADDLE_OCR_CACHE:
            return _PADDLE_OCR_CACHE[lang]
        from paddleocr import PaddleOCR  # type: ignore

        ocr = PaddleOCR(use_angle_cls=True, lang=lang)
        _PADDLE_OCR_CACHE[lang] = ocr
        return ocr



def ocr_image(
    image_path: str,
    *,
    engine: Literal["paddleocr", "tesseract"] = "paddleocr",
    # 兼容：部分调用方可能使用 ocr_engine= 参数名
    ocr_engine: Optional[str] = None,
    lang: str = "ch",
    **_kwargs,
) -> List[OCRToken]:
    """
    OCR 单张图片，返回 tokens（带 bbox）。

    - paddleocr：更适合扫描件/中文；但依赖较重。
    - tesseract：依赖较轻，作为兜底。
    """

    engine = (ocr_engine or engine or "paddleocr").strip().lower()

    if engine == "paddleocr":
        try:
            # Imported for dependency check only; instance is created via cache below.
            from paddleocr import PaddleOCR  # type: ignore  # noqa: F401
        except Exception as e:
            raise RuntimeError(
                "未安装 PaddleOCR。可选：\n"
                "1) pip install paddleocr pypdfium2 --break-system-packages\n"
                "2) 或改用 engine='tesseract'（需要系统安装 tesseract）"
            ) from e

        # 说明：PaddleOCR 的 lang 取值不是 ISO 代码，这里做一个简单映射
        ocr_lang = "ch" if lang.lower().startswith("zh") or lang.lower() in ("ch", "cn") else "en"
        ocr = _get_paddle_ocr(lang=ocr_lang)
        # NOTE: paddleocr / paddlex 版本差异：部分版本的 ocr() 不接受 cls 参数，
        # 会报 "PaddleOCR.predict() got an unexpected keyword argument 'cls'".
        # use_angle_cls 已在构造函数中启用，这里不再传 cls。
        res = getattr(ocr, "ocr")(image_path) or []
        out: List[OCRToken] = []
        # res 可能是：
        # 1) [[ [poly], (text, conf) ], ...]
        # 2) [ [ [poly], (text, conf) ], ... ] 的再包一层（某些版本/批量接口）
        lines = []
        if isinstance(res, list) and res:
            # case 1
            if isinstance(res[0], list) and len(res[0]) == 2:
                lines = res
            # case 2
            elif isinstance(res[0], list):
                lines = res[0]
        for line in lines:
            try:
                poly = line[0]
                txt = str(line[1][0] or "").strip()
                conf = float(line[1][1] or 0.0)
                if not txt:
                    continue
                out.append(OCRToken(text=txt, bbox=_bbox_from_poly(poly), conf=conf))
            except Exception:
                continue
        return out

    # --- tesseract fallback ---
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "未安装 tesseract OCR 依赖。可选：\n"
            "1) pip install pytesseract pillow --break-system-packages，并在系统安装 tesseract\n"
            "2) 或改用 PaddleOCR"
        ) from e

    # Ensure tessdata exists for requested language
    import os as _os

    tessdata_prefix = _os.getenv("TESSDATA_PREFIX") or ""
    # For Homebrew macOS, this is typically /opt/homebrew/share/tessdata
    if not tessdata_prefix:
        for p in ("/opt/homebrew/share/tessdata", "/usr/local/share/tessdata"):
            if _os.path.isdir(p):
                tessdata_prefix = p
                break

    # Use chi_sim + eng for Chinese docs to improve digit recognition in tables.
    lang_code = "chi_sim+eng" if lang.lower().startswith("zh") else "eng"
    if lang.lower().startswith("zh"):
        td = _os.path.join(tessdata_prefix, "chi_sim.traineddata") if tessdata_prefix else ""
        if not (td and _os.path.exists(td)):
            raise RuntimeError(
                "未找到 tesseract 中文语言包 chi_sim.traineddata。\n"
                "macOS(Homebrew) 推荐：brew install tesseract-lang\n"
                "并设置：export TESSDATA_PREFIX=\"$(brew --prefix)/share/tessdata\""
            )

    img = Image.open(image_path)
    # image_to_data can output per-word bbox + confidence
    # Use PSM 6 (assume a uniform block of text) and preserve spaces, which helps table OCR.
    config = "--psm 6 -c preserve_interword_spaces=1"
    data = pytesseract.image_to_data(img, lang=lang_code, config=config, output_type=pytesseract.Output.DICT)
    out2: List[OCRToken] = []
    n = len(data.get("text") or [])
    for i in range(n):
        txt = str((data.get("text") or [""])[i] or "").strip()
        if not txt:
            continue
        try:
            conf = float((data.get("conf") or ["0"])[i] or 0.0) / 100.0
        except Exception:
            conf = 0.0
        try:
            x = int((data.get("left") or [0])[i])
            y = int((data.get("top") or [0])[i])
            w = int((data.get("width") or [0])[i])
            h = int((data.get("height") or [0])[i])
            bbox: BBox = (x, y, x + w, y + h)
        except Exception:
            bbox = (0, 0, 0, 0)
        out2.append(OCRToken(text=txt, bbox=bbox, conf=conf))
    return out2


def choose_best_ocr_engine() -> str:
    """
    “你给我一个最佳选择”的 PoC 策略：
    - 扫描件优先 PaddleOCR（若可用）
    - 否则用 tesseract
    """
    try:
        import paddleocr  # type: ignore  # noqa: F401

        return "paddleocr"
    except Exception:
        return "tesseract"
