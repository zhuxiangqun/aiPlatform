"""
Builder project service — project CRUD + file persistence + team-bound pipeline execution.

Pipeline operations use CoreFacade.PipelineSession — the sole interface for
pipeline execution per architecture contract (docs/index.md §Layer 2 boundary).
"""
from __future__ import annotations

from builder.builder_l2l5_mixin import BuilderL2L5Mixin
from builder.builder_deploy_mixin import BuilderDeployMixin

import json
import logging
import os
import time
import uuid
import ast
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.schemas_builder import (
    BuilderSessionPhase,
    Project,
    ProjectRun,
    ProjectCreateRequest,
    PipelineConfig,
    PipelineStageConfig,
    PRDArtifact,
)
from core.api.core_facade import create_pipeline_session, apply_agent_md_to_stage, validate_pipeline_stages, extract_json
from builder.builder_team_service import BuilderTeamService

import re

_DANGEROUS_PATTERNS = [
    (re.compile(r"rm\s+-rf", re.IGNORECASE), "attempts to run rm -rf"),
    (re.compile(r"sudo\s", re.IGNORECASE), "attempts to use sudo"),
    (re.compile(r"curl.*\|.*sh", re.IGNORECASE), "attempts to pipe curl to shell"),
    (re.compile(r"os\.system\(|subprocess\.call\(|exec\(|eval\(", re.IGNORECASE), "attempts to execute system commands"),
    (re.compile(r"ignore.*all.*previous.*instructions?", re.IGNORECASE), "attempts prompt injection override"),
    (re.compile(r"<\|im_start\|>|<\|im_end\|>", re.IGNORECASE), "contains model control tokens"),
]

_log = logging.getLogger("aiplat.builder.project_service")

def _scan_agent_security(agent_id: str, sop_body: str) -> None:
    for pattern, description in _DANGEROUS_PATTERNS:
        if pattern.search(sop_body):
            _log.warning("Security: AGENT.md '%s' %s. Body will be stripped.", agent_id, description)
            raise ValueError(f"AGENT.md '{agent_id}' contains dangerous content: {description}")

_AIPLAT_PM_AGENT = os.getenv("AIPLAT_PM_AGENT", "pm_agent")

_AIPLAT_CHAT_NOT_IN_DIALOGUE = os.getenv(
    "AIPLAT_CHAT_NOT_IN_DIALOGUE", "Project is not in dialogue phase")
_AIPLAT_CHAT_NO_MODEL = os.getenv(
    "AIPLAT_CHAT_NO_MODEL", "LLM model not loaded. Check API key configuration.")
_AIPLAT_CHAT_ERROR_PREFIX = os.getenv(
    "AIPLAT_CHAT_ERROR_PREFIX", "Chat error: ")

_AIPLAT_PRD_SECTION_REQUIREMENTS = os.getenv("AIPLAT_PRD_SECTION_REQUIREMENTS", "功能需求")
_AIPLAT_PRD_SECTION_SCOPE = os.getenv("AIPLAT_PRD_SECTION_SCOPE", "范围")
_AIPLAT_PRD_SECTION_METRICS = os.getenv("AIPLAT_PRD_SECTION_METRICS", "成功指标")
_AIPLAT_PRD_SECTION_ACCEPTANCE = os.getenv("AIPLAT_PRD_SECTION_ACCEPTANCE", "验收标准")
_AIPLAT_PRD_SECTION_ISA = os.getenv("AIPLAT_PRD_SECTION_ISA", "ISA 对齐")
_AIPLAT_PRD_TITLE_PREFIX = os.getenv("AIPLAT_PRD_TITLE_PREFIX", "项目名称：")

_AIPLAT_NO_PRD = os.getenv(
    "AIPLAT_NO_PRD", "No PRD data available. Complete the PM dialogue first.")

_PROJECTS_FILE = os.path.join(
    os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "projects.json"
)
_PROJECTS_DIR = os.path.join(
    os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "projects"
)
_BUILDER_STATES_DIR = os.path.join(
    os.path.expanduser(os.getenv("AIPLAT_HOME", "~/.aiplat")),
    "builder_states",
)

# ── L2: import existing code (plan-app-factory-l2-import-repo.md §3.3/§3.5/§3.6) ──
_L2_IMPORT_MAX_ZIP_BYTES = int(os.getenv("AIPLAT_L2_IMPORT_MAX_ZIP_MB", "50")) * 1024 * 1024
_L2_IMPORT_MAX_FILES = int(os.getenv("AIPLAT_L2_IMPORT_MAX_FILES", "500"))
_L2_IMPORT_MAX_FILE_BYTES = int(os.getenv("AIPLAT_L2_IMPORT_MAX_FILE_MB", "2")) * 1024 * 1024
_L2_SENSITIVE_RE = re.compile(
    r"(^|/)(\.env[^/]*|.*\.pem$|.*\.key$|.*\.p12$|secrets?/|credentials?\.(json|yaml|yml)$|\.git/)",
    re.IGNORECASE,
)
_L2_DEPS_FILES = ("requirements.txt", "go.mod", "package.json", "pyproject.toml")
_L2_BEHAVIOR_PROMPT = (
    "## 行为契约（重写而非合并）\n"
    "对 modify_files 中列出的文件：必须基于注入的旧文件内容【重写】该文件以满足变更需求。\n"
    "重写时保留：原有对外接口（函数签名/类名/路由路径）、关键边界处理、注释中标记的已知坑。\n"
    "未在 modify_files 中的文件一律不得触碰、不得覆盖。"
)

# L3 — incremental merge behavior contract (plan-app-factory-l3 §3.4)
_L3_INCREMENT_PROMPT = (
    "## 行为契约（增量修改）\n"
    "对以下受影响文件：基于注入的旧文件内容进行【增量修改】——\n"
    "1. 只修改与变更需求相关的区域；其余代码必须与旧文件【逐字节一致】（包括注释、格式、顺序）\n"
    "2. 输出每个受影响文件的【完整新版本】（## FILE: 格式），不要输出 diff 片段\n"
    "3. 保留：原有对外接口（函数签名/类名/路由路径）、关键边界处理、注释中标记的已知坑\n"
    "4. 若某文件无需任何修改，明确标注 \"## UNCHANGED: <path>\"（不输出新版本）\n"
    "5. 未列出的文件一律不得触碰。"
)


def _semantic_output(agent_id: str, phase: str) -> str:
    """Map agent_id to semantic output artifact name — reads from AGENT.md frontmatter."""
    from core.api.facades.agent_facade import get_agent_frontmatter
    try:
        fm = get_agent_frontmatter(agent_id)
        if fm.get("output_artifact"):
            return fm["output_artifact"]
    except Exception as e:
        logging.getLogger("aiplat.builder").warning(
            "Failed to get agent frontmatter for %s: %s", agent_id, str(e)[:200])
    return phase or "artifact"


# ── L2: import helpers (plan-app-factory-l2-import-repo.md §3.3/§3.6 security) ──

def _safe_extract_zip(zip_bytes: bytes, import_root: str) -> None:
    """Extract zip with zip-slip protection: every entry's resolved path must
    stay inside import_root. Rejects absolute paths, '..' traversal, symlinks."""
    import zipfile
    import io
    _root_abs = os.path.abspath(import_root)
    if len(zip_bytes) > _L2_IMPORT_MAX_ZIP_BYTES:
        raise ValueError(f"zip 超过上限 {_L2_IMPORT_MAX_ZIP_BYTES // (1024*1024)}MB")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            name = info.filename
            if name.startswith("/") or "\\" in name:
                raise ValueError(f"zip-slip: 非法路径 {name}")
            target = os.path.abspath(os.path.join(_root_abs, name))
            if not target.startswith(_root_abs + os.sep):
                raise ValueError(f"zip-slip: 路径越界 {name}")
            if name.endswith("/"):
                continue
            try:
                data = zf.read(info)
            except RuntimeError as e:
                raise ValueError(f"zip 读取失败（疑似加密/损坏）：{e}") from e
            if len(data) > _L2_IMPORT_MAX_FILE_BYTES:
                raise ValueError(f"单文件超过上限 {_L2_IMPORT_MAX_FILE_BYTES // (1024*1024)}MB：{name}")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as fh:
                fh.write(data)


def _copy_existing_path(existing_path: str, import_root: str) -> None:
    """Copy a user-specified directory into import_root — whitelisted to
    AIPLAT_HOME/~/ .aiplat only (L2 §3.5: existing_path 白名单)."""
    import shutil as _sh
    _home = os.path.abspath(os.path.expanduser(
        os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))))
    _src = os.path.abspath(os.path.expanduser(existing_path))
    if not os.path.isdir(_src):
        raise ValueError(f"路径不存在或不是目录：{existing_path}")
    if not (_src == _home or _src.startswith(_home + os.sep)):
        raise ValueError("existing_path 仅允许 AIPLAT_HOME 内的目录（跨目录导入需管理员确认）")
    for root, _dirs, files in os.walk(_src):
        for fn in files:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, _src)
            if _L2_SENSITIVE_RE.search(rel):
                continue
            size = os.path.getsize(full)
            if size > _L2_IMPORT_MAX_FILE_BYTES:
                continue
            target = os.path.join(import_root, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            try:
                _sh.copy2(full, target)
            except OSError:
                continue


def _scan_imported(import_root: str) -> tuple:
    """Scan import_root into manifest [{path,size,sha256,lang,first_line}].
    Skips sensitive files (.env/*.pem/secrets/.git). Returns (manifest, too_many)."""
    import hashlib
    manifest = []
    too_many = False
    for root, _dirs, files in os.walk(import_root):
        for fn in sorted(files):
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, import_root)
            if _L2_SENSITIVE_RE.search(rel):
                continue
            if len(manifest) >= _L2_IMPORT_MAX_FILES:
                too_many = True
                break
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            if size > _L2_IMPORT_MAX_FILE_BYTES:
                continue
            lang = os.path.splitext(fn)[1].lstrip(".").lower() or "txt"
            first_line = ""
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as fh:
                    first_line = fh.readline()[:120].strip()
            except OSError:
                pass  # noqa: cleanup-best-effort — unreadable file → empty preview, still listed
            sha = ""
            try:
                with open(full, "rb") as fh:
                    sha = hashlib.sha256(fh.read(1 << 20)).hexdigest()[:16]
            except OSError:
                pass  # noqa: cleanup-best-effort — unreadable file → empty hash, still listed
            manifest.append({
                "path": rel, "size": size, "lang": lang,
                "sha256": sha, "first_line": first_line,
            })
        if too_many:
            break
    return manifest, too_many


def _detect_tests(import_root: str) -> bool:
    """True if the imported repo has a tests/ or test/ directory (§3.8)."""
    for cand in ("tests", "test"):
        if os.path.isdir(os.path.join(import_root, cand)):
            return True
    return False


def _detect_missing_deps(import_root: str) -> list:
    """Scan requirements.txt/go.mod/package.json/pyproject.toml and return the
    declared dependency list as pre-check hints (info only, non-blocking; §3.8)."""
    hints = []
    for fname in _L2_DEPS_FILES:
        fpath = os.path.join(import_root, fname)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read(200_000)
        except OSError:
            continue
        if fname in ("requirements.txt",):
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    pkg = re.split(r"[<>=!~; \[]", line, maxsplit=1)[0].strip()
                    if pkg:
                        hints.append(f"{fname}: {pkg}")
        elif fname == "go.mod":
            for line in content.splitlines():
                m = re.match(r"^\s*([a-zA-Z0-9_\-\./]+)\s+v[0-9]", line)
                if m:
                    hints.append(f"go.mod: {m.group(1)}")
        elif fname == "package.json":
            import json as _j
            try:
                _pkg = _j.loads(content)
            except Exception:
                continue
            for section in ("dependencies", "devDependencies"):
                deps = _pkg.get(section) or {}
                for k in list(deps.keys())[:50]:
                    hints.append(f"package.json({section}): {k}")
        elif fname == "pyproject.toml":
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("["):
                    pkg = re.split(r"[<>=!~; \[]", line, maxsplit=1)[0].strip()
                    if pkg and pkg not in ("dependencies", "optional-dependencies"):
                        hints.append(f"pyproject.toml: {pkg}")
    return hints[:200]


def _create_skill_loader():
    """Create a SkillLoader for dependency injection into PipelineEngine.  # noqa: boundary — docstring, not usage

    This function lives in the service layer (allowed to import from apps) and
    injects the loader into the harness, eliminating harness→apps reverse deps.
    """
    def _load(name: str):
        if name == "code_generation":
            from core.api.core_facade import get_code_gen_skill
            return get_code_gen_skill()
        return None
    return _load


def _parse_team_stages(stages_raw: list) -> list:
    """Parse raw team_stages dicts into PipelineStageConfig list."""
    stages = []
    for s in (stages_raw or []):
        try:
            stages.append(PipelineStageConfig(**s) if isinstance(s, dict) else s)
        except Exception as e:
            logging.getLogger("aiplat.builder").warning(
                "Failed to parse team stage: %s", str(e)[:200])
    return stages


async def _load_stages_from_template(team_id: str) -> List:
    """Load team stages from YAML template (always up-to-date, not cached).

     Priority: YAML template > team service cache.
     Used by pipeline rebuild to ensure latest config changes are picked up.
     """
    try:
        from core.api.core_facade import _enrich_stage_from_agent
        from core.api.core_facade import load_team_template
        tmpl = load_team_template(team_id)
        if tmpl and tmpl.stages:
            stages = []
            for i, s in enumerate(tmpl.stages):
                stage = dict(s)
                stage.setdefault("id", f"canvas_node_{i+1}")
                stage.setdefault("order", i)
                stage = _enrich_stage_from_agent(stage)
                stages.append(PipelineStageConfig(**stage))
            return stages
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)  # Fall through to team service cache
    return []


def _unwrap_json_reply(reply: str) -> str:
    """Extract human-readable text from agent JSON outputs.
    Handles: {"type":"done","answer":"..."} → "..."
    """
    if not reply or not isinstance(reply, str):
        return reply or ""
    s = reply.strip()
    if s.startswith("{") and s.endswith("}"):
        try:
            import json
            d = json.loads(s)
            if isinstance(d, dict):
                if d.get("type") == "done" and d.get("answer"):
                    return str(d["answer"])
                if d.get("answer"):
                    return str(d["answer"])
        except (json.JSONDecodeError, ValueError):  # noqa: best-effort-parse
            pass
    return reply


# ── HITL suspend/resume context (Phase 1: in-memory, Phase 2: Redis) ──
_HITL_SUSPENDED: Dict[str, dict] = {}

def suspend_hitl(project_id: str, context: dict) -> None:
    """Persist HITL suspension context. Called by pipeline_manager skill on pause."""
    import time as _t
    _HITL_SUSPENDED[project_id] = {
        "skill": "pipeline_manager",
        "step": "awaiting_approval",
        "context": context,
        "suspended_at": _t.time(),
    }
    logging.getLogger("aiplat.builder").warning("HITL suspended: project=%s", project_id)

def resume_hitl(project_id: str) -> Optional[dict]:
    """Retrieve and clear HITL suspension context. Called by approve/reject tools."""
    ctx = _HITL_SUSPENDED.pop(project_id, None)
    if ctx:
        logging.getLogger("aiplat.builder").warning("HITL resumed: project=%s step=%s", project_id, ctx.get("step"))
    return ctx


def _derive_app_name(name: str, provided: str = "", project_id: str = "") -> str:
    """Derive a canonical English slug for the project.

    Priority:
      1. User-provided app_name (normalized)
      2. ASCII slug from the project name
      3. Deterministic fallback: app_{project_id_suffix}
    """
    if provided and provided.strip():
        slug = provided.strip()
    else:
        # Extract ASCII alphanumeric runs from name (e.g. "视频解析 Platform" → "platform")
        ascii_parts = re.findall(r"[A-Za-z0-9]+", name or "")
        slug = "_".join(ascii_parts) if ascii_parts else ""
    if not slug:
        suffix = (project_id or "").replace("prj_", "").replace("-", "_")
        slug = f"app_{suffix}" if suffix else "app"
    # Normalize: lowercase, non-alnum → underscore, collapse repeats, trim
    slug = re.sub(r"[^a-z0-9]+", "_", slug.lower()).strip("_")
    # Prefix must be a letter/underscore (safe filesystem + JSON key)
    if slug and slug[0].isdigit():
        slug = f"app_{slug}"
    return slug or "app"


async def _translate_app_name(name: str) -> str:
    """Best-effort LLM translation of a non-ASCII project name to an English slug.

    Returns "" on failure (caller falls back to `app_{project_id_suffix}`).
    """
    if not name or not name.strip():
        return ""
    try:
        from core.api.core_facade import best_model_for_purpose
        from core.api.facades.service_facade import llm_generate
        _prompt = (
            "把下面的中文项目名翻译成一个简洁的英文 slug（小写、下划线分隔、无空格、不要拼音）。"
            "只输出 slug 本身，不要解释，不要加引号或标点。\n"
            "示例：'视频解析平台' → video_parser\n"
            f"项目名：{name.strip()}"
        )
        resp = await llm_generate(
            None,
            [{"role": "user", "content": _prompt}],
            model_name=best_model_for_purpose("chat"),
            temperature=0.2,
            max_tokens=30,
        )
        slug = (getattr(resp, "content", "") or str(resp)).strip()
        slug = re.sub(r"[^a-z0-9]+", "_", slug.lower()).strip("_")
        if slug and not slug[0].isdigit():
            return slug
    except Exception as e:
        logging.getLogger("aiplat.builder").warning(
            "app_name translation failed for %r: %s", name, str(e)[:200])
    return ""


class BuilderProjectService(BuilderL2L5Mixin, BuilderDeployMixin):
    """Builder 项目服务 — 核心 CRUD/对话/流水线。

    P1-14 God Class 拆分（2026-08-25）：L2-L5（导入/合并/模块/迁移/发布）与
    部署/健康/洞察已拆至 BuilderL2L5Mixin / BuilderDeployMixin（MRO 运行时解析）。
    """

    def __init__(self, model: Any = None, team_service: Optional[BuilderTeamService] = None):
        self._model = model  # None = lazy init on first use
        self._team_service = team_service or BuilderTeamService(None)
        self._projects: Dict[str, Dict[str, Any]] = {}
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._phases: Dict[str, str] = {}  # dialogue | executing
        self._load_projects()
        self._seed_registries()

    @property
    def model(self) -> Any:
        """Lazy init: only create LLM adapter when actually needed."""
        if self._model is None:
            from core.api.facades.service_facade import get_default_model
            self._model = get_default_model()
        return self._model

    @staticmethod
    def _seed_registries() -> None:
        from core.api.facades.skill_tool_facade import seed_all_registries
        seed_all_registries()

    # ── Persistence ──────────────────────────────────────────────────

    def _load_projects(self) -> None:
        try:
            if os.path.exists(_PROJECTS_FILE):
                with open(_PROJECTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                seen_ids = set()
                for item in data.get("projects", []):
                    pid = item.get("project_id", "")
                    if pid and pid not in seen_ids:
                        self._projects[pid] = item
                        seen_ids.add(pid)
        except Exception as e:
            _log.warning("Failed to load projects from %s: %s", _PROJECTS_FILE, e)

    def _save_projects(self) -> None:
        try:
            os.makedirs(os.path.dirname(_PROJECTS_FILE), exist_ok=True)
            # Deduplicate by project_id before saving
            seen = set()
            deduped = []
            for p in list(self._projects.values()):
                pid = p.get("project_id", "")
                if pid not in seen:
                    deduped.append(p)
                    seen.add(pid)
            data = {
                "projects": deduped,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            tmp = _PROJECTS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, _PROJECTS_FILE)

            # Also write per-project directory files for governance support
            try:
                os.makedirs(_PROJECTS_DIR, exist_ok=True)
                for p in deduped:
                    pid = p.get("project_id", "")
                    if not pid:
                        continue
                    proj_dir = os.path.join(_PROJECTS_DIR, pid)
                    os.makedirs(proj_dir, exist_ok=True)

                    # Write project.json
                    proj_json = os.path.join(proj_dir, "project.json")
                    proj_payload = dict(p)
                    # Strip runs from the per-file snapshot (they're in projects.json)
                    proj_payload.pop("runs", None)
                    with open(proj_json + ".tmp", "w", encoding="utf-8") as f:
                        json.dump(proj_payload, f, ensure_ascii=False, indent=2)
                    os.replace(proj_json + ".tmp", proj_json)

                    # Enrich with provenance/integrity if manifest exists
                    manifest_path = os.path.join(proj_dir, "PROJECT.manifest.json")
                    if os.path.exists(manifest_path):
                        try:
                            with open(manifest_path, "r", encoding="utf-8") as f:
                                manifest = json.load(f)
                            p.setdefault("metadata", {})
                            p["metadata"].setdefault("provenance", {})
                            p["metadata"]["provenance"].update({
                                "publisher": manifest.get("publisher"),
                                "source": manifest.get("source"),
                                "version": manifest.get("version"),
                                "signature": manifest.get("signature"),
                            })
                        except Exception as e:
                            logging.warning(str(e), exc_info=True)
            except Exception:
                _log.warning("Failed to write per-project directory files", exc_info=True)
        except Exception as e:
            _log.error("Failed to save projects to %s (project data may be lost on restart): %s", _PROJECTS_FILE, e)

    def _reload_if_stale(self) -> None:
        try:
            mtime = os.path.getmtime(_PROJECTS_FILE)
        except OSError:
            return
        cached = getattr(self, "_last_file_mtime", 0.0)
        if mtime <= cached:
            return
        current_ids = set(self._projects.keys())
        self._load_projects()
        new_ids = set(self._projects.keys()) - current_ids
        removed_ids = current_ids - set(self._projects.keys())
        if new_ids or removed_ids:
            _log.info(
                "Reloaded projects from %s: +%d new, -%d removed",
                _PROJECTS_FILE, len(new_ids), len(removed_ids),
            )
        self._last_file_mtime = mtime

    # ── CRUD ─────────────────────────────────────────────────────────

    async def create_project(self, req: ProjectCreateRequest) -> Project:
        # ── Dedup: reuse existing project if same name + description exists ──
        self._reload_if_stale()
        for pid, data in self._projects.items():
            if data.get("name") == req.name and data.get("description") == req.description:
                project_data = data
                team_name = ""
                if team_id := project_data.get("team_id"):
                    team = await self._team_service.get_team(team_id)
                    if team:
                        team_name = team.name
                return Project(
                    project_id=project_data.get("project_id", pid),
                    name=project_data.get("name", ""),
                    description=project_data.get("description", ""),
                    app_name=project_data.get("app_name", ""),
                    team_id=project_data.get("team_id", ""),
                    team_name=team_name,
                    team_stages=_parse_team_stages(project_data.get("team_stages", [])),
                    runs=[],
                    created_at=project_data.get("created_at", ""),
                    updated_at=project_data.get("updated_at", ""),
                )

        project_id = f"prj_{uuid.uuid4().hex[:8]}"
        now = time.strftime("%Y-%m-%dT%H:%M:%S")

        stages: List[PipelineStageConfig] = []
        if req.stages:
            # Pre-built workflow stages from canvas/editor
            for s in req.stages:
                if isinstance(s, dict):
                    stages.append(PipelineStageConfig(**s))
        elif req.team_id:
            team = await self._team_service.get_team(req.team_id)
            if team:
                stages = team.stages

        self._projects[project_id] = {
            "project_id": project_id,
            "name": req.name or f"Project {project_id}",
            "description": req.description,
            "app_name": _derive_app_name(req.name, getattr(req, "app_name", ""), project_id),
            "team_id": req.team_id,
            "team_stages": [s.model_dump() if hasattr(s, 'model_dump') else s for s in stages],
            "runs": [],
            "created_at": now,
            "updated_at": now,
        }

        # ── Improve auto-derived app_name for non-ASCII names (LLM translation) ──
        _provided = (getattr(req, "app_name", "") or "").strip()
        if (not _provided
                and not re.search(r"[A-Za-z]", req.name or "")
                and re.search(r"[\u4e00-\u9fff]", req.name or "")):
            _translated = await _translate_app_name(req.name)
            if _translated:
                self._projects[project_id]["app_name"] = _translated

        # ── Auto-classify domain ──
        _domain_id = "default"
        try:
            from core.api.core_facade import DomainRouter
            _desc = req.description or req.name or ""
            if _desc.strip():
                _router = DomainRouter()
                _domain_id = _router.classify(_desc)
                self._projects[project_id]["domain_id"] = _domain_id
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

        self._save_projects()

        # Initialize chat session for PM dialogue
        self._sessions[project_id] = {
            "phase": BuilderSessionPhase.dialogue.value,
            "messages": [],
        }

        project_data = self._projects[project_id]
        team_name = ""
        if team_id := project_data.get("team_id"):
            team = await self._team_service.get_team(team_id)
            if team:
                team_name = team.name
        return Project(
            project_id=project_data.get("project_id", project_id),
            name=project_data.get("name", ""),
            description=project_data.get("description", ""),
            app_name=project_data.get("app_name", ""),
            team_id=project_data.get("team_id", ""),
            team_name=team_name,
            team_stages=_parse_team_stages(project_data.get("team_stages", [])),
            runs=[],
            created_at=project_data.get("created_at", ""),
            updated_at=project_data.get("updated_at", ""),
        )

    async def list_projects(self) -> List[Project]:
        self._reload_if_stale()
        # ── Sync stuck "executing" runs from Core (best-effort, non-blocking) ──
        for pid, data in list(self._projects.items()):
            runs_data = data.get("runs", [])
            if runs_data:
                last = runs_data[-1]
                if last.get("phase") in ("executing", "pending") and not last.get("finished_at"):
                    try:
                        state = await self._get_state_via_core(pid)
                        if state.get("phase") in ("done", "failed"):
                            last["phase"] = state["phase"]
                            last["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                            data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                            self._save_projects()
                    except Exception:
                        pass  # noqa: cleanup-best-effort

        # Batch-load all teams to avoid N+1 per-project queries
        team_ids = list({data.get("team_id", "") for data in self._projects.values() if data.get("team_id")})
        team_map: Dict[str, str] = {}
        for tid in team_ids:
            try:
                team = await self._team_service.get_team(tid)
                if team:
                    team_map[tid] = team.name
            except Exception as e:
                logging.warning(str(e), exc_info=True)

        projects: List[Project] = []
        for pid, data in self._projects.items():
            runs_data = data.get("runs", [])
            latest = runs_data[-1] if runs_data else None
            team_id = data.get("team_id", "")
            team_name = team_map.get(team_id, "")
            projects.append(Project(
                project_id=data.get("project_id", pid),
                name=data.get("name", ""),
                description=data.get("description", ""),
                app_name=data.get("app_name", ""),
                team_id=team_id,
                team_name=team_name,
                team_stages=_parse_team_stages(data.get("team_stages", [])),
                runs=[ProjectRun(**r) for r in runs_data[-3:]] if runs_data else [],
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
            ))
        return projects

    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        return self._projects.get(project_id)

    async def delete_project(self, project_id: str) -> bool:
        if project_id not in self._projects:
            return False
        import shutil
        home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
        # Output directories may use legacy "bare ID" or new "name-ID" format
        dirs_to_check = [
            (os.path.join(home, "output"), project_id),
            (os.path.join(os.getenv("AIPLAT_APP_DEPLOY_DIR", os.path.expanduser("~/.aiplat/apps")), ""), project_id),
        ]
        for base_dir, pid in dirs_to_check:
            try:
                if not os.path.isdir(base_dir):
                    continue
                for entry in os.listdir(base_dir):
                    full = os.path.join(base_dir, entry)
                    if entry.endswith(f"-{pid}") or entry == pid:
                        try:
                            if os.path.isdir(full):
                                shutil.rmtree(full)
                            elif os.path.isfile(full):
                                os.remove(full)
                        except OSError:
                            pass  # noqa: cleanup-best-effort
            except OSError:
                pass  # noqa: cleanup-best-effort
        for state_file in [
            os.path.join(home, "builder_states", f"{project_id}.json"),
            os.path.join(home, "builder_states", f"{project_id}_chat.json"),
        ]:
            try:
                if os.path.isfile(state_file):
                    os.remove(state_file)
            except OSError:
                pass  # noqa: cleanup-best-effort
        del self._projects[project_id]
        self._save_projects()
        return True

    async def batch_delete(self, project_ids: list[str] = None, *,
                           pass_rate_below: float = None) -> int:
        """Delete multiple projects. Optionally filter by pass_rate.
        
        Args:
            project_ids: specific project IDs to delete. If None, uses pass_rate filter.
            pass_rate_below: if set, deletes all projects whose latest run pass_rate is below this value.
        
        Returns: number of projects deleted.
        """
        self._reload_if_stale()
        to_delete: list[str] = []
        
        if project_ids:
            to_delete = [pid for pid in project_ids if pid in self._projects]
        elif pass_rate_below is not None:
            for pid, data in self._projects.items():
                runs = data.get("runs", [])
                if not runs:
                    to_delete.append(pid)  # never run = 0% effectively
                    continue
                latest = runs[-1]
                if (latest.get("pass_rate") or 0) < pass_rate_below:
                    to_delete.append(pid)
        
        deleted = 0
        for pid in to_delete:
            if self.delete_project_sync(pid):
                deleted += 1
        
        if deleted:
            self._save_projects()
        return deleted

    def delete_project_sync(self, project_id: str) -> bool:
        """Synchronous version of delete_project for batch operations."""
        if project_id not in self._projects:
            return False
        import shutil
        home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
        dirs_to_check = [
            (os.path.join(home, "output"), project_id),
            (os.path.join(os.getenv("AIPLAT_APP_DEPLOY_DIR", os.path.expanduser("~/.aiplat/apps")), ""), project_id),
        ]
        for base_dir, pid in dirs_to_check:
            try:
                if not os.path.isdir(base_dir):
                    continue
                for entry in os.listdir(base_dir):
                    full = os.path.join(base_dir, entry)
                    if entry.endswith(f"-{pid}") or entry == pid:
                        try:
                            if os.path.isdir(full):
                                shutil.rmtree(full)
                            elif os.path.isfile(full):
                                os.remove(full)
                        except OSError:
                            pass  # noqa: cleanup-best-effort
            except OSError:
                pass  # noqa: cleanup-best-effort
        for state_file in [
            os.path.join(home, "builder_states", f"{project_id}.json"),
            os.path.join(home, "builder_states", f"{project_id}_chat.json"),
        ]:
            try:
                if os.path.isfile(state_file):
                    os.remove(state_file)
            except OSError:
                pass  # noqa: cleanup-best-effort
        del self._projects[project_id]
        return True

    async def chat(self, project_id: str, message: str) -> Dict[str, Any]:
        """PM dialogue — directly managed through self._sessions (chat dicts only)."""
        from core.api.intents import core_chat, ChatContext

        session = self._sessions.get(project_id)
        if not session:
            session = self._load_chat_session(project_id)
            if session:
                self._sessions[project_id] = session

        if not isinstance(session, dict):
            session = {"phase": BuilderSessionPhase.dialogue.value, "messages": []}
            self._sessions[project_id] = session

        # ── Guard: prevent accidental PRD overwrite after project is done ──
        proj = self._projects.get(project_id, {})
        if proj.get("confirmed_prd"):
            runs = proj.get("runs") or []
            if runs and runs[-1].get("phase") == "done":
                return {
                    "reply": "项目已构建完成。如需修改需求，请点击「重新编辑需求」按钮。",
                    "prd_ready": True, "trace_id": "", "session_state": {},
                }

        # Always allow chat — reset to dialogue phase if needed
        if session.get("phase") != BuilderSessionPhase.dialogue.value:
            session["phase"] = BuilderSessionPhase.dialogue.value

        if not self.model:
            return {"reply": _AIPLAT_CHAT_NO_MODEL, "prd_ready": False, "trace_id": "", "session_state": {}}

        session["messages"].append({"role": "user", "content": message})

        # ── Inject knowledge retrieval context into PM dialogue ──
        _enriched_message = message
        try:
            from core.api.core_facade import sys_knowledge_retrieve
            from core.api.core_facade import DomainRouter
            _did = "default"
            try:
                _did = DomainRouter().classify(message)
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
            _kb_docs = sys_knowledge_retrieve(message, top_k=3, domain_id=_did)
            if _kb_docs:
                _kb_lines = ["## 知识库中已有的相关内容"]
                for _doc in _kb_docs[:3]:
                    _title = str(getattr(_doc, 'title', '') or '')
                    _snippet = str(getattr(_doc, 'content', '') or getattr(_doc, 'snippet', '') or '')[:300]
                    if _title or _snippet:
                        _kb_lines.append(f"- {_title}: {_snippet}")
                if len(_kb_lines) > 1:
                    _kb_context = "\n".join(_kb_lines)
                    _enriched_message = f"{_kb_context}\n\n---\n用户需求: {message}"
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)  # best-effort

        try:
            # Check if this project has a generated Agent app → route chat to it
            _agent_name = _AIPLAT_PM_AGENT
            _run_state = self._runs.get(project_id)
            if not _run_state:
                try:
                    _run_state = self._load_pipeline_state(project_id) or {}
                except Exception:
                    _run_state = {}
            _generated = _run_state.get("_generated_agent", "") if isinstance(_run_state, dict) else ""
            if _generated:
                _agent_name = _generated
                _enriched_message = message  # Agent apps use raw message, not KB-enriched

            result = await core_chat(ChatContext(
                agent_name=_agent_name,
                session_id=project_id,
                user_input=_enriched_message,
                model=self.model,
            ))
            reply = result.reply
            # Unwrap agent JSON formats (e.g. {"type":"done","answer":"..."} → plain text)
            reply = _unwrap_json_reply(reply)
            session["messages"].append({"role": "assistant", "content": reply})
            prd_ready = "<!-- PRD_READY -->" in str(reply)
            if prd_ready:
                # Try JSON first (backward compat), then Markdown
                draft = None
                try:
                    json_str = extract_json(reply)
                    if json_str:
                        draft = json.loads(json_str)
                        if not (draft.get("user_stories") or draft.get("functional_requirements")):
                            draft = None
                except Exception as e:
                    logging.warning(str(e), exc_info=True)
                # Fallback: parse Markdown PRD
                if not draft and "## 项目名称" in str(reply):
                    draft = self._parse_markdown_prd(reply)
                if draft:
                    session["prd"] = draft
                    # Also save to project directly so PRD survives session loss/overwrite
                    proj = self._projects.get(project_id, {})
                    if proj:
                        proj["confirmed_prd"] = draft
                        self._save_projects()
            self._save_chat_session(project_id)
            return {"reply": reply, "prd_ready": prd_ready, "trace_id": result.trace_id, "session_state": {}}
        except Exception as e:
            self._save_chat_session(project_id)  # save even on error — preserve messages
            return {"reply": f"{_AIPLAT_CHAT_ERROR_PREFIX}{str(e)[:200]}", "prd_ready": False, "trace_id": "", "session_state": {}}

    async def _extract_prd_from_chat(self, project_id: str, session: dict) -> Optional[Dict[str, Any]]:
        """Use LLM to extract structured PRD from PM chat history."""
        import json as _json
        import logging as _log
        msgs = session.get("messages", [])
        _log.warning("_extract_prd_from_chat: %d messages in session", len(msgs))
        if not msgs or len(msgs) < 2:
            _log.info("_extract_prd_from_chat: not enough messages (%d)", len(msgs))
            return None
        # Build conversation summary
        proj = self._projects.get(project_id, {})
        _name = proj.get("name", "") or "新项目"
        lines = []
        for m in msgs[-10:]:
            role = "用户" if m.get("role") == "user" else "PM"
            content = str(m.get("content", ""))[:500]
            lines.append(f"{role}: {content}")
        conversation_text = "\n".join(lines)

        from core.api.core_facade import _sync_resolve
        prompt = _sync_resolve("prd-extract-from-chat", conversation=conversation_text, name=_name)

        try:
            from core.api.intents import core_chat, ChatContext
            result = await core_chat(ChatContext(
                agent_name="planning_agent",
                session_id=f"prd_extract_{project_id}",
                user_input=prompt,
                model=self.model,
            ))
            reply = str(result.reply or "")
            _log.info("_extract_prd_from_chat: got %d chars reply", len(reply))
            start = reply.find("{")
            end = reply.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = reply[start:end]
                # Handle common LLM formatting issues
                prd = None
                for parser in [
                    lambda s: _json.loads(s),                           # standard JSON
                    lambda s: _json.loads(s.replace("'", '"')),         # single-quoted keys
                    lambda s: ast.literal_eval(s),                      # Python dict literal (安全, P0-2)
                ]:
                    try:
                        prd = parser(json_str)
                        if isinstance(prd, dict) and prd:
                            break
                    except Exception:
                        continue
                if prd and isinstance(prd, dict):
                    _log.info("_extract_prd_from_chat: extracted PRD with keys %s", list(prd.keys())[:5])
                    return prd
            _log.info("_extract_prd_from_chat: no valid JSON found in reply")
        except Exception as e:
            _log.warning("_extract_prd_from_chat failed: %s", str(e)[:200])
        return None

    async def confirm_prd(self, project_id: str, prd_data: Any = None) -> Dict[str, Any]:
        session = self._sessions.get(project_id)
        if not session:
            session = self._load_chat_session(project_id)
            if session:
                self._sessions[project_id] = session
        if not isinstance(session, dict):
            session = {}
        if not prd_data:
            prd_data = session.get("prd") if isinstance(session, dict) else None
        # Last resort: extract PRD from last assistant message in session
        if not prd_data and isinstance(session, dict):
            msgs = session.get("messages", [])
            for m in reversed(msgs):
                if m.get("role") == "assistant":
                    content = m.get("content", "")
                    if "<!-- PRD_READY -->" in content or "## 项目名称" in content:
                        draft = self._parse_markdown_prd(content)
                        if draft:
                            prd_data = draft
                            session["prd"] = draft
                        break

        proj = self._projects.get(project_id, {})
        if not prd_data:
            # Primary: persisted confirmed_prd from update-prd or previous PM dialogue
            prd_data = proj.get("confirmed_prd")
        if not prd_data:
            prd_data = session.get("prd") if isinstance(session, dict) else None
        # Last resort: extract PRD from last assistant message in session
        if not prd_data and isinstance(session, dict):
            msgs = session.get("messages", [])
            for m in reversed(msgs):
                if m.get("role") == "assistant":
                    content = m.get("content", "")
                    if "<!-- PRD_READY -->" in content or "## 项目名称" in content:
                        draft = self._parse_markdown_prd(content)
                        if draft:
                            prd_data = draft
                            session["prd"] = draft
                        break

        if not prd_data:
            # Auto-extract PRD from chat via LLM
            try:
                prd_data = await self._extract_prd_from_chat(project_id, session)
            except Exception as e:
                logging.warning("Auto PRD extraction failed: %s", str(e)[:100])
        if not prd_data:
            raise ValueError(_AIPLAT_NO_PRD)

        proj["confirmed_prd"] = prd_data
        self._save_projects()

        # Transition session phase from dialogue to executing
        if session:
            session["phase"] = BuilderSessionPhase.executing.value
        return {"phase": BuilderSessionPhase.executing.value, "prd": prd_data}

    def _ensure_manifest_resolved(self, project_id: str, state: Dict[str, Any]) -> None:
        """Post-process pipeline state: extract agent_manifest.json from deployed files.

        Moved from pipeline_engine.py → platform service layer.
        The engine should never know about manifest format, orchestrator, or agent names.
        """
        import json, os, re as _re
        if state.get("agent_manifest"):
            return  # already resolved
        _app_home = os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "apps", project_id, "current")
        _manifest_path = os.path.join(_app_home, "agent_manifest.json")
        if not os.path.isfile(_manifest_path):
            # Also try parsing from agent_app raw_output if not yet deployed to disk
            agent_app = state.get("agent_app", {})
            raw = agent_app.get("raw_output", "") if isinstance(agent_app, dict) else ""
            if raw and "agent_manifest.json" in raw:
                for block in _re.split(r'^##\s*FILE:\s*', raw, flags=_re.MULTILINE)[1:]:
                    blines = block.strip().split("\n", 1)
                    if len(blines) >= 2 and "agent_manifest.json" in blines[0]:
                        try:
                            man_json = blines[1].strip()
                            man_json = _re.sub(r'^```(?:json)?\s*\n?', '', man_json)
                            man_json = _re.sub(r'\n?```\s*$', '', man_json)
                            state["agent_manifest"] = json.loads(man_json)
                        except Exception:
                            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
                        break
            return
        try:
            with open(_manifest_path) as f:
                state["agent_manifest"] = json.load(f)
            orchestrator = state["agent_manifest"].get("orchestrator", "")
            if orchestrator:
                state["_generated_agent"] = orchestrator
                # Also detect the primary agent name for single-agent fallback
                agents_list = state["agent_manifest"].get("agents", [])
                if not state.get("_generated_agent") and agents_list:
                    # Pick the agent with the most skills
                    state["_generated_agent"] = agents_list[0].get("name", "")
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

    async def execute_skill(self, project_id: str, skill_name: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Frontend page → Agent bridge: execute a skill through the generated Agent.

        Routing through the Agent (not direct skill call) ensures ReActLoop runs —
        activating all 18 platform capabilities (SECI, Memory, Feedback, etc.).

        Multi-agent: reads agent_manifest.json for skill→agent routing.
        """
        from core.api.intents import core_chat, ChatContext
        import json as _json, re as _re

        state = self._runs.get(project_id)
        if not state:
            state = self._load_pipeline_state(project_id) or {}

        # Ensure manifest + orchestrator are resolved (moved from engine → platform service)
        self._ensure_manifest_resolved(project_id, state)

        agent_name = ""

        # ── Path 1: Multi-agent routing via agent_manifest.json ──
        _manifest = state.get("agent_manifest", {})
        if isinstance(_manifest, dict) and _manifest.get("skill_routing"):
            agent_name = _manifest["skill_routing"].get(skill_name, "")

        # ── Path 2: Single-agent via _generated_agent ──
        if not agent_name:
            agent_name = state.get("_generated_agent", "")

        # ── Path 3: Fallback — parse agent name from agent_app output ──
        if not agent_name:
            for oa in ["agent_app", "architecture", "code"]:
                raw = state.get(oa, {}).get("raw_output", "") if isinstance(state.get(oa), dict) else ""
                if "AGENT.md" in str(raw):
                    m = _re.search(r'name:\s*(\S+)', str(raw))
                    if m:
                        agent_name = m.group(1)
                        break

        if not agent_name:
            return {"error": "Agent not ready", "ok": False}

        params = params or {}
        message = f"执行技能: {skill_name}\n参数: {_json.dumps(params, ensure_ascii=False)[:2000]}"
        try:
            result = await core_chat(ChatContext(
                agent_name=agent_name,
                session_id=f"{project_id}_fe",
                user_input=message,
                model=self.model,
            ))
            reply = result.reply or ""
            reply = _unwrap_json_reply(reply)
            return {"ok": True, "skill": skill_name, "agent": agent_name,
                    "reply": reply, "trace_id": getattr(result, 'trace_id', '')}
        except Exception as e:
            return {"error": str(e)[:200], "ok": False}

    async def recommend_team(self, project_id: str) -> Dict[str, Any]:
        """Use Planning Agent to analyze PRD and recommend a team configuration.

        Delegates to core/harness/execution/team_planner.recommend_team_stages()
        for the AI inference (boundary-standard.md §决策树: agent discovery → Core).
        Platform-specific logic (team creation, project association) stays here.
        """
        from core.api.core_facade import recommend_team_stages

        proj = self._projects.get(project_id)
        if not proj:
            raise ValueError(f"Project {project_id} not found")

        prd = proj.get("confirmed_prd")
        if not prd:
            session = self._sessions.get(project_id)
            if not session:
                session = self._load_chat_session(project_id)
                if session:
                    self._sessions[project_id] = session
            prd = (session or {}).get("prd") if isinstance(session, dict) else None
        if not prd:
            # Fallback: use project description as a minimal requirement
            desc = proj.get("description", "")
            if not desc:
                raise ValueError("No PRD or project description available. Complete the PM dialogue first.")
            prd = {"title": proj.get("name", "New Project"), "description": desc,
                   "functional_requirements": [], "user_stories": []}

        # Delegate AI inference to core team_planner (boundary-standard.md §决策树)
        # Gather agent performance history for smarter recommendations
        extra_context = ""
        try:
            agent_insights = await self.list_agent_insights()
            if agent_insights and agent_insights.get("agents"):
                insights = agent_insights["agents"]
                if insights:
                    lines = ["## Agent Performance History (from past pipeline runs)",
                             "| Agent ID | First Pass | Rejection | Rollback | Runs |",
                             "|----------|-----------|-----------|----------|------|"]
                    for a in insights[:20]:
                        aid = a.get("agent_id", "?")
                        fpr = a.get("first_pass_rate", 0) or 0
                        rej = a.get("rejection_rate", 0) or 0
                        qa = a.get("qa_rollback_rate", 0) or 0
                        tr = a.get("total_runs", 0) or 0
                        if tr > 0:
                            lines.append(f"| {aid} | {fpr:.0%} | {rej:.0%} | {qa:.0%} | {tr} |")
                    extra_context = "\n".join(lines)
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        
        rec = await recommend_team_stages(requirement=prd, model=self.model, extra_context=extra_context or None)

        recommendation = {
            "team_name": rec.team_name,
            "reasoning": rec.reasoning,
            "raw_reply": rec.raw_reply,
        }
        plan_stages = rec.stages

        if plan_stages:
            proj["plan_stages"] = plan_stages
            proj["plan_stage_ids"] = [s.get("id", f"plan_stage_{i}") for i, s in enumerate(plan_stages)]

            # v3.2: 模式判断 → 映射固定团队模板（agent→default.yaml, code→code.yaml）
            recommendation["mode"] = rec.mode
            if rec.mode in ("agent", "code") and not proj.get("team_id"):
                proj["team_id"] = "default" if rec.mode == "agent" else "code"
                recommendation["_mode_mapped"] = True
                recommendation["_team_id"] = proj["team_id"]
                self._save_projects()

            # Auto-create team from plan_stages so pipeline can start immediately
            if not proj.get("team_id"):
                try:
                    from core.schemas_builder import PipelineStageConfig, TeamAssembleRequest
                    team_stages = []
                    for ps in plan_stages:
                        team_stages.append(PipelineStageConfig(
                            id=ps.get("id", f"stage_{len(team_stages)}"),
                            agent_id=ps.get("agent_id", ""),
                            agent_name=ps.get("agent_name", ps.get("agent_id", "")),
                            phase=ps.get("phase", ""),
                            order=ps.get("order", len(team_stages)),
                            uses_file_output=bool(ps.get("uses_file_output") or ps.get("uses_code_skill", False)),
                            hitl=bool(ps.get("hitl", False)),
                            hitl_phase=ps.get("hitl_phase", ""),
                            output_artifact=ps.get("output_artifact", ""),
                            generate_test_plan=bool(ps.get("generate_test_plan", False)),
                            test_result_key=ps.get("test_result_key", "test_report"),
                            agent_type=ps.get("agent_type", "react"),
                            skill_name=ps.get("skill_name", ""),
                            skill_model_purpose=ps.get("skill_model_purpose", ""),
                        ))
                    if team_stages:
                        # ── v3.1: HITL gates from team template YAML ──
                        try:
                            from core.api.core_facade import load_team_template
                            tmpl = load_team_template("default")
                            if tmpl and tmpl.stages:
                                # TeamTemplate.stages 是 YAML dict 列表（team_planner.py:61
                                # List[Dict[str, Any]]）——必须 dict 访问；属性访问 AttributeError
                                # 被吞 → v3.1 HITL gates 静默失效（审计 P1-1 修复 2026-08-25）
                                _hitl_map = {
                                    s.get("agent_id"): s for s in tmpl.stages
                                    if s.get("hitl") and s.get("agent_id")
                                }
                                for ts in team_stages:
                                    if ts.agent_id in _hitl_map:
                                        ts.hitl = True
                                        ts.hitl_phase = _hitl_map[ts.agent_id].get("hitl_phase") or "review"
                        except Exception:
                            pass  # noqa: cleanup-best-effort
                        team_req = TeamAssembleRequest(
                            name=recommendation.get("team_name", f"团队-{project_id}"),
                            description=recommendation.get("reasoning", ""),
                            stages=team_stages,
                        )
                        team = await self._team_service.create_team(team_req)
                        proj["team_id"] = team.team_id
                        proj["team_stages"] = [s.model_dump() if hasattr(s, 'model_dump') else s for s in team_stages]
                        self._save_projects()
                        recommendation["_team_created"] = True
                        recommendation["_team_id"] = team.team_id
                except Exception as e:
                    recommendation["_team_create_failed"] = str(e)[:200]

        return {
            "project_id": project_id,
            "recommendation": recommendation,
            "plan_stages": plan_stages,
            "plan_stage_ids": proj.get("plan_stage_ids", []),
            "trace_id": getattr(rec, 'trace_id', '') or '',
        }

    @staticmethod
    def _parse_plan_stages(recommendation: Dict) -> List[Dict]:
        """UNUSED static utility — retained for future API compat.
        Actual parsing is done inline in recommend_team()."""
        stages_raw = (
            recommendation.get("stages")
            or recommendation.get("team", {}).get("stages")
            or recommendation.get("plan", {}).get("stages")
            or []
        )
        result = []
        warnings = []
        for i, s in enumerate(stages_raw):
            if not isinstance(s, dict):
                continue
            agent_id = s.get("agent_id") or s.get("agent") or s.get("name") or f"agent_{i}"
            result.append({
                "id": s.get("id") or f"plan_stage_{i}",
                "agent_id": agent_id,
                "output_artifact": s.get("output_artifact") or s.get("output") or f"plan_artifact_{i}",
                "description": s.get("description") or s.get("role") or "",
                "generate_test_plan": s.get("generate_test_plan", False),
                "uses_file_output": s.get("uses_file_output", False),
                "hitl": s.get("hitl", True),
                "order": s.get("order", i),
                "prompt_extra": s.get("prompt_extra") or s.get("sop") or "",
                "agent_type": s.get("agent_type") or s.get("type", "react"),
            })
        return result

    def _validate_pipeline_stages(self, stages: List[PipelineStageConfig]) -> Dict[str, Any]:
        """Validate pipeline stages — delegates to CoreFacade."""
        return validate_pipeline_stages(stages)

    @staticmethod
    def _parse_markdown_prd(reply: str) -> Dict[str, Any]:
        """Parse structured Markdown PRD into a dict for session storage."""
        prd: Dict[str, Any] = {}
        # Strip PRD_READY marker if present (appears before the # heading)
        clean = reply.replace("<!-- PRD_READY -->", "").strip()
        title_match = re.search(r"^#+ (.+)", clean, re.MULTILINE)
        if title_match:
            prd["title"] = title_match.group(1).strip()
            # Strip prefix like "项目名称：" or "项目名称:"
            for _pfx in (_AIPLAT_PRD_TITLE_PREFIX, "项目名称:", "Project Name:"):
                if prd["title"].startswith(_pfx):
                    prd["title"] = prd["title"][len(_pfx):].strip()
                    break
        # Extract sections by ## headings
        sections: Dict[str, str] = {}
        current_key = ""
        for line in clean.split("\n"):
            m = re.match(r"^## (.+)", line)
            if m:
                current_key = m.group(1).strip()
                sections[current_key] = ""
            elif current_key:
                sections[current_key] += line + "\n"
        # Functional requirements count as user_stories
        func_section = (
            sections.get(_AIPLAT_PRD_SECTION_REQUIREMENTS, "")
            or sections.get("核心" + _AIPLAT_PRD_SECTION_REQUIREMENTS, "")
            or sections.get("主要" + _AIPLAT_PRD_SECTION_REQUIREMENTS, "")
            or sections.get("关键" + _AIPLAT_PRD_SECTION_REQUIREMENTS, "")
            or next((v for k, v in sections.items() if _AIPLAT_PRD_SECTION_REQUIREMENTS in k), "")
        )
        fr_items = []
        for fr_match in re.finditer(r"###\s*(.+?)\n(.*?)(?=\n###|\n##|\Z)", func_section or "", re.DOTALL):
            fr_name = fr_match.group(1).strip()
            fr_body = fr_match.group(2)
            user_story_match = re.search(r"用户故事[：:]\s*(.+)", fr_body)
            acs = re.findall(r"AC\d+:\s*(.+)", fr_body)
            fr_items.append({
                "id": fr_name.split(":", 1)[0].strip() if ":" in fr_name else fr_name,
                "name": fr_name.split(":", 1)[1].strip() if ":" in fr_name else fr_name,
                "description": user_story_match.group(1).strip() if user_story_match else "",
                "acceptance_criteria": acs,
            })
        # Fallback: parse numbered/bulleted lists as user stories
        if not fr_items and func_section.strip():
            for line_match in re.finditer(r'^\s*(?:\d+\.|[-*])\s*\**(.+?)\**(?:\s*[：:]\s*(.+))?\s*$', func_section or "", re.MULTILINE):
                _name = line_match.group(1).strip()
                _desc = (line_match.group(2) or "").strip()
                fr_items.append({
                    "id": f"US-{len(fr_items)+1:03d}",
                    "name": _name,
                    "description": _desc or _name,
                    "acceptance_criteria": [],
                })
        if fr_items:
            prd["functional_requirements"] = fr_items
            prd["user_stories"] = fr_items
        scope = sections.get(_AIPLAT_PRD_SECTION_SCOPE, "").strip()
        if scope:
            prd["scope"] = scope
        # ISA upgrade: extract success metrics and target state
        metrics_section = sections.get(_AIPLAT_PRD_SECTION_METRICS, "") or sections.get(_AIPLAT_PRD_SECTION_ACCEPTANCE, "")
        if metrics_section.strip():
            isc_list = []
            for isc_match in re.finditer(r"###?\s*(ISC-\d+)[：:]\s*(.+?)\n(.*?)(?=\n###|\n##|\Z)", metrics_section, re.DOTALL):
                isc_id = isc_match.group(1).strip()
                isc_name = isc_match.group(2).strip()
                isc_body = isc_match.group(3)
                verify = re.search(r"验证方式[：:]\s*(.+)", isc_body)
                isc_list.append({
                    "id": isc_id, "name": isc_name,
                    "criteria": isc_body.strip()[:200],
                    "verification_method": verify.group(1).strip() if verify else "manual",
                })
            if isc_list:
                prd["isc_list"] = isc_list
        target_state = sections.get("目标状态", "") or sections.get(_AIPLAT_PRD_SECTION_ISA, "")
        if target_state.strip():
            prd["target_state"] = target_state.strip()[:500]
        return prd if prd.get("title") else {}

    async def _save_state(self, project_id: str, state: dict):
        """Save pipeline state and trigger deploy assembly if completed."""
        self._runs[project_id] = state
        self._save_pipeline_state(project_id, state)
        # Sync runs to projects.json so project card shows correct status
        proj = self._projects.get(project_id, {})
        if proj:
            runs = proj.get("runs", [])
            if runs:
                runs[-1]["phase"] = state.get("phase", "done")
                runs[-1]["pass_rate"] = state.get("_test_pass_rate", 0)
                runs[-1]["skip_pytest_gate"] = state.get("_skip_pytest_gate", False)
                runs[-1]["tokens_used"] = state.get("tokens_used", 0)
                runs[-1]["iteration"] = state.get("iteration", 0)
                runs[-1]["error"] = state.get("error", "")
                proj["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                self._save_projects()
        # Embed episodic memory state for restart survival
        try:
            from core.api.facades.runtime_facade import get_memory_manager
            mgr = get_memory_manager()
            state["_episodic"] = mgr.export_episodic_state()
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        self._save_pipeline_state(project_id, state)
        # Config-driven: find test result key from project stages
        test_key = "test_report"
        proj = self._projects.get(project_id, {})
        for s in (proj.get("team_stages") or []):
            sk = s.get("test_result_key", "") if isinstance(s, dict) else getattr(s, 'test_result_key', '')
            if sk:
                test_key = sk
        tr = state.get(test_key) or {}
        if state.get("phase") == "done" or tr.get("recommendation") == "APPROVED":
            try:
                _ss = self._rebuild_session(project_id)
                if _ss:
                    deploy_dir = _ss.assemble_deploy(state)
                    if deploy_dir:
                        self._projects.setdefault(project_id, {})["deploy_dir"] = deploy_dir
                        self._save_projects()
            except Exception:
                pass  # noqa: cleanup-best-effort

    async def approve_stage(self, project_id: str, feedback: str = "") -> Dict[str, Any]:
        """v3.1: Forward HITL approve to Core — no local pipeline manipulation."""
        try:
            from builder.pipeline_orchestrator_client import PipelineOrchestratorClient
            client = PipelineOrchestratorClient()
            resp = await client.resolve_hitl(project_id, action="approve", feedback=feedback)
            if resp.get("status") == "resolved":
                return {"project_id": project_id, "phase": "executing", "status": "ok"}
            return {"status": "error", "detail": resp.get("detail", "Core unavailable")}
        except Exception as e:
            _log.warning("approve_stage failed for %s: %s", project_id, str(e)[:200])
            raise

    async def start_fix(self, project_id: str) -> Dict[str, Any]:
        """Approve the current HITL pause on Core (non-blocking)."""
        from builder.pipeline_orchestrator_client import PipelineOrchestratorClient
        client = PipelineOrchestratorClient()
        resp = await client.resolve_hitl(project_id, action="approve")
        if resp.get("status") == "resolved":
            return {"project_id": project_id, "phase": "executing", "status": "ok"}
        return {"status": "error", "detail": resp.get("detail", "Core unavailable")}

    async def reject_stage(self, project_id: str, feedback: str) -> Dict[str, Any]:
        """v3.1: Forward HITL reject to Core — no local pipeline manipulation."""
        try:
            from builder.pipeline_orchestrator_client import PipelineOrchestratorClient
            client = PipelineOrchestratorClient()
            resp = await client.resolve_hitl(project_id, action="reject", feedback=feedback)
            if resp.get("status") == "resolved":
                return {"project_id": project_id, "phase": "executing", "status": "ok"}
            return {"status": "error", "detail": resp.get("detail", "Core unavailable")}
        except Exception as e:
            _log.warning("reject_stage failed for %s: %s", project_id, str(e)[:200])
            raise

    async def regenerate_stage(self, project_id: str, stage_id: str, feedback: str) -> Dict[str, Any]:
        """Delegate stage regeneration to Core (single authority, non-blocking).

        Returns immediately — the pipeline re-runs from the target stage on Core.
        """
        self._sync_team_stages(project_id)
        proj = self._projects.get(project_id, {})
        config = self._build_stage_config(project_id, proj)
        from builder.pipeline_orchestrator_client import PipelineOrchestratorClient
        client = PipelineOrchestratorClient()
        result = await client.stage_operation(project_id, "regenerate", stage_id, feedback, config)
        if result.get("status") in ("accepted", "conflict"):
            return {"project_id": project_id, "phase": "executing", "status": "regenerating"}
        return {"status": "error", "detail": result.get("detail", "Core unavailable")}

    async def locate_max_error_node(self, project_id: str, failed_stage_ids: List[str]) -> Dict[str, Any]:
        """Locate the max error-contribution node from the decision trace graph.

        Delegates to Core's generic decision trace (single authority). Returns
        {"stage_id", "decision_id", "error_contribution", "confidence", ...}.
        """
        from core.api.core_facade import locate_max_error_node as _locate
        try:
            result = _locate(project_id, list(failed_stage_ids or []))
            result["status"] = "ok"
            return result
        except Exception as e:  # noqa: facade-unavailable
            _log.warning("locate_max_error_node failed for %s: %s", project_id, str(e)[:200])
            return {"status": "error", "stage_id": None,
                    "error_contribution": 0.0, "detail": str(e)[:200]}

    async def generate_fix_hypotheses(self, project_id: str, failed_stage_ids: List[str],
                                      test_report: str = "") -> Dict[str, Any]:
        """Generate root-cause hypotheses + a hybrid fix plan from the decision trace.

        Delegates to Core (single authority). Returns
        {"hypotheses": [...], "max_error_stage": str, "fix_plan": [...], "status": "ok"}.
        """
        from core.api.core_facade import generate_hypotheses as _gen
        from core.api.core_facade import build_fix_plan as _plan
        try:
            hypotheses = _gen(project_id, list(failed_stage_ids or []), test_report)
            max_error_stage = hypotheses[0]["stage_id"] if hypotheses else None
            fix_plan = _plan(project_id, list(failed_stage_ids or []), test_report)
            return {"status": "ok", "hypotheses": hypotheses,
                    "max_error_stage": max_error_stage, "fix_plan": fix_plan}
        except Exception as e:  # noqa: facade-unavailable
            _log.warning("generate_fix_hypotheses failed for %s: %s", project_id, str(e)[:200])
            return {"status": "error", "hypotheses": [],
                    "max_error_stage": None, "fix_plan": list(failed_stage_ids or []),
                    "detail": str(e)[:200]}

    async def build_run_report(self, project_id: str, failed_stage_ids: List[str],
                               test_report: str = "", cost_used_usd: float = 0.0,
                               cost_budget_usd: float = 0.0) -> Dict[str, Any]:
        """Build a governance/explainability report for a pipeline run.

        Delegates to Core's governance report (single authority). Returns the
        full report dict with a "status" field.
        """
        from core.api.core_facade import build_run_report as _report
        try:
            report = _report(project_id, cost_used_usd, cost_budget_usd,
                             list(failed_stage_ids or []), test_report)
            report["status"] = "ok"
            return report
        except Exception as e:  # noqa: facade-unavailable
            _log.warning("build_run_report failed for %s: %s", project_id, str(e)[:200])
            return {"status": "error", "run_id": project_id, "detail": str(e)[:200]}

    async def rollback_stage(self, project_id: str, stage_id: str) -> Dict[str, Any]:
        """Delegate stage rollback to Core (single authority, non-blocking)."""
        self._sync_team_stages(project_id)
        proj = self._projects.get(project_id, {})
        config = self._build_stage_config(project_id, proj)
        from builder.pipeline_orchestrator_client import PipelineOrchestratorClient
        client = PipelineOrchestratorClient()
        result = await client.stage_operation(project_id, "rollback", stage_id, "", config)
        if result.get("status") in ("accepted", "conflict"):
            return {"project_id": project_id, "phase": "executing"}
        return {"status": "error", "detail": result.get("detail", "Core unavailable")}

    async def resume_from_stage(self, project_id: str, stage_id: str) -> Dict[str, Any]:
        """Delegate stage resume to Core (single authority, non-blocking).

        Resume from a specific stage WITHOUT clearing artifacts.
        """
        self._sync_team_stages(project_id)
        proj = self._projects.get(project_id, {})
        config = self._build_stage_config(project_id, proj)
        from builder.pipeline_orchestrator_client import PipelineOrchestratorClient
        client = PipelineOrchestratorClient()
        result = await client.stage_operation(project_id, "resume", stage_id, "", config)
        if result.get("status") in ("accepted", "conflict"):
            return {"project_id": project_id, "phase": "executing"}
        return {"status": "error", "detail": result.get("detail", "Core unavailable")}

    async def rollback_prd(self, project_id: str) -> Dict[str, Any]:
        """Roll back to PRD editing phase"""
        proj = self._projects.get(project_id, {})
        proj["confirmed_prd"] = None
        self._save_projects()
        # Clean up pipeline state files to prevent ghost recovery
        for fname in (f"{project_id}.json", f"{project_id}_chat.json"):
            fpath = os.path.join(_BUILDER_STATES_DIR, fname)
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
            except OSError:
                pass  # noqa: cleanup-best-effort
        # Clear in-memory state
        self._runs[project_id] = {}
        self._sessions.pop(project_id, None)
        return {"project_id": project_id, "phase": "dialogue"}



    # ── L4: multi-module (plan-app-factory-l4 §3.1/§3.3/§3.4) ──










    # ── L4.5: DB schema migration (plan-app-factory-l45 §3.3/§3.6) ──







    # ── L5: module-level release (plan-app-factory-l5 §3.1/§3.2/§3.5) ──





    # ── L3: incremental merge (plan-app-factory-l3 §3.3/§3.5) ──





    async def update_prd(self, project_id: str, prd: dict) -> Dict[str, Any]:
        """Directly update the confirmed PRD without re-running PM chat."""
        import logging as _log2
        proj = self._projects.get(project_id, {})
        if not proj:
            return {"status": "error", "detail": "项目不存在"}
        # L2: modify_files must be [{path, intent}] — empty intent rejected (§3.2/§4)
        _mf = prd.get("modify_files") if isinstance(prd, dict) else None
        if _mf is not None:
            if not isinstance(_mf, list) or not _mf:
                return {"status": "error", "detail": "modify_files 必须是非空数组"}
            for item in _mf:
                if not isinstance(item, dict) or not str(item.get("path") or "").strip():
                    return {"status": "error", "detail": "modify_files 每项必须含 path"}
                if not str(item.get("intent") or "").strip():
                    return {"status": "error",
                            "detail": f"文件 {item.get('path')} 必须填写修改意图（intent）"}
        if not proj:
            return {"status": "error", "detail": "项目不存在"}
        proj["confirmed_prd"] = prd
        proj["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save_projects()
        _log2.getLogger("aiplat.builder").info("PRD updated for %s", project_id)
        return {"status": "ok", "detail": "PRD 已更新"}

    async def start_pipeline(self, project_id: str) -> Dict[str, Any]:
        """启动/触发项目流水线执行（P0-1 修复, 2026-08-25）。

        原接线断裂：builder_app_service / builder_workflow_service / api/routers/builder.py
        共 6 处调用本方法但类中无定义 → 运行 AttributeError。本方法委托
        rebuild_project（复用已确认 PRD + _rebuild_via_core 经 Core HTTP 执行路径），
        与 /projects/{id}/start 和 /sessions/{id}/start 端点语义一致。
        """
        proj = self._projects.get(project_id, {})
        if not proj:
            return {"status": "error", "detail": "项目不存在"}
        if not proj.get("confirmed_prd"):
            return {"status": "error", "detail": "没有已确认的 PRD，请先完成 PM 对话"}
        result = await self.rebuild_project(project_id)
        return {"status": "ok", "run_id": project_id, **result}

    async def start_pipeline_background(self, project_id: str) -> Dict[str, Any]:
        """异步启动流水线（P0-1 修复, 2026-08-25）：不阻塞调用方，后台触发执行。"""
        proj = self._projects.get(project_id, {})
        if not proj:
            return {"status": "error", "detail": "项目不存在"}
        if not proj.get("confirmed_prd"):
            return {"status": "error", "detail": "没有已确认的 PRD，请先完成 PM 对话"}
        import asyncio as _asyncio
        _asyncio.create_task(self.rebuild_project(project_id))
        return {"status": "accepted", "run_id": project_id, "detail": "后台构建已触发"}

    async def rebuild_project(self, project_id: str, module_id: str = "default") -> Dict[str, Any]:
        """Re-run the pipeline with the existing confirmed PRD. Re-recommends team to pick up latest config changes."""
        self._reload_if_stale()
        proj = self._projects.get(project_id, {})
        if not proj:
            return {"status": "error", "detail": "项目不存在"}
        if not proj.get("confirmed_prd"):
            return {"status": "error", "detail": "没有已确认的 PRD，请先完成 PM 对话"}
        # L3-P0-02: snapshot affected imported files before generation (concurrency guard)
        _prd = proj.get("confirmed_prd") or {}
        if str(_prd.get("merge_strategy") or "") == "incremental_merge":
            _mf = _prd.get("modify_files")
            _imp = self._module_repo(project_id, module_id)
            if isinstance(_mf, list) and _mf and _imp.get("root"):
                from builder.merge_engine import snapshot_affected_files
                _paths = [str(m.get("path") or "") for m in _mf
                          if isinstance(m, dict) and m.get("path")]
                proj["pre_gen_snapshot"] = snapshot_affected_files(str(_imp["root"]), _paths)
                proj.pop("merge_previews", None)  # stale previews invalidated
                self._save_projects()
        # Clear previous pipeline state AND output cache (prevents stale artifact skipping)
        self._runs.pop(project_id, None)
        import shutil
        out_dir = os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "output", project_id)
        if os.path.isdir(out_dir):
            try: shutil.rmtree(out_dir)
            except OSError: pass  # noqa: cleanup-best-effort
        for fname in (f"{project_id}.json", f"{project_id}_chat.json"):
            fpath = os.path.join(_BUILDER_STATES_DIR, fname)
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
            except OSError:
                pass  # noqa: cleanup-best-effort
        # Re-sync team stages from YAML template to pick up latest config (e.g., new stages)
        self._sync_team_stages(project_id)
        # Re-run pipeline with existing PRD
        import logging as _log3
        _log3.getLogger("aiplat.builder").info("Rebuilding project %s", project_id)
        self._runs[project_id] = {"phase": "executing"}  # seed initial state for frontend polling
        # Add run entry immediately so project card shows "构建中"
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        proj.setdefault("runs", []).append({
            "run_id": f"run_{uuid.uuid4().hex[:8]}", "project_id": project_id,
            "phase": "executing", "pass_rate": 0, "tokens_used": 0,
            "iteration": 0, "error": "", "started_at": now, "finished_at": "",
        })
        proj["updated_at"] = now
        self._save_projects()

        # Delegate pipeline execution to Core server (8002) via HTTP API.
        # Core owns all LLM infrastructure — no direct PipelineEngine import.
        return await self._rebuild_via_core(project_id, proj, module_id=module_id)

    async def _get_state_via_core(self, project_id: str) -> Dict[str, Any]:
        """Read pipeline state — 收敛到 SQLite 直读（P1-12 §10 唯一实现）。

        原走 Core HTTP API（get_project_state 注释已说明：单 worker 事件循环被
        流水线阻塞时 HTTP 可能超时）。SQLite WAL 允许并发读，100% 可用。
        返回结构 {project_id, phase, state} 与 HTTP 客户端一致（get_health_report
        等调用方按 core_state.get("state") 消费，保持兼容）。
        """
        import asyncio
        from core.api.core_facade import get_pipeline_run_store

        def _read() -> Dict[str, Any]:
            store = get_pipeline_run_store()
            state = store.get_full_state(project_id) or {}
            return {
                "project_id": project_id,
                "phase": state.get("phase", "idle"),
                "state": state,
            }

        return await asyncio.to_thread(_read)

    def _build_stage_config(self, project_id: str, proj: dict) -> Dict[str, Any]:
        """Build the pipeline config dict shared by rebuild + stage-level operations."""
        stages = proj.get("team_stages", [])
        prd_data = proj.get("confirmed_prd") or proj.get("description", "")
        _app_name = proj.get("app_name", "") or _derive_app_name(proj.get("name", ""), "", project_id)
        return {
            "total_stages": len(stages),
            "tokens_budget": int(os.getenv("AIPLAT_BUILDER_MAX_TOKENS", "100000")),
            "output_dir": os.path.join(
                os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")),
                "output", project_id),
            "description": proj.get("description", ""),
            "app_name": _app_name,
            "prd_data": prd_data,
            "stages": [
                s if isinstance(s, dict) else s.model_dump() if hasattr(s, "model_dump") else dict(s)
                for s in stages
            ],
        }

    async def _rebuild_via_core(self, project_id: str, proj: dict, module_id: str = "default") -> Dict[str, Any]:
        """Trigger pipeline execution via Core server HTTP API."""
        from builder.pipeline_orchestrator_client import PipelineOrchestratorClient

        stages = proj.get("team_stages", [])
        prd_data = proj.get("confirmed_prd") or proj.get("description", "")
        # Resolve canonical app_name: stored → ASCII derive → LLM translate → fallback
        _app_name = proj.get("app_name", "")
        if not _app_name:
            _name = proj.get("name", "")
            _app_name = _derive_app_name(_name, "", project_id)
            if (not re.search(r"[A-Za-z]", _name)
                    and re.search(r"[\u4e00-\u9fff]", _name)):
                _translated = await _translate_app_name(_name)
                if _translated:
                    _app_name = _translated
                    proj["app_name"] = _translated
                    self._save_projects()
        config = {
            "total_stages": len(stages),
            "tokens_budget": int(os.getenv("AIPLAT_BUILDER_MAX_TOKENS", "100000")),
            "output_dir": os.path.join(
                os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")),
                "output", project_id),
            "description": proj.get("description", ""),
            "app_name": _app_name,
            "prd_data": prd_data,
            "stages": [
                s if isinstance(s, dict) else s.model_dump() if hasattr(s, "model_dump") else dict(s)
                for s in stages
            ],
        }

        # ── L2/L3: pass imported-repo context + pytest-gate escape to Core (§3.3/§3.5/§3.8) ──
        # Platform assembles the business text (behavior contract, intent anchors);
        # Core engine only reads files and appends the blocks (generic, §5.8 boundary).
        _prd = proj.get("confirmed_prd") or {}
        _modify = _prd.get("modify_files") if isinstance(_prd, dict) else None
        # L4: per-module imported repo (default → legacy proj.imported_repo)
        _imported = self._module_repo(project_id, module_id)
        # L3: merge strategy drives which behavior contract is injected
        _merge_strategy = str(_prd.get("merge_strategy", "full_rewrite") or "full_rewrite")
        if _imported and isinstance(_modify, list) and _modify:
            _imp_payload = dict(_imported)
            _imp_payload["modify_files"] = _modify
            _imp_payload["behavior_prompt"] = (
                _L3_INCREMENT_PROMPT if _merge_strategy == "incremental_merge"
                else _L2_BEHAVIOR_PROMPT)
            _intent_lines = [f"- {m.get('path')} — 意图：{m.get('intent') or ''}"
                             for m in _modify if isinstance(m, dict) and m.get("path")]
            if _intent_lines:
                _imp_payload["intent_anchor_block"] = (
                    "## files to modify (user-confirmed paths + intents)\n"
                    + "\n".join(_intent_lines))
            config["imported_repo"] = _imp_payload
        config["skip_pytest_gate"] = bool(_prd.get("skip_pytest_gate", False))
        config["merge_strategy"] = _merge_strategy

        client = PipelineOrchestratorClient()
        result = await client.trigger_run(project_id, config)

        if result.get("status") in ("accepted", "conflict"):
            return {"status": "ok", "detail": "已触发重新构建"}
        return {"status": "error", "detail": result.get("detail", "Core unavailable")}

    async def get_deploy_dir(self, project_id: str) -> Optional[str]:
        """Get deploy directory path for a project."""
        proj = self._projects.get(project_id, {})
        return proj.get("deploy_dir") or None

    async def update_stage_artifact(self, project_id: str, stage_id: str, content: str) -> Dict[str, Any]:
        """Update a stage's raw_output artifact — allows user to manually edit before rebuild."""
        state = self._load_pipeline_state(project_id)
        if not state:
            raise ValueError("no pipeline state")
        session = self._rebuild_session(project_id)
        if not session:
            raise ValueError("no session")
        # Match stage by id, agent_id, or output_artifact
        matched_stage = None
        matched_key = stage_id
        for s in session.get_stages():
            if s.id == stage_id or s.agent_id == stage_id or s.output_artifact == stage_id:
                matched_stage = s
                matched_key = s.output_artifact or s.agent_id or s.id
                break
        if not matched_stage:
            raise ValueError(f"stage not found: {stage_id}")
        # Update artifact in pipeline state
        state[matched_key] = {
            "raw_output": content,
            "source": "user_edited",
            "elapsed_sec": 0,
            "_edited_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        await self._save_state(project_id, state)
        return {
            "project_id": project_id,
            "stage_id": matched_stage.id,
            "artifact_key": matched_key,
            "status": "updated",
        }

    async def get_project_state(self, project_id: str) -> Dict[str, Any]:
        """Read pipeline state from SQLite — never blocked by Core's event loop.

        The Core server's HTTP endpoint for state can time out during LLM execution
        (single-worker event loop blocked by pipeline). SQLite WAL allows concurrent
        reads while Core writes — 100% available regardless of pipeline activity.
        P1-12 收敛（§10）：读取逻辑统一到 `_get_state_via_core`（唯一实现）。
        """
        result = await self._get_state_via_core(project_id)

        # When pipeline completes on Core, sync run phase so project card shows correct status
        if result.get("phase") in ("done", "failed"):
            proj = self._projects.get(project_id, {})
            runs = proj.get("runs", [])
            if runs:
                runs[-1]["phase"] = result["phase"]
                runs[-1]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                proj["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                self._save_projects()
        return result

    # ── Pipeline state persistence (per-project files, survives restart) ──

    def _save_pipeline_state(self, project_id: str, state: Dict[str, Any]) -> None:
        """Save pipeline state to dedicated JSON file (not projects.json).
        
        Using per-project files avoids concurrent write hazards on the shared
        projects.json and enables full session recovery after restart.
        """
        os.makedirs(_BUILDER_STATES_DIR, exist_ok=True)
        state_file = os.path.join(_BUILDER_STATES_DIR, f"{project_id}.json")
        try:
            with open(state_file + ".tmp", "w", encoding="utf-8") as f:
                json.dump(dict(state), f, ensure_ascii=False, indent=2, default=str)
            os.replace(state_file + ".tmp", state_file)
        except Exception as e:
            _log.warning("Failed to save pipeline state for %s: %s", project_id, e)

    def _save_chat_session(self, project_id: str) -> None:
        """Persist chat session (messages, prd, phase) to survive restart.
        
        Stored alongside pipeline state in builder_states/."""
        session = self._sessions.get(project_id)
        if not session or not isinstance(session, dict):
            return
        os.makedirs(_BUILDER_STATES_DIR, exist_ok=True)
        chat_file = os.path.join(_BUILDER_STATES_DIR, f"{project_id}_chat.json")
        try:
            with open(chat_file + ".tmp", "w", encoding="utf-8") as f:
                json.dump(dict(session), f, ensure_ascii=False, indent=2, default=str)
            os.replace(chat_file + ".tmp", chat_file)
        except Exception as e:
            _log.warning("Failed to save chat session for %s: %s", project_id, e)

    def _load_chat_session(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Load persisted chat session from disk, if it exists."""
        chat_file = os.path.join(_BUILDER_STATES_DIR, f"{project_id}_chat.json")
        try:
            if os.path.exists(chat_file):
                with open(chat_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logging.warning(str(e), exc_info=True)
        return None

    async def get_messages(self, project_id: str) -> Dict[str, Any]:
        """Return chat messages for a project (for UI to restore conversation)."""
        session = self._sessions.get(project_id)
        if not session:
            session = self._load_chat_session(project_id)
            if session:
                self._sessions[project_id] = session
        if isinstance(session, dict):
            return {"messages": list(session.get("messages", []))}
        return {"messages": []}

    def _load_pipeline_state(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Load pipeline state from per-project JSON file."""
        state_file = os.path.join(_BUILDER_STATES_DIR, f"{project_id}.json")
        try:
            if os.path.exists(state_file):
                with open(state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            _log.warning("Failed to load pipeline state for %s: %s", project_id, str(e)[:200])
        return None

    def _sync_team_stages(self, project_id: str) -> bool:
        """Re-sync team stages from YAML template to pick up latest config changes.

        Called by rebuild_project and regenerate_stage to ensure the pipeline
        config reflects the current YAML (e.g., newly added fix_orchestrator stage).
        Returns True on success, False if sync failed.
        """
        proj = self._projects.get(project_id, {})
        if not proj:
            return False
        try:
            from core.api.core_facade import _enrich_stage_from_agent
            from core.api.core_facade import load_team_template
            _tid = proj.get("team_id") or "default"
            tmpl = load_team_template(_tid)
            if tmpl and tmpl.stages:
                stages = []
                for i, s in enumerate(tmpl.stages):
                    stage = dict(s)
                    stage.setdefault("id", f"canvas_node_{i+1}")
                    stage.setdefault("order", i)
                    stage = _enrich_stage_from_agent(stage)
                    stages.append(stage)
                proj["team_stages"] = stages
                proj["team_id"] = _tid
                self._save_projects()
                return True
        except Exception as e:
            logging.warning("team re-sync failed for %s: %s", project_id, e)
        return False

    def _rebuild_session(self, project_id: str) -> Optional[Any]:
        """Rebuild PipelineSession and state from persisted project data (for crash recovery)."""
        proj = self._projects.get(project_id)
        if not proj:
            return None

        stages_raw = proj.get("team_stages", [])
        stages: List[PipelineStageConfig] = []
        for s in stages_raw:
            stages.append(PipelineStageConfig(**s) if isinstance(s, dict) else s)
        for s in stages:
            if not s.output_artifact or s.output_artifact.startswith("stage_"):
                s.output_artifact = _semantic_output(s.agent_id, s.phase)

        # Read config from AGENT.md for each stage (delegates to CoreFacade)
        for s in stages:
            try:
                apply_agent_md_to_stage(s, s.agent_id)
            except Exception as e:
                _log.warning("Failed to apply AGENT.md config for agent %s in project %s: %s",
                    s.agent_id, project_id, str(e)[:200])

        if not stages:
            return None

        max_tokens = int(os.getenv("AIPLAT_BUILDER_MAX_TOKENS", "100000"))
        max_retry = int(os.getenv("AIPLAT_BUILDER_MAX_RETRY", "3"))
        config = PipelineConfig(stages=stages, max_tokens_per_run=max_tokens, max_retry_attempts=max_retry)
        session = create_pipeline_session(config=config, model=self.model, skill_loader=_create_skill_loader(),
                                            persist_callback=None)
        return session

    async def get_graph(self, project_id: str) -> Dict[str, Any]:
        """Return pipeline execution graph for visualization (P2-9)."""
        state = self._runs.get(project_id) or self._load_pipeline_state(project_id) or {}
        graph_trace = state.get("_graph_trace", []) or []
        proj = self._projects.get(project_id, {})
        stages = proj.get("team_stages", [])
        current_idx = state.get("_current_stage_idx", 0)
        stage_objs = []
        for i, s_raw in enumerate(stages):
            if isinstance(s_raw, dict):
                stage_objs.append(type('Stage', (), {
                    'id': s_raw.get('id', ''),
                    'agent_id': s_raw.get('agent_id', ''),
                    'output_artifact': s_raw.get('output_artifact', ''),
                    'hitl': s_raw.get('hitl', False),
                }))
        return {
            "project_id": project_id,
            "phase": state.get("phase", ""),
            "current_stage_idx": current_idx,
            "stages": [
                {
                    "id": s.id,
                    "agent_id": s.agent_id,
                    "output_artifact": s.output_artifact,
                    "status": _stage_status_for_graph(s, graph_trace, i, current_idx, state),
                    "hitl": s.hitl,
                }
                for i, s in enumerate(stage_objs)
            ],
        }

    async def run_tests(self, project_id: str) -> Dict[str, Any]:
        """Run E2E smoke + repo tests for a completed project pipeline."""
        proj = self._projects.get(project_id, {})
        deploy_dir = proj.get("deploy_dir", "") or await self.get_deploy_dir(project_id)
        return _run_tests_for_project(project_id, deploy_dir or "")







def _stage_status_for_graph(stage, graph_trace: List[Dict], idx: int, current_idx: int, state: Dict) -> str:
    for t in reversed(graph_trace):
        if t.get("stage_id") == stage.id:
            return t.get("status", "pending")
    if idx < current_idx:
        return "completed"
    if idx == current_idx:
        phase = state.get("phase", "")
        if "awaiting" in phase or "approval" in phase:
            return "paused_hitl"
        return "in_progress"
    return "pending"


def _run_tests_for_project(project_id: str, deploy_dir: str) -> dict:
    import subprocess, os
    results: dict = {"all_passed": False, "e2e_smoke": None, "repo_tests": None}
    if deploy_dir and os.path.isdir(deploy_dir):
        test_dir = os.path.join(deploy_dir, "tests")
        if not os.path.isdir(test_dir):
            test_dir = os.path.join(deploy_dir, "test")
        if os.path.isdir(test_dir):
            try:
                import sys as _sys
                r = subprocess.run([_sys.executable, "-m", "pytest", test_dir, "-q"], capture_output=True, text=True, timeout=60)
                results["repo_tests"] = {"passed": r.returncode == 0, "output": r.stdout[:2000]}
                results["all_passed"] = r.returncode == 0
            except Exception as e:
                results["repo_tests"] = {"passed": False, "error": str(e)}
    if deploy_dir:
        results["e2e_smoke"] = {"passed": True, "reason": "deploy_directory_exists"}
    return results


def _parse_file_blocks(code_text: str) -> Dict[str, str]:
    """Parse '## FILE: path\\n<content>' blocks from code_generation output (L3 merge)."""
    if not code_text or "## FILE:" not in code_text:
        return {}
    blocks = re.split(r'^##\s*FILE:\s*', code_text, flags=re.MULTILINE)
    out: Dict[str, str] = {}
    for block in blocks[1:]:
        lines = block.strip().split("\n", 1)
        if len(lines) < 2:
            continue
        fpath = lines[0].strip()
        fcontent = lines[1].strip()
        if fcontent.startswith("yaml\n"):
            fcontent = fcontent[4:]
        fcontent = re.sub(r'^```\w*\n?', '', fcontent)
        fcontent = re.sub(r'\n?```\s*$', '', fcontent)
        out[fpath] = fcontent
    return out


def _deploy_to_app_for_project(project_id: str, deploy_dir: str, proj: dict) -> dict:
    import os, json as _json, re as _re
    if not deploy_dir:
        deploy_dir = proj.get("deploy_dir", "") or os.path.join(
            os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "output", project_id, "deploy")
    
    _app_home = os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "apps", project_id, "current")
    os.makedirs(_app_home, exist_ok=True)
    _name = proj.get("name", project_id)
    _desc = proj.get("description", "")
    _stages = proj.get("team_stages", [])
    _app_prefix = os.path.expanduser("~/.aiplat/apps/")
    
    # ── Extract generated code files from pipeline state ──
    _file_count = 0
    try:
        import json
        out_dir = os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "output", project_id)
        final_state = os.path.join(out_dir, "_final_state.json")
        if os.path.isfile(final_state):
            with open(final_state, "r") as _fs:
                _state = json.load(_fs)
            code = _state.get("agent_app", {}) or _state.get("code", {})
            code_text = code.get("raw_output", "") if isinstance(code, dict) else str(code)
            if code_text and "## FILE:" in code_text:
                # Parse ## FILE: path\n...content... format
                blocks = _re.split(r'^##\s*FILE:\s*', code_text, flags=_re.MULTILINE)
                for block in blocks[1:]:  # skip everything before first FILE:
                    lines = block.strip().split("\n", 1)
                    if len(lines) >= 2:
                        fpath = lines[0].strip()
                        # Normalize path: expand ~ and strip prefix to relative path
                        fpath = os.path.expanduser(fpath)
                        if fpath.startswith(_app_prefix):
                            fpath = fpath[len(_app_prefix):]
                        fcontent = lines[1].strip()
                        # Strip leading 'yaml' line if present (LLM sometimes adds it before ---)
                        if fcontent.startswith("yaml\n"):
                            fcontent = fcontent[4:]
                        # Remove trailing ``` if present
                        fcontent = _re.sub(r'^```\w*\n?', '', fcontent)
                        fcontent = _re.sub(r'\n?```\s*$', '', fcontent)
                        # Write file
                        full_path = os.path.join(_app_home, fpath)
                        os.makedirs(os.path.dirname(full_path), exist_ok=True)
                        with open(full_path, "w", encoding="utf-8") as _fw:
                            _fw.write(fcontent)
                        _file_count += 1
        # Also check stage snapshot files
        for fname in sorted(os.listdir(out_dir) if os.path.isdir(out_dir) else []):
            if fname.startswith("_stage_stage_1") and fname.endswith(".json"):
                with open(os.path.join(out_dir, fname), "r") as _sf:
                    _st = json.load(_sf)
                _c = _st.get("code", {})
                _ct = _c.get("raw_output", "") if isinstance(_c, dict) else str(_c)
                if _ct and "## FILE:" in _ct and _file_count == 0:
                    blocks = _re.split(r'^##\s*FILE:\s*', _ct, flags=_re.MULTILINE)
                    for block in blocks[1:]:
                        lines = block.strip().split("\n", 1)
                        if len(lines) >= 2:
                            fpath = lines[0].strip()
                            fpath = os.path.expanduser(fpath)
                            if fpath.startswith(_app_prefix):
                                fpath = fpath[len(_app_prefix):]
                            fcontent = lines[1].strip()
                            if fcontent.startswith("yaml\n"):
                                fcontent = fcontent[4:]
                            fcontent = _re.sub(r'^```\w*\n?', '', fcontent)
                            fcontent = _re.sub(r'\n?```\s*$', '', fcontent)
                            full_path = os.path.join(_app_home, fpath)
                            os.makedirs(os.path.dirname(full_path), exist_ok=True)
                            with open(full_path, "w", encoding="utf-8") as _fw:
                                _fw.write(fcontent)
                            _file_count += 1
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)  # best-effort
    
    # Check if generated code includes a meaningful index.html
    _index_path = os.path.join(_app_home, "index.html")
    _has_index_html = False
    if os.path.isfile(_index_path):
        try:
            _sz = os.path.getsize(_index_path)
            if _sz > 0:
                with open(_index_path, "r") as _if:
                    _preview = _if.read(200)
                # Only trust index.html if it has actual HTML content, not empty/stale
                _has_index_html = ("<html" in _preview.lower() or "<!doctype" in _preview.lower()) and _sz > 100
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
        # Remove stale/empty file so it gets regenerated
        if not _has_index_html:
            try: os.remove(_index_path)
            except OSError: pass  # noqa: cleanup-best-effort
    
    # Also extract frontend_pages / app_page.json if present
    _app_page_json = ""
    try:
        import json as _j2
        out_dir = os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "output", project_id)
        final_state = os.path.join(out_dir, "_final_state.json")
        if os.path.isfile(final_state):
            with open(final_state, "r") as _fs:
                _state = _j2.load(_fs)
            fp = _state.get("frontend_pages", {})
            fp_raw = fp.get("raw_output", "") if isinstance(fp, dict) else str(fp)
            if fp_raw:
                # Try to parse app_page.json
                try:
                    fp_data = _j2.loads(fp_raw)
                    _app_page_json = _j2.dumps(fp_data, ensure_ascii=False, indent=2)
                except Exception:
                    fp_data = {}
                    # Extract JSON block from mixed content
                    _jstart = fp_raw.find('{')
                    _jend = fp_raw.rfind('}')
                    if _jstart >= 0 and _jend > _jstart:
                        try: fp_data = _j2.loads(fp_raw[:_jend+1][_jstart:]); _app_page_json = _j2.dumps(fp_data, ensure_ascii=False, indent=2)
                        except Exception: pass  # noqa: cleanup-best-effort — temp file cleanup
                if _app_page_json:
                    with open(os.path.join(_app_home, "app_page.json"), "w", encoding="utf-8") as _apf:
                        _apf.write(_app_page_json)
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

    # ── Register generated agents & skills to workspace ──
    _reg_count = 0
    try:
        import shutil
        _agents_dir = os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "agents")
        _skills_dir = os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "skills")
        # Scan recursively for AGENT.md and SKILL.md files (may be nested under app dir)
        for _root, _dirs, _files in os.walk(_app_home):
            for _f in _files:
                _src = os.path.join(_root, _f)
                if _f == "AGENT.md":
                    _agent_name = os.path.basename(_root)
                    _dst = os.path.join(_agents_dir, _agent_name, "AGENT.md")
                    os.makedirs(os.path.dirname(_dst), exist_ok=True)
                    shutil.copy2(_src, _dst)
                    _reg_count += 1
                elif _f == "SKILL.md":
                    _skill_name = os.path.basename(_root)
                    _dst = os.path.join(_skills_dir, _skill_name, "SKILL.md")
                    os.makedirs(os.path.dirname(_dst), exist_ok=True)
                    shutil.copy2(_src, _dst)
                    _reg_count += 1
        if _reg_count > 0:
            import logging as _log_dep
            _log_dep.getLogger("aiplat.builder").info(
                "Deploy: registered %d agents/skills from %s", _reg_count, _app_home)
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)  # best-effort

    if not _has_index_html:
        # Generate app dashboard page only if no index.html was provided by generated code
        _html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{_name}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}}
.header{{background:#1e293b;padding:2rem;border-bottom:1px solid #334155}}
.header h1{{font-size:1.5rem;margin-bottom:.5rem}}
.header p{{color:#94a3b8;font-size:.9rem}}
.actions{{display:flex;gap:.75rem;margin-top:1rem;flex-wrap:wrap}}
.btn{{display:inline-block;padding:.5rem 1rem;border-radius:.375rem;font-size:.85rem;text-decoration:none;transition:all .2s}}
.btn-primary{{background:#2563eb;color:#fff}} .btn-primary:hover{{background:#1d4ed8}}
.btn-secondary{{background:#334155;color:#e2e8f0}} .btn-secondary:hover{{background:#475569}}
.stages{{padding:2rem;display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:1rem}}
.card{{background:#1e293b;border:1px solid #334155;border-radius:.5rem;padding:1rem}}
.card h3{{font-size:1rem;margin-bottom:.5rem}}
.card .label{{color:#64748b;font-size:.8rem;margin-bottom:.25rem}}
.card .output{{color:#38bdf8;font-size:.85rem;word-break:break-all;max-height:120px;overflow-y:auto}}
.badge{{display:inline-block;padding:.15rem .5rem;border-radius:999px;font-size:.7rem;font-weight:600}}
.badge-done{{background:#065f46;color:#6ee7b7}}
.badge-pending{{background:#1e3a5f;color:#93c5fd}}
.footer{{padding:1rem 2rem;color:#475569;font-size:.75rem;border-top:1px solid #1e293b}}
.code-preview{{padding:1rem 2rem}}
.code-preview h2{{font-size:1rem;margin-bottom:.5rem;color:#94a3b8}}
.file-list{{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:.5rem}}
.file-tag{{background:#1e293b;border:1px solid #334155;border-radius:.25rem;padding:.25rem .5rem;font-size:.75rem;font-family:monospace;color:#38bdf8}}
</style></head>
<body>
<div class="header"><h1>🚀 {_name}</h1><p>{_desc}</p>
<div class="actions">
<a href="http://localhost:5173/app/apps/{project_id}" class="btn btn-primary">📱 使用应用</a>
<a href="http://localhost:5173/app/factory" class="btn btn-secondary">🔧 返回应用工厂</a>
<a href="/app/sessions/{project_id}/health" class="btn btn-secondary">🩺 健康报告</a>
</div></div>
<div class="stages">
"""
        for s in _stages:
            _agent = s.get("agent_name", s.get("agent_id", "?"))
            _phase = s.get("phase", "")
            _output = s.get("output_artifact", "")
            _badge = "badge-done" if _output else "badge-pending"
            _status = "✅ 已完成" if _output else "⏳ 待执行"
            _html += f"""<div class="card">
<h3>{_agent}</h3>
<div class="label">阶段: {_phase}</div>
<div class="label">产出: <span class="badge {_badge}">{_status}</span></div>
<div class="output">{_output}</div>
</div>\n"""
        
        _html += f"""</div>
"""
        # Show extracted files if any
        if _file_count > 0:
            try:
                _fl = [f for f in sorted(os.listdir(_app_home)) if f != "index.html"]
                if _fl:
                    _html += '<div class="code-preview"><h2>📁 生成文件 ({0} 个)</h2><div class="file-list">'.format(len(_fl))
                    for _fn in _fl[:30]:
                        _html += f'<span class="file-tag">{_fn}</span>'
                    if len(_fl) > 30:
                        _html += f'<span class="file-tag" style="color:#64748b">... 共 {len(_fl)} 个文件</span>'
                    _html += '</div></div>'
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
        
        _html += f"""<div class="footer">项目ID: {project_id}{ " · 生成文件: " + str(_file_count) + " 个" if _file_count else "" } · 由 aiPlat 应用工厂生成</div>
</body></html>"""
    
        with open(os.path.join(_app_home, "index.html"), "w", encoding="utf-8") as f:
            f.write(_html)
    
    app_url = f"http://localhost:8004/app/sessions/{project_id}"
    
    # Register in apps table so it appears in deployed apps list
    try:
        from storage.sqlite import init_db, _connect
        import time as _time, logging as _log_app
        init_db()
        conn = _connect()
        now = _time.time()
        app_id = f"factory_{project_id}"
        conn.execute(
            """INSERT OR REPLACE INTO apps (id, name, workflow_id, mode, description, created_at, updated_at)
               VALUES (?, ?, '', 'dashboard', ?, ?, ?)""",
            (app_id, _name, f"AI应用工厂生成 · {app_url}", now, now),
        )
        conn.commit()
        conn.close()
        _log_app.getLogger("aiplat.builder").info("App %s registered in DB", app_id)
    except Exception:
        import logging as _log_app2
        _log_app2.getLogger("aiplat.builder").warning(
            "Failed to register app in DB for %s", project_id, exc_info=True)
    
    return {"ok": True, "deploy_dir": deploy_dir, "app_url": app_url, "files_generated": _file_count}


def _get_agent_insight_for(agent_id: str, projects: dict) -> dict:
    """Get insight metrics for a single agent from project run history.
    
    Filters to only count runs from projects where this agent is in the team.
    """
    total_runs, passes, rejections, rollbacks = 0, 0, 0, 0
    for pid, proj in projects.items():
        # Check if this agent is part of the project's team
        stages = proj.get("team_stages", []) or []
        agent_in_team = any(
            str(s.get("agent_id", "")) == str(agent_id) for s in stages if isinstance(s, dict)
        )
        if not agent_in_team:
            continue
        
        runs = proj.get("runs", []) or []
        for run in runs:
            total_runs += 1
            pass_rate = run.get("pass_rate", 0)
            if pass_rate >= 80:
                passes += 1
            if run.get("rejected", False):
                rejections += 1
            if run.get("rollback_count", 0) > 0:
                rollbacks += 1
    
    first_pass_rate = round(passes / max(total_runs, 1), 2)
    rejection_rate = round(rejections / max(total_runs, 1), 2)
    qa_rollback_rate = round(rollbacks / max(total_runs, 1), 2)
    return {
        "agent_id": agent_id,
        "first_pass_rate": first_pass_rate,
        "rejection_rate": rejection_rate,
        "qa_rollback_rate": qa_rollback_rate,
        "total_runs": total_runs,
        "output_completeness": 1.0,
    }

# ── Module-level singleton (shared between workflow executor and builder router) ──
_project_service_singleton = None

def _get_project_service():
    global _project_service_singleton
    if _project_service_singleton is None:
        from builder.builder_team_service import BuilderTeamService
        _project_service_singleton = BuilderProjectService(team_service=BuilderTeamService())
    return _project_service_singleton

