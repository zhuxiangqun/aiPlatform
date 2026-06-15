"""
Asset Installer — shared base for importing open-source agents, skills, MCPs, and workflows.
Supports git (url+ref), local directory path, and zip file.

Security:
- Host allowlist for git URLs (env AIPLAT_ASSET_INSTALL_GIT_ALLOWLIST_HOSTS, default github.com)
- https:// and file:// schemes only
- Git ref REQUIRED to prevent supply-chain drift
- File count / total bytes quotas
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
    allow_raw = os.getenv("AIPLAT_ASSET_INSTALL_GIT_ALLOWLIST_HOSTS", "github.com")
    allow = {h.strip().lower() for h in allow_raw.split(",") if h.strip()}
    return (host in allow) if allow else False


def resolve_remote_head_sha(url: str) -> str:
    """Resolve remote HEAD commit SHA for a git URL."""
    if not _allowlisted_git_url(url):
        raise ValueError("git_url_not_allowed")
    out = _run(["git", "ls-remote", str(url), "HEAD"], timeout_s=30)
    sha = ""
    for ln in (out or "").splitlines():
        parts = ln.strip().split()
        if len(parts) >= 2 and parts[1].endswith("HEAD"):
            sha = parts[0].strip()
            break
    if not sha or len(sha) < 7:
        raise ValueError("failed_to_resolve_head")
    return sha


def _validate_ref(ref: str) -> None:
    if not ref or not isinstance(ref, str):
        raise ValueError("ref_required")
    if not _REF_RE.match(ref.strip()):
        raise ValueError("invalid_ref")


def _parse_yaml_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """Minimal YAML frontmatter parser (no PyYAML dependency)."""
    text = text or ""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("\n")
    end = None
    for i in range(1, min(len(parts), 2000)):
        if parts[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    fm_lines = parts[1:end]
    body = "\n".join(parts[end + 1:])
    fm: Dict[str, Any] = {}
    for ln in fm_lines:
        if ":" not in ln:
            continue
        k, v = ln.split(":", 1)
        key = k.strip()
        val = v.strip()
        if not key:
            continue
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()] if inner else []
        else:
            fm[key] = val.strip().strip("'\"")
    return fm, body


def _check_copy_limits(src_dir: Path) -> None:
    max_files = int(os.getenv("AIPLAT_ASSET_INSTALL_MAX_FILES", "200") or "200")
    max_bytes = int(os.getenv("AIPLAT_ASSET_INSTALL_MAX_TOTAL_BYTES", str(2 * 1024 * 1024)) or str(2 * 1024 * 1024))
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
            raise ValueError("asset_install_too_many_files")
        if total > max_bytes:
            raise ValueError("asset_install_too_large")


def _auto_detect_subdir(root: Path, patterns: List[str]) -> Optional[str]:
    """Auto-detect where assets live by checking common conventions."""
    candidates = [
        ".opencode/skills",
        ".opencode/agents",
        ".claude/skills",
        ".claude/agents",
        ".agents/skills",
        ".agents/agents",
        "skills",
        "agents",
        "mcps",
        "workflows",
        "aiPlat-core/skills",
        "aiPlat-core/agents",
    ]
    best: Tuple[int, Optional[str]] = (0, None)
    for c in candidates:
        d = root / c
        if not d.exists() or not d.is_dir():
            continue
        count = 0
        for item in d.iterdir():
            if not item.is_dir():
                continue
            for pat in patterns:
                if (item / pat).exists():
                    count += 1
                    break
        if count > best[0]:
            best = (count, c)
    return best[1] if best[0] > 0 else None


@dataclass
class InstallResult:
    installed: List[str]
    skipped: List[Dict[str, Any]]
    converted: Optional[Dict[str, Any]] = None


@dataclass
class PlanResult:
    source: Dict[str, Any]
    detected_subdir: Optional[str]
    assets: List[Dict[str, Any]]
    warnings: List[str]
    claude_plugin: bool = False


def _record_asset_import_audit(asset_dir: Path, asset_name: str, asset_type: str, source: dict) -> None:
    """Record an import audit event for any asset type (best-effort, non-blocking)."""
    try:
        from core.harness.kernel import get_kernel_runtime
        rt = get_kernel_runtime()
        store = getattr(rt, "execution_store", None) if rt else None
        if store is None or not hasattr(store, "add_import_audit"):
            return
        source_type = str((source or {}).get("source_type", "zip"))
        pattern = asset_type
        adapted = False
        try:
            import anyio
            anyio.run(
                store.add_import_audit,
                skill_id=f"{asset_type}:{asset_name}",
                skill_name=asset_name,
                source_type=source_type,
                pattern=pattern,
                adapted=adapted,
                details={"asset_type": asset_type, "asset_dir": str(asset_dir)},
            )
        except Exception:
            pass
    except Exception:
        pass


class AssetInstaller:
    """
    Generic installer for third-party open-source assets.
    Subclass and override:
      - _FILE_PATTERN: filename to detect (e.g. "SKILL.md", "AGENT.md")
      - _MANIFEST_NAME: manifest filename (e.g. "SKILL.manifest.json")
      - ASSET_TYPE: label (e.g. "agent", "skill", "mcp", "workflow")
    """

    _FILE_PATTERN: str = ""
    _MANIFEST_NAME: str = ""
    ASSET_TYPE: str = "asset"

    def __init__(self, *, target_base_dir: Path):
        self._target_base_dir = target_base_dir

    # ── Public API ──────────────────────────────────────────────

    def install_from_git(
        self, *, url: str, ref: str, asset_id: Optional[str] = None,
        subdir: Optional[str] = None, auto_detect_subdir: bool = True,
        allow_overwrite: bool = False, metadata: Optional[Dict[str, Any]] = None,
        skip_claude_plugin: bool = False,
    ) -> InstallResult:
        if not _allowlisted_git_url(url):
            raise ValueError("git_url_not_allowed")
        _validate_ref(ref)
        with tempfile.TemporaryDirectory(prefix=f"aiplat-{self.ASSET_TYPE}-install-git-") as td:
            repo_dir = Path(td) / "repo"
            _run(["git", "clone", "--no-checkout", "--depth", "1", str(url), str(repo_dir)], timeout_s=120)
            _run(["git", "-C", str(repo_dir), "checkout", str(ref)], timeout_s=60)
            commit = ""
            try:
                commit = _run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], timeout_s=10)
            except Exception:
                commit = ""
            if not subdir and auto_detect_subdir:
                subdir = _auto_detect_subdir(repo_dir, [self._FILE_PATTERN])
            detect = repo_dir if not subdir else repo_dir / subdir

            # Check for Claude Code plugin layout
            claude = None
            if not skip_claude_plugin and _is_claude_plugin(repo_dir):
                claude = self._adapt_claude_plugin(repo_dir)
                if claude.get("converted"):
                    result = self._install_from_dir(root=repo_dir, source={"publisher": "git", "source": url,
                        "ref": ref, "commit": commit, "subdir": subdir or "", "metadata": metadata or {}},
                        asset_id=asset_id, subdir=subdir, allow_overwrite=allow_overwrite)
                    result.converted = claude
                    return result

            return self._install_from_dir(root=detect, source={"publisher": "git", "source": url,
                "ref": ref, "commit": commit, "subdir": subdir or "", "metadata": metadata or {}},
                asset_id=asset_id, subdir=None, allow_overwrite=allow_overwrite)

    def install_from_path(
        self, *, path: str, asset_id: Optional[str] = None,
        subdir: Optional[str] = None, auto_detect_subdir: bool = True,
        allow_overwrite: bool = False, metadata: Optional[Dict[str, Any]] = None,
    ) -> InstallResult:
        root = Path(path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError("path_not_found")
        if not subdir and auto_detect_subdir:
            subdir = _auto_detect_subdir(root, [self._FILE_PATTERN])
        detect = root if not subdir else root / subdir
        return self._install_from_dir(root=detect, source={"publisher": "local", "source": str(root),
            "ref": "", "metadata": metadata or {}}, asset_id=asset_id, subdir=None,
            allow_overwrite=allow_overwrite)

    def install_from_zip(
        self, *, zip_path: str, asset_id: Optional[str] = None,
        subdir: Optional[str] = None, auto_detect_subdir: bool = True,
        allow_overwrite: bool = False, metadata: Optional[Dict[str, Any]] = None,
    ) -> InstallResult:
        zp = Path(zip_path).expanduser().resolve()
        if not zp.exists() or not zp.is_file():
            raise ValueError("zip_not_found")
        with tempfile.TemporaryDirectory(prefix=f"aiplat-{self.ASSET_TYPE}-install-zip-") as td:
            root = Path(td) / "unzipped"
            root.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(str(zp), "r") as zf:
                zf.extractall(str(root))
            if not subdir and auto_detect_subdir:
                subdir = _auto_detect_subdir(root, [self._FILE_PATTERN])
            detect = root if not subdir else root / subdir
            return self._install_from_dir(root=detect, source={"publisher": "zip",
                "source": str(zp), "ref": "", "metadata": metadata or {}},
                asset_id=asset_id, subdir=None, allow_overwrite=allow_overwrite)

    def plan_from_git(
        self, *, url: str, ref: str, asset_id: Optional[str] = None,
        subdir: Optional[str] = None, auto_detect_subdir: bool = True,
        metadata: Optional[Dict[str, Any]] = None, skip_claude_plugin: bool = False,
    ) -> PlanResult:
        if not _allowlisted_git_url(url):
            raise ValueError("git_url_not_allowed")
        _validate_ref(ref)
        with tempfile.TemporaryDirectory(prefix=f"aiplat-{self.ASSET_TYPE}-plan-git-") as td:
            repo_dir = Path(td) / "repo"
            _run(["git", "clone", "--no-checkout", "--depth", "1", str(url), str(repo_dir)], timeout_s=120)
            _run(["git", "-C", str(repo_dir), "checkout", str(ref)], timeout_s=60)
            commit = ""
            try:
                commit = _run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], timeout_s=10)
            except Exception:
                commit = ""
            if not subdir and auto_detect_subdir:
                subdir = _auto_detect_subdir(repo_dir, [self._FILE_PATTERN])
            detect = repo_dir if not subdir else repo_dir / subdir

            claude = not skip_claude_plugin and _is_claude_plugin(repo_dir)
            return self._plan_from_dir(root=detect, source={"publisher": "git", "source": url,
                "ref": ref, "commit": commit, "subdir": subdir or "", "metadata": metadata or {}},
                asset_id=asset_id, subdir=None, claude_plugin=claude)

    def plan_from_path(
        self, *, path: str, asset_id: Optional[str] = None,
        subdir: Optional[str] = None, auto_detect_subdir: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PlanResult:
        root = Path(path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError("path_not_found")
        if not subdir and auto_detect_subdir:
            subdir = _auto_detect_subdir(root, [self._FILE_PATTERN])
        detect = root if not subdir else root / subdir
        return self._plan_from_dir(root=detect, source={"publisher": "local",
            "source": str(root), "ref": "", "metadata": metadata or {}},
            asset_id=asset_id, subdir=None)

    def plan_from_zip(
        self, *, zip_path: str, asset_id: Optional[str] = None,
        subdir: Optional[str] = None, auto_detect_subdir: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PlanResult:
        zp = Path(zip_path).expanduser().resolve()
        if not zp.exists() or not zp.is_file():
            raise ValueError("zip_not_found")
        with tempfile.TemporaryDirectory(prefix=f"aiplat-{self.ASSET_TYPE}-plan-zip-") as td:
            root = Path(td) / "unzipped"
            root.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(str(zp), "r") as zf:
                zf.extractall(str(root))
            if not subdir and auto_detect_subdir:
                subdir = _auto_detect_subdir(root, [self._FILE_PATTERN])
            detect = root if not subdir else root / subdir
            return self._plan_from_dir(root=detect, source={"publisher": "zip",
                "source": str(zp), "ref": "", "metadata": metadata or {}},
                asset_id=asset_id, subdir=None)

    # ── Subclass hooks ──────────────────────────────────────────

    def _iter_asset_dirs(self, root: Path) -> List[Path]:
        """Yield directories containing this asset type's file pattern."""
        out: List[Path] = []
        if not root.exists() or not root.is_dir():
            return out
        for item in root.iterdir():
            if not item.is_dir():
                if item.suffix == ".md" and self._FILE_PATTERN.endswith(".md"):
                    out.append(item.parent)
                continue
            if (item / self._FILE_PATTERN).exists():
                out.append(item)
            else:
                for sub in item.iterdir():
                    if sub.is_dir() and (sub / self._FILE_PATTERN).exists():
                        out.append(sub)
        return out

    def _find_asset_dirs(self, root: Path) -> List[Path]:
        """Recursively find all directories containing this asset type's file pattern."""
        seen: set = set()
        out: List[Path] = []
        for entry in sorted(root.rglob(self._FILE_PATTERN)):
            d = entry.parent
            key = str(d.resolve())
            if key not in seen:
                seen.add(key)
                out.append(d)
        return out

    def _parse_asset_info(self, asset_dir: Path) -> Dict[str, Any]:
        """Parse frontmatter/metadata for the asset preview."""
        cfg_file = asset_dir / self._FILE_PATTERN
        info: Dict[str, Any] = {"id": asset_dir.name}
        try:
            raw = cfg_file.read_text(encoding="utf-8", errors="replace")
            fm, _body = _parse_yaml_frontmatter(raw)
            info["name"] = str(fm.get("name") or asset_dir.name)
            info["display_name"] = str(fm.get("display_name") or fm.get("name") or asset_dir.name)
            info["description"] = str(fm.get("description") or "")[:1024]
            info["version"] = str(fm.get("version") or "")
            info["status"] = str(fm.get("status") or "ready")
            info.update({k: v for k, v in fm.items() if k not in info})
        except Exception:
            info["name"] = asset_dir.name
            info["display_name"] = asset_dir.name
            info["description"] = ""
            info["version"] = ""
        return info

    def _write_manifest(self, dest_dir: Path, *, source: Dict[str, Any]) -> None:
        p = dest_dir / self._MANIFEST_NAME
        data = {
            "type": self.ASSET_TYPE,
            "publisher": str(source.get("publisher") or "unknown"),
            "source": str(source.get("source") or ""),
            "ref": str(source.get("ref") or ""),
            "commit": str(source.get("commit") or ""),
            "subdir": str(source.get("subdir") or ""),
            "asset_id": str(source.get("asset_id") or dest_dir.name),
            "installed_at": float(time.time()),
        }
        try:
            extra = source.get("metadata")
            if isinstance(extra, dict):
                data["metadata"] = extra
        except Exception:
            pass
        p.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")

    def _get_target_dir(self, asset_name: str) -> Path:
        """Override if target dir differs from base_dir/name."""
        return self._target_base_dir / asset_name

    # ── Internal ────────────────────────────────────────────────

    def _install_from_dir(self, *, root: Path, source: Dict[str, Any],
                          asset_id: Optional[str], subdir: Optional[str],
                          allow_overwrite: bool) -> InstallResult:
        # First, try format adapters (Hermes, OpenClaw, etc.)
        converted = None
        try:
            converted = _try_adapt(root, self._target_base_dir)
        except Exception:
            pass

        assets = self._iter_asset_dirs(root)
        if not assets and not subdir:
            assets = self._find_asset_dirs(root)
        if not assets and not (converted and converted.get("converted")):
            raise ValueError(f"no_{self.ASSET_TYPE}s_found")

        installed: List[str] = []
        skipped: List[Dict[str, Any]] = []
        for ad in assets:
            if asset_id and ad.name != asset_id:
                try:
                    raw = (ad / self._FILE_PATTERN).read_text(encoding="utf-8", errors="replace")
                    if f"name: {asset_id}" not in raw and asset_id not in ad.name:
                        continue
                except Exception:
                    continue

            _check_copy_limits(ad)
            dst = self._get_target_dir(ad.name)
            if dst.exists():
                if not allow_overwrite:
                    skipped.append({"id": ad.name, "reason": "already_exists"})
                    # Still run enrichment on existing dir (may be broken from previous import)
                    try:
                        self._enrich_asset_frontmatter(dst)
                    except Exception:
                        pass
                    continue
                try:
                    shutil.rmtree(dst)
                except Exception:
                    raise RuntimeError("failed_to_remove_existing_dir")

            shutil.copytree(ad, dst)
            # Enrich frontmatter: status, category, execution_type, tool crosswalk
            self._enrich_asset_frontmatter(dst)
            try:
                src2 = dict(source or {})
                src2["asset_id"] = ad.name
                self._write_manifest(dst, source=src2)
            except Exception:
                pass
            # Record import audit (best-effort)
            try:
                _record_asset_import_audit(dst, ad.name, self.ASSET_TYPE, source)
            except Exception:
                pass
            installed.append(ad.name)

        return InstallResult(installed=installed, skipped=skipped,
                             converted=converted)

    def _enrich_asset_frontmatter(self, dst: Path) -> None:
        """Post-install: enrich frontmatter with defaults + tool crosswalk."""
        cfg_file = dst / self._FILE_PATTERN
        if not cfg_file.exists():
            return

        try:
            raw = cfg_file.read_text(encoding="utf-8", errors="replace")
            # Split YAML frontmatter from body
            if not raw.startswith("---"):
                # No frontmatter — add minimal one
                name = dst.name.replace("-", " ").title()
                enriched = f"""---
name: {name}
description: {name}
execution_type: prompt
category: general
status: draft
_auto_adapted: true
---
{raw}"""
                cfg_file.write_text(enriched, encoding="utf-8")
                return

            parts = raw.split("---", 2)
            if len(parts) < 3:
                return

            import yaml
            fm = yaml.safe_load(parts[1]) or {}
            if not isinstance(fm, dict):
                fm = {}
            body = parts[2]

            # Apply defaults
            fm.setdefault("status", "draft")
            fm["_auto_adapted"] = True

            if self.ASSET_TYPE == "agent":
                fm.setdefault("category", "general")
                fm.setdefault("execution_type", "prompt")
            elif self.ASSET_TYPE == "mcp":
                fm.setdefault("transport", "stdio")
                fm.setdefault("auth", "none")
            elif self.ASSET_TYPE == "workflow":
                fm.setdefault("trigger", "manual")

            # Tool crosswalk: detect external tool names in SOP body
            try:
                from core.management.skill_adapter import _TOOL_REF_PATTERN
                detected = set(_TOOL_REF_PATTERN.findall(body))
                if detected:
                    from core.management.skill_adapter import TOOL_NAME_CROSSWALK
                    mapped = []
                    missing = []
                    for tool in detected:
                        m = TOOL_NAME_CROSSWALK.get(tool)
                        if m and m.primary:
                            mapped.append(m.primary)
                        else:
                            missing.append(tool)
                    if mapped:
                        fm.setdefault("tools", [])
                        existing = fm["tools"]
                        if isinstance(existing, list):
                            for mt in mapped:
                                if mt not in existing:
                                    existing.append(mt)
                    if missing:
                        fm["missing_capabilities"] = missing
                        critical = [t for t in missing
                                  if TOOL_NAME_CROSSWALK.get(t, None) and TOOL_NAME_CROSSWALK[t].critical]
                        if critical:
                            fm["status"] = "draft"
                            fm["block_reason"] = f"missing critical tools: {', '.join(critical)}"
            except ImportError:
                pass

            # Write back
            new_fm = yaml.dump(dict(fm), allow_unicode=True, sort_keys=False).strip()
            new_content = f"---\n{new_fm}\n---{body}"
            cfg_file.write_text(new_content, encoding="utf-8")

        except Exception:
            pass

    def _plan_from_dir(self, *, root: Path, source: Dict[str, Any],
                       asset_id: Optional[str], subdir: Optional[str],
                       claude_plugin: bool = False) -> PlanResult:
        assets = self._iter_asset_dirs(root)
        if not assets and not subdir:
            assets = self._find_asset_dirs(root)
        if not assets:
            raise ValueError(f"no_{self.ASSET_TYPE}s_found")

        warnings: List[str] = []
        out: List[Dict[str, Any]] = []
        for ad in assets:
            if asset_id and ad.name != asset_id:
                try:
                    raw = (ad / self._FILE_PATTERN).read_text(encoding="utf-8", errors="replace")
                    if f"name: {asset_id}" not in raw and asset_id not in ad.name:
                        continue
                except Exception:
                    continue

            try:
                _check_copy_limits(ad)
                limit_ok, limit_err = True, None
            except Exception as e:
                limit_ok, limit_err = False, str(e)

            info = self._parse_asset_info(ad)
            info["limits_ok"] = limit_ok
            info["limits_error"] = limit_err
            out.append(info)

        return PlanResult(source=source, detected_subdir=subdir, assets=out,
                          warnings=warnings, claude_plugin=claude_plugin)

    def _adapt_claude_plugin(self, root_dir: Path) -> Dict[str, Any]:
        """Decompose Claude Code plugin bundle into aiPlatform components."""
        import os as _os
        manifest: Dict[str, Any] = {"converted": [], "skipped": [], "mcp_hints": []}
        import shutil as _shutil

        base = _os.path.expanduser("~/.aiplat")
        skills_dest = Path(base) / "skills"
        agents_dest = Path(base) / "agents"
        hooks_dest = Path(base) / "hooks"

        # skills/
        if (root_dir / "skills").is_dir():
            skills_dest.mkdir(parents=True, exist_ok=True)
            for item in (root_dir / "skills").iterdir():
                if item.suffix == ".md":
                    dest = skills_dest / item.name
                    if not dest.exists():
                        _shutil.copy2(item, dest)
            manifest["converted"].append("skills")

        # agents/
        if (root_dir / "agents").is_dir():
            agents_dest.mkdir(parents=True, exist_ok=True)
            for item in (root_dir / "agents").iterdir():
                if item.is_dir():
                    dest_dir = agents_dest / item.name
                    if (item / "AGENT.md").is_file() and not dest_dir.exists():
                        _shutil.copytree(item, dest_dir)
                elif item.suffix == ".md":
                    dest = agents_dest / item.name
                    if not dest.exists():
                        _shutil.copy2(item, dest)
            manifest["converted"].append("agents")

        # hooks/
        if (root_dir / "hooks").is_dir():
            hooks_dest.mkdir(parents=True, exist_ok=True)
            for item in (root_dir / "hooks").iterdir():
                if item.suffix == ".py":
                    dest = hooks_dest / item.name
                    if not dest.exists():
                        _shutil.copy2(item, dest)
            manifest["converted"].append("hooks")

        # commands/ → skip
        if (root_dir / "commands").is_dir():
            manifest["skipped"].append({"component": "commands", "reason": "aiPlatform 无 slash command"})

        # mcp/
        if (root_dir / "mcp").is_dir():
            for item in (root_dir / "mcp").iterdir():
                if item.suffix == ".json":
                    manifest["mcp_hints"].append(str(item.name))
            if not manifest["mcp_hints"]:
                manifest["skipped"].append({"component": "mcp", "reason": "MCP server 配置已发现，需在管理界面手动注册"})

        return manifest


def _is_claude_plugin(root: Path) -> bool:
    """Detect if the root is a Claude Code plugin bundle."""
    has_skills = (root / "skills").is_dir()
    has_agents = (root / "agents").is_dir()
    has_hooks = (root / "hooks").is_dir()
    return bool(has_skills or has_agents or has_hooks)


# ── Concrete installers ────────────────────────────────────────

class AgentInstaller(AssetInstaller):
    _FILE_PATTERN = "AGENT.md"
    _MANIFEST_NAME = "AGENT.manifest.json"
    ASSET_TYPE = "agent"


class MCPInstaller(AssetInstaller):
    _FILE_PATTERN = "server.yaml"
    _MANIFEST_NAME = "MCP.manifest.json"
    ASSET_TYPE = "mcp"

    def _iter_asset_dirs(self, root: Path) -> List[Path]:
        out: List[Path] = []
        if not root.exists() or not root.is_dir():
            return out
        for item in root.iterdir():
            if item.is_dir():
                if (item / "server.yaml").exists() or (item / "mcp.json").exists():
                    out.append(item)
            elif item.name in ("server.yaml", "mcp.json"):
                out.append(root)
                break
        return out


class WorkflowInstaller(AssetInstaller):
    _FILE_PATTERN = "workflow.yaml"
    _MANIFEST_NAME = "WORKFLOW.manifest.json"
    ASSET_TYPE = "workflow"


def _try_adapt(root_dir: Path, target_skills_base: Path) -> Optional[Dict[str, Any]]:
    """Try format adapters before normal file scanning."""
    try:
        from core.management.format_adapters import detect_and_convert
        return detect_and_convert(root_dir, target_skills_base)
    except Exception:
        return None
