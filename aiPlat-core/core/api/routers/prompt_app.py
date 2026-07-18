"""Prompt App Templates API — user-facing prompt templates organized by category."""
from __future__ import annotations
import json
import json as _json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from core.harness.kernel.runtime import get_kernel_runtime
from core.harness.syscalls.llm import sys_llm_generate
from core.schemas_prompt_app import (
    PromptAppTemplateCreate, PromptAppTemplateUpdate,
    PromptPreviewRequest, PromptPreviewTextRequest, PromptOptimizeRequest,
    PromptRunRequest,
    PromptCategoryCreate,
    PromptAppInstanceCreate, PromptAppInstanceUpdate,
)

router = APIRouter()
_log = logging.getLogger("aiplat.prompt_app")


async def _record_changeset(store, name: str, target_id: str, status: str = "success", args: dict = None, result: dict = None):
    try:
        from core.governance.changeset import record_changeset
        await record_changeset(
            store=store, name=name, target_type="prompt_app_template", target_id=target_id,
            status=status, args=args or {}, result=result, user_id="admin",
        )
    except Exception:
        _log.warning("变更集记录失败: name=%s target_id=%s", name, target_id, exc_info=True)


def _verify_template_signature(template_id: str) -> Optional[bool]:
    """Best-effort signature verification for prompt app templates."""
    try:
        from core.management.prompt_app_manager import PromptAppManager
        from core.security.skill_signature_gate import get_trusted_skill_pubkeys_map
        import asyncio
        mgr = PromptAppManager()
        tpl = mgr.get(template_id)
        if not tpl: return None
        prov = dict(tpl.metadata.get("provenance", {}))
        if not prov.get("signature"): return None
        rt = get_kernel_runtime()
        store = getattr(rt, "execution_store", None) if rt else None
        import concurrent.futures as _cf
        with _cf.ThreadPoolExecutor(max_workers=1) as _pool:
            trusted = _pool.submit(asyncio.run, get_trusted_skill_pubkeys_map(store)).result(timeout=10) if store else {}
        result = mgr.compute_signature_verification(tpl, trusted)
        return result.get("signature_verified")
    except Exception:
        return None


def _store():
    rt = get_kernel_runtime()
    return getattr(rt, "execution_store", None) if rt else None


def _new_id(prefix: str = "pt") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ── Template CRUD ──────────────────────────────────────────────────

@router.post("/prompts/app/templates/{template_id}/sign", response_model=Dict[str, Any])
async def sign_prompt_app_template(template_id: str, req: Dict[str, Any]):
    """Sign a prompt app template directory with Ed25519 key. Writes TEMPLATE.manifest.json."""
    private_key = str(req.get("private_key") or "").strip()
    private_key = private_key.replace("\\n", "\n")  # normalize escaped newlines from frontend
    if not private_key:
        raise HTTPException(status_code=400, detail="private_key is required")

    try:
        from core.management.prompt_app_manager import PromptAppManager
        mgr = PromptAppManager()
    except Exception:
        raise HTTPException(status_code=503, detail="PromptAppManager not available")

    tpl = mgr.get(template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="template not found")

    try:
        from core.harness.infrastructure.crypto.signature import sign_skill as sign_tpl

        tmpl_dir = Path(tpl.metadata.get("filesystem", {}).get("template_dir") or "")
        if not tmpl_dir or not tmpl_dir.exists():
            raise HTTPException(status_code=500, detail="Template directory not found")

        mgr._enrich_provenance_and_integrity(tpl.metadata, template_dir=tmpl_dir)
        integ = tpl.metadata.get("integrity", {})
        bundle_sha256 = integ.get("bundle_sha256", "")
        if not bundle_sha256:
            raise HTTPException(status_code=500, detail="Could not compute bundle_sha256")

        version = req.get("version") or tpl.version or "0.1.0"
        signature = sign_tpl(private_key=private_key, skill_id=template_id, version=str(version), bundle_sha256=bundle_sha256)

        manifest_path = tmpl_dir / "TEMPLATE.manifest.json"
        manifest = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                _log.warning("无法解析 manifest JSON: %s", manifest_path, exc_info=True)
        manifest["signature"] = signature
        manifest["version"] = str(version)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        mgr._enrich_provenance_and_integrity(tpl.metadata, template_dir=tmpl_dir)

    except HTTPException: raise
    except ValueError as e: raise HTTPException(status_code=400, detail=f"Invalid private key: {str(e)}")
    except Exception as e: raise HTTPException(status_code=500, detail=f"Signing failed: {str(e)}")

    return {"status": "signed", "bundle_sha256": bundle_sha256, "version": str(version), "signature": signature}
