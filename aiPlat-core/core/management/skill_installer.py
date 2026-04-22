"""
Skill Installer (workspace scope).

Goal:
- Install third-party open-source skills into workspace skill directories safely.
- Support git (url+ref), local directory path, and local zip file path.

Security posture (production):
- Default allowlist for git hosts (env AIPLAT_SKILL_INSTALL_GIT_ALLOWLIST_HOSTS, default "github.com").
- Only allow https:// and file:// for git URLs.
- For git installs, ref is REQUIRED (tag/commit) to avoid supply-chain drift.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse


_REF_RE = re.compile(r"^[A-Za-z0-9._/\-]{1,128}$")


def _run(cmd: List[str], *, cwd: Optional[str] = None, timeout_s: int = 60) -> str:
    cp = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout_s)
    if cp.returncode != 0:
        msg = (cp.stderr or cp.stdout or "").strip()
        raise RuntimeError(msg[:1000] if msg else f"command_failed:{cmd[0]}")
    return (cp.stdout or "").strip()


def _allowlisted_git_url(url: str) -> bool:
    u = urlparse(url)
    if u.scheme == "file":
        return True
    if u.scheme != "https":
        return False
    host = (u.hostname or "").strip().lower()
    allow_raw = os.getenv("AIPLAT_SKILL_INSTALL_GIT_ALLOWLIST_HOSTS", "github.com")
    allow = {h.strip().lower() for h in allow_raw.split(",") if h.strip()}
    return (host in allow) if allow else False


def resolve_remote_head_sha(url: str) -> str:
    """
    Resolve the current remote HEAD commit SHA for a git URL.

    Security:
    - url must pass _allowlisted_git_url (https allowlist or file://)
    """
    if not _allowlisted_git_url(url):
        raise ValueError("git_url_not_allowed")
    # `git ls-remote <url> HEAD` prints: "<sha>\tHEAD"
    out = _run(["git", "ls-remote", str(url), "HEAD"], timeout_s=30)
    sha = ""
    for ln in (out or "").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        parts = ln.split()
        if len(parts) >= 2 and parts[1].endswith("HEAD"):
            sha = parts[0].strip()
            break
    if not sha or len(sha) < 7:
        raise ValueError("failed_to_resolve_head")
    return sha


def _validate_ref(ref: str) -> None:
    if not ref or not isinstance(ref, str):
        raise ValueError("ref_required")
    r = ref.strip()
    if not _REF_RE.match(r):
        raise ValueError("invalid_ref")


def _iter_skill_dirs(root: Path, *, subdir: Optional[str] = None) -> List[Path]:
    base = root
    if subdir:
        base = (root / subdir).resolve()
    if not base.exists() or not base.is_dir():
        return []
    out: List[Path] = []
    for item in base.iterdir():
        if not item.is_dir():
            continue
        if (item / "SKILL.md").exists():
            out.append(item)
    return out


def _parse_frontmatter(skill_md_text: str) -> Tuple[Dict[str, Any], str]:
    """
    Minimal YAML-frontmatter parser.

    We intentionally avoid importing project YAML stack here to keep installer lightweight.
    Returns: (front_matter_dict, body_markdown)
    """
    text = skill_md_text or ""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("\n")
    # find second --- line
    end = None
    for i in range(1, min(len(parts), 2000)):
        if parts[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    fm_lines = parts[1:end]
    body = "\n".join(parts[end + 1 :])

    fm: Dict[str, Any] = {}
    for ln in fm_lines:
        if ":" not in ln:
            continue
        k, v = ln.split(":", 1)
        key = k.strip()
        val = v.strip()
        if not key:
            continue
        # very small parsing for list-in-brackets
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            if not inner:
                fm[key] = []
            else:
                fm[key] = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]
        else:
            fm[key] = val.strip().strip("'\"")
    return fm, body


def _auto_detect_subdir(root: Path) -> Optional[str]:
    """
    Auto-detect where skills live in a repository/layout.

    We check common conventions (OpenCode/Claude/Agents + generic skills/) and pick
    the directory containing the most skills.
    """
    candidates = [
        ".opencode/skills",
        ".claude/skills",
        ".agents/skills",
        "skills",
        "aiPlat-core/skills",
    ]
    best: Tuple[int, Optional[str]] = (0, None)
    for c in candidates:
        skills = _iter_skill_dirs(root, subdir=c)
        if len(skills) > best[0]:
            best = (len(skills), c)
    return best[1] if best[0] > 0 else None


def _check_copy_limits(src_dir: Path) -> None:
    max_files = int(os.getenv("AIPLAT_SKILL_INSTALL_MAX_FILES", "200") or "200")
    max_bytes = int(os.getenv("AIPLAT_SKILL_INSTALL_MAX_TOTAL_BYTES", str(2 * 1024 * 1024)) or str(2 * 1024 * 1024))
    files = 0
    total = 0
    for p in src_dir.rglob("*"):
        if p.is_dir():
            continue
        rel = str(p.relative_to(src_dir))
        if rel.startswith(".git/") or rel.startswith("__pycache__/") or rel.endswith(".pyc"):
            continue
        files += 1
        try:
            total += int(p.stat().st_size)
        except Exception:
            pass
        if files > max_files:
            raise ValueError("skill_install_too_many_files")
        if total > max_bytes:
            raise ValueError("skill_install_too_large")


def _write_manifest(skill_dir: Path, *, source: Dict[str, Any]) -> None:
    p = skill_dir / "SKILL.manifest.json"
    data = {
        "publisher": str(source.get("publisher") or "unknown"),
        "source": str(source.get("source") or ""),
        "ref": str(source.get("ref") or ""),
        "commit": str(source.get("commit") or ""),
        "subdir": str(source.get("subdir") or ""),
        "skill_id": str(source.get("skill_id") or skill_dir.name),
        "installed_at": float(time.time()),
    }
    try:
        extra = source.get("metadata")
        if isinstance(extra, dict):
            data["metadata"] = extra
    except Exception:
        pass
    p.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")


@dataclass
class InstallResult:
    installed: List[str]
    skipped: List[Dict[str, Any]]


@dataclass
class PlanResult:
    """
    Dry-run plan output for installer.
    """

    source: Dict[str, Any]
    detected_subdir: Optional[str]
    skills: List[Dict[str, Any]]
    warnings: List[str]


class SkillInstaller:
    """
    Installer that materializes SKILL.md directories into a target skills base path.
    """

    def __init__(self, *, target_base_dir: Path):
        self._target_base_dir = target_base_dir

    def install_from_git(
        self,
        *,
        url: str,
        ref: str,
        skill_id: Optional[str] = None,
        subdir: Optional[str] = None,
        auto_detect_subdir: bool = True,
        allow_overwrite: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InstallResult:
        if not _allowlisted_git_url(url):
            raise ValueError("git_url_not_allowed")
        _validate_ref(ref)

        with tempfile.TemporaryDirectory(prefix="aiplat-skill-install-git-") as td:
            repo_dir = Path(td) / "repo"
            _run(["git", "clone", "--no-checkout", "--depth", "1", str(url), str(repo_dir)], timeout_s=120)
            _run(["git", "-C", str(repo_dir), "checkout", str(ref)], timeout_s=60)
            commit = ""
            try:
                commit = _run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], timeout_s=10)
            except Exception:
                commit = ""
            if not subdir and auto_detect_subdir:
                subdir = _auto_detect_subdir(repo_dir)
            return self._install_from_dir(
                root=repo_dir,
                source={"publisher": "git", "source": url, "ref": ref, "commit": commit, "subdir": subdir or "", "metadata": metadata or {}},
                skill_id=skill_id,
                subdir=subdir,
                allow_overwrite=allow_overwrite,
            )

    def install_from_path(
        self,
        *,
        path: str,
        skill_id: Optional[str] = None,
        subdir: Optional[str] = None,
        auto_detect_subdir: bool = True,
        allow_overwrite: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InstallResult:
        root = Path(path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError("path_not_found")
        if not subdir and auto_detect_subdir:
            subdir = _auto_detect_subdir(root)
        return self._install_from_dir(
            root=root,
            source={"publisher": "local", "source": str(root), "ref": "", "metadata": metadata or {}},
            skill_id=skill_id,
            subdir=subdir,
            allow_overwrite=allow_overwrite,
        )

    def install_from_zip(
        self,
        *,
        zip_path: str,
        skill_id: Optional[str] = None,
        subdir: Optional[str] = None,
        auto_detect_subdir: bool = True,
        allow_overwrite: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InstallResult:
        zp = Path(zip_path).expanduser().resolve()
        if not zp.exists() or not zp.is_file():
            raise ValueError("zip_not_found")
        with tempfile.TemporaryDirectory(prefix="aiplat-skill-install-zip-") as td:
            root = Path(td) / "unzipped"
            root.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(str(zp), "r") as zf:
                zf.extractall(str(root))
            if not subdir and auto_detect_subdir:
                subdir = _auto_detect_subdir(root)
            return self._install_from_dir(
                root=root,
                source={"publisher": "zip", "source": str(zp), "ref": "", "metadata": metadata or {}},
                skill_id=skill_id,
                subdir=subdir,
                allow_overwrite=allow_overwrite,
            )

    def plan_from_git(
        self,
        *,
        url: str,
        ref: str,
        skill_id: Optional[str] = None,
        subdir: Optional[str] = None,
        auto_detect_subdir: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PlanResult:
        if not _allowlisted_git_url(url):
            raise ValueError("git_url_not_allowed")
        _validate_ref(ref)
        with tempfile.TemporaryDirectory(prefix="aiplat-skill-plan-git-") as td:
            repo_dir = Path(td) / "repo"
            _run(["git", "clone", "--no-checkout", "--depth", "1", str(url), str(repo_dir)], timeout_s=120)
            _run(["git", "-C", str(repo_dir), "checkout", str(ref)], timeout_s=60)
            commit = ""
            try:
                commit = _run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], timeout_s=10)
            except Exception:
                commit = ""
            if not subdir and auto_detect_subdir:
                subdir = _auto_detect_subdir(repo_dir)
            return self._plan_from_dir(
                root=repo_dir,
                source={"publisher": "git", "source": url, "ref": ref, "commit": commit, "subdir": subdir or "", "metadata": metadata or {}},
                skill_id=skill_id,
                subdir=subdir,
            )

    def plan_from_path(
        self,
        *,
        path: str,
        skill_id: Optional[str] = None,
        subdir: Optional[str] = None,
        auto_detect_subdir: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PlanResult:
        root = Path(path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError("path_not_found")
        if not subdir and auto_detect_subdir:
            subdir = _auto_detect_subdir(root)
        return self._plan_from_dir(
            root=root,
            source={"publisher": "local", "source": str(root), "ref": "", "metadata": metadata or {}},
            skill_id=skill_id,
            subdir=subdir,
        )

    def plan_from_zip(
        self,
        *,
        zip_path: str,
        skill_id: Optional[str] = None,
        subdir: Optional[str] = None,
        auto_detect_subdir: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PlanResult:
        zp = Path(zip_path).expanduser().resolve()
        if not zp.exists() or not zp.is_file():
            raise ValueError("zip_not_found")
        with tempfile.TemporaryDirectory(prefix="aiplat-skill-plan-zip-") as td:
            root = Path(td) / "unzipped"
            root.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(str(zp), "r") as zf:
                zf.extractall(str(root))
            if not subdir and auto_detect_subdir:
                subdir = _auto_detect_subdir(root)
            return self._plan_from_dir(
                root=root,
                source={"publisher": "zip", "source": str(zp), "ref": "", "metadata": metadata or {}},
                skill_id=skill_id,
                subdir=subdir,
            )

    def _install_from_dir(
        self,
        *,
        root: Path,
        source: Dict[str, Any],
        skill_id: Optional[str],
        subdir: Optional[str],
        allow_overwrite: bool,
    ) -> InstallResult:
        skills = _iter_skill_dirs(root, subdir=subdir)
        if not skills:
            raise ValueError("no_skills_found")

        installed: List[str] = []
        skipped: List[Dict[str, Any]] = []
        for sd in skills:
            # select single skill if requested
            if skill_id and sd.name != skill_id:
                # Also allow frontmatter name to match (best-effort)
                try:
                    raw = (sd / "SKILL.md").read_text(encoding="utf-8", errors="replace")
                    if f"name: {skill_id}" not in raw:
                        continue
                except Exception:
                    continue

            _check_copy_limits(sd)

            dst = self._target_base_dir / sd.name
            if dst.exists():
                if not allow_overwrite:
                    skipped.append({"skill_id": sd.name, "reason": "already_exists"})
                    continue
                try:
                    shutil.rmtree(dst)
                except Exception:
                    raise RuntimeError("failed_to_remove_existing_skill_dir")

            shutil.copytree(sd, dst)
            try:
                src2 = dict(source or {})
                src2["skill_id"] = sd.name
                _write_manifest(dst, source=src2)
            except Exception:
                pass
            installed.append(sd.name)

        return InstallResult(installed=installed, skipped=skipped)

    def _plan_from_dir(
        self,
        *,
        root: Path,
        source: Dict[str, Any],
        skill_id: Optional[str],
        subdir: Optional[str],
    ) -> PlanResult:
        skills = _iter_skill_dirs(root, subdir=subdir)
        if not skills:
            raise ValueError("no_skills_found")

        warnings: List[str] = []
        detected = subdir
        if not detected:
            # best-effort: maybe still detect for transparency
            detected = _auto_detect_subdir(root)
            if detected:
                warnings.append("subdir_not_specified_detected_alternative")

        out: List[Dict[str, Any]] = []
        for sd in skills:
            if skill_id and sd.name != skill_id:
                try:
                    raw = (sd / "SKILL.md").read_text(encoding="utf-8", errors="replace")
                    if f"name: {skill_id}" not in raw:
                        continue
                except Exception:
                    continue

            # measure size/files and enforce limits like install would
            try:
                _check_copy_limits(sd)
                limit_ok = True
                limit_err = None
            except Exception as e:
                limit_ok = False
                limit_err = str(e)

            # parse frontmatter
            try:
                raw = (sd / "SKILL.md").read_text(encoding="utf-8", errors="replace")
            except Exception:
                raw = ""
            fm, _body = _parse_frontmatter(raw)

            # detect kind (align with contracts / skill_manager)
            exe = fm.get("executable")
            runtime = str(fm.get("runtime") or "").strip()
            entrypoint = str(fm.get("entrypoint") or fm.get("handler") or "").strip()
            perms = fm.get("permissions") or []
            if isinstance(perms, str):
                perms = [perms]
            if not isinstance(perms, list):
                perms = []

            kind = "rule"
            exe_s = str(exe).strip().lower()
            if exe is False or exe_s in {"false", "0", "no"}:
                kind = "rule"
            elif exe is True or exe_s in {"true", "1", "yes"}:
                kind = "executable"
                if not perms:
                    kind = "rule"
            else:
                if (sd / "handler.py").exists() or any((sd / f).exists() for f in ["manifest.json", "manifest.yaml", "manifest.yml"]):
                    kind = "executable" if perms else "rule"

            out.append(
                {
                    "skill_id": sd.name,
                    "name": str(fm.get("name") or sd.name),
                    "description": str(fm.get("description") or "")[:1024],
                    "version": str(fm.get("version") or ""),
                    "kind": kind,
                    "runtime": runtime,
                    "entrypoint": entrypoint,
                    "permissions": [str(p).strip() for p in perms if str(p).strip()],
                    "limits_ok": limit_ok,
                    "limits_error": limit_err,
                }
            )

        return PlanResult(source=source, detected_subdir=detected, skills=out, warnings=warnings)
