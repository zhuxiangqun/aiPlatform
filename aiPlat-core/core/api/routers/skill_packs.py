from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from core.api.utils.governance import governance_links
from core.governance.changeset import record_changeset
from core.governance.gating import autosmoke_enforce, gate_with_change_control, new_change_id
from core.harness.kernel.runtime import get_kernel_runtime
from core.schemas import SkillPackCreateRequest, SkillPackInstallRequest, SkillPackPublishRequest, SkillPackUpdateRequest


router = APIRouter()


def _rt():
    return get_kernel_runtime()


def _store():
    rt = _rt()
    return getattr(rt, "execution_store", None) if rt else None


def _mgrs():
    rt = _rt()
    if not rt:
        return None, None, None, None, None
    return (
        getattr(rt, "workspace_agent_manager", None),
        getattr(rt, "workspace_skill_manager", None),
        getattr(rt, "workspace_mcp_manager", None),
        getattr(rt, "skill_manager", None),
        getattr(rt, "mcp_manager", None),
    )


def _normalize_skill_pack_manifest(manifest: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(manifest or {}) if isinstance(manifest, dict) else {}
    # Normalize skills list into [{id,...}] shape.
    skills = out.get("skills", [])
    if skills is None:
        skills = []
    if not isinstance(skills, list):
        raise HTTPException(status_code=400, detail="manifest.skills must be an array")

    norm_skills: List[Dict[str, Any]] = []
    for it in skills:
        if isinstance(it, str):
            sid = it.strip()
            if not sid:
                raise HTTPException(status_code=400, detail="manifest.skills contains empty string id")
            if " " in sid:
                raise HTTPException(status_code=400, detail=f"invalid skill id (contains spaces): {sid}")
            norm_skills.append({"id": sid})
            continue
        if isinstance(it, dict):
            sid = str(it.get("id") or it.get("skill_id") or "").strip()
            if not sid:
                raise HTTPException(status_code=400, detail="manifest.skills contains an item without id")
            if " " in sid:
                raise HTTPException(status_code=400, detail=f"invalid skill id (contains spaces): {sid}")
            spec = dict(it)
            spec["id"] = sid
            norm_skills.append(spec)
            continue
        raise HTTPException(status_code=400, detail="manifest.skills items must be string or object")

    out["skills"] = norm_skills
    return out


@router.get("/skill-packs")
async def list_skill_packs(limit: int = 100, offset: int = 0):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_skill_packs(limit=limit, offset=offset)


@router.post("/skill-packs")
async def create_skill_pack(request: SkillPackCreateRequest):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    manifest = _normalize_skill_pack_manifest(request.manifest)
    return await store.create_skill_pack({"name": request.name, "description": request.description, "manifest": manifest})


@router.get("/skill-packs/{pack_id}")
async def get_skill_pack(pack_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    pack = await store.get_skill_pack(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Skill pack not found")
    return pack


@router.put("/skill-packs/{pack_id}")
async def update_skill_pack(pack_id: str, request: SkillPackUpdateRequest):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    patch = request.model_dump(exclude_unset=True)
    if "manifest" in patch:
        patch["manifest"] = _normalize_skill_pack_manifest(patch.get("manifest"))
    updated = await store.update_skill_pack(pack_id, patch)
    if not updated:
        raise HTTPException(status_code=404, detail="Skill pack not found")
    return updated


@router.delete("/skill-packs/{pack_id}")
async def delete_skill_pack(pack_id: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    ok = await store.delete_skill_pack(pack_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Skill pack not found")
    return {"status": "deleted", "id": pack_id}


@router.post("/skill-packs/{pack_id}/publish")
async def publish_skill_pack(pack_id: str, request: SkillPackPublishRequest):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    change_id = new_change_id()
    # Validate manifest before publishing a version snapshot.
    pack = await store.get_skill_pack(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Skill pack not found")
    _normalize_skill_pack_manifest(pack.get("manifest"))

    # Gate: referenced skills should be verified when enforcement enabled.
    try:
        manifest = _normalize_skill_pack_manifest(pack.get("manifest") if isinstance(pack, dict) else {})
        skills = manifest.get("skills") if isinstance(manifest, dict) else []
        targets: list[tuple[str, str]] = []
        if isinstance(skills, list):
            for it in skills:
                if not isinstance(it, dict):
                    continue
                sid = str(it.get("id") or "").strip()
                if sid:
                    targets.append(("skill", sid))
        if targets and autosmoke_enforce(store=store):
            wam, wsm, wmm, sm, mm = _mgrs()
            change_id = await gate_with_change_control(
                store=store,
                operation="skill_pack.publish",
                targets=list({(t[0], t[1]) for t in targets}),
                actor={"actor_id": "admin"},
                workspace_agent_manager=wam,
                workspace_skill_manager=wsm,
                skill_manager=sm,
                workspace_mcp_manager=wmm,
                mcp_manager=mm,
            )
    except HTTPException:
        raise
    except Exception:
        pass

    try:
        res = await store.publish_skill_pack_version(pack_id=pack_id, version=request.version)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    try:
        await record_changeset(
            store=store,
            name="skill_pack.publish",
            target_type="change",
            target_id=change_id,
            status="success",
            args={"pack_id": pack_id, "version": request.version},
            user_id="admin",
        )
    except Exception:
        pass
    return {**(res or {}), "change_id": change_id, "links": governance_links(change_id=change_id)}


@router.get("/skill-packs/{pack_id}/versions")
async def list_skill_pack_versions(pack_id: str, limit: int = 100, offset: int = 0):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_skill_pack_versions(pack_id=pack_id, limit=limit, offset=offset)


@router.post("/skill-packs/{pack_id}/install")
async def install_skill_pack(pack_id: str, request: SkillPackInstallRequest):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    change_id = new_change_id()

    # Gate: referenced skills should be verified before install when enforcement enabled.
    try:
        manifest = None
        if request.version:
            vrec = await store.get_skill_pack_version(pack_id=pack_id, version=request.version)
            manifest = vrec.get("manifest") if isinstance(vrec, dict) else None
        if manifest is None:
            pack = await store.get_skill_pack(pack_id)
            manifest = pack.get("manifest") if isinstance(pack, dict) else None
        manifest = _normalize_skill_pack_manifest(manifest if isinstance(manifest, dict) else {})
        skills = manifest.get("skills") if isinstance(manifest, dict) else []
        targets: list[tuple[str, str]] = []
        if isinstance(skills, list):
            for it in skills:
                if not isinstance(it, dict):
                    continue
                sid = str(it.get("id") or "").strip()
                if sid:
                    targets.append(("skill", sid))
        if targets and autosmoke_enforce(store=store):
            wam, wsm, wmm, sm, mm = _mgrs()
            change_id = await gate_with_change_control(
                store=store,
                operation="skill_pack.install",
                targets=list({(t[0], t[1]) for t in targets}),
                actor={"actor_id": "admin"},
                workspace_agent_manager=wam,
                workspace_skill_manager=wsm,
                skill_manager=sm,
                workspace_mcp_manager=wmm,
                mcp_manager=mm,
            )
    except HTTPException:
        raise
    except Exception:
        pass

    try:
        install = await store.install_skill_pack(pack_id=pack_id, version=request.version, scope=request.scope, metadata=request.metadata or {})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Apply install (best-effort): materialize/enable skills declared by manifest.
    applied: List[Dict[str, Any]] = []
    try:
        manifest2 = None
        if request.version:
            vrec = await store.get_skill_pack_version(pack_id=pack_id, version=request.version)
            manifest2 = vrec.get("manifest") if isinstance(vrec, dict) else None
        if manifest2 is None:
            pack = await store.get_skill_pack(pack_id)
            manifest2 = pack.get("manifest") if isinstance(pack, dict) else None
        manifest2 = _normalize_skill_pack_manifest(manifest2 if isinstance(manifest2, dict) else {})
        skills2 = manifest2.get("skills") if isinstance(manifest2, dict) else []
        if not isinstance(skills2, list):
            skills2 = []

        scope = str(request.scope or "workspace")
        rt = _rt()
        target_mgr = (getattr(rt, "workspace_skill_manager", None) if rt else None) if scope == "workspace" else (getattr(rt, "skill_manager", None) if rt else None)
        for item in skills2:
            try:
                if not isinstance(item, dict):
                    continue
                sid = str(item.get("id") or "").strip()
                spec = dict(item)
                if not sid:
                    continue
                if not target_mgr:
                    applied.append({"skill_id": sid, "status": "skipped", "reason": "skill_manager_unavailable"})
                    continue
                if scope == "workspace":
                    try:
                        await target_mgr.import_skill_from_pack(  # type: ignore[attr-defined]
                            skill_id=sid,
                            display_name=spec.get("display_name") or spec.get("name"),
                            category=spec.get("category") or "general",
                            description=spec.get("description") or "",
                            version=spec.get("version") or "1.0.0",
                            sop_markdown=spec.get("sop_markdown") or spec.get("sop") or "",
                            pack_metadata={"pack_id": pack_id, "version": request.version, "scope": scope},
                        )
                    except Exception as e:
                        applied.append({"skill_id": sid, "status": "skipped", "reason": str(e)})
                        continue
                ok = await target_mgr.enable_skill(sid)  # type: ignore[attr-defined]
                if not ok:
                    ok = await target_mgr.restore_skill(sid)  # type: ignore[attr-defined]
                applied.append({"skill_id": sid, "status": "enabled" if ok else "skipped"})
            except Exception as e:
                applied.append({"skill_id": str(item), "status": "skipped", "reason": str(e)})
    except Exception:
        applied = applied or []

    try:
        await record_changeset(
            store=store,
            name="skill_pack.install",
            target_type="change",
            target_id=change_id,
            status="success",
            args={"pack_id": pack_id, "version": request.version, "scope": request.scope},
            user_id="admin",
        )
    except Exception:
        pass
    return {"install": install, "applied": applied, "change_id": change_id, "links": governance_links(change_id=change_id)}


@router.get("/skill-packs/installs")
async def list_skill_pack_installs(scope: Optional[str] = None, limit: int = 100, offset: int = 0):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_skill_pack_installs(scope=scope, limit=limit, offset=offset)

