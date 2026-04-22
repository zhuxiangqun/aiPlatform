"""
Sync the auto-eval design doc's API section from OpenAPI snapshot.

This is the "final form" anti-drift mechanism:
  Code (OpenAPI) -> snapshot json -> generated markdown section -> design doc.

Usage:
  python -m core.tools.sync_eval_docs

It will update docs/design/evaluation/auto-eval-and-regression.md between markers:
  <!-- OPENAPI_EVAL_BEGIN -->
  <!-- OPENAPI_EVAL_END -->
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _as_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _load_snapshot(repo_root: Path) -> Dict[str, Any]:
    p = repo_root / "docs" / "design" / "evaluation" / "openapi-eval.snapshot.json"
    return json.loads(p.read_text(encoding="utf-8", errors="ignore"))


def render_openapi_section(snapshot: Dict[str, Any]) -> str:
    """
    Render markdown section for API surface.
    """
    endpoints = _as_dict(snapshot.get("endpoints"))
    keys = sorted(endpoints.keys())

    lines: List[str] = []
    lines.append("### 5.X OpenAPI 生成的接口面（防脱节｜As-Is）")
    lines.append("")
    lines.append("> 本段落由 `docs/design/evaluation/openapi-eval.snapshot.json` 自动生成，请勿手工编辑。")
    lines.append("")
    lines.append("| Endpoint | 请求字段（JSON body） | 必填 |")
    lines.append("|---|---|---|")
    for k in keys:
        info = _as_dict(endpoints.get(k))
        if info.get("missing"):
            lines.append(f"| `{k}` | ❌ missing | - |")
            continue
        props = info.get("request_properties") or []
        req = info.get("request_required") or []
        props_s = ", ".join([f"`{p}`" for p in props]) if props else "-"
        req_s = ", ".join([f"`{p}`" for p in req]) if req else "-"
        lines.append(f"| `{k}` | {props_s} | {req_s} |")
    lines.append("")
    lines.append("更新方式：")
    lines.append("")
    lines.append("1) 更新快照：`python -m core.tools.export_eval_openapi > docs/design/evaluation/openapi-eval.snapshot.json`")
    lines.append("2) 同步文档：`python -m core.tools.sync_eval_docs`")
    return "\n".join(lines).rstrip() + "\n"


def sync_doc(repo_root: Path) -> Tuple[bool, str]:
    doc_path = repo_root / "docs" / "design" / "evaluation" / "auto-eval-and-regression.md"
    text = doc_path.read_text(encoding="utf-8", errors="ignore")
    begin = "<!-- OPENAPI_EVAL_BEGIN -->"
    end = "<!-- OPENAPI_EVAL_END -->"
    if begin not in text or end not in text:
        return False, "missing markers in doc"

    snapshot = _load_snapshot(repo_root)
    section = render_openapi_section(snapshot)

    pre, rest = text.split(begin, 1)
    _, post = rest.split(end, 1)
    new_text = pre + begin + "\n\n" + section + "\n" + end + post
    if new_text == text:
        return True, "no_change"
    doc_path.write_text(new_text, encoding="utf-8")
    return True, "updated"


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    ok, msg = sync_doc(repo_root)
    if not ok:
        raise SystemExit(msg)
    print(msg)


if __name__ == "__main__":
    main()

