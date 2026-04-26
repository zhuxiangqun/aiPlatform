from __future__ import annotations

import hashlib
import os
import shutil
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from fastapi import APIRouter, HTTPException, Request

from core.api.utils.governance import gate_error_envelope, governance_links, ui_url
from core.governance.changeset import record_changeset
from core.governance.gating import new_change_id
from core.governance.verification import apply_autosmoke_result, mark_resource_pending
from core.harness.kernel.runtime import get_kernel_runtime
from core.mcp.prod_policy import runtime_env
from core.mcp.runtime_sync import sync_mcp_runtime
from core.schemas import PackageInstallRequest, PackagePublishRequest, PackageUninstallRequest
from core.workspace.reload import rebuild_workspace_managers_into_runtime


router = APIRouter()


def _rt():
    return get_kernel_runtime()


def _store():
    rt = _rt()
    return getattr(rt, "execution_store", None) if rt else None


def _approval_manager():
    rt = _rt()
    return getattr(rt, "approval_manager", None) if rt else None


def _job_scheduler():
    rt = _rt()
    return getattr(rt, "job_scheduler", None) if rt else None


def _pkg_managers():
    rt = _rt()
    if not rt:
        return None, None
    return getattr(rt, "workspace_package_manager", None), getattr(rt, "package_manager", None)


def _workspace_managers():
    rt = _rt()
    if not rt:
        return None, None, None
    return (
        getattr(rt, "workspace_agent_manager", None),
        getattr(rt, "workspace_skill_manager", None),
        getattr(rt, "workspace_mcp_manager", None),
    )


def _engine_mcp_manager():
    rt = _rt()
    return getattr(rt, "mcp_manager", None) if rt else None


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _packages_registry_dir() -> Path:
    return (Path.home() / ".aiplat" / "registry" / "packages").resolve()


def _is_approval_resolved_approved(approval_request_id: str) -> bool:
    mgr = _approval_manager()
    if not approval_request_id or not mgr:
        return False
    from core.harness.infrastructure.approval.types import RequestStatus

    r = mgr.get_request(str(approval_request_id))
    if not r:
        return False
    return r.status in (RequestStatus.APPROVED, RequestStatus.AUTO_APPROVED)


async def _require_package_approval(*, operation: str, user_id: str, details: str, metadata: Dict[str, Any]) -> str:
    from core.harness.infrastructure.approval.types import ApprovalContext, ApprovalRule, RuleType

    mgr = _approval_manager()
    if not mgr:
        raise HTTPException(status_code=503, detail="Approval manager not available")
    rule = ApprovalRule(
        rule_id=f"packages_{operation}",
        rule_type=RuleType.SENSITIVE_OPERATION,
        name=f"Packages {operation} 审批",
        description=f"{operation} package 需要审批",
        priority=1,
        metadata={"sensitive_operations": [f"packages:{operation}"]},
    )
    mgr.register_rule(rule)
    ctx = ApprovalContext(
        user_id=user_id,
        operation=f"packages:{operation}",
        operation_context={"details": details},
        metadata=metadata or {},
    )
    req = mgr.create_request(ctx, rule=rule)
    try:
        await mgr._persist(req)  # type: ignore[attr-defined]
    except Exception:
        pass
    return req.request_id


def _find_filesystem_package(pkg_name: str):
    workspace_pkg_mgr, engine_pkg_mgr = _pkg_managers()
    p = workspace_pkg_mgr.get_package(pkg_name) if workspace_pkg_mgr else None
    if not p and engine_pkg_mgr:
        p = engine_pkg_mgr.get_package(pkg_name)
    return p


def _build_bundle_dir_for_package(pkg: Dict[str, Any], out_bundle_dir: Path) -> None:
    """
    Build a normalized bundle directory for publishing.
    Prefers <package_dir>/bundle when present; otherwise materializes from source dirs.
    """
    pkg_dir = Path(str(pkg.get("package_dir") or ""))
    existing_bundle = pkg_dir / "bundle"
    if existing_bundle.exists() and existing_bundle.is_dir():
        shutil.copytree(existing_bundle, out_bundle_dir, dirs_exist_ok=True)
        return

    repo_root = Path(__file__).resolve().parent.parent.parent  # aiPlat-core/core
    engine_agents = (repo_root / "engine" / "agents").resolve()
    engine_skills = (repo_root / "engine" / "skills").resolve()
    engine_mcps = (repo_root / "engine" / "mcps").resolve()
    wk_agents = (Path.home() / ".aiplat" / "agents").resolve()
    wk_skills = (Path.home() / ".aiplat" / "skills").resolve()
    wk_mcps = (Path.home() / ".aiplat" / "mcps").resolve()
    wk_hooks = (Path.home() / ".aiplat" / "hooks").resolve()

    (out_bundle_dir / "agents").mkdir(parents=True, exist_ok=True)
    (out_bundle_dir / "skills").mkdir(parents=True, exist_ok=True)
    (out_bundle_dir / "mcps").mkdir(parents=True, exist_ok=True)
    (out_bundle_dir / "hooks").mkdir(parents=True, exist_ok=True)

    resources = pkg.get("resources") or []
    if not isinstance(resources, list):
        resources = []
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
            dst = out_bundle_dir / "agents" / rid
            if src.exists() and src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
        elif kind == "skill":
            src = (engine_skills / rid) if scope == "engine" else (wk_skills / rid)
            dst = out_bundle_dir / "skills" / rid
            if src.exists() and src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
        elif kind == "mcp":
            src = (engine_mcps / rid) if scope == "engine" else (wk_mcps / rid)
            dst = out_bundle_dir / "mcps" / rid
            if src.exists() and src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
        elif kind == "hook":
            src = wk_hooks / f"{rid}.py"
            dst = out_bundle_dir / "hooks" / f"{rid}.py"
            if src.exists() and src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)


@router.get("/packages/{pkg_name}/versions")
async def list_package_versions(pkg_name: str, limit: int = 100, offset: int = 0):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_package_versions(package_name=pkg_name, limit=limit, offset=offset)


@router.get("/packages/{pkg_name}/versions/{version}")
async def get_package_version(pkg_name: str, version: str):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    v = await store.get_package_version(package_name=pkg_name, version=version)
    if not v:
        raise HTTPException(status_code=404, detail="package_version_not_found")
    return v


@router.post("/packages/{pkg_name}/publish")
async def publish_package(pkg_name: str, http_request: Request, request: PackagePublishRequest):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    change_id = new_change_id()
    force_approval_in_prod = (os.getenv("AIPLAT_PACKAGES_FORCE_APPROVAL_IN_PROD", "true") or "true").strip().lower() in {"1", "true", "yes", "on"}
    if runtime_env() == "prod" and force_approval_in_prod:
        request.require_approval = True

    # Optional approval
    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_package_approval(
                operation="publish",
                user_id="admin",
                details=request.details or f"publish package {pkg_name}@{request.version}",
                metadata={"package_name": pkg_name, "version": request.version},
            )
            try:
                await record_changeset(
                    store=store,
                    name="packages.publish",
                    target_type="change",
                    target_id=change_id,
                    status="approval_required",
                    args={"package_name": pkg_name, "version": request.version},
                    approval_request_id=rid,
                    user_id=str(http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")),
                    tenant_id=str(http_request.headers.get("X-AIPLAT-TENANT-ID")) if http_request.headers.get("X-AIPLAT-TENANT-ID") else None,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": rid, "change_id": change_id, "links": governance_links(change_id=change_id, approval_request_id=rid)}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await record_changeset(
                    store=store,
                    name="packages.publish",
                    target_type="change",
                    target_id=change_id,
                    status="failed",
                    args={"package_name": pkg_name, "version": request.version},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                    user_id=str(http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")),
                    tenant_id=str(http_request.headers.get("X-AIPLAT-TENANT-ID")) if http_request.headers.get("X-AIPLAT-TENANT-ID") else None,
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    change_id=change_id,
                    approval_request_id=str(request.approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(request.approval_request_id)}],
                ),
            )

    pkg = _find_filesystem_package(pkg_name)
    if not pkg:
        raise HTTPException(status_code=404, detail="package_not_found")

    # Build archive from bundle
    reg_dir = _packages_registry_dir() / pkg_name
    reg_dir.mkdir(parents=True, exist_ok=True)
    archive_path = reg_dir / f"{request.version}.tar.gz"

    with tempfile.TemporaryDirectory(prefix="aiplat_pkg_publish_") as td:
        td_path = Path(td)
        root = td_path / "pkg"
        root.mkdir(parents=True, exist_ok=True)
        bundle_dir = root / "bundle"
        _build_bundle_dir_for_package(pkg.__dict__ if hasattr(pkg, "__dict__") else (pkg if isinstance(pkg, dict) else {}), bundle_dir)
        manifest = {
            "name": getattr(pkg, "name", pkg_name),
            "version": request.version,
            "description": getattr(pkg, "description", "") if hasattr(pkg, "description") else "",
            "resources": getattr(pkg, "resources", []) if hasattr(pkg, "resources") else (pkg.get("resources") if isinstance(pkg, dict) else []),
        }
        (root / "package.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
        with tarfile.open(str(archive_path), "w:gz") as tar:
            tar.add(str(root / "package.yaml"), arcname="package.yaml")
            tar.add(str(bundle_dir), arcname="bundle")

    sha = _sha256_file(archive_path)
    rec = await store.publish_package_version(
        package_name=pkg_name,
        version=request.version,
        manifest=manifest,
        artifact_path=str(archive_path),
        artifact_sha256=sha,
        approval_request_id=request.approval_request_id,
    )
    try:
        await record_changeset(
            store=store,
            name="packages.publish",
            target_type="change",
            target_id=change_id,
            status="success",
            args={"package_name": pkg_name, "version": request.version},
            result={"artifact_sha256": sha, "artifact_path": str(archive_path)},
            approval_request_id=request.approval_request_id,
            user_id=str(http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")),
            tenant_id=str(http_request.headers.get("X-AIPLAT-TENANT-ID")) if http_request.headers.get("X-AIPLAT-TENANT-ID") else None,
        )
    except Exception:
        pass
    return {"status": "published", "package_version": rec, "change_id": change_id, "links": governance_links(change_id=change_id)}


@router.post("/packages/{pkg_name}/install")
async def install_package(pkg_name: str, http_request: Request, request: PackageInstallRequest):
    rt = _rt()
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")

    workspace_pkg_mgr, engine_pkg_mgr = _pkg_managers()
    if not workspace_pkg_mgr:
        raise HTTPException(status_code=503, detail="Workspace package manager not available")

    change_id = new_change_id()
    version = (request.version or "").strip() or None
    force_approval_in_prod = (os.getenv("AIPLAT_PACKAGES_FORCE_APPROVAL_IN_PROD", "true") or "true").strip().lower() in {"1", "true", "yes", "on"}
    if runtime_env() == "prod" and force_approval_in_prod:
        request.require_approval = True

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_package_approval(
                operation="install",
                user_id="admin",
                details=request.details or f"install package {pkg_name}@{version or 'filesystem'}",
                metadata={"package_name": pkg_name, "version": version},
            )
            try:
                await record_changeset(
                    store=store,
                    name="packages.install",
                    target_type="change",
                    target_id=change_id,
                    status="approval_required",
                    args={"package_name": pkg_name, "version": version, "scope": str(request.scope or "workspace")},
                    approval_request_id=rid,
                    user_id=str(http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")),
                    tenant_id=str(http_request.headers.get("X-AIPLAT-TENANT-ID")) if http_request.headers.get("X-AIPLAT-TENANT-ID") else None,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": rid, "change_id": change_id, "links": governance_links(change_id=change_id, approval_request_id=rid)}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await record_changeset(
                    store=store,
                    name="packages.install",
                    target_type="change",
                    target_id=change_id,
                    status="failed",
                    args={"package_name": pkg_name, "version": version, "scope": str(request.scope or "workspace")},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                    user_id=str(http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")),
                    tenant_id=str(http_request.headers.get("X-AIPLAT-TENANT-ID")) if http_request.headers.get("X-AIPLAT-TENANT-ID") else None,
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    change_id=change_id,
                    approval_request_id=str(request.approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(request.approval_request_id)}],
                ),
            )

    applied_record: Dict[str, Any] = {}
    manifest: Dict[str, Any] = {}
    artifact_sha256: Optional[str] = None

    if version:
        v = await store.get_package_version(package_name=pkg_name, version=version)
        if not v:
            raise HTTPException(status_code=404, detail="package_version_not_found")
        artifact_path = v.get("artifact_path")
        if not artifact_path or not Path(artifact_path).exists():
            raise HTTPException(status_code=404, detail="package_artifact_missing")
        manifest = v.get("manifest") or {}
        artifact_sha256 = v.get("artifact_sha256")
        with tempfile.TemporaryDirectory(prefix="aiplat_pkg_install_") as td:
            td_path = Path(td)
            with tarfile.open(str(artifact_path), "r:gz") as tar:
                tar.extractall(path=str(td_path))
            bundle_dir = td_path / "bundle"
            if not bundle_dir.exists():
                nested = td_path / "pkg" / "bundle"
                bundle_dir = nested if nested.exists() else bundle_dir
            if not bundle_dir.exists():
                raise HTTPException(status_code=500, detail="invalid_package_artifact_bundle")
            applied_record = workspace_pkg_mgr.install_bundle(
                pkg_name=pkg_name,
                pkg_version=version,
                manifest=manifest,
                bundle_dir=bundle_dir,
                allow_overwrite=bool(request.allow_overwrite),
            )
    else:
        mgr = workspace_pkg_mgr if (workspace_pkg_mgr and workspace_pkg_mgr.get_package(pkg_name)) else engine_pkg_mgr
        if not mgr:
            raise HTTPException(status_code=404, detail="package_not_found")
        applied_record = mgr.install(pkg_name=pkg_name, allow_overwrite=bool(request.allow_overwrite))
        try:
            manifest = {"resources": (mgr.get_package(pkg_name).resources if mgr.get_package(pkg_name) else [])}
        except Exception:
            manifest = {}

    install_rec = await store.record_package_install(
        package_name=pkg_name,
        version=version,
        scope=str(request.scope or "workspace"),
        metadata={"record": applied_record, **(request.metadata or {}), "artifact_sha256": artifact_sha256},
        approval_request_id=request.approval_request_id,
    )

    # Reload managers from filesystem into runtime and sync MCP runtime
    if rt is not None:
        await rebuild_workspace_managers_into_runtime(runtime=rt)
    await sync_mcp_runtime(mcp_manager=_engine_mcp_manager(), workspace_mcp_manager=getattr(rt, "workspace_mcp_manager", None) if rt else None)

    # Verification: mark pending + enqueue autosmoke
    try:
        scheduler = _job_scheduler()
        if scheduler is not None:
            from core.harness.smoke import enqueue_autosmoke

            tenant_id = http_request.headers.get("X-AIPLAT-TENANT-ID", "ops_smoke")
            actor_id = http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")
            wam, wsm, wmm = _workspace_managers()
            for it in (applied_record.get("applied") or []):
                k = str(it.get("kind") or "")
                rid = str(it.get("id") or "")
                if k not in {"agent", "skill", "mcp"} or not rid:
                    continue

                await mark_resource_pending(resource_type=k, resource_id=rid, workspace_agent_manager=wam, workspace_skill_manager=wsm, workspace_mcp_manager=wmm)

                async def _on_complete(job_run: Dict[str, Any], *, _k=k, _rid=rid):
                    await apply_autosmoke_result(resource_type=_k, resource_id=_rid, job_run=job_run, workspace_agent_manager=wam, workspace_skill_manager=wsm, workspace_mcp_manager=wmm)

                await enqueue_autosmoke(
                    execution_store=store,
                    job_scheduler=scheduler,
                    resource_type=k,
                    resource_id=rid,
                    tenant_id=tenant_id or "ops_smoke",
                    actor_id=actor_id or "admin",
                    detail={"op": "package_install", "package": pkg_name, "version": version},
                    on_complete=_on_complete,
                )
    except Exception:
        pass

    # Change control record (best-effort)
    try:
        targets = []
        for it in (applied_record.get("applied") or []):
            if isinstance(it, dict) and it.get("kind") and it.get("id"):
                targets.append({"type": str(it.get("kind")), "id": str(it.get("id"))})
        await record_changeset(
            store=store,
            name="packages.install",
            target_type="change",
            target_id=change_id,
            status="success",
            args={"package_name": pkg_name, "version": version, "scope": str(request.scope or "workspace"), "targets": targets},
            result={"installed": True, "targets_count": len(targets)},
            approval_request_id=request.approval_request_id,
            user_id=str(http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")),
            tenant_id=str(http_request.headers.get("X-AIPLAT-TENANT-ID")) if http_request.headers.get("X-AIPLAT-TENANT-ID") else None,
        )
    except Exception:
        pass

    return {"status": "installed", "install": install_rec, "record": applied_record, "change_id": change_id, "links": governance_links(change_id=change_id)}


@router.get("/packages/installs")
async def list_package_installs(scope: Optional[str] = None, limit: int = 100, offset: int = 0):
    store = _store()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    return await store.list_package_installs(scope=scope, limit=limit, offset=offset)


@router.post("/packages/{pkg_name}/uninstall")
async def uninstall_package(pkg_name: str, http_request: Request, request: PackageUninstallRequest):
    store = _store()
    rt = _rt()
    if not store:
        raise HTTPException(status_code=503, detail="ExecutionStore not initialized")
    workspace_pkg_mgr, _ = _pkg_managers()
    if not workspace_pkg_mgr:
        raise HTTPException(status_code=503, detail="Workspace package manager not available")

    change_id = new_change_id()
    force_approval_in_prod = (os.getenv("AIPLAT_PACKAGES_FORCE_APPROVAL_IN_PROD", "true") or "true").strip().lower() in {"1", "true", "yes", "on"}
    if runtime_env() == "prod" and force_approval_in_prod:
        request.require_approval = True

    if request.require_approval:
        if not request.approval_request_id:
            rid = await _require_package_approval(
                operation="uninstall",
                user_id="admin",
                details=request.details or f"uninstall package {pkg_name}",
                metadata={"package_name": pkg_name},
            )
            try:
                await record_changeset(store=store, name="package_uninstall", target_type="package", target_id=str(pkg_name), status="approval_required", args={"package_name": pkg_name, "keep_modified": bool(request.keep_modified)}, approval_request_id=rid)
            except Exception:
                pass
            try:
                await record_changeset(
                    store=store,
                    name="packages.uninstall",
                    target_type="change",
                    target_id=change_id,
                    status="approval_required",
                    args={"package_name": pkg_name, "keep_modified": bool(request.keep_modified)},
                    approval_request_id=rid,
                    user_id=str(http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")),
                    tenant_id=str(http_request.headers.get("X-AIPLAT-TENANT-ID")) if http_request.headers.get("X-AIPLAT-TENANT-ID") else None,
                )
            except Exception:
                pass
            return {"status": "approval_required", "approval_request_id": rid, "change_id": change_id, "links": governance_links(change_id=change_id, approval_request_id=rid)}
        if not _is_approval_resolved_approved(request.approval_request_id):
            try:
                await record_changeset(
                    store=store,
                    name="packages.uninstall",
                    target_type="change",
                    target_id=change_id,
                    status="failed",
                    args={"package_name": pkg_name, "keep_modified": bool(request.keep_modified)},
                    error="not_approved",
                    approval_request_id=request.approval_request_id,
                    user_id=str(http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")),
                    tenant_id=str(http_request.headers.get("X-AIPLAT-TENANT-ID")) if http_request.headers.get("X-AIPLAT-TENANT-ID") else None,
                )
            except Exception:
                pass
            raise HTTPException(
                status_code=409,
                detail=gate_error_envelope(
                    code="not_approved",
                    message="not_approved",
                    change_id=change_id,
                    approval_request_id=str(request.approval_request_id),
                    next_actions=[{"type": "open_approvals", "label": "打开审批中心", "url": ui_url("/core/approvals"), "approval_request_id": str(request.approval_request_id)}],
                ),
            )

    try:
        res = workspace_pkg_mgr.uninstall(pkg_name=pkg_name, keep_modified=bool(request.keep_modified))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        await record_changeset(
            store=store,
            name="package_uninstall",
            target_type="package",
            target_id=str(pkg_name),
            args={"package_name": pkg_name, "keep_modified": bool(request.keep_modified)},
            result={"removed": len((res or {}).get("removed") or []), "kept": len((res or {}).get("kept") or [])},
            approval_request_id=request.approval_request_id,
        )
    except Exception:
        pass

    try:
        await record_changeset(
            store=store,
            name="packages.uninstall",
            target_type="change",
            target_id=change_id,
            status="success",
            args={"package_name": pkg_name, "keep_modified": bool(request.keep_modified)},
            result={"removed": len((res or {}).get("removed") or []), "kept": len((res or {}).get("kept") or [])},
            approval_request_id=request.approval_request_id,
            user_id=str(http_request.headers.get("X-AIPLAT-ACTOR-ID", "admin")),
            tenant_id=str(http_request.headers.get("X-AIPLAT-TENANT-ID")) if http_request.headers.get("X-AIPLAT-TENANT-ID") else None,
        )
    except Exception:
        pass

    if rt is not None:
        await rebuild_workspace_managers_into_runtime(runtime=rt)
    await sync_mcp_runtime(mcp_manager=_engine_mcp_manager(), workspace_mcp_manager=getattr(rt, "workspace_mcp_manager", None) if rt else None)

    return {
        "status": "uninstalled",
        "result": res,
        "approval_request_id": request.approval_request_id,
        "change_id": change_id,
        "links": governance_links(change_id=change_id, approval_request_id=str(request.approval_request_id) if request.approval_request_id else None),
    }

