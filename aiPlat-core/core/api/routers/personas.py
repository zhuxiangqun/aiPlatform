from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from fastapi import APIRouter, HTTPException, Request

from core.api.deps.rbac import rbac_guard, actor_from_http
from core.harness.kernel.runtime import get_kernel_runtime

router = APIRouter()


def _rt():
    return get_kernel_runtime()


def _store():
    rt = _rt()
    return getattr(rt, "execution_store", None) if rt else None

def _json_loads(s: Optional[str]) -> Dict[str, Any]:
    if not isinstance(s, str) or not s.strip():
        return {}
    try:
        import json as _json

        out = _json.loads(s)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def _parse_front_matter(md: str) -> tuple[Dict[str, Any], str]:
    if not isinstance(md, str) or not md.strip():
        return {}, ""
    m = _FRONT_MATTER_RE.match(md)
    if not m:
        return {}, md
    fm_raw = m.group(1) or ""
    body = md[m.end() :] if m.end() < len(md) else ""
    try:
        fm = yaml.safe_load(fm_raw) or {}
    except Exception:
        fm = {}
    return (fm if isinstance(fm, dict) else {}), body


def _slug(s: str) -> str:
    s = str(s or "").strip().lower()
    s = re.sub(r"[^a-z0-9._:-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "unknown"


def _extract_section(md_body: str, *, title_contains: str, max_chars: int = 4000) -> str:
    """
    Extract a markdown section by heading keyword (best-effort).
    Looks for lines starting with '##' that contain the keyword, and returns until next '## '.
    """
    if not isinstance(md_body, str) or not md_body:
        return ""
    lines = md_body.splitlines()
    start = None
    key = str(title_contains).strip().lower()
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("##") and key in ln.lower():
            start = i + 1
            break
    if start is None:
        return ""
    out_lines = []
    for j in range(start, len(lines)):
        ln = lines[j]
        if ln.lstrip().startswith("##"):
            break
        out_lines.append(ln)
        if sum(len(x) + 1 for x in out_lines) > max_chars:
            break
    return ("\n".join(out_lines)).strip()[:max_chars]


@router.get("/personas")
async def list_personas(limit: int = 100, offset: int = 0, q: Optional[str] = None, category: Optional[str] = None, source: Optional[str] = None):
    """
    Read-only Personas list (stored in prompt_templates with metadata.type=persona).
    Filtering is best-effort by scanning prompt_templates metadata_json.
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    # overscan to compensate for filtering
    scan_limit = min(max(int(limit) * 10, 200), 2000)
    rows = await store.list_prompt_templates(limit=scan_limit, offset=int(offset))
    items = rows.get("items") or []
    out = []
    qq = str(q or "").strip().lower()
    cc = str(category or "").strip().lower()
    ss = str(source or "").strip().lower()
    for it in items:
        if not isinstance(it, dict):
            continue
        md = _json_loads(it.get("metadata_json"))
        if str((md.get("type") if isinstance(md, dict) else "") or "").strip().lower() != "persona":
            continue
        if ss and str(md.get("source") or "").strip().lower() != ss:
            continue
        if cc and str(md.get("category") or "").strip().lower() != cc:
            continue
        name = str(it.get("name") or "")
        tid = str(it.get("template_id") or "")
        disp = md.get("display") if isinstance(md, dict) else None
        vibe = (disp.get("vibe") if isinstance(disp, dict) else None) or (md.get("frontmatter", {}).get("vibe") if isinstance(md.get("frontmatter"), dict) else None)
        if qq:
            hay = " ".join(
                [
                    tid.lower(),
                    name.lower(),
                    str((disp.get("description") if isinstance(disp, dict) else "") or "").lower(),
                    str(vibe or "").lower(),
                    str(md.get("category") or "").lower(),
                ]
            )
            if qq not in hay:
                continue
        out.append(
            {
                "template_id": tid,
                "name": name,
                "version": it.get("version"),
                "category": md.get("category") if isinstance(md, dict) else None,
                "source": md.get("source") if isinstance(md, dict) else None,
                "display": disp if isinstance(disp, dict) else {},
                "sections": md.get("sections") if isinstance(md.get("sections"), dict) else {},
                "updated_at": it.get("updated_at"),
            }
        )
        if len(out) >= int(limit):
            break
    return {"items": out, "limit": int(limit), "offset": int(offset), "returned": len(out)}


@router.get("/personas/{template_id}")
async def get_persona(template_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    tpl = await store.get_prompt_template(template_id=str(template_id))
    if not tpl:
        raise HTTPException(status_code=404, detail="not_found")
    md = _json_loads(tpl.get("metadata_json"))
    if str(md.get("type") or "").strip().lower() != "persona":
        raise HTTPException(status_code=404, detail="not_a_persona")
    out = dict(tpl)
    out["metadata"] = md
    out["display"] = md.get("display") if isinstance(md.get("display"), dict) else {}
    out["sections"] = md.get("sections") if isinstance(md.get("sections"), dict) else {}
    return out


@router.post("/personas/import/agency-agents")
async def import_agency_agents(request: dict, http_request: Request):
    """
    Import agency-agents markdown personas into prompt_templates.

    Body:
      {
        "root": "/abs/path/to/agency-agents",
        "categories": ["engineering","design"],   // optional; default = all directories under root
        "prefix": "persona:agency"               // optional
      }
    """
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    body = dict(request or {}) if isinstance(request, dict) else {}
    actor = actor_from_http(http_request, body)
    deny = await rbac_guard(
        http_request=http_request,
        payload=body,
        action="update",
        resource_type="prompt_template",
        resource_id="persona_import",
        run_id=None,
    )
    if deny:
        return deny

    root = body.get("root")
    if not isinstance(root, str) or not root.strip():
        raise HTTPException(status_code=400, detail="missing_root")
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise HTTPException(status_code=400, detail="root_not_found")

    prefix = str(body.get("prefix") or "persona:agency").strip() or "persona:agency"
    cats = body.get("categories")
    categories = [str(x).strip() for x in cats] if isinstance(cats, list) else []
    categories = [c for c in categories if c]

    # Determine category folders
    if not categories:
        categories = [p.name for p in root_path.iterdir() if p.is_dir() and not p.name.startswith(".")]

    imported = []
    skipped = 0

    for cat in categories:
        cat_dir = (root_path / cat).resolve()
        if not cat_dir.exists() or not cat_dir.is_dir():
            continue
        for md_path in sorted(cat_dir.glob("*.md")):
            raw = md_path.read_text(encoding="utf-8")
            fm, body_md = _parse_front_matter(raw)
            name = str(fm.get("name") or md_path.stem)
            desc = str(fm.get("description") or "")
            vibe = str(fm.get("vibe") or "")
            template_id = f"{prefix}:{_slug(cat)}:{_slug(md_path.stem)}"

            # Use body_md as prompt; fallback to full raw if body empty.
            prompt = (body_md or "").strip()
            if not prompt:
                prompt = raw.strip()
            if not prompt:
                skipped += 1
                continue

            meta = {
                "type": "persona",
                "source": "agency-agents",
                "source_path": str(md_path),
                "category": str(cat),
                "frontmatter": fm,
                "display": {"name": name, "description": desc, "vibe": vibe},
                "sections": {
                    "success_metrics": _extract_section(prompt, title_contains="success metrics"),
                    "critical_rules": _extract_section(prompt, title_contains="critical rules"),
                    "core_mission": _extract_section(prompt, title_contains="core mission"),
                },
                "imported_by": {"actor_id": actor.get("actor_id"), "actor_role": actor.get("actor_role")},
            }
            await store.upsert_prompt_template(template_id=template_id, name=name, template=prompt, metadata=meta, increment_version=True)
            imported.append({"template_id": template_id, "name": name, "category": str(cat), "path": str(md_path)})

    return {"status": "ok", "root": str(root_path), "count": len(imported), "skipped": skipped, "items": imported[:200]}
