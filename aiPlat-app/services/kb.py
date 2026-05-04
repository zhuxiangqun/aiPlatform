"""
Knowledge Base Service - KB API Client

只依赖 aiPlat-platform REST API（不依赖 aiPlat-core）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from .client import APIClient


class KBService:
    def __init__(self, client: APIClient):
        self._client = client

    def upload_and_ingest_pdf(self, *, collection_id: str, file_path: str) -> Dict[str, Any]:
        p = Path(file_path).expanduser()
        if not p.is_file():
            return {"error": f"file_not_found:{p}"}
        with p.open("rb") as f:
            files = {"file": (p.name, f, "application/pdf")}
            return self._client.post_multipart(f"/api/v1/kb/collections/{collection_id}/documents/upload", files=files)

    def query(self, *, collection_id: str, question: str, year: Optional[int] = None, limit: int = 50) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"collection_id": collection_id, "question": question, "limit": int(limit)}
        if year is not None:
            payload["year"] = int(year)
        return self._client.post("/api/v1/kb/query", payload)

    def download_asset(self, *, asset_url: str, out_path: str) -> str:
        """
        下载 /api/v1/kb/assets/... 到本地 out_path，返回实际写入路径。
        """
        url = f"{self._client.base_url}{asset_url}"
        resp = requests.get(url, headers={k: v for k, v in self._client._headers.items() if k.lower() != "content-type"}, timeout=60)
        resp.raise_for_status()
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(resp.content)
        return str(out)

    @staticmethod
    def write_html_report(*, kb_result: Dict[str, Any], out_dir: str) -> str:
        """
        生成一个简单的 HTML 报告：展示 items 与每条 citation 的页图 + bbox 高亮框。
        """
        outp = Path(out_dir)
        outp.mkdir(parents=True, exist_ok=True)
        report = outp / "kb_report.html"

        kb = kb_result.get("kb") if isinstance(kb_result.get("kb"), dict) else {}
        items = kb.get("items") if isinstance(kb.get("items"), list) else []
        cits = kb.get("citations") if isinstance(kb.get("citations"), list) else []

        def esc(s: Any) -> str:
            return (
                str(s)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )

        html = [
            "<!doctype html><html><head><meta charset='utf-8'/>",
            "<title>aiPlat KB Report</title>",
            "<style>",
            "body{font-family:Arial,Helvetica,sans-serif; margin:20px;} .item{margin:6px 0;}",
            ".imgwrap{position:relative; display:inline-block; border:1px solid #ddd; margin:10px 0;}",
            ".hl{position:absolute; border:2px solid rgba(255,0,0,0.8); background:rgba(255,0,0,0.15);}",
            ".meta{color:#666; font-size:12px; margin-bottom:6px;}",
            "</style></head><body>",
            f"<h1>KB Query Report</h1>",
            f"<h2>Items ({len(items)})</h2>",
        ]
        for it in items:
            if isinstance(it, dict):
                html.append(f"<div class='item'>- {esc(it.get('item'))}：{esc(it.get('amount_raw'))} {esc(it.get('unit'))}（{esc(it.get('year'))}）</div>")

        html.append(f"<h2>Citations ({len(cits)})</h2>")
        for i, c in enumerate(cits):
            if not isinstance(c, dict):
                continue
            bbox = c.get("bbox") or []
            if not (isinstance(bbox, list) and len(bbox) == 4):
                continue
            x1, y1, x2, y2 = [int(v) for v in bbox]
            img = c.get("local_asset") or c.get("asset_url") or ""
            html.append(f"<div class='meta'>[{i+1}] doc_id={esc(c.get('doc_id'))} page={esc(c.get('page_idx'))} item={esc((c.get('extra') or {}).get('item'))}</div>")
            html.append("<div class='imgwrap'>")
            html.append(f"<img src='{esc(img)}' style='max-width:1000px; height:auto;'/>")
            html.append(f"<div class='hl' style='left:{x1}px; top:{y1}px; width:{max(1,x2-x1)}px; height:{max(1,y2-y1)}px;'></div>")
            html.append("</div>")

        html.append("<hr/><pre>")
        html.append(esc(json.dumps(kb_result, ensure_ascii=False, indent=2)))
        html.append("</pre></body></html>")

        report.write_text("\n".join(html), encoding="utf-8")
        return str(report)


def get_kb_service(base_url: str = "http://localhost:8080", api_key: str = "", tenant_id: str = "") -> KBService:
    client = APIClient(base_url=base_url, api_key=api_key)
    if api_key:
        client.set_api_key(api_key)
    if tenant_id:
        client.set_tenant_id(tenant_id)
    return KBService(client)

