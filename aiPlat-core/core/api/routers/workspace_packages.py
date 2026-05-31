"""Package management endpoints.

⚠ BOUNDARY BLUR (cross-layer audit): package registry management belongs in
aiPlat-platform's API layer. Currently served from core's FastAPI server.
Migration plan: move to platform/api/routers/.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from core.harness.kernel.runtime import get_kernel_runtime
from core.mcp.runtime_sync import sync_mcp_runtime
from core.workspace.reload import rebuild_workspace_managers_into_runtime

router = APIRouter()


def _rt():
    return get_kernel_runtime()


def _mgrs():
    rt = _rt()
    if not rt:
        return None, None
    return getattr(rt, "workspace_package_manager", None), getattr(rt, "package_manager", None)


@router.get("/workspace/packages")
async def list_workspace_packages(include_engine: bool = True) -> Dict[str, Any]:
    workspace_pkg_mgr, engine_pkg_mgr = _mgrs()
    items: List[Dict[str, Any]] = []
    if workspace_pkg_mgr:
        for p in workspace_pkg_mgr.list_packages():
            items.append({"name": p.name, "scope": p.scope, "version": p.version, "description": p.description, "resources": p.resources})
    if include_engine and engine_pkg_mgr:
        for p in engine_pkg_mgr.list_packages():
            items.append({"name": p.name, "scope": p.scope, "version": p.version, "description": p.description, "resources": p.resources})
    return {"items": items, "total": len(items)}


@router.get("/workspace/packages/{pkg_name}")
async def get_workspace_package(pkg_name: str) -> Dict[str, Any]:
    workspace_pkg_mgr, engine_pkg_mgr = _mgrs()
    p = workspace_pkg_mgr.get_package(pkg_name) if workspace_pkg_mgr else None
    if not p and engine_pkg_mgr:
        p = engine_pkg_mgr.get_package(pkg_name)
    if not p:
        raise HTTPException(status_code=404, detail="package_not_found")
    return {
        "name": p.name,
        "scope": p.scope,
        "version": p.version,
        "description": p.description,
        "manifest_path": p.manifest_path,
        "package_dir": p.package_dir,
        "resources": p.resources,
    }


@router.post("/workspace/packages/export")
async def export_workspace_package(data: Dict[str, Any]):
    """Export workspace assets as a redistributable plugin zip."""
    from pathlib import Path
    import shutil
    import tempfile
    import yaml

    name = str((data or {}).get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    resources = (data or {}).get("resources") or []
    if not isinstance(resources, list) or not resources:
        raise HTTPException(status_code=400, detail="resources list is required")

    workspace_root = Path.home() / ".aiplat"

    # Create temp package directory
    tmpdir = tempfile.mkdtemp(prefix=f"aiplat-plugin-{name}-")
    pkg_dir = Path(tmpdir) / name
    bundle_dir = pkg_dir / "bundle"

    try:
        # Generate package.yaml
        manifest = {
            "name": name,
            "type": "plugin",
            "version": str((data or {}).get("version") or "0.1.0"),
            "description": str((data or {}).get("description") or ""),
            "resources": resources,
        }
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "package.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )

        # Copy each resource into bundle/
        copied = 0
        for r in resources:
            kind = str(r.get("kind") or "").strip()
            rid = str(r.get("id") or "").strip()
            if not kind or not rid:
                continue

            src = workspace_root / f"{kind}s" / rid
            # For hooks, also try .py file directly
            if kind == "hook" and not src.exists():
                src = workspace_root / "hooks" / f"{rid}.py"
            if not src.exists():
                continue

            dst = bundle_dir / f"{kind}s" / rid
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())
            else:
                dst.mkdir(parents=True, exist_ok=True)
                for item in src.iterdir():
                    dest = dst / item.name
                    if item.is_dir():
                        if not dest.exists():
                            shutil.copytree(item, dest)
                    else:
                        shutil.copy2(item, dest)
            copied += 1

        if copied == 0:
            raise HTTPException(status_code=400, detail="No resources were found in workspace")

        # Create zip
        zip_path = Path(tmpdir) / f"{name}.zip"
        shutil.make_archive(
            str(zip_path.with_suffix("")), "zip",
            root_dir=str(pkg_dir.parent), base_dir=name
        )

        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=f"{name}.zip",
            headers={"X-Resources-Copied": str(copied)},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


@router.post("/workspace/packages")
async def create_workspace_package(request: Dict[str, Any]) -> Dict[str, Any]:
    workspace_pkg_mgr, _ = _mgrs()
    if not workspace_pkg_mgr:
        raise HTTPException(status_code=503, detail="Workspace package manager not available")
    name = str((request or {}).get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="missing_name")
    bundle = bool((request or {}).get("bundle", True))
    resources = (request or {}).get("resources") or []
    if not isinstance(resources, list):
        raise HTTPException(status_code=400, detail="resources_must_be_list")

    import yaml

    manifest = {
        "name": name,
        "version": str((request or {}).get("version") or "0.1.0"),
        "description": str((request or {}).get("description") or ""),
        "resources": resources,
    }
    info = workspace_pkg_mgr.upsert_package(manifest=manifest)

    # Optional: bundle resources into package/bundle/*
    if bundle:
        try:
            import shutil
            from pathlib import Path

            pkg_dir = Path(info.package_dir)
            bdir = pkg_dir / "bundle"
            if bdir.exists():
                shutil.rmtree(bdir, ignore_errors=True)
            (bdir / "agents").mkdir(parents=True, exist_ok=True)
            (bdir / "skills").mkdir(parents=True, exist_ok=True)
            (bdir / "mcps").mkdir(parents=True, exist_ok=True)
            (bdir / "hooks").mkdir(parents=True, exist_ok=True)

            repo_root = Path(__file__).resolve().parent.parent.parent  # aiPlat-core/core
            engine_agents = (repo_root / "engine" / "agents").resolve()
            engine_skills = (repo_root / "engine" / "skills").resolve()
            engine_mcps = (repo_root / "engine" / "mcps").resolve()
            wk_agents = (Path.home() / ".aiplat" / "agents").resolve()
            wk_skills = (Path.home() / ".aiplat" / "skills").resolve()
            wk_mcps = (Path.home() / ".aiplat" / "mcps").resolve()
            wk_hooks = (Path.home() / ".aiplat" / "hooks").resolve()

            for r in resources:
                if not isinstance(r, dict):
                    continue
                kind = str(r.get("kind") or "")
                rid = str(r.get("id") or "")
                scope = str(r.get("scope") or "engine").lower()
                if not kind or not rid:
                    continue
                if kind == "agent":
                    src = (engine_agents / rid) if scope == "engine" else (wk_agents / rid)
                    dst = bdir / "agents" / rid
                    if src.exists() and src.is_dir():
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                        r["bundled"] = True
                elif kind == "skill":
                    src = (engine_skills / rid) if scope == "engine" else (wk_skills / rid)
                    dst = bdir / "skills" / rid
                    if src.exists() and src.is_dir():
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                        r["bundled"] = True
                elif kind == "mcp":
                    src = (engine_mcps / rid) if scope == "engine" else (wk_mcps / rid)
                    dst = bdir / "mcps" / rid
                    if src.exists() and src.is_dir():
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                        r["bundled"] = True
                elif kind == "hook":
                    src = wk_hooks / f"{rid}.py"
                    dst = bdir / "hooks" / f"{rid}.py"
                    if src.exists() and src.is_file():
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
                        r["bundled"] = True

            (pkg_dir / "package.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
            workspace_pkg_mgr.reload()
        except Exception:
            pass

    return {"status": "upserted", "package": await get_workspace_package(name)}


@router.delete("/workspace/packages/{pkg_name}")
async def delete_workspace_package(pkg_name: str) -> Dict[str, Any]:
    workspace_pkg_mgr, _ = _mgrs()
    if not workspace_pkg_mgr:
        raise HTTPException(status_code=503, detail="Workspace package manager not available")
    ok = workspace_pkg_mgr.delete_package(pkg_name)
    if not ok:
        raise HTTPException(status_code=404, detail="package_not_found")
    return {"status": "deleted", "name": pkg_name}


@router.post("/workspace/packages/{pkg_name}/install")
async def install_workspace_package(pkg_name: str, http_request: Request, request: Dict[str, Any]) -> Dict[str, Any]:
    rt = _rt()
    if not rt:
        raise HTTPException(status_code=503, detail="Kernel runtime not available")
    allow_overwrite = bool((request or {}).get("allow_overwrite", False))
    workspace_pkg_mgr, engine_pkg_mgr = _mgrs()
    mgr = workspace_pkg_mgr if (workspace_pkg_mgr and workspace_pkg_mgr.get_package(pkg_name)) else engine_pkg_mgr
    if not mgr:
        raise HTTPException(status_code=404, detail="package_not_found")
    try:
        record = mgr.install(pkg_name=pkg_name, allow_overwrite=allow_overwrite)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Reload workspace managers from filesystem and re-sync MCP runtime.
    await rebuild_workspace_managers_into_runtime(runtime=rt)
    await sync_mcp_runtime(mcp_manager=getattr(rt, "mcp_manager", None), workspace_mcp_manager=getattr(rt, "workspace_mcp_manager", None))

    # Optional autosmoke for newly applied resources
    try:
        store = getattr(rt, "execution_store", None)
        scheduler = getattr(rt, "job_scheduler", None)
        if store is not None and scheduler is not None:
            from core.harness.smoke import enqueue_autosmoke

            tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")
            for it in (record.get("applied") or []):
                k = str(it.get("kind") or "")
                rid = str(it.get("id") or "")
                if k not in {"agent", "skill", "mcp"} or not rid:
                    continue
                await enqueue_autosmoke(
                    execution_store=store,
                    job_scheduler=scheduler,
                    resource_type=k,
                    resource_id=rid,
                    tenant_id=tenant_id or "ops_smoke",
                    actor_id=actor_id or "admin",
                    detail={"op": "package_install", "package": pkg_name},
                )
    except Exception:
        pass

    return {"status": "installed", "record": record}


@router.post("/workspace/packages/{pkg_name}/uninstall")
async def uninstall_workspace_package(pkg_name: str, request: Dict[str, Any]) -> Dict[str, Any]:
    rt = _rt()
    if not rt:
        raise HTTPException(status_code=503, detail="Kernel runtime not available")
    workspace_pkg_mgr, _ = _mgrs()
    if not workspace_pkg_mgr:
        raise HTTPException(status_code=503, detail="Workspace package manager not available")
    keep_modified = bool((request or {}).get("keep_modified", True))
    try:
        res = workspace_pkg_mgr.uninstall(pkg_name=pkg_name, keep_modified=keep_modified)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    await rebuild_workspace_managers_into_runtime(runtime=rt)
    await sync_mcp_runtime(mcp_manager=getattr(rt, "mcp_manager", None), workspace_mcp_manager=getattr(rt, "workspace_mcp_manager", None))
    return {"status": "uninstalled", "result": res}

