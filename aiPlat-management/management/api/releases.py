"""
发行管理 + 一键部署 API

- GET  /releases         列出所有版本
- POST /releases         创建新版本 (git tag + push)
- POST /deploy           执行 deploy.sh
- GET  /deploy/status    查询部署状态
"""
import asyncio
import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter(prefix="", tags=["releases"])

_deploy_log: list[str] = []
_deploy_running = False
_deploy_lock = threading.Lock()
_deploy_result: dict = {}


def _get_project_root() -> str:
    return os.environ.get(
        "AIPLAT_PROJECT_ROOT",
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    )


@router.get("/releases")
async def list_releases():
    """获取 git tag 版本列表"""
    root = _get_project_root()
    try:
        result = subprocess.run(
            ["git", "tag", "--sort=-creatordate", "--format=%(refname:strip=2)|%(creatordate:short)|%(objectname:short)|%(subject)"],
            capture_output=True, text=True, cwd=root, timeout=10,
        )
        if result.returncode != 0:
            return {"releases": [], "error": result.stderr.strip()}

        releases = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 3)
            releases.append({
                "version": parts[0] if len(parts) > 0 else "",
                "date": parts[1] if len(parts) > 1 else "",
                "commit": parts[2] if len(parts) > 2 else "",
                "message": parts[3] if len(parts) > 3 else "",
            })
        return {"releases": releases}
    except Exception as e:
        return {"releases": [], "error": str(e)}


@router.post("/releases")
async def create_release(version: str = Query(...), message: str = Query("")):
    """打 git tag 并 push"""
    if not version:
        raise HTTPException(status_code=400, detail="version is required")

    root = _get_project_root()
    try:
        # git tag
        tag_cmd = ["git", "tag", version]
        if message:
            tag_cmd += ["-m", message]
        r1 = subprocess.run(tag_cmd, capture_output=True, text=True, cwd=root, timeout=10)
        if r1.returncode != 0:
            raise HTTPException(status_code=500, detail=f"git tag failed: {r1.stderr.strip()}")

        # git push
        r2 = subprocess.run(
            ["git", "push", "origin", version],
            capture_output=True, text=True, cwd=root, timeout=30,
        )
        if r2.returncode != 0:
            raise HTTPException(status_code=500, detail=f"git push failed: {r2.stderr.strip()}")

        return {"ok": True, "version": version, "message": message}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deploy/build")
async def build_release(ids: str = Query("")):
    """执行 build-release.sh, 构建 Docker 镜像并打包 zip。
    可选 ids 参数: "agent:site_tester,skill:my_skill" 只导出指定内容"""
    global _deploy_running, _deploy_log
    with _deploy_lock:
        if _deploy_running:
            return {"ok": False, "message": "构建已在进行中"}
        _deploy_running = True
        _deploy_log = []
        _deploy_result = {}

    root = _get_project_root()
    script = os.path.join(root, "scripts", "build-release.sh")
    build_ids = ids.strip()

    async def _run_build():
        global _deploy_running, _deploy_log, _deploy_result
        try:
            cmd = ["bash", script]
            if build_ids:
                cmd.append(build_ids)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=root,
            )
            last_line = ""
            async for line in proc.stdout:
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    _deploy_log.append(text)
                    last_line = text
            await proc.wait()
            _deploy_result["zip_path"] = last_line if last_line.endswith(".zip") else ""
        except Exception as e:
            _deploy_log.append(f"ERROR: {e}")
        finally:
            _deploy_running = False

    asyncio.create_task(_run_build())
    return {"ok": True, "message": "构建已启动"}


@router.get("/deploy/status")
async def deploy_status():
    """查询部署状态和日志"""
    return {
        "running": _deploy_running,
        "log": _deploy_log[-100:] if len(_deploy_log) > 100 else _deploy_log,
        "zip_path": _deploy_result.get("zip_path", ""),
    }


@router.get("/deploy/download")
async def download_build(path: str = Query("")):
    """下载构建产物 zip 文件"""
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=os.path.basename(path), media_type="application/zip")


@router.get("/deploy/history")
async def deploy_history():
    """列出项目根目录下所有 deploy-kit-*.zip 文件"""
    root = _get_project_root()
    files = []
    for f in sorted(Path(root).glob("deploy-kit-*.zip"), reverse=True):
        st = f.stat()
        files.append({
            "name": f.name,
            "path": str(f),
            "size": st.st_size,
            "size_mb": round(st.st_size / 1024 / 1024, 1),
            "created": datetime.fromtimestamp(st.st_ctime, timezone.utc).isoformat(),
        })
    return {"files": files}


@router.delete("/deploy/delete")
async def delete_build(path: str = Query("")):
    """删除指定的部署包 zip 文件"""
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    if "deploy-kit-" not in path or not path.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only deploy-kit-*.zip files can be deleted")
    try:
        os.remove(path)
        return {"ok": True, "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export-workspace")
async def export_workspace():
    """导出 workspace 配置为种子文件"""
    root = _get_project_root()
    script = os.path.join(root, "scripts", "export_workspace.py")
    try:
        result = subprocess.run(
            ["python3", script],
            capture_output=True, text=True, cwd=root, timeout=30,
        )
        return {"ok": result.returncode == 0, "output": result.stdout.strip(), "error": result.stderr.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}
