from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ingest import ingest_scanned_pdf
from .query import answer_question


def _cmd_pdf(args: argparse.Namespace) -> int:
    res = ingest_scanned_pdf(
        args.pdf,
        out_dir=args.out_dir,
        dpi=int(args.dpi),
        max_pages=int(args.max_pages) if args.max_pages else None,
        ocr_lang=str(args.lang),
        ocr_engine=str(args.ocr) if args.ocr else None,
    )
    payload = {
        "doc_id": res.doc_id,
        "pdf_path": res.pdf_path,
        "page_images": res.page_images,
        "pages": [
            {
                "page_idx": i,
                "token_count": len(res.ocr_by_page[i]),
                "number_count": len(res.numbers_by_page[i]),
            }
            for i in range(len(res.page_images))
        ],
    }
    out = Path(args.out_dir) / res.doc_id / "ingest_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nSaved: {out}")
    return 0


def _cmd_ask(args: argparse.Namespace) -> int:
    # Load ingest_summary.json to locate doc folder
    doc_dir = Path(args.doc_dir)
    if doc_dir.is_file() and doc_dir.name.endswith(".json"):
        summary = json.loads(doc_dir.read_text(encoding="utf-8"))
        doc_id = summary["doc_id"]
        doc_dir = doc_dir.parent
    else:
        doc_id = doc_dir.name

    # Reconstruct minimal IngestResult from files (PoC)
    # NOTE: For PoC we re-run ingest quickly to avoid persisting huge OCR results.
    # In production we will persist OCR and structured facts in DB.
    pdf_path = args.pdf
    if not pdf_path:
        # try infer
        s = doc_dir / "ingest_summary.json"
        if s.exists():
            summary = json.loads(s.read_text(encoding="utf-8"))
            pdf_path = summary.get("pdf_path")
    if not pdf_path:
        raise SystemExit("Missing --pdf (or ingest_summary.json missing pdf_path)")

    ing = ingest_scanned_pdf(
        pdf_path,
        out_dir=str(doc_dir.parent),
        dpi=int(args.dpi),
        max_pages=int(args.max_pages) if args.max_pages else None,
        ocr_lang=str(args.lang),
        ocr_engine=str(args.ocr) if args.ocr else None,
    )
    qa = answer_question(ing, args.question)
    payload = {
        "answer": qa.answer,
        "citations": [
            {
                "page_idx": c.page_idx,
                "asset_path": c.asset_path,
                "bbox": list(c.bbox) if c.bbox else None,
                "extra": c.extra,
            }
            for c in qa.citations
        ],
        "debug": qa.debug,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="aiPlat Multimodal KB PoC")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_pdf = sub.add_parser("ingest_pdf", help="Ingest scanned PDF (render+OCR+bbox)")
    p_pdf.add_argument("--pdf", required=True, help="PDF file path")
    p_pdf.add_argument("--out-dir", default="./kb_poc_out", help="Output directory")
    p_pdf.add_argument("--dpi", default="220")
    p_pdf.add_argument("--max-pages", default="")
    p_pdf.add_argument("--lang", default="zh")
    p_pdf.add_argument("--ocr", default="", help="paddleocr|tesseract|auto")
    p_pdf.set_defaults(func=_cmd_pdf)

    p_ask = sub.add_parser("ask", help="Ask a question over a PDF (PoC)")
    p_ask.add_argument("--doc-dir", required=True, help="Doc dir or ingest_summary.json")
    p_ask.add_argument("--pdf", default="", help="PDF file path (optional if summary contains it)")
    p_ask.add_argument("--question", required=True)
    p_ask.add_argument("--dpi", default="220")
    p_ask.add_argument("--max-pages", default="")
    p_ask.add_argument("--lang", default="zh")
    p_ask.add_argument("--ocr", default="", help="paddleocr|tesseract|auto")
    p_ask.set_defaults(func=_cmd_ask)

    args = p.parse_args()
    if getattr(args, "ocr", "") in ("", None, "auto"):
        args.ocr = ""
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

