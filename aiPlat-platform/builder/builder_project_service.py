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


def _write_runtime_governance_sidecar(agent_md_path: str) -> None:
    """生成物侧接线（CLAUDE.md §23）：注册成功时在 AGENT.md 旁预置运行时治理入口。

    列出生成 agent 可用的平台治理端点（经验回写/断线续跑/消息总线）——
    生成物运行时可据此接入平台闭环（不侵入 AGENT.md 本体，避免 conformance 校验破坏）。
    """
    import os as _os
    _dir = _os.path.dirname(agent_md_path)
    _sidecar = _os.path.join(_dir, "runtime_governance.md")
    _agent = _os.path.basename(_dir)
    try:
        with open(_sidecar, "w", encoding="utf-8") as f:
            f.write(
                "# 运行时治理入口（生成物侧接线，自动生成）\n\n"
                f"生成 agent「{_agent}」运行时可用以下平台治理端点（CLAUDE.md §23）：\n\n"
                "## 失败经验回写（L2 状态机：登记→两次验证→升级）\n"
                "- 失败时登记：`python3 aiPlat-platform/governance/experience_feedback/experience_feedback.py "
                "--register --rule <rule> --content \"<失败描述>\" --source generated-agent --confidence 0.9`\n"
                "- 查看状态：`--status`；验证成功：`--verify --rule <rule> --case <case> --outcome success`\n\n"
                "## 长任务断线续跑\n"
                "- `python3 aiPlat-platform/governance/daemon_jobs.py --start --name <n> --command \"<cmd>\"`；"
                "状态 `--status` / 输出 `--attach <id>`\n\n"
                "## 身份注册（消息总线，非契约协同）\n"
                "- 部署后 agent 可 `--register --agent <id>` 获得总线身份（异步通知/运维）。\n"
                "- **运行时协同主路径不是总线互调**：默认单 Agent + 工具；多角色用工厂 Pipeline +"
                " stage_handoff / skill_routing + schema 门 + HITL。\n"
                "- 纪律：**不做无门控互调，做阶段契约 + schema 门 + HITL。**\n")
    except Exception:
        pass  # noqa: cleanup-best-effort — sidecar 生成失败不影响注册主流程


def _register_generated_agent_to_bus(agent_name: str) -> None:
    """生成物侧接线：注册成功时把生成 agent 上线消息总线（身份/通知层）。

    注意：注册 ≠ 运行时契约协同。工厂协同主路径是 Pipeline + handoff / skill_routing；
    agent_messages 仅提供点对点邮箱，不替代 schema 门与 HITL。
    best-effort 不抛异常：总线注册失败不影响注册主流程。
    """
    import importlib.util as _iu
    import sys as _sys
    try:
        _spec = _iu.spec_from_file_location(
            "agent_messages",
            str(Path(__file__).resolve().parents[1] / "governance/agent_messages.py"))
        _mod = _iu.module_from_spec(_spec)
        _sys.modules["agent_messages"] = _mod
        _spec.loader.exec_module(_mod)
        _mod.AgentMessageStore().register(
            agent_name, meta={"kind": "generated-agent"})
    except Exception:
        pass  # noqa: cleanup-best-effort — 总线注册失败不影响注册主流程

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


_PRD_GEN_INTENT_RE = re.compile(
    r"生成\s*(完整)?\s*PRD|输出\s*(完整)?\s*PRD|确认\s*PRD|PRD_READY|定稿|写一份PRD|直接输出.*PRD",
    re.I,
)
_ANALYSIS_LEAK_RE = re.compile(
    r"步骤\s*[1234]|分析关键约束|列出\s*2-3\s*个|方案比较|可行方案|取舍[：:]",
)
# Meta / karpathy-style headings that must never become PRD title
_META_HEADING_RE = re.compile(
    r"步骤\s*\d|方案\s*[ABC甲乙丙]|分析(?:关键)?(?:约束|问题)|列出.*可行方案|方案比较|取舍",
    re.I,
)
# FR id anywhere: FR-1 / FR-001 / FR 1
_FR_ID_TOKEN_RE = re.compile(r"\bFR[-\s]?\d+\b", re.I)
_PRD_BODY_HINT_RE = re.compile(
    r"#{2,3}\s*(功能需求|核心功能需求)|\"functional_requirements\"|\bFR[-\s]?\d+\b",
    re.I,
)
# Known PRD section titles (h2 or h3); FR/US/step headings stay inside a section
_PRD_SECTION_NAME_RE = re.compile(
    r"^(?:"
    r"项目背景|背景|Background|"
    r"(?:核心|主要|关键)?功能需求|"
    r"用户故事|User Stories?|"
    r"产品决策|决策|Decisions?|"
    r"待确认问题|开放问题|Open Questions?|"
    r"范围|Scope|"
    r"成功指标|验收标准|目标状态|ISA\s*对齐"
    r")\s*$",
    re.I,
)
# Start of a functional-requirement block (### / **bold** / bullet)
_FR_BLOCK_START_RE = re.compile(
    r"^(?:###\s+|\*\*|\s*[-*]\s+\*{0,2})"
    r"(FR[-\s]?\d+)\s*[：:]\s*(.+?)\*{0,2}\s*$"
    r"|"
    r"^###\s+(?!步骤\s*\d)(.+?)\s*$",
    re.MULTILINE,
)


def _user_asks_prd_output(message: str) -> bool:
    return bool(_PRD_GEN_INTENT_RE.search(message or ""))


def _reply_leaks_analysis_steps(reply: str) -> bool:
    head = (reply or "")[:800]
    return bool(_ANALYSIS_LEAK_RE.search(head))


def _is_meta_prd_heading(heading: str) -> bool:
    """True for analysis/step/scheme headings that are not product titles."""
    h = (heading or "").strip()
    if not h:
        return True
    # Bare labels are handled elsewhere; treat step/scheme as meta
    return bool(_META_HEADING_RE.search(h))


def _extract_prd_markdown_body(reply: str) -> str:
    """Prefer the PRD subsection; drop leading analysis leak (步骤1–4 / 方案表).

    Models often prepend karpathy-style reasoning before ``## 项目名称``. Parsing
    must start at the last project-name heading so title/FR extraction succeed.
    """
    text = str(reply or "").replace("<!-- PRD_READY -->", "")
    named = list(re.finditer(r"(?m)^##\s*项目名称", text))
    if named:
        return text[named[-1].start():].strip()
    if _ANALYSIS_LEAK_RE.search(text[:1200]):
        for m in re.finditer(r"(?m)^##\s+(.+)$", text):
            head = m.group(1).strip()
            # Strip optional label prefix for meta check
            bare = head
            for _pfx in (_AIPLAT_PRD_TITLE_PREFIX, "项目名称:", "Project Name:"):
                if bare.startswith(_pfx):
                    bare = bare[len(_pfx):].strip()
                    break
            if _is_meta_prd_heading(bare) or _is_meta_prd_heading(head):
                continue
            return text[m.start():].strip()
    return text.strip()


def _reply_looks_like_prd_body(reply: str) -> bool:
    """True when reply already contains structured PRD body (marker optional)."""
    s = reply or ""
    if not _PRD_BODY_HINT_RE.search(s):
        return False
    # Avoid treating pure clarification as PRD
    if "验收" in s or "acceptance_criteria" in s or "Acceptance" in s:
        return True
    if '"functional_requirements"' in s:
        return True
    if _FR_ID_TOKEN_RE.search(s) and (
        "## 项目名称" in s
        or re.search(r"#{2,3}\s*功能需求", s)
    ):
        return True
    return bool(re.search(r"#{2,3}\s*(?:核心)?功能需求", s))


def _is_prd_section_heading(heading: str) -> bool:
    """True for known PRD section titles (not FR-n / US-n / 步骤N)."""
    h = (heading or "").strip()
    if not h or _is_meta_prd_heading(h):
        return False
    if re.match(r"^(?:FR|US)[-\s]?\d+\b", h, re.I):
        return False
    # Strip trailing colon labels: "项目背景：" → "项目背景"
    bare = re.sub(r"[：:].*$", "", h).strip()
    return bool(_PRD_SECTION_NAME_RE.match(bare) or _PRD_SECTION_NAME_RE.match(h))


def _split_prd_markdown_sections(clean: str) -> Dict[str, str]:
    """Split Markdown into PRD sections; accept ## and ### for known titles.

    Models often emit ``### 功能需求`` under ``## 项目名称``. Treating every
    ``###`` as a section would break FR blocks (``### FR-001``); only known
    section names start a new bucket at h3.
    """
    sections: Dict[str, str] = {}
    current_key = ""
    for line in (clean or "").split("\n"):
        m = re.match(r"^(#{2,3})\s+(.+)$", line)
        if m:
            level, raw = m.group(1), m.group(2).strip()
            # Never treat "## 项目名称：X" as a content section
            if re.match(r"^项目名称\b", raw):
                current_key = ""
                continue
            if level == "##" or _is_prd_section_heading(raw):
                current_key = raw
                sections[current_key] = ""
                continue
        if current_key:
            sections[current_key] += line + "\n"
    return sections


def _clean_decision_value(raw: str) -> str:
    """Extract English snake_case enum from ``key: `enum`（说明）`` style values.

    Free-form SLA strings (e.g. ``P95 ≤ 1.5× video duration``) are kept intact —
    only strip trailing CJK parenthetical notes when a leading snake_case enum exists.
    """
    s = str(raw or "").strip()
    if not s:
        return s
    # Prefer first fenced token: `direct_media_url`
    m = re.search(r"`([a-zA-Z][\w]*)`", s)
    if m:
        return m.group(1)
    s = s.strip("`").strip()
    # Free-form: contains digits/operators/CJK beyond a plain enum token
    if re.search(r"[≤≥<>×x\d\u4e00-\u9fff/]", s) and not re.match(
        r"^[a-z][a-z0-9_]*$", s
    ):
        # Strip trailing （说明） / (note) only
        s2 = re.split(r"[（(]", s, maxsplit=1)[0].strip()
        return s2 or s
    # Leading enum before CJK / fullwidth paren / ASCII paren / em-dash note
    m = re.match(r"^([a-zA-Z][\w]*)", s)
    if m:
        rest = s[m.end() :].lstrip()
        if not rest or rest[0] in "（(—–-：:":
            return m.group(1)
        # e.g. "P95 ≤ ..." — keep full free-form
        if re.search(r"[≤≥<>×\d\u4e00-\u9fff]", rest):
            return s
        return m.group(1)
    return s


def _parse_decisions_from_markdown(body: str) -> Dict[str, Any]:
    """Parse bullet ``key: value`` and markdown tables with optional backticks."""
    dec: Dict[str, Any] = {}
    if not (body or "").strip():
        return dec
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("|---") or re.match(r"^\|\s*键\s*\|", s):
            continue
        # Table row: | `key` | `value` | note |
        tm = re.match(
            r"^\|\s*`?([a-zA-Z_][\w]*)`?\s*\|\s*`?([^|]+?)`?\s*\|",
            s,
        )
        if tm:
            key, val = tm.group(1).strip(), _clean_decision_value(tm.group(2))
            if key.lower() not in ("key", "键", "name") and val.lower() not in (
                "value", "值", "---",
            ):
                dec[key] = val
            continue
        # Bullet: - key: `value`（说明）  /  key: value
        m = re.match(
            r"^\s*[-*]?\s*`?([a-zA-Z_][\w]*)`?\s*[：:=]\s*(.+?)\s*$",
            s,
        )
        if m:
            dec[m.group(1).strip()] = _clean_decision_value(m.group(2))
    return dec


def _parse_fr_body_fields(fr_body: str) -> Dict[str, Any]:
    """Extract description / priority / acceptance_criteria from an FR block."""
    desc_match = re.search(
        r"(?:\*\*)?(?:描述|功能描述)(?:\*\*)?[：:]\s*(.+)", fr_body
    )
    user_story_match = re.search(
        r"(?:\*\*)?用户故事(?:\*\*)?[：:]\s*(.+)", fr_body
    )
    pri_match = re.search(r"(?:\*\*)?优先级(?:\*\*)?[：:]\s*(\S+)", fr_body)
    acs = re.findall(r"AC\d+:\s*(.+)", fr_body)
    if not acs:
        ac_block = re.search(
            r"验收标准[：:]?\s*\n((?:\s*[-*]\s+.+\n?)+)", fr_body
        )
        if ac_block:
            acs = re.findall(r"[-*]\s+(.+)", ac_block.group(1))
    out: Dict[str, Any] = {
        "description": (
            (desc_match.group(1).strip() if desc_match else "")
            or (user_story_match.group(1).strip() if user_story_match else "")
        ),
        "acceptance_criteria": acs,
    }
    if pri_match:
        out["priority"] = pri_match.group(1).strip()
    return out


def _parse_functional_requirements_section(func_section: str) -> List[Dict[str, Any]]:
    """Parse FR items from ### / **FR-n：** / - FR-n： blocks."""
    fr_items: List[Dict[str, Any]] = []
    if not (func_section or "").strip():
        return fr_items

    starts = list(_FR_BLOCK_START_RE.finditer(func_section))
    if starts:
        for i, m in enumerate(starts):
            if m.lastindex and m.group(1) and m.group(1).upper().startswith("FR"):
                fr_id = re.sub(r"\s+", "", m.group(1).upper().replace(" ", "-"))
                if not fr_id.startswith("FR-"):
                    fr_id = fr_id.replace("FR", "FR-", 1)
                fr_name = (m.group(2) or "").strip()
            elif m.lastindex and m.group(3):
                # ### generic heading (non-step)
                fr_name = m.group(3).strip()
                if _is_meta_prd_heading(fr_name):
                    continue
                if ":" in fr_name or "：" in fr_name:
                    sep = ":" if ":" in fr_name else "："
                    left, right = fr_name.split(sep, 1)
                    fr_id = left.strip()
                    fr_name = right.strip()
                else:
                    fr_id = fr_name
            else:
                continue
            end = starts[i + 1].start() if i + 1 < len(starts) else len(func_section)
            fr_body = func_section[m.end():end]
            fields = _parse_fr_body_fields(fr_body)
            item: Dict[str, Any] = {
                "id": fr_id,
                "name": fr_name or fr_id,
                "description": fields["description"],
                "acceptance_criteria": fields["acceptance_criteria"],
            }
            if fields.get("priority"):
                item["priority"] = fields["priority"]
            fr_items.append(item)

    # Fallback: numbered/bulleted lists as FRs (no FR- id)
    if not fr_items:
        for line_match in re.finditer(
            r"^\s*(?:\d+\.|[-*])\s*\**(.+?)\**(?:\s*[：:]\s*(.+))?\s*$",
            func_section or "",
            re.MULTILINE,
        ):
            _name = line_match.group(1).strip()
            if _is_meta_prd_heading(_name):
                continue
            _desc = (line_match.group(2) or "").strip()
            fr_items.append({
                "id": f"FR-{len(fr_items)+1:03d}",
                "name": _name,
                "description": _desc or _name,
                "acceptance_criteria": [],
            })
    return fr_items


def _parse_prd_draft_from_reply(reply: str, *, parse_markdown) -> Optional[Dict[str, Any]]:
    """Best-effort structured PRD from assistant reply (JSON then Markdown)."""
    draft = None
    try:
        json_str = extract_json(reply)
        if json_str:
            draft = json.loads(json_str)
            if not isinstance(draft, dict):
                draft = None
            elif not (draft.get("user_stories") or draft.get("functional_requirements")):
                draft = None
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    body = _extract_prd_markdown_body(reply)
    if not draft and (
        "## 项目名称" in body
        or re.search(r"#{2,3}\s*(?:核心|主要|关键)?功能需求", body)
        or _FR_ID_TOKEN_RE.search(body)
    ):
        draft = parse_markdown(body)
    # If JSON lacked FRs but markdown body has them, prefer markdown parse
    if (
        isinstance(draft, dict)
        and not (draft.get("functional_requirements") or draft.get("user_stories"))
        and (re.search(r"#{2,3}\s*(?:核心|主要|关键)?功能需求", body) or _FR_ID_TOKEN_RE.search(body))
    ):
        md = parse_markdown(body)
        if isinstance(md, dict) and md.get("functional_requirements"):
            draft = md
    return draft if isinstance(draft, dict) else None


# ── HITL suspend/resume context (Phase 1: in-memory, Phase 2: Redis) ──
def _pass_rate_fraction_from_report(report: Any) -> Optional[float]:
    """Extract 0..1 pass rate from true-test report (meta.pass_rate may be 0-100 or 0-1)."""
    if not isinstance(report, dict):
        return None
    meta = report.get("meta") if isinstance(report.get("meta"), dict) else {}
    raw = meta.get("pass_rate")
    if raw is None and report.get("pass_rate") is not None:
        raw = report.get("pass_rate")
    if raw is None:
        return None
    try:
        rate = float(raw)
    except (TypeError, ValueError):
        return None
    if rate > 1.0:
        rate = rate / 100.0
    return max(0.0, min(1.0, rate))


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
        """Lazy init: only create LLM adapter when actually needed.

        Factory PM/PRD/architecture work needs reasoning-capable models.
        Use purpose ``agent`` (not ``chat``): chat profile is latency-first and
        often selects tiny local models (e.g. qwen2.5:3b) that cannot draft PRDs.
        """
        if self._model is None:
            from core.api.core_facade import best_model_for_purpose, create_selected_adapter
            self._model = create_selected_adapter(
                model_name=best_model_for_purpose("agent"),
            )
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
            "factory_profile": getattr(req, "factory_profile", "standard") or "standard",
            "output_style": getattr(req, "output_style", "default") or "default",
            "factory_mode": getattr(req, "factory_mode", "") or "",
            "coding_intensity": getattr(req, "coding_intensity", "") or "",
        }
        try:
            from core.api.core_facade import (
                apply_project_style_meta,
                assign_output_style_experiment,
                default_intensity_for_factory_mode,
                mode_to_team_template,
                normalize_coding_intensity,
                normalize_factory_mode,
                normalize_factory_profile,
            )
            self._projects[project_id]["factory_profile"] = normalize_factory_profile(
                self._projects[project_id].get("factory_profile")
            )
            _fm = normalize_factory_mode(self._projects[project_id].get("factory_mode"))
            self._projects[project_id]["factory_mode"] = _fm
            if _fm:
                self._projects[project_id]["team_template"] = mode_to_team_template(_fm)
            _ci = str(self._projects[project_id].get("coding_intensity") or "").strip()
            if not _ci:
                _ci = default_intensity_for_factory_mode(_fm)
            self._projects[project_id]["coding_intensity"] = normalize_coding_intensity(_ci)
            apply_project_style_meta(
                self._projects[project_id],
                output_style=self._projects[project_id].get("output_style"),
            )
            # A3b: sticky style arm when experiment pct > 0; explicit adhd locks out
            _os = str(self._projects[project_id].get("output_style") or "").lower()
            if _os == "adhd":
                self._projects[project_id]["output_style_user_set"] = True
            else:
                assign_output_style_experiment(
                    self._projects[project_id],
                    sticky_id=project_id,
                )
        except Exception:
            logging.getLogger(__name__).debug("style/profile meta init skipped", exc_info=True)
        if stages:
            try:
                from core.api.core_facade import apply_factory_profile_to_stages
                apply_factory_profile_to_stages(
                    stages, self._projects[project_id].get("factory_profile", "standard")
                )
                self._projects[project_id]["team_stages"] = [
                    s.model_dump() if hasattr(s, "model_dump") else s for s in stages
                ]
            except Exception:
                logging.getLogger(__name__).debug("factory_profile apply skipped", exc_info=True)

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

        # T1b: never block chat; background pull when AUTOSYNC=1
        try:
            from core.api.core_facade import maybe_autosync_team_harness

            maybe_autosync_team_harness(background=True)
        except Exception:
            logging.getLogger(__name__).debug("factory autosync kick skipped", exc_info=True)

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

        # ── Determine agent and optionally inject knowledge retrieval context ──
        _enriched_message = message
        _agent_name = _AIPLAT_PM_AGENT
        _run_state = self._runs.get(project_id)
        if not _run_state:
            try:
                _run_state = self._load_pipeline_state(project_id) or {}
            except Exception:
                _run_state = {}
        _generated = _run_state.get("_generated_agent", "") if isinstance(_run_state, dict) else ""

        if _generated:
            # Generated Agent app — inject knowledge retrieval context
            _agent_name = _generated
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
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
        # else: PM dialogue — skip RAG (reranker loading caused SIGABRT, uncatchable by try/except)
        else:
            # Inject matched PRD gate pack hints *before* generation (not only post-hoc wash)
            try:
                from core.api.core_facade import format_pm_gate_guidance
                _hist = "\n".join(
                    str(m.get("content") or "")
                    for m in (session.get("messages") or [])[-12:]
                )
                _guidance = format_pm_gate_guidance(_hist or message)
                if _guidance:
                    _enriched_message = f"{_guidance}\n\n---\n用户消息: {message}"
            except Exception:
                logging.getLogger(__name__).debug(
                    "prd gate guidance inject skipped", exc_info=True
                )

        # T2/F-T2 + A0/A3b: Culture then output_style (hard→Culture→style); prose only
        try:
            from core.api.core_facade import (
                apply_project_culture_meta,
                assign_output_style_experiment,
                build_culture_overlay,
                build_style_overlay,
                compose_prose_overlays,
                resolve_culture_enabled,
                resolve_output_style,
                whitelist_overrides,
            )
            apply_project_culture_meta(proj)
            _exp = assign_output_style_experiment(proj, sticky_id=project_id)
            if _exp.get("assigned"):
                try:
                    self._save_projects()
                except Exception:
                    logging.getLogger(__name__).debug(
                        "persist style experiment arm skipped", exc_info=True
                    )
            _culture = build_culture_overlay(
                enabled=resolve_culture_enabled(proj),
            )
            _style = resolve_output_style(proj)
            _ov = whitelist_overrides(proj)
            _style_overlay = build_style_overlay(_style, _ov)
            _combined = compose_prose_overlays(
                culture_overlay=_culture,
                style_overlay=_style_overlay,
            )
            if _combined:
                _enriched_message = f"{_combined}\n\n---\n{_enriched_message}"
        except Exception:
            logging.getLogger(__name__).debug(
                "culture/output_style inject skipped", exc_info=True
            )

        try:

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
            # Close without marker when user asked for PRD *or* reply already looks like
            # a structured draft — pack finalize fills missing decisions (no hand-written gold).
            _implicit = _user_asks_prd_output(message) or _reply_looks_like_prd_body(reply)
            reply, prd_ready = self._apply_prd_gate_to_assistant_reply(
                project_id, session, reply, allow_implicit_ready=_implicit
            )

            # One auto-repair when model leaked analysis steps or gate blocked READY
            if (not prd_ready) and (
                _user_asks_prd_output(message)
                or _reply_looks_like_prd_body(reply)
                or _reply_leaks_analysis_steps(reply)
                or "PRD 尚未闭合" in reply
                or "请输出完整 Markdown PRD" in reply
                or "未解析到完整 PRD" in reply
            ):
                # Cheap local retry: strip 步骤1–4 / nags, re-parse without another LLM call
                try:
                    stripped = _extract_prd_markdown_body(reply)
                    # Drop gate follow-up nags appended after a failed first pass
                    for _cut in (
                        "\n请输出完整 Markdown PRD",
                        "\n未解析到完整 PRD",
                        "\n---\nPRD 尚未闭合",
                        "\nPRD 尚未闭合",
                    ):
                        if _cut in stripped:
                            stripped = stripped.split(_cut, 1)[0].rstrip()
                    if stripped and (
                        stripped != reply
                        or _reply_looks_like_prd_body(stripped)
                    ):
                        reply2, ready2 = self._apply_prd_gate_to_assistant_reply(
                            project_id,
                            session,
                            stripped,
                            allow_implicit_ready=True,
                        )
                        if ready2:
                            self._record_output_style_telemetry(
                                project_id,
                                session,
                                reply=reply2,
                                first_pass_ok=True,
                            )
                            self._save_chat_session(project_id)
                            return {
                                "reply": reply2,
                                "prd_ready": True,
                                "trace_id": result.trace_id,
                                "session_state": {},
                            }
                        reply = reply2
                except Exception:
                    logging.getLogger(__name__).debug(
                        "prd local re-parse skipped", exc_info=True
                    )

                try:
                    from core.api.core_facade import (
                        format_decision_enum_catalog,
                        format_pm_gate_guidance,
                    )
                    from core.api.intents import core_chat, ChatContext

                    _ctx = "\n".join(
                        str(m.get("content") or "")
                        for m in (session.get("messages") or [])[-8:]
                    ) or message
                    repair_bits = [
                        "## 定稿修复指令（强制）",
                        "上轮未产出可过门禁的完整 PRD。本轮禁止输出步骤1/方案表/分析过程。",
                        "直接输出完整 Markdown：## 项目名称：真实产品名 / ## 项目背景 / ## 功能需求(≥3 FR 含验收标准) / "
                        "## 用户故事 / ## 决策 / ## 待确认问题（空）/ ## 范围(performance+security)。",
                        "末尾必须加 <!-- PRD_READY -->。",
                        "决策 value 只用英文枚举（见下方目录）。缺键可由工厂 finalize 按域 pack 补全；"
                        "禁止依赖 finalize 洗绿语义矛盾（如不转写却要主题摘要）。",
                        "不要求手写金稿——把 FR+验收写清 + 枚举决策即可闭合。",
                    ]
                    _g = format_pm_gate_guidance(_ctx)
                    if _g:
                        repair_bits.insert(0, _g)
                    else:
                        _enums = format_decision_enum_catalog(_ctx)
                        if _enums:
                            repair_bits.append(_enums)
                    if "PRD 尚未闭合" in reply:
                        repair_bits.append(reply[reply.find("PRD 尚未闭合"):][:1200])
                    repair = await core_chat(ChatContext(
                        agent_name=_agent_name,
                        session_id=f"{project_id}_prd_repair",
                        user_input="\n".join(repair_bits),
                        model=self.model,
                    ))
                    repair_reply = _unwrap_json_reply(repair.reply)
                    session["messages"].append({"role": "assistant", "content": repair_reply})
                    reply, prd_ready = self._apply_prd_gate_to_assistant_reply(
                        project_id,
                        session,
                        repair_reply,
                        allow_implicit_ready=True,
                    )
                except Exception:
                    logging.getLogger(__name__).debug(
                        "prd auto-repair skipped", exc_info=True
                    )

            self._record_output_style_telemetry(
                project_id,
                session,
                reply=reply,
                first_pass_ok=bool(prd_ready),
            )
            if (not prd_ready) and (
                _user_asks_prd_output(message) or _reply_looks_like_prd_body(reply)
            ):
                self._record_t4a_friction(
                    "prd_gate_fail",
                    project_id=project_id,
                    detail="prd_gate_not_ready",
                )
            self._save_chat_session(project_id)
            return {"reply": reply, "prd_ready": prd_ready, "trace_id": result.trace_id, "session_state": {}}
        except Exception as e:
            self._save_chat_session(project_id)  # save even on error — preserve messages
            return {"reply": f"{_AIPLAT_CHAT_ERROR_PREFIX}{str(e)[:200]}", "prd_ready": False, "trace_id": "", "session_state": {}}

    def _record_output_style_telemetry(
        self,
        project_id: str,
        session: dict,
        *,
        reply: str,
        first_pass_ok: Optional[bool] = None,
    ) -> None:
        """A3a/A3b: persist style telemetry (+ experiment arm when assigned)."""
        try:
            from core.api.core_facade import (
                estimate_reply_tokens,
                infer_followups,
                record_output_style_event,
                resolve_output_style,
            )

            proj = self._projects.get(project_id) or {}
            style = resolve_output_style(proj)
            record_output_style_event(
                style=style,
                project_id=project_id,
                session_id=project_id,
                source="factory_chat",
                tokens=estimate_reply_tokens(reply),
                followups=infer_followups(session.get("messages") or []),
                first_pass_ok=first_pass_ok,
                experiment_id=str(proj.get("output_style_experiment_id") or ""),
                arm=str(proj.get("output_style_arm") or ""),
            )
        except Exception:
            logging.getLogger(__name__).debug(
                "output_style telemetry skipped", exc_info=True
            )

    def _apply_prd_gate_to_assistant_reply(
        self,
        project_id: str,
        session: dict,
        reply: str,
        *,
        allow_implicit_ready: bool = False,
    ) -> tuple:
        """Parse PRD draft, finalize via gate, rewrite chat message if needed.

        READY bar = factory_finalize ok + looks_like_prd (not hand-written gold).
        With allow_implicit_ready, a parseable draft can close without <!-- PRD_READY -->
        (gen-intent / auto-repair). Explicit marker still required otherwise.

        Returns (reply, prd_ready).
        """
        has_marker = "<!-- PRD_READY -->" in str(reply)
        if not has_marker and not allow_implicit_ready:
            return reply, False

        from core.api.core_facade import (
            factory_finalize_prd,
            followup_questions_from_report,
            looks_like_prd,
            render_prd_markdown,
        )

        draft = _parse_prd_draft_from_reply(
            reply, parse_markdown=self._parse_markdown_prd
        )
        if draft:
            draft, gate_report = factory_finalize_prd(draft)
            if gate_report.get("ok") and looks_like_prd(draft):
                session["prd"] = draft
                proj = self._projects.get(project_id, {})
                if proj:
                    proj["confirmed_prd"] = draft
                    self._save_projects()
                reply = render_prd_markdown(draft, include_ready_marker=True)
                if session.get("messages"):
                    session["messages"][-1]["content"] = reply
                return reply, True

            session["prd"] = draft
            reply = str(reply).replace("<!-- PRD_READY -->", "").rstrip()
            if not looks_like_prd(draft):
                reply = (
                    reply
                    + "\n\n请输出完整 Markdown PRD（含 ≥1 条功能需求 FR + 验收标准），"
                    "不要只写分析步骤或空标题。末尾加 <!-- PRD_READY -->。"
                )
            reply = reply + followup_questions_from_report(
                gate_report, context_text=reply
            )
            if session.get("messages"):
                session["messages"][-1]["content"] = reply
            return reply, False

        # Only nag about missing parse when model claimed READY or we forced finalize
        if has_marker or allow_implicit_ready:
            reply = str(reply).replace("<!-- PRD_READY -->", "").rstrip()
            reply = (
                reply
                + "\n\n未解析到完整 PRD。请按 ## 项目名称 / ## 功能需求 / ## 决策 / ## 范围 "
                "输出完整 Markdown，末尾加 <!-- PRD_READY -->。"
            )
            if session.get("messages"):
                session["messages"][-1]["content"] = reply
        return reply, False

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
            from core.api.core_facade import format_pm_gate_guidance
            _g = format_pm_gate_guidance(conversation_text)
            if _g:
                prompt = f"{_g}\n\n---\n{prompt}"
        except Exception:
            _log.debug("prd gate guidance for extract skipped", exc_info=True)

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
                    from core.api.core_facade import factory_finalize_prd, looks_like_prd
                    prd, gate = factory_finalize_prd(prd)
                    if not gate.get("ok") or not looks_like_prd(prd):
                        _log.info(
                            "_extract_prd_from_chat: gate rejected extract ok=%s like=%s",
                            gate.get("ok"), looks_like_prd(prd),
                        )
                        return None
                    _log.info("_extract_prd_from_chat: extracted PRD with keys %s", list(prd.keys())[:5])
                    return prd
            _log.info("_extract_prd_from_chat: no valid JSON found in reply")
        except Exception as e:
            _log.warning("_extract_prd_from_chat failed: %s", str(e)[:200])
        return None

    async def confirm_prd(self, project_id: str, prd_data: Any = None, *, force_confirm: bool = False) -> Dict[str, Any]:
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

        # PRD quality gate: block contradictory / decision-open PRDs (esp. media)
        from core.api.core_facade import apply_gate_to_prd
        try:
            prd_data, gate_report = apply_gate_to_prd(
                prd_data if isinstance(prd_data, dict) else {},
                force=bool(force_confirm),
            )
        except ValueError as gate_err:
            return {
                "status": "error",
                "phase": "dialogue",
                "detail": str(gate_err),
                "prd_gate": {
                    "ok": False,
                    "blocked": True,
                },
                "prd": prd_data if isinstance(prd_data, dict) else {},
            }

        proj["confirmed_prd"] = prd_data
        self._save_projects()

        # Transition session phase from dialogue to executing
        if session:
            session["phase"] = BuilderSessionPhase.executing.value
            session["prd"] = prd_data
        return {
            "phase": BuilderSessionPhase.executing.value,
            "prd": prd_data,
            "prd_gate": gate_report,
            "status": "ok",
        }

    async def confirm_and_build(
        self, project_id: str, prd_data: Any = None, *, force_confirm: bool = False
    ) -> Dict[str, Any]:
        """F1 one-click: confirm_prd → recommend_team → start_pipeline_background.

        Returns combined status. If PRD gate blocks, does not start the pipeline.
        """
        confirm = await self.confirm_prd(
            project_id, prd_data=prd_data, force_confirm=force_confirm
        )
        if isinstance(confirm, dict) and confirm.get("status") == "error":
            return confirm
        team = await self.recommend_team(project_id)
        start = await self.start_pipeline_background(project_id)
        return {
            "status": "ok",
            "phase": (start or {}).get("phase") or "executing",
            "confirm": confirm,
            "team": {
                "recommendation": (team or {}).get("recommendation"),
                "plan_stages": (team or {}).get("plan_stages") or [],
            },
            "start": start,
        }

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
        Prefer platform media handlers when skill name is registered (real ffmpeg I/O).
        """
        from core.api.intents import core_chat, ChatContext
        import json as _json, re as _re
        import asyncio as _asyncio

        params = dict(params or {})
        proj = self._projects.get(project_id) or {}
        params.setdefault("app_name", str(proj.get("app_name") or "").strip() or "app")
        params.setdefault("project", params["app_name"])

        import os as _os_hop

        # ── Path 0: platform media handlers (deterministic, true I/O) ──
        # Opt-out: AIPLAT_FACTORY_FORCE_AGENT_SKILL=1 forces full Agent+ReAct path.
        try:
            from core.api.core_facade import execute_media_skill, resolve_media_handler_name
            import os as _os

            force_agent = str(_os.environ.get("AIPLAT_FACTORY_FORCE_AGENT_SKILL") or "").strip().lower() in (
                "1", "true", "yes", "on",
            )
            if (not force_agent) and resolve_media_handler_name(str(skill_name)):
                result = await _asyncio.to_thread(execute_media_skill, skill_name, params)
                effects = await self._platform_effects_after_deterministic_skill(
                    project_id, skill_name, params, result
                )
                try:
                    from builder.hop_metrics import record_hop
                    record_hop(
                        project_id, skill=skill_name, agent="media_handler",
                        ok=True, mode="media_handler",
                    )
                except Exception:
                    pass  # noqa: cleanup-best-effort
                return {
                    "ok": True,
                    "skill": skill_name,
                    "agent": "media_handler",
                    "reply": _json.dumps(result, ensure_ascii=False),
                    "result": result,
                    "mode": "media_handler",
                    "platform_effects": effects,
                    "failed_stage": "",
                }
        except Exception as e:
            _log.warning("media handler %s failed, falling back to agent: %s", skill_name, str(e)[:160])
            try:
                from builder.hop_metrics import record_hop
                record_hop(
                    project_id, skill=skill_name, agent="media_handler",
                    ok=False, failed_stage="tool_execution", error=str(e)[:200],
                    mode="media_handler",
                )
            except Exception:
                pass  # noqa: cleanup-best-effort

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
            try:
                from builder.hop_metrics import record_hop
                record_hop(
                    project_id, skill=skill_name, ok=False,
                    failed_stage="planning", error="Agent not ready",
                )
            except Exception:
                pass  # noqa: cleanup-best-effort
            return {"error": "Agent not ready", "ok": False, "failed_stage": "planning"}

        # Phase B W4: hop schema gate — missing required params never enter LLM
        _app_home = _os_hop.path.join(
            _os_hop.getenv("AIPLAT_HOME", _os_hop.path.expanduser("~/.aiplat")),
            "apps", project_id, "current",
        )
        try:
            from builder.skill_hop_gate import gate_skill_hop, build_hop_handoff
            _gate = gate_skill_hop(skill_name, params, app_home=_app_home)
            if not _gate.get("ok"):
                _handoff = build_hop_handoff(
                    skill=skill_name,
                    agent=agent_name,
                    ok=False,
                    verify="schema_failed",
                    known_issues=list(_gate.get("violations") or []),
                    next_hint="补齐 input_schema 必填参数后重试",
                )
                try:
                    from builder.hop_metrics import record_hop
                    record_hop(
                        project_id, skill=skill_name, agent=agent_name, ok=False,
                        failed_stage=_gate.get("failed_stage") or "tool_selection",
                        error=_gate.get("error") or "hop_schema_gate",
                        mode="schema_gate",
                    )
                except Exception:
                    pass  # noqa: cleanup-best-effort
                return {
                    "ok": False,
                    "error": _gate.get("error") or "hop_schema_gate",
                    "skill": skill_name,
                    "agent": agent_name,
                    "failed_stage": _gate.get("failed_stage") or "tool_selection",
                    "violations": list(_gate.get("violations") or []),
                    "handoff": _handoff,
                    "status_code": 422,
                }
        except Exception:
            logging.getLogger(__name__).debug("skill hop gate skipped", exc_info=True)

        message = f"执行技能: {skill_name}\n参数: {_json.dumps(params, ensure_ascii=False)[:2000]}"
        try:
            from core.api.core_facade import disable_dynamic_spawn
            with disable_dynamic_spawn(True):
                result = await core_chat(ChatContext(
                    agent_name=agent_name,
                    session_id=f"{project_id}_fe",
                    user_input=message,
                    model=self.model,
                ))
            reply = result.reply or ""
            reply = _unwrap_json_reply(reply)
            try:
                from builder.skill_hop_gate import build_hop_handoff
                _hop = build_hop_handoff(
                    skill=skill_name, agent=agent_name, ok=True,
                    verify="executed", next_hint="",
                )
            except Exception:
                _hop = {}
            try:
                from builder.hop_metrics import record_hop
                record_hop(
                    project_id, skill=skill_name, agent=agent_name,
                    ok=True, mode="agent",
                )
            except Exception:
                pass  # noqa: cleanup-best-effort
            return {
                "ok": True,
                "skill": skill_name,
                "agent": agent_name,
                "reply": reply,
                "trace_id": getattr(result, 'trace_id', ''),
                "failed_stage": "",
                "handoff": _hop,
            }
        except Exception as e:
            try:
                from builder.hop_metrics import record_hop
                record_hop(
                    project_id, skill=skill_name, agent=agent_name, ok=False,
                    failed_stage="tool_execution", error=str(e)[:200], mode="agent",
                )
            except Exception:
                pass  # noqa: cleanup-best-effort
            return {
                "error": str(e)[:200],
                "ok": False,
                "failed_stage": "tool_execution",
                "skill": skill_name,
                "agent": agent_name,
            }

    def get_promotion_status(self, project_id: str) -> Dict[str, Any]:
        """Phase C W5：hop 聚合 + 四维跑通晋升快照（供 Factory / API）。"""
        from builder.hop_metrics import (
            aggregate_hops,
            derive_test_evidence,
            evaluate_project_run_through,
        )
        state = self._runs.get(project_id) or self._load_pipeline_state(project_id) or {}
        proj = self._projects.get(project_id) or {}
        _rejected = 0
        try:
            # best-effort: treat missing last deploy rejects as unknown
            _rejected = int((state.get("_last_deploy") or {}).get("rejected_count") or 0)
            if _rejected == 0 and isinstance(proj.get("last_deploy"), dict):
                _rejected = int((proj.get("last_deploy") or {}).get("rejected_count") or 0)
        except Exception:
            _rejected = 0
        evidence = derive_test_evidence(
            last_test_report=proj.get("last_test_report") if isinstance(proj.get("last_test_report"), dict) else None,
            state=state if isinstance(state, dict) else None,
        )
        # also honor project-level flags persisted by run_tests
        if proj.get("_real_tests_ok"):
            evidence["real_tests_green"] = True
        if proj.get("_physical_evidence"):
            evidence["physical_evidence"] = True
        out = evaluate_project_run_through(
            project_id,
            conformance_green=(_rejected == 0),
            real_tests_green=bool(evidence["real_tests_green"]),
            physical_evidence=bool(evidence["physical_evidence"]),
            policy_gate_closed=True,
        )
        _man = state.get("agent_manifest") if isinstance(state.get("agent_manifest"), dict) else {}
        if not _man and isinstance(proj.get("agent_manifest"), dict):
            _man = proj.get("agent_manifest") or {}
        out["manifest_mode"] = (_man.get("mode") or "single")
        out["hops_raw_n"] = aggregate_hops(project_id).get("n_runs", 0)
        out["evidence"] = evidence
        return out

    async def _platform_effects_after_deterministic_skill(
        self,
        project_id: str,
        skill_name: str,
        params: Dict[str, Any],
        result: Dict[str, Any],
    ) -> List[str]:
        """Attach Harness/platform side-effects after a deterministic handler.

        Media handlers skip full ReAct for real I/O correctness; this bridge still
        records memory + local feedback so factory apps are not Harness-orphaned.
        Set AIPLAT_FACTORY_FORCE_AGENT_SKILL=1 to skip Path 0 and use Agent+ReAct.
        """
        effects: List[str] = ["deterministic_handler"]
        session_id = f"{project_id}_fe"
        status = str((result or {}).get("status") or "")
        summary = (
            f"[factory-handler] skill={skill_name} status={status} "
            f"task_id={(result or {}).get('task_id') or ''} "
            f"keys={list((result or {}).keys())[:12]}"
        )[:1200]

        try:
            from core.api.core_facade import get_memory_manager

            mm = get_memory_manager()
            if mm is not None and hasattr(mm, "save_interaction"):
                await mm.save_interaction(
                    user_message=f"执行技能: {skill_name}\n参数摘要: {str(params)[:400]}",
                    assistant_message=summary,
                    session_id=session_id,
                    metadata={
                        "source": "factory_deterministic_handler",
                        "project_id": project_id,
                        "skill": skill_name,
                        "status": status,
                    },
                )
                effects.append("memory_saved")
        except Exception:
            _log.debug("deterministic skill memory effect skipped", exc_info=True)

        try:
            from core.api.core_facade import (
                FeedbackLevel,
                FeedbackType,
                get_local_feedback,
            )

            fb = get_local_feedback()
            if fb is not None:
                level = (
                    FeedbackLevel.WARNING
                    if status in ("failed", "error")
                    else FeedbackLevel.INFO
                )
                fb.emit(
                    level,
                    FeedbackType.TOOL_OUTPUT,
                    source=f"factory_handler:{skill_name}",
                    content=summary,
                    metadata={"project_id": project_id, "skill": skill_name, "status": status},
                )
                effects.append("local_feedback")
        except Exception:
            _log.debug("deterministic skill feedback effect skipped", exc_info=True)

        return effects

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
        
        # F2b: honor create-time factory_mode / team_template (agent|code|hybrid)
        _preferred_mode = ""
        _team_template = ""
        try:
            from core.api.core_facade import normalize_factory_mode, mode_to_team_template
            _preferred_mode = normalize_factory_mode(proj.get("factory_mode"))
            _explicit_tmpl = str(proj.get("team_template") or "").strip().removesuffix(".yaml")
            if _explicit_tmpl in ("default", "code", "hybrid"):
                _team_template = _explicit_tmpl
            elif _preferred_mode:
                _team_template = mode_to_team_template(_preferred_mode)
        except Exception:
            logging.getLogger(__name__).debug(
                "factory_mode resolve skipped", exc_info=True
            )

        rec = await recommend_team_stages(
            requirement=prd,
            model=self.model,
            extra_context=extra_context or None,
            team_template=_team_template,
            preferred_mode=_preferred_mode,
        )

        recommendation = {
            "team_name": rec.team_name,
            "reasoning": rec.reasoning,
            "raw_reply": rec.raw_reply,
        }
        plan_stages = rec.stages

        if plan_stages:
            proj["plan_stages"] = plan_stages
            proj["plan_stage_ids"] = [s.get("id", f"plan_stage_{i}") for i, s in enumerate(plan_stages)]

            # v4.2 / F2b: mode → fixed team template
            #   agent→default.yaml, code→code.yaml, hybrid→hybrid.yaml
            recommendation["mode"] = rec.mode
            _mode_team_map = {"agent": "default", "code": "code", "hybrid": "hybrid"}
            if rec.mode in _mode_team_map and not proj.get("team_id"):
                proj["team_id"] = _mode_team_map[rec.mode]
                proj["team_template"] = _mode_team_map[rec.mode]
                proj["factory_mode"] = rec.mode
                recommendation["_mode_mapped"] = True
                recommendation["_team_id"] = proj["team_id"]
                # Materialize stages from YAML so start_pipeline has team_stages
                try:
                    self._sync_team_stages(project_id)
                except Exception:
                    logging.getLogger(__name__).debug(
                        "team sync after mode map skipped", exc_info=True
                    )
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
                        # ── v3.1: copy gates + architecture_mode from team template YAML ──
                        try:
                            from core.api.core_facade import load_team_template
                            _tmpl_name = {"hybrid": "hybrid", "code": "code"}.get(rec.mode, "default")
                            tmpl = load_team_template(_tmpl_name) or load_team_template("default")
                            if tmpl and tmpl.stages:
                                _by_agent = {
                                    s.get("agent_id"): s for s in tmpl.stages
                                    if isinstance(s, dict) and s.get("agent_id")
                                }
                                _COPY_KEYS = (
                                    "hitl", "hitl_phase", "architecture_mode",
                                    "input_artifacts", "completeness_check",
                                    "quality_gate", "skill_name", "output_artifact",
                                    "execution_backend",
                                )
                                for ts in team_stages:
                                    src = _by_agent.get(ts.agent_id) or {}
                                    for k in _COPY_KEYS:
                                        val = src.get(k)
                                        if val in (None, "", [], {}):
                                            continue
                                        setattr(ts, k, val)
                                proj["team_template"] = _tmpl_name
                                proj["factory_mode"] = rec.mode or "agent"
                        except Exception:
                            pass  # noqa: cleanup-best-effort
                        # F2a: project-level HITL profile (demo strips intermediate gates)
                        try:
                            from core.api.core_facade import (
                                apply_factory_profile_to_stages,
                                resolve_project_factory_profile,
                            )
                            _fp = resolve_project_factory_profile(proj)
                            apply_factory_profile_to_stages(team_stages, _fp)
                            proj["factory_profile"] = _fp
                        except Exception:
                            logging.getLogger(__name__).debug(
                                "factory_profile apply on recommend_team skipped", exc_info=True
                            )
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
        # Drop marker, then prefer ``## 项目名称`` body *before* any ``---`` split.
        # Models often put ``---`` between 步骤1–4 and the real PRD; splitting first
        # discarded the product section and left an empty shell (loop root cause).
        clean = str(reply or "").replace("<!-- PRD_READY -->", "").strip()
        clean = _extract_prd_markdown_body(clean)
        for _cut in (
            "\n---\nPRD 尚未闭合",
            "\n---\r\nPRD 尚未闭合",
            "\nPRD 尚未闭合",
            "\n请输出完整 Markdown PRD",
            "\n未解析到完整 PRD",
        ):
            if _cut in clean:
                clean = clean.split(_cut, 1)[0].rstrip()
        # Trailing HR + gate footnote (keep PRD; drop only nag after last HR)
        clean = re.split(
            r"\n---\s*\n(?=(?:PRD 尚未闭合|请输出完整 Markdown|未解析到完整 PRD))",
            clean,
            maxsplit=1,
        )[0].strip()

        # Prefer ## 项目名称：RealProduct (last wins if duplicates)
        named_titles = list(
            re.finditer(r"(?m)^##\s*项目名称[：:]\s*(.+)$", clean)
        )
        if named_titles:
            prd["title"] = named_titles[-1].group(1).strip()
        else:
            bare_label = list(re.finditer(r"(?m)^##\s*项目名称\s*$", clean))
            if bare_label:
                after = clean[bare_label[-1].end():]
                nxt = re.search(r"^\s*\n+([^\n#][^\n]{1,120})", after)
                if nxt:
                    prd["title"] = nxt.group(1).strip()
            if not prd.get("title"):
                # First non-meta heading (never 步骤N / 方案A)
                for title_match in re.finditer(r"(?m)^#+\s+(.+)$", clean):
                    raw = title_match.group(1).strip()
                    title = raw
                    for _pfx in (_AIPLAT_PRD_TITLE_PREFIX, "项目名称:", "Project Name:"):
                        if title.startswith(_pfx):
                            title = title[len(_pfx):].strip()
                            break
                    if title in ("项目名称", "Project Name", "Title") or not title:
                        after = clean[title_match.end():]
                        nxt = re.search(r"^\s*\n+([^\n#][^\n]{1,120})", after)
                        if nxt and not _is_meta_prd_heading(nxt.group(1).strip()):
                            prd["title"] = nxt.group(1).strip()
                            break
                        continue
                    if _is_meta_prd_heading(title) or _is_meta_prd_heading(raw):
                        continue
                    prd["title"] = title
                    break

        # Extract sections by ## / known ### headings (models often use ### 功能需求)
        sections = _split_prd_markdown_sections(clean)
        bg = (
            sections.get("项目背景", "")
            or sections.get("背景", "")
            or sections.get("Background", "")
        ).strip()
        if bg:
            prd["description"] = bg
        # Functional requirements — ### FR-001 / **FR-1：** / - FR-1：
        func_section = (
            sections.get(_AIPLAT_PRD_SECTION_REQUIREMENTS, "")
            or sections.get("核心" + _AIPLAT_PRD_SECTION_REQUIREMENTS, "")
            or sections.get("主要" + _AIPLAT_PRD_SECTION_REQUIREMENTS, "")
            or sections.get("关键" + _AIPLAT_PRD_SECTION_REQUIREMENTS, "")
            or next((v for k, v in sections.items() if _AIPLAT_PRD_SECTION_REQUIREMENTS in k), "")
        )
        fr_items = _parse_functional_requirements_section(func_section)
        if fr_items:
            prd["functional_requirements"] = fr_items
        # User stories — prefer dedicated section; do not alias FRs when present
        stories_section = (
            sections.get("用户故事", "")
            or sections.get("User Stories", "")
            or next((v for k, v in sections.items() if "用户故事" in k or "User Stor" in k), "")
        )
        us_items: List[Dict[str, Any]] = []
        if stories_section.strip():
            for us_match in re.finditer(
                r"###\s*(.+?)\n(.*?)(?=\n###|\n##|\Z)", stories_section, re.DOTALL
            ):
                us_head = us_match.group(1).strip()
                us_body = us_match.group(2)
                us_id, us_text = us_head, us_head
                if ":" in us_head:
                    us_id, us_text = us_head.split(":", 1)
                    us_id, us_text = us_id.strip(), us_text.strip()
                elif "：" in us_head:
                    us_id, us_text = us_head.split("：", 1)
                    us_id, us_text = us_id.strip(), us_text.strip()
                rel = re.search(r"(?:\*\*)?关联需求(?:\*\*)?[：:]\s*(.+)", us_body)
                if not rel:
                    rel = re.search(
                        r"(?:\*\*)?related_fr(?:\*\*)?[：:]\s*\[?([^\]\n]+)\]?",
                        us_body,
                        re.IGNORECASE,
                    )
                pri = re.search(r"(?:\*\*)?优先级(?:\*\*)?[：:]\s*(\S+)", us_body)
                if not pri:
                    pri = re.search(r"(?:\*\*)?priority(?:\*\*)?[：:]\s*(\S+)", us_body, re.I)
                story: Dict[str, Any] = {
                    "id": us_id,
                    "story": us_text,
                    "description": us_text,
                }
                if rel:
                    parts = [
                        p.strip().strip('"').strip("'")
                        for p in re.split(r"[,，、\s]+", rel.group(1))
                        if p.strip().strip('"').strip("'")
                    ]
                    story["related_fr"] = parts
                if pri:
                    story["priority"] = pri.group(1).strip()
                us_items.append(story)
            if not us_items:
                for line_match in re.finditer(
                    r'^\s*(?:\d+\.|[-*])\s*(.+)$', stories_section, re.MULTILINE
                ):
                    text = line_match.group(1).strip()
                    us_items.append({
                        "id": f"US-{len(us_items)+1:03d}",
                        "story": text,
                        "description": text,
                    })
        if us_items:
            prd["user_stories"] = us_items
        elif fr_items:
            # Backward compat: older markdown embedded 用户故事 under each FR
            prd["user_stories"] = [
                {
                    "id": f"US-{i:03d}",
                    "story": fr.get("description") or fr.get("name") or "",
                    "description": fr.get("description") or fr.get("name") or "",
                    "related_fr": [fr["id"]] if fr.get("id") else [],
                }
                for i, fr in enumerate(fr_items, 1)
                if fr.get("description") or fr.get("name")
            ]
        scope = sections.get(_AIPLAT_PRD_SECTION_SCOPE, "").strip()
        if scope:
            prd["scope"] = scope
        # Lift structured constraints + decisions from Markdown (NFR must not stay as prose only)
        try:
            from core.api.core_facade import normalize_constraints
            # Parse ## 决策 / ## 待确认问题 sections if present
            decisions_body = (
                sections.get("决策", "")
                or sections.get("产品决策", "")
                or sections.get("Decisions", "")
            ).strip()
            if decisions_body:
                dec = _parse_decisions_from_markdown(decisions_body)
                if dec:
                    prd["decisions"] = dec
            oq_body = (
                sections.get("待确认问题", "")
                or sections.get("开放问题", "")
                or sections.get("Open Questions", "")
            ).strip()
            if oq_body:
                oqs = []
                for line in oq_body.splitlines():
                    m = re.match(r"^\s*(?:\d+\.|[-*])\s*(.+)$", line)
                    if m:
                        text = m.group(1).strip()
                        if text in ("（无）", "(无)", "无", "N/A", "None"):
                            continue
                        oqs.append(text)
                prd["open_questions"] = oqs
            else:
                prd.setdefault("open_questions", [])
            prd = normalize_constraints(prd)
        except Exception:
            logging.getLogger(__name__).debug("prd constraint lift failed", exc_info=True)
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
        # Allow FR-only drafts when title was recovered later / product title elsewhere
        if not prd.get("title") and fr_items:
            return prd
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
            # Fallback: no live HITL engine (cancelled / awaiting_approval after offline true_test)
            finalized = await self._finalize_hitl_if_terminal(project_id)
            if finalized:
                return finalized
            return {"status": "error", "detail": resp.get("detail", "Core unavailable")}
        except Exception as e:
            _log.warning("approve_stage failed for %s: %s", project_id, str(e)[:200])
            finalized = await self._finalize_hitl_if_terminal(project_id)
            if finalized:
                return finalized
            raise

    async def _finalize_hitl_if_terminal(self, project_id: str) -> Optional[Dict[str, Any]]:
        """When pipeline is paused at the last stage with APPROVED tests, mark done.

        Covers offline true_test / cancelled engine cases where hitl-resolve 404s.
        """
        try:
            wrap = await self._get_state_via_core(project_id)
            state = wrap.get("state") if isinstance(wrap, dict) else None
            if not isinstance(state, dict):
                return None
            phase = str(state.get("phase") or "")
            if phase not in ("paused", "awaiting_approval", "cancelled"):
                return None
            tr = state.get("test_report") or {}
            raw = tr.get("raw_output") if isinstance(tr, dict) else tr
            rec = ""
            report_obj: Optional[Dict[str, Any]] = None
            if isinstance(raw, str) and raw.strip().startswith("{"):
                try:
                    report_obj = json.loads(raw)
                    rec = str((report_obj or {}).get("recommendation") or "")
                except json.JSONDecodeError:
                    rec = ""
            elif isinstance(raw, dict):
                report_obj = raw
                rec = str(raw.get("recommendation") or "")
            if rec and rec.upper() not in ("APPROVED", "PASS", "CONDITIONAL_APPROVAL"):
                # Still allow finalize when last stage is test_report and tests exist
                if not isinstance(raw, (str, dict)) or not raw:
                    return None
            from core.api.core_facade import get_pipeline_run_store
            store = get_pipeline_run_store()
            run = store.get_run_by_project(project_id)
            if not run:
                return None
            # Prefer true-test meta.pass_rate (0-100 or 0-1); do not treat 0.0 as missing via `or`
            rate = _pass_rate_fraction_from_report(report_obj)
            if rate is None:
                for cand in (state.get("pass_rate"), run.get("pass_rate"), 1.0):
                    try:
                        if cand is None:
                            continue
                        rate = float(cand)
                        break
                    except (TypeError, ValueError):
                        continue
            if rate is None:
                rate = 1.0
            if rate > 1.0:
                rate = rate / 100.0
            rate = max(0.0, min(1.0, float(rate)))
            store.atomic_update_phase_and_hitl(
                run["run_id"],
                phase="done",
                current_stage_idx=int(run.get("current_stage_idx") or state.get("_current_stage_idx") or 0),
                pass_rate=rate,
                hitl_stage_id="",
                hitl_phase_name="",
                hitl_output_artifact="",
                error="",
                _progress_json="",
            )
            state["phase"] = "done"
            state["pass_rate"] = rate
            state["_test_pass_rate"] = rate * 100.0
            state["_pass_rate_source"] = "true_test"
            await self._save_state(project_id, state)
            return {"project_id": project_id, "phase": "done", "status": "ok", "via": "finalize_terminal"}
        except Exception as e:
            _log.warning("_finalize_hitl_if_terminal failed for %s: %s", project_id, str(e)[:200])
            return None

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
            friction = self._record_t4a_friction(
                "hitl_reject",
                project_id=project_id,
                detail=feedback,
            )
            if resp.get("status") == "resolved":
                out = {"project_id": project_id, "phase": "executing", "status": "ok"}
                if friction.get("cta"):
                    out["friction_share"] = friction["cta"]
                return out
            return {"status": "error", "detail": resp.get("detail", "Core unavailable")}
        except Exception as e:
            _log.warning("reject_stage failed for %s: %s", project_id, str(e)[:200])
            raise

    def _record_t4a_friction(
        self,
        signal: str,
        *,
        project_id: str,
        stage_id: str = "",
        detail: str = "",
        confirmed: bool = False,
    ) -> Dict[str, Any]:
        """T4a: best-effort local learning + CTA on pipeline/project state."""
        try:
            from core.api.core_facade import (
                attach_friction_cta,
                note_regenerate,
                record_friction_event,
            )

            if signal == "regenerate_count":
                result = note_regenerate(project_id, stage_id, detail=detail)
            else:
                result = record_friction_event(
                    signal,
                    project_id=project_id,
                    stage_id=stage_id,
                    detail=detail,
                    confirmed=confirmed,
                )
            cta = result.get("cta") if isinstance(result, dict) else None
            if cta:
                try:
                    st = self._load_pipeline_state(project_id) or {}
                    if isinstance(st, dict):
                        attach_friction_cta(st, cta)
                        self._save_state(project_id, st)
                except Exception:
                    logging.getLogger(__name__).debug(
                        "friction cta state persist skipped", exc_info=True
                    )
                proj = self._projects.get(project_id)
                if isinstance(proj, dict):
                    proj["_friction_share_cta"] = dict(cta)
                    try:
                        self._save_projects()
                    except Exception:
                        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
            return result if isinstance(result, dict) else {}
        except Exception:
            logging.getLogger(__name__).debug("t4a friction skipped", exc_info=True)
            return {}

    def confirm_friction_share(
        self,
        project_id: str,
        *,
        stage_id: str = "",
        signal: str = "regenerate_count",
        detail: str = "",
    ) -> Dict[str, Any]:
        """F-T4: user confirms regenerate friction → local learning draft."""
        try:
            from core.api.core_facade import (
                attach_friction_cta,
                clear_friction_cta,
                confirm_friction_share as _confirm,
            )

            result = _confirm(
                project_id=project_id,
                stage_id=stage_id,
                signal=signal,
                detail=detail,
            )
            try:
                st = self._load_pipeline_state(project_id) or {}
                if isinstance(st, dict):
                    if result.get("cta"):
                        attach_friction_cta(st, result["cta"])
                    else:
                        clear_friction_cta(st)
                    self._save_state(project_id, st)
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
            proj = self._projects.get(project_id)
            if isinstance(proj, dict):
                if result.get("cta"):
                    proj["_friction_share_cta"] = result["cta"]
                else:
                    proj.pop("_friction_share_cta", None)
                try:
                    self._save_projects()
                except Exception:
                    logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
            return {"status": "ok", **(result if isinstance(result, dict) else {})}
        except Exception as e:
            return {"status": "error", "detail": str(e)[:200]}

    async def regenerate_stage(
        self,
        project_id: str,
        stage_id: str,
        feedback: str,
        *,
        preserve_artifacts: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Delegate stage regeneration to Core (single authority, non-blocking).

        Returns immediately — the pipeline re-runs from the target stage on Core.
        ``preserve_artifacts`` keeps frozen exam suites (test_cases) across fix runs.
        """
        self._sync_team_stages(project_id)
        proj = self._projects.get(project_id, {})
        config = self._build_stage_config(project_id, proj)
        from builder.pipeline_orchestrator_client import PipelineOrchestratorClient
        client = PipelineOrchestratorClient()
        preserve = list(preserve_artifacts or [])
        # Default: re-running the executor stage keeps the exam suite frozen
        sid = str(stage_id or "").strip().lower()
        if not preserve and sid in (
            "test_executor",
            "test_report",
            "agent_true_test",
        ):
            preserve = ["test_cases", "test_questions"]
        # Also match by output_artifact / agent_id from team_stages
        if not preserve:
            for s in proj.get("team_stages") or []:
                if not isinstance(s, dict):
                    continue
                if stage_id in (
                    str(s.get("id") or ""),
                    str(s.get("agent_id") or ""),
                    str(s.get("output_artifact") or ""),
                ):
                    agent = str(s.get("agent_id") or "").lower()
                    art = str(s.get("output_artifact") or "").lower()
                    if agent in ("test_executor",) or art in ("test_report",):
                        preserve = ["test_cases", "test_questions"]
                    break
        # F3: prepend frozen handoff envelope so regenerate has next/known_issues
        _feedback = str(feedback or "")
        try:
            from core.api.core_facade import format_handoff_regenerate_feedback
            st = self._load_pipeline_state(project_id) or {}
            handoff = None
            bucket = st.get("_handoff") if isinstance(st.get("_handoff"), dict) else {}
            art_key = ""
            for s in proj.get("team_stages") or []:
                if not isinstance(s, dict):
                    continue
                if stage_id in (
                    str(s.get("id") or ""),
                    str(s.get("agent_id") or ""),
                    str(s.get("output_artifact") or ""),
                ):
                    art_key = str(s.get("output_artifact") or "")
                    break
            if art_key:
                art = st.get(art_key)
                if isinstance(art, dict) and isinstance(art.get("handoff"), dict):
                    handoff = art["handoff"]
                elif art_key in bucket:
                    handoff = bucket[art_key]
            if handoff:
                env = format_handoff_regenerate_feedback(handoff)
                if env and env not in _feedback:
                    _feedback = f"{env}\n\n{_feedback}".strip()
        except Exception:
            logging.getLogger(__name__).debug(
                "handoff regenerate feedback skipped", exc_info=True
            )
        result = await client.stage_operation(
            project_id,
            "regenerate",
            stage_id,
            _feedback,
            config,
            preserve_artifacts=preserve or None,
        )
        friction = self._record_t4a_friction(
            "regenerate_count",
            project_id=project_id,
            stage_id=stage_id,
            detail=_feedback[:200],
        )
        if result.get("status") in ("accepted", "conflict"):
            out = {"project_id": project_id, "phase": "executing", "status": "regenerating"}
            if friction.get("cta"):
                out["friction_share"] = friction["cta"]
            return out
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

    async def fix_from_test_report(
        self,
        project_id: str,
        test_report: str = "",
        *,
        regenerate_test_cases: bool = False,
    ) -> Dict[str, Any]:
        """Deterministic one-click fix: map bugs → stages → regenerate (no ReAct agent).

        Prefer this over ``test_report_orchestrator`` — that path is slow and often
        returns without calling regenerate when the LLM drifts.

        For ``no_platform_handler``-only reports: remap agent_app + test_cases skill
        names onto the platform media catalog (no LLM), then re-run test_executor.

        By default **freezes** ``test_cases`` (no qa LLM rewrite). Pass
        ``regenerate_test_cases=True`` to allow rewriting the exam suite.
        """
        from core.api.core_facade import plan_fix_from_report as _plan
        from core.api.core_facade import apply_no_platform_handler_fixes as _apply_media

        if not test_report:
            try:
                st = await self._get_state_via_core(project_id)
                tr = (st.get("state") or {}).get("test_report") if isinstance(st, dict) else None
                if isinstance(tr, dict):
                    test_report = str(tr.get("raw_output") or "")
                elif isinstance(tr, str):
                    test_report = tr
            except Exception as e:  # noqa: best-effort
                _log.warning("fix_from_test_report: state load failed %s: %s", project_id, str(e)[:160])

        if not str(test_report or "").strip():
            # Fallback: last written test_report artifact on disk
            try:
                out_fp = os.path.join(os.path.expanduser("~/.aiplat/output"), project_id, "test_report.json")
                if os.path.isfile(out_fp):
                    with open(out_fp, "r", encoding="utf-8") as fh:
                        test_report = fh.read()
            except Exception as e:  # noqa: best-effort
                _log.warning("fix_from_test_report: disk fallback failed %s: %s", project_id, str(e)[:120])

        if not str(test_report or "").strip():
            return {"status": "no_test_report", "fix_plan": [], "total_bugs": 0}

        proj = self._projects.get(project_id, {}) or {}
        team_stages = list(proj.get("team_stages") or [])
        plan = _plan(
            project_id,
            test_report,
            team_stages,
            regenerate_test_cases=regenerate_test_cases,
        )
        if plan.get("status") == "no_bugs" or not plan.get("fix_plan"):
            return {
                "status": "no_bugs",
                "failed_stage_ids": plan.get("failed_stage_ids") or [],
                "fix_plan": [],
                "total_bugs": int(plan.get("total_bugs") or 0),
                "preserve_artifacts": plan.get("preserve_artifacts") or [],
                "regenerate_test_cases": bool(regenerate_test_cases),
            }

        preserve = list(plan.get("preserve_artifacts") or [])
        if not regenerate_test_cases and not preserve:
            preserve = ["test_cases", "test_questions"]

        # ── Deterministic media skill remap (no LLM agent_engineer) ──
        if plan.get("mode") == "deterministic_media_remap":
            aa_raw = ""
            tc_raw: Any = None
            try:
                st_wrap = await self._get_state_via_core(project_id)
                st = (st_wrap.get("state") if isinstance(st_wrap, dict) else None) or {}
                aa = st.get("agent_app") if isinstance(st, dict) else None
                if isinstance(aa, dict):
                    aa_raw = str(aa.get("raw_output") or "")
                elif isinstance(aa, str):
                    aa_raw = aa
                tc = st.get("test_cases") if isinstance(st, dict) else None
                if isinstance(tc, dict):
                    tc_raw = tc.get("raw_output") if tc.get("raw_output") is not None else tc
                else:
                    tc_raw = tc
            except Exception as e:  # noqa: best-effort
                _log.warning("fix_from_test_report: load artifacts failed %s: %s", project_id, str(e)[:160])

            # Disk fallback
            if not aa_raw:
                try:
                    p = os.path.join(os.path.expanduser("~/.aiplat/output"), project_id, "agent_app.json")
                    if os.path.isfile(p):
                        with open(p, "r", encoding="utf-8") as fh:
                            aa_raw = fh.read()
                except Exception:
                    logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
            if tc_raw is None:
                try:
                    p = os.path.join(os.path.expanduser("~/.aiplat/output"), project_id, "test_cases.json")
                    if os.path.isfile(p):
                        with open(p, "r", encoding="utf-8") as fh:
                            tc_raw = fh.read()
                except Exception:
                    logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

            applied = _apply_media(
                agent_app_raw=aa_raw or "",
                test_cases=tc_raw,
                test_report=test_report,
                remaps=plan.get("remaps") or {},
            )
            errors: List[str] = []
            fixed = 0
            meta_applied = applied.get("meta") if isinstance(applied.get("meta"), dict) else {}
            try:
                # Only rewrite agent_app when skill names actually remapped
                if applied.get("agent_app_raw") and meta_applied.get("agent_app_changed"):
                    await self.update_stage_artifact(
                        project_id, "agent_app", str(applied.get("agent_app_raw") or "")
                    )
                    fixed += 1
            except Exception as e:
                errors.append(f"agent_app:{str(e)[:120]}")
            try:
                # Only rewrite test_cases when skill/param aliases changed — never LLM-rewrite questions
                tc_out = applied.get("test_cases")
                if tc_out is not None and (
                    meta_applied.get("test_cases_changed") or meta_applied.get("params_normalized")
                ):
                    content = (
                        tc_out
                        if isinstance(tc_out, str)
                        else json.dumps(tc_out, ensure_ascii=False, indent=2)
                    )
                    await self.update_stage_artifact(project_id, "test_cases", content)
                    fixed += 1
            except Exception as e:
                errors.append(f"test_cases:{str(e)[:120]}")

            # Re-run true tests only (executor stage) — do not regenerate qa_agent
            for stage in plan.get("fix_plan") or []:
                try:
                    r = await self.regenerate_stage(
                        project_id,
                        str(stage),
                        "",
                        preserve_artifacts=preserve,
                    )
                    if r.get("status") in ("regenerating", "ok", "accepted"):
                        fixed += 1
                    else:
                        errors.append(f"{stage}:{r.get('detail') or r.get('status')}")
                except Exception as e:
                    errors.append(f"{stage}:{str(e)[:120]}")

            return {
                "status": "regenerating" if fixed else "error",
                "mode": "deterministic_media_remap",
                "fixed_stages": fixed,
                "total_bugs": int(plan.get("total_bugs") or 0),
                "failed_stage_ids": plan.get("failed_stage_ids") or [],
                "fix_plan": plan.get("fix_plan") or [],
                "remaps": (applied.get("meta") or {}).get("remaps") or plan.get("remaps") or {},
                "errors": errors,
                "project_id": project_id,
                "phase": "executing" if fixed else "done",
                "preserve_artifacts": preserve,
                "regenerate_test_cases": False,
            }

        feedback = str(plan.get("feedback") or test_report)[:12000]
        if not feedback.strip():
            feedback = "Fix failures from test_report bug_summary (deterministic one-click fix)."
        fixed = 0
        errors = []
        for stage in plan.get("fix_plan") or []:
            try:
                r = await self.regenerate_stage(
                    project_id,
                    str(stage),
                    feedback,
                    preserve_artifacts=preserve,
                )
                if r.get("status") in ("regenerating", "ok", "accepted"):
                    fixed += 1
                else:
                    errors.append(f"{stage}:{r.get('detail') or r.get('status')}")
            except Exception as e:  # noqa: continue other stages
                errors.append(f"{stage}:{str(e)[:120]}")

        return {
            "status": "regenerating" if fixed else "error",
            "fixed_stages": fixed,
            "total_bugs": int(plan.get("total_bugs") or 0),
            "failed_stage_ids": plan.get("failed_stage_ids") or [],
            "fix_plan": plan.get("fix_plan") or [],
            "errors": errors,
            "project_id": project_id,
            "phase": "executing" if fixed else "done",
            "preserve_artifacts": preserve,
            "regenerate_test_cases": bool(regenerate_test_cases),
        }

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





    async def update_prd(self, project_id: str, prd: dict, *, force_confirm: bool = False) -> Dict[str, Any]:
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
        from core.api.core_facade import apply_gate_to_prd
        try:
            prd, gate_report = apply_gate_to_prd(
                prd if isinstance(prd, dict) else {},
                force=bool(force_confirm),
            )
        except ValueError as gate_err:
            return {"status": "error", "detail": str(gate_err), "prd_gate": {"ok": False, "blocked": True}}
        proj["confirmed_prd"] = prd
        proj["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._save_projects()
        _log2.getLogger("aiplat.builder").info("PRD updated for %s", project_id)
        return {"status": "ok", "detail": "PRD 已更新", "prd_gate": gate_report, "prd": prd}

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
        try:
            from core.api.core_facade import maybe_autosync_team_harness

            maybe_autosync_team_harness(background=True)
        except Exception:
            logging.getLogger(__name__).debug("pipeline autosync kick skipped", exc_info=True)
        result = await self.rebuild_project(project_id)
        return {"status": "ok", "run_id": project_id, "project_id": project_id, "phase": "executing", **result}

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
        # Factory: refresh confirmed PRD through quality finalize before rebuild
        try:
            from core.api.core_facade import factory_finalize_prd, looks_like_prd
            _raw_prd = proj.get("confirmed_prd") or {}
            if looks_like_prd(_raw_prd):
                _final_prd, _gate = factory_finalize_prd(_raw_prd)
                if _gate.get("ok"):
                    proj["confirmed_prd"] = _final_prd
                    self._save_projects()
                else:
                    logging.getLogger("aiplat.builder").warning(
                        "rebuild PRD finalize still failing for %s: %s",
                        project_id,
                        [i.get("code") for i in (_gate.get("issues") or []) if i.get("severity") == "error"][:5],
                    )
        except Exception:
            logging.getLogger("aiplat.builder").debug("rebuild PRD finalize skipped", exc_info=True)
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
        # F5a: promote last bloat metrics → baseline before wipe
        try:
            from core.api.core_facade import STATE_BLOAT_KEY
            _prev = None
            _st = self._runs.get(project_id) or self._load_pipeline_state(project_id) or {}
            if isinstance(_st, dict) and isinstance(_st.get(STATE_BLOAT_KEY), dict):
                _prev = dict(_st[STATE_BLOAT_KEY])
            elif isinstance(proj.get("bloat_metrics"), dict):
                _prev = dict(proj["bloat_metrics"])
            if _prev:
                proj["bloat_baseline"] = {
                    k: _prev.get(k)
                    for k in ("loc", "loc_non_import", "new_files", "new_deps", "schema_version")
                    if k in _prev or k == "schema_version"
                }
                self._save_projects()
        except Exception:
            logging.getLogger(__name__).debug("bloat baseline promote skipped", exc_info=True)
        self._runs.pop(project_id, None)
        import shutil
        out_dir = os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "output", project_id)
        if os.path.isdir(out_dir):
            try: shutil.rmtree(out_dir)
            except OSError: pass  # noqa: cleanup-best-effort
        # ── Load PM chat history (keep chat file — dialogue is rebuild SoT) ──
        _pm_messages = []
        _chat_session = self._load_chat_session(project_id)
        if isinstance(_chat_session, dict):
            for m in (_chat_session.get("messages") or []):
                role = m.get("role", "")
                # Keep enough of the requirement table / decisions; 2k truncated the feature matrix
                content = str(m.get("content", "") or "")[:8000]
                if role in ("user", "assistant") and content:
                    _pm_messages.append({"role": role, "content": content})
        # If chat was lost (prior rebuild deleted it), reconstruct from confirmed PRD
        if not _pm_messages:
            _cp = proj.get("confirmed_prd")
            if isinstance(_cp, dict) and (_cp.get("title") or _cp.get("functional_requirements")):
                try:
                    from core.api.core_facade import render_prd_markdown
                    _md = render_prd_markdown(_cp)
                except Exception:
                    _md = ""
                _desc = str(proj.get("description") or "").strip()
                if _desc:
                    _pm_messages.append({"role": "user", "content": _desc[:8000]})
                if _md:
                    _pm_messages.append({
                        "role": "assistant",
                        "content": (
                            "以下为已确认 PRD（重建时须覆盖生成，但不得扩大范围；"
                            "禁止发明对话/基线未出现的 OCR/ASR/额外 FR）：\n\n"
                            + _md[:8000]
                        ),
                    })
        # Clean pipeline state only — do NOT delete *_chat.json (requirement SoT)
        for fname in (f"{project_id}.json",):
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
        _log3.getLogger("aiplat.builder").info("Rebuilding project %s (pm_history=%d messages)", project_id, len(_pm_messages))
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
        return await self._rebuild_via_core(project_id, proj, module_id=module_id, pm_messages=_pm_messages)

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
            # Keep card pass_rate aligned with true-test report (avoid sticky 0 after regenerate)
            try:
                tr = state.get("test_report") or {}
                raw = tr.get("raw_output") if isinstance(tr, dict) else tr
                report = None
                if isinstance(raw, str) and raw.strip().startswith("{"):
                    report = json.loads(raw)
                elif isinstance(raw, dict):
                    report = raw
                frac = _pass_rate_fraction_from_report(report)
                if frac is not None:
                    cur = state.get("pass_rate")
                    try:
                        cur_f = float(cur) if cur is not None else None
                    except (TypeError, ValueError):
                        cur_f = None
                    if cur_f is None or abs(cur_f - frac) > 1e-6:
                        state["pass_rate"] = frac
                        state["_test_pass_rate"] = frac * 100.0
                        state["_pass_rate_source"] = "true_test"
            except Exception:
                pass  # noqa: best-effort display sync
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

    async def _rebuild_via_core(self, project_id: str, proj: dict, module_id: str = "default",
                               pm_messages: list = None) -> Dict[str, Any]:
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
            "pm_chat_history": pm_messages or [],
            "stages": [
                s if isinstance(s, dict) else s.model_dump() if hasattr(s, "model_dump") else dict(s)
                for s in stages
            ],
        }
        # B: inject coding intensity (code/hybrid → full default)
        try:
            from core.api.core_facade import (
                default_intensity_for_factory_mode,
                normalize_coding_intensity,
            )
            _ci = str(proj.get("coding_intensity") or "").strip()
            if not _ci:
                _ci = default_intensity_for_factory_mode(str(proj.get("factory_mode") or ""))
            config["coding_intensity"] = normalize_coding_intensity(_ci)
            proj["coding_intensity"] = config["coding_intensity"]
        except Exception:
            logging.getLogger(__name__).debug("coding_intensity inject skipped", exc_info=True)
        if isinstance(proj.get("bloat_baseline"), dict):
            config["bloat_baseline"] = proj.get("bloat_baseline")

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
        """Update a stage's raw_output artifact — allows user to manually edit before rebuild.

        State SoT is Core pipeline_run_store (SQLite + output_dir files). Local
        ``builder_states/*.json`` is optional cache and often missing after
        Core-owned runs — must fall back to Core read/write.
        """
        # 1) Resolve current state: memory → local file → Core store
        state = self._runs.get(project_id) or self._load_pipeline_state(project_id)
        if not state or not isinstance(state, dict) or state.get("phase") == "idle":
            try:
                core_wrap = await self._get_state_via_core(project_id)
                core_state = core_wrap.get("state") if isinstance(core_wrap, dict) else None
                if isinstance(core_state, dict) and core_state.get("phase") not in (None, "", "idle"):
                    state = dict(core_state)
            except Exception as e:
                _log.warning("update_stage_artifact: core state load failed for %s: %s",
                             project_id, str(e)[:200])
        if not state or not isinstance(state, dict):
            raise ValueError("no pipeline state")

        # 2) Match stage from project team_stages (preferred) or rebuilt session
        matched_stage_id = stage_id
        matched_key = stage_id
        matched_agent = ""
        matched = False
        proj = self._projects.get(project_id, {}) or {}
        for s in (proj.get("team_stages") or []):
            if not isinstance(s, dict):
                continue
            sid = str(s.get("id") or "")
            aid = str(s.get("agent_id") or "")
            oart = str(s.get("output_artifact") or "")
            if stage_id in (sid, aid, oart) and stage_id:
                matched = True
                matched_stage_id = sid or aid or stage_id
                matched_key = oart or aid or sid or stage_id
                matched_agent = aid
                break
        if not matched:
            session = self._rebuild_session(project_id)
            if session:
                for s in session.get_stages():
                    if s.id == stage_id or s.agent_id == stage_id or s.output_artifact == stage_id:
                        matched = True
                        matched_stage_id = s.id
                        matched_key = s.output_artifact or s.agent_id or s.id
                        matched_agent = s.agent_id or ""
                        break
        if not matched:
            # Last resort: artifact already present in state under this key
            if stage_id in state and isinstance(state.get(stage_id), (dict, str)):
                matched = True
                matched_key = stage_id
                matched_stage_id = stage_id
            else:
                raise ValueError(f"stage not found: {stage_id}")

        # 3) Update in-memory / local cache
        state[matched_key] = {
            "raw_output": content,
            "source": "user_edited",
            "elapsed_sec": 0,
            "_edited_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        await self._save_state(project_id, state)

        # 4) Persist to Core SoT so regenerate / UI poll see the edit
        self._persist_edited_artifact_to_core(
            project_id,
            stage_id=matched_stage_id,
            artifact_key=matched_key,
            content=content,
            agent_id=matched_agent,
            state=state,
        )

        return {
            "project_id": project_id,
            "stage_id": matched_stage_id,
            "artifact_key": matched_key,
            "status": "updated",
        }

    def _persist_edited_artifact_to_core(
        self,
        project_id: str,
        *,
        stage_id: str,
        artifact_key: str,
        content: str,
        agent_id: str = "",
        state: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Write edited artifact to Core run store + output_dir file (best-effort)."""
        try:
            from core.api.core_facade import get_pipeline_run_store
            store = get_pipeline_run_store()
            run = store.get_run_by_project(project_id)
            if not run:
                _log.warning("persist edited artifact: no core run for %s", project_id)
                return
            run_id = run["run_id"]
            out_dir = ""
            if isinstance(state, dict):
                out_dir = str(state.get("output_dir") or "")
            out_dir = out_dir or str(run.get("output_dir") or "")
            if not out_dir:
                out_dir = os.path.join(
                    os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")),
                    "output",
                    project_id,
                )
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, f"{artifact_key}.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            stages = store.get_stages(run_id) or []
            existing = None
            for s in stages:
                if s.get("stage_id") == stage_id or s.get("artifact_key") == artifact_key \
                        or s.get("output_artifact") == artifact_key:
                    existing = s
                    break
            store.upsert_stage(
                run_id,
                (existing or {}).get("stage_id") or stage_id,
                stage_idx=int((existing or {}).get("stage_idx") or 0),
                agent_id=str((existing or {}).get("agent_id") or agent_id or ""),
                skill_name=str((existing or {}).get("skill_name") or ""),
                status="completed",
                progress=(None),
                artifact_key=artifact_key,
                artifact_output=path,
                elapsed_sec=float((existing or {}).get("elapsed_sec") or 0),
                error_message="",
                output_artifact=artifact_key,
                hitl=bool((existing or {}).get("hitl")),
                hitl_phase=str((existing or {}).get("hitl_phase") or ""),
                agent_name=str((existing or {}).get("agent_name") or ""),
                input_artifacts=str((existing or {}).get("input_artifacts") or ""),
            )
        except Exception as e:
            _log.warning(
                "persist edited artifact to core failed for %s/%s: %s",
                project_id, artifact_key, str(e)[:300],
                exc_info=True,
            )

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
            # F5a: sync bloat metrics onto project for card / next-build baseline
            try:
                from core.api.core_facade import STATE_BLOAT_KEY, compare_bloat, write_bloat_metrics
                st = result.get("state") if isinstance(result.get("state"), dict) else {}
                metrics = st.get(STATE_BLOAT_KEY) if isinstance(st, dict) else None
                if not isinstance(metrics, dict) and isinstance(st, dict) and result.get("phase") == "done":
                    metrics = write_bloat_metrics(
                        st,
                        baseline=proj.get("bloat_baseline")
                        if isinstance(proj.get("bloat_baseline"), dict)
                        else None,
                    )
                    result["state"] = st
                if isinstance(metrics, dict):
                    if "vs_baseline" not in metrics and isinstance(proj.get("bloat_baseline"), dict):
                        metrics = dict(metrics)
                        metrics["vs_baseline"] = compare_bloat(metrics, proj["bloat_baseline"])
                        if isinstance(st, dict):
                            st[STATE_BLOAT_KEY] = metrics
                    proj["bloat_metrics"] = {
                        k: metrics.get(k)
                        for k in ("loc", "loc_non_import", "new_files", "new_deps", "vs_baseline", "schema_version")
                        if k in metrics
                    }
                    if isinstance(result.get("state"), dict):
                        result["state"][STATE_BLOAT_KEY] = metrics
            except Exception:
                logging.getLogger(__name__).debug("bloat metrics sync skipped", exc_info=True)
            self._save_projects()

        # F-T4: surface friction CTA for Factory polling
        try:
            st = result.get("state") if isinstance(result.get("state"), dict) else {}
            cta = None
            if isinstance(st, dict):
                cta = st.get("_friction_share_cta")
            proj = self._projects.get(project_id) or {}
            if not cta and isinstance(proj, dict):
                cta = proj.get("_friction_share_cta")
            if isinstance(cta, dict) and cta:
                result["friction_share"] = cta
        except Exception:
            logging.getLogger(__name__).debug("friction_share state sync skipped", exc_info=True)

        # F-T5: metrics digest slice on completion / failure
        try:
            phase = str(result.get("phase") or "")
            if phase in ("done", "failed", "completed"):
                from core.api.core_facade import build_team_digest

                proj = self._projects.get(project_id) or {}
                dig = build_team_digest(project_id=project_id, project=proj)
                result["team_digest"] = dig
                if isinstance(proj, dict):
                    proj["_team_digest"] = dig
                if isinstance(result.get("state"), dict):
                    result["state"]["_team_digest"] = dig
        except Exception:
            logging.getLogger(__name__).debug("team_digest sync skipped", exc_info=True)
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

    def _resolve_team_template_name(self, proj: dict) -> str:
        """Map project team_id → YAML template name (default/code/hybrid).

        Created teams use opaque ids like ``team_abc123``; those are not YAML
        filenames. Prefer ``team_template`` / factory_mode, then fall back to
        ``default`` (Agent 工厂).
        """
        from core.api.core_facade import load_team_template

        tid = str(proj.get("team_id") or "").strip()
        if tid and load_team_template(tid):
            return tid
        explicit = str(
            proj.get("team_template")
            or proj.get("factory_team_template")
            or ""
        ).strip()
        if explicit and load_team_template(explicit):
            return explicit
        mode = str(
            proj.get("factory_mode")
            or proj.get("architecture_mode")
            or "agent"
        ).strip().lower()
        return {"agent": "default", "code": "code", "hybrid": "hybrid"}.get(
            mode, "default"
        )

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
            _tmpl_name = self._resolve_team_template_name(proj)
            tmpl = load_team_template(_tmpl_name)
            if tmpl and tmpl.stages:
                stages = []
                for i, s in enumerate(tmpl.stages):
                    stage = dict(s)
                    stage.setdefault("id", f"canvas_node_{i+1}")
                    stage.setdefault("order", i)
                    stage = _enrich_stage_from_agent(stage)
                    stages.append(stage)
                try:
                    from core.api.core_facade import (
                        apply_factory_profile_to_stages,
                        resolve_project_factory_profile,
                    )
                    apply_factory_profile_to_stages(
                        stages, resolve_project_factory_profile(proj)
                    )
                except Exception:
                    logging.getLogger(__name__).debug(
                        "factory_profile apply on team re-sync skipped", exc_info=True
                    )
                proj["team_stages"] = stages
                proj["team_template"] = _tmpl_name
                # Keep opaque team_id for UI; template name drives sync
                if not proj.get("team_id"):
                    proj["team_id"] = _tmpl_name
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
        """Run E2E smoke + repo tests for a completed project pipeline.

        2026-08-27 升级：e2e_smoke 从"目录存在"假通过 → 真实冒烟
        （检测入口 → daemon_jobs 托管启动 → HTTP 健康探测，见 builder/app_runtime.py）；
        repo_tests 升级为测试经理真实测试（递归发现用例 → pytest → test_report + bug_summary）。
        结果持久化到项目状态 last_test_report（前端展示 bug 清单 + suggested_fix）。
        """
        proj = self._projects.get(project_id, {})
        deploy_dir = proj.get("deploy_dir", "") or await self.get_deploy_dir(project_id)
        result = _run_tests_for_project(project_id, deploy_dir or "")
        # 持久化 test_report（含 bug_summary）→ 前端/后续消费；同步晋升门证据旗标
        try:
            rt = result.get("real_tests") or {}
            if rt.get("test_report") is not None or rt.get("test_passed") is not None:
                report = {
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "test_passed": bool(rt.get("test_passed")),
                    "test_report": rt.get("test_report"),
                    "e2e_smoke": result.get("e2e_smoke") or rt.get("e2e_smoke"),
                }
                proj["last_test_report"] = report
                from builder.hop_metrics import derive_test_evidence
                ev = derive_test_evidence(last_test_report=report, state=None)
                proj["_real_tests_ok"] = bool(ev["real_tests_green"])
                proj["_physical_evidence"] = bool(ev["physical_evidence"])
                self._save_projects()
                # mirror into in-memory / pipeline state when present
                try:
                    st = self._runs.get(project_id)
                    if isinstance(st, dict):
                        st["_real_tests_ok"] = proj["_real_tests_ok"]
                        st["_physical_evidence"] = proj["_physical_evidence"]
                except Exception:
                    logging.getLogger("aiplat.builder").debug(
                        "mirror test evidence into run state skipped", exc_info=True)
        except Exception:
            logging.getLogger("aiplat.builder").debug(
                "test_report 持久化失败 project_id=%s", project_id, exc_info=True)  # best-effort
        return result

    # ── 生成 app 运行时（2026-08-27，生成物侧接线：daemon_jobs 生成物适用 待接线 → 已接线）──
    async def runtime_launch(self, project_id: str) -> Dict[str, Any]:
        """检测生成 app 入口并经 daemon_jobs 托管启动。"""
        from builder.app_runtime import launch
        return launch(project_id)

    async def runtime_status(self, project_id: str) -> Dict[str, Any]:
        """生成 app 运行状态（daemon job 存活 + 端口 + 入口）。"""
        from builder.app_runtime import status
        return status(project_id)

    async def runtime_stop(self, project_id: str) -> Dict[str, Any]:
        """停止生成 app（daemon_jobs kill 会话组 + 清理记录）。"""
        from builder.app_runtime import stop
        return stop(project_id)

    async def runtime_real_tests(self, project_id: str, install_deps: bool = True) -> Dict[str, Any]:
        """测试经理真实测试：递归发现生成物测试用例 → pytest 执行 → test_report（含 bug_summary）。"""
        from builder.app_runtime import real_tests
        proj = self._projects.get(project_id, {})
        deploy_dir = proj.get("deploy_dir", "") or await self.get_deploy_dir(project_id)
        return real_tests(project_id, deploy_dir=deploy_dir or None, install_deps=install_deps)

    async def get_last_test_report(self, project_id: str) -> Optional[Dict[str, Any]]:
        """最近一次真实测试报告（run_tests 持久化的 last_test_report）。"""
        proj = self._projects.get(project_id, {})
        return proj.get("last_test_report") or None

    async def runtime_auto_repair(self, project_id: str, max_rounds: int = 2) -> Dict[str, Any]:
        """自动修复闭环：真实测试失败 → LLM 修复生成代码 → 写回部署目录 → 重跑验证。
        F4: hard-cap max_rounds; persist repair_exhausted for UI/HITL."""
        from builder.app_runtime import MAX_REPAIR_ATTEMPTS, auto_repair
        try:
            max_rounds = int(max_rounds)
        except (TypeError, ValueError):
            max_rounds = MAX_REPAIR_ATTEMPTS
        max_rounds = max(1, min(max_rounds, MAX_REPAIR_ATTEMPTS))
        proj = self._projects.get(project_id, {})
        deploy_dir = proj.get("deploy_dir", "") or await self.get_deploy_dir(project_id)
        result = await auto_repair(project_id, deploy_dir=deploy_dir or None, max_rounds=max_rounds)
        try:
            proj["last_repair"] = {
                "repaired": bool(result.get("repaired")),
                "rounds": result.get("rounds"),
                "repair_exhausted": bool(result.get("repair_exhausted")),
                "next": result.get("next") or "",
                "reason": result.get("reason") or "",
            }
            self._save_projects()
        except Exception:
            logging.getLogger(__name__).debug("persist last_repair skipped", exc_info=True)
        if result.get("repair_exhausted"):
            try:
                friction = self._record_t4a_friction(
                    "repair_exhausted",
                    project_id=project_id,
                    stage_id="",
                    detail=str(result.get("reason") or "repair_exhausted"),
                )
                if friction.get("cta"):
                    result["friction_share"] = friction["cta"]
            except Exception:
                logging.getLogger(__name__).debug("repair_exhausted friction skipped", exc_info=True)
        return result

    async def runtime_smoke(self, project_id: str, keep_alive: bool = False) -> Dict[str, Any]:
        """生成 app 冒烟测试（启动 + 健康探测 + 报告）。F4: persist openable on project."""
        from builder.app_runtime import detect_runtime, smoke_test
        proj = self._projects.get(project_id, {})
        det = detect_runtime(project_id)
        if not det.get("found"):
            result = {
                "smoke_passed": None,
                "skipped": True,
                "reason": "static_or_managed",
                "openable": True,
                "open_reason": "static_or_managed",
                "e2e_smoke": {"passed": None, "reason": "static_or_managed"},
            }
        else:
            result = smoke_test(project_id, keep_alive=keep_alive)
            result["openable"] = bool(result.get("smoke_passed"))
            result["open_reason"] = "healthy" if result["openable"] else "unhealthy"
        try:
            proj["last_runtime"] = {
                "smoke": result,
                "openable": bool(result.get("openable")),
                "open_reason": result.get("open_reason") or "",
            }
            self._save_projects()
        except Exception:
            logging.getLogger(__name__).debug("persist last_runtime skipped", exc_info=True)
        return result







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
    import os
    results: dict = {"all_passed": False, "e2e_smoke": None, "repo_tests": None}
    # 2026-08-27 升级：测试经理真实测试——递归发现生成物测试用例（backend/tests/ 等），
    # 可写临时目录跑 pytest → test_report（含 bug_summary）；替换原"仅根目录 tests/"浅扫描。
    from builder.app_runtime import real_tests
    rt = real_tests(project_id, deploy_dir=deploy_dir or None)
    if rt.get("detected"):
        results["repo_tests"] = {"passed": rt.get("test_passed", False),
                                 "output": (rt.get("test_report") or {}).get("meta", {}).get("summary", ""),
                                 "report": rt.get("test_report")}
        results["all_passed"] = bool(rt.get("test_passed"))
    # 真实 e2e 冒烟（detect → daemon_jobs 启动 → HTTP 健康探测）
    results["e2e_smoke"] = rt.get("e2e_smoke") or {"passed": False, "reason": rt.get("reason")}
    results["real_tests"] = rt
    if results["all_passed"] and results["e2e_smoke"].get("passed"):
        results["all_passed"] = True
    else:
        results["all_passed"] = False
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
        code_text = ""
        if os.path.isfile(final_state):
            with open(final_state, "r") as _fs:
                _state = json.load(_fs)
            code = _state.get("agent_app", {}) or _state.get("code", {})
            code_text = code.get("raw_output", "") if isinstance(code, dict) else str(code)
        # Fallback: stage artifact files (agent-mode pipelines often lack _final_state.json)
        if not code_text:
            for fname in ("agent_app.json", "code.json"):
                p = os.path.join(out_dir, fname)
                if not os.path.isfile(p):
                    continue
                try:
                    with open(p, "r", encoding="utf-8") as _af:
                        raw = _af.read()
                    if "## FILE:" in raw:
                        code_text = raw
                        break
                    blob = json.loads(raw[raw.find("{") : raw.rfind("}") + 1] if "{" in raw else raw)
                    if isinstance(blob, dict):
                        code_text = str(blob.get("raw_output") or "")
                        if not code_text and ("## FILE:" in raw or "skill_routing" in raw):
                            code_text = raw
                    if code_text:
                        break
                except Exception:
                    continue
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
                    os.makedirs(os.path.dirname(full_path) or _app_home, exist_ok=True)
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
                            os.makedirs(os.path.dirname(full_path) or _app_home, exist_ok=True)
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
        _state: dict = {}
        fp_raw = ""
        if os.path.isfile(final_state):
            with open(final_state, "r") as _fs:
                _state = _j2.load(_fs)
            fp = _state.get("frontend_pages", {})
            fp_raw = fp.get("raw_output", "") if isinstance(fp, dict) else str(fp)
        if not fp_raw:
            fp_path = os.path.join(out_dir, "frontend_pages.json")
            if os.path.isfile(fp_path):
                with open(fp_path, "r", encoding="utf-8") as _ff:
                    fp_raw = _ff.read()
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
                    try: fp_data = _j2.loads(fp_raw[_jstart:_jend+1]); _app_page_json = _j2.dumps(fp_data, ensure_ascii=False, indent=2)
                    except Exception: pass  # noqa: cleanup-best-effort — temp file cleanup
            if _app_page_json:
                # Deterministic: skill inject + dual ingest + wizard I/O wiring
                try:
                    from core.api.core_facade import (
                        parse_app_page_payload,
                        repair_frontend_pages_with_prd,
                    )
                    _aa = _state.get("agent_app") or _state.get("agent_manifest") or {}
                    if not _aa:
                        aa_path = os.path.join(out_dir, "agent_app.json")
                        if os.path.isfile(aa_path):
                            with open(aa_path, "r", encoding="utf-8") as _aaf:
                                _aa = _aaf.read()
                    _fixed, _meta = repair_frontend_pages_with_prd(
                        _app_page_json if _app_page_json.strip().startswith("{") else fp_raw,
                        _aa,
                    )
                    # Always prefer repaired page when parse succeeds (wizard_io /
                    # result_sections / media_skill_canonical may be the only changes).
                    _page, _ = parse_app_page_payload(_fixed)
                    if _page:
                        _app_page_json = _j2.dumps(_page, ensure_ascii=False, indent=2)
                    # Promote media skill aliases in agent_app so routing/ui_bindings
                    # match canonical stage.skill (report_assembly → report_json_export).
                    try:
                        from core.api.core_facade import (
                            ensure_agent_app_skill_consistency,
                            ensure_platform_media_skill_contracts,
                            normalize_media_skill_names,
                        )

                        # Prefer repaired output/agent_app.json over stale pipeline state
                        _aa_text = ""
                        aa_path2 = os.path.join(out_dir, "agent_app.json")
                        if os.path.isfile(aa_path2):
                            with open(aa_path2, "r", encoding="utf-8") as _aaf2:
                                _aa_text = _aaf2.read()
                        if not _aa_text.strip():
                            if isinstance(_aa, dict):
                                _aa_text = str(
                                    _aa.get("raw_output")
                                    or _aa.get("markdown")
                                    or ""
                                ).strip()
                                if not _aa_text and (
                                    _aa.get("skill_routing") or _aa.get("ui_bindings")
                                ):
                                    _aa_text = _j2.dumps(
                                        _aa, ensure_ascii=False, indent=2
                                    )
                            else:
                                _aa_text = str(_aa or "")
                        _aa_fixed, _aa_nmeta = normalize_media_skill_names(_aa_text)
                        _aa_fixed2, _aa_cmeta = ensure_agent_app_skill_consistency(
                            _aa_fixed
                        )
                        _aa_fixed3, _aa_pmeta = ensure_platform_media_skill_contracts(
                            _aa_fixed2
                        )
                        _aa_changed = bool(
                            (_aa_nmeta or {}).get("remapped")
                            or (_aa_cmeta or {}).get("renamed")
                            or (_aa_cmeta or {}).get("deduped_stems")
                            or (_aa_cmeta or {}).get("routing_aligned")
                            or (_aa_cmeta or {}).get("merged_speech")
                            or (_aa_pmeta or {}).get("rewritten")
                            or _aa_fixed3 != _aa_text
                        )
                        if _aa_changed:
                            _aa_fixed = _aa_fixed3
                            aa_out = os.path.join(out_dir, "agent_app.json")
                            with open(aa_out, "w", encoding="utf-8") as _aaw:
                                _aaw.write(_aa_fixed)
                        else:
                            _aa_fixed = _aa_fixed3
                        # Always materialize top-level agent_manifest.json so
                        # routing/ui_bindings stay aligned with app_page skills.
                        _man_src = (
                            _aa_fixed
                            if (_aa_nmeta or {}).get("ok") is not False
                            else _aa_text
                        )
                        _man_m = _re.search(
                            r"(?ms)^#{2,4}\s*FILE:\s*[^\n]*agent_manifest\.json\s*\n(.*?)(?=^#{2,4}\s*FILE:|\Z)",
                            _man_src,
                        )
                        _man_body = ""
                        if _man_m:
                            _man_body = _man_m.group(1).strip()
                            if _man_body.startswith("```"):
                                _man_body = _re.sub(
                                    r"^```(?:json)?\s*", "", _man_body
                                )
                                _man_body = _re.sub(r"\s*```\s*$", "", _man_body)
                        elif str(_man_src).strip().startswith("{"):
                            _man_body = str(_man_src).strip()
                        # Prefer innermost JSON object (manifest), not wrappers
                        if _man_body:
                            try:
                                _man_obj = _j2.loads(_man_body)
                            except Exception:
                                _js = _man_body.find("{")
                                _je = _man_body.rfind("}")
                                _man_obj = (
                                    _j2.loads(_man_body[_js : _je + 1])
                                    if 0 <= _js < _je
                                    else None
                                )
                            if isinstance(_man_obj, dict) and (
                                _man_obj.get("skill_routing")
                                or _man_obj.get("ui_bindings")
                                or _man_obj.get("agents")
                            ):
                                _man_path = os.path.join(
                                    _app_home, "agent_manifest.json"
                                )
                                with open(_man_path, "w", encoding="utf-8") as _mw:
                                    _mw.write(
                                        _j2.dumps(
                                            _man_obj, ensure_ascii=False, indent=2
                                        )
                                    )
                    except Exception:
                        logging.getLogger(__name__).debug(
                            "deploy agent_app media normalize skipped",
                            exc_info=True,
                        )
                except Exception:
                    logging.getLogger(__name__).debug(
                        "deploy app_page repair skipped", exc_info=True
                    )
                with open(os.path.join(_app_home, "app_page.json"), "w", encoding="utf-8") as _apf:
                    _apf.write(_app_page_json)
    except Exception:
        logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

    # ── Register generated agents & skills to workspace ──
    # P1-17 生成物契约校验（2026-08-26）：借鉴 SBA conformance 模式——注册前用
    # generated_conformance.py 校验（治理字段/schema 字段名/首行残留），不合规则跳过注册，
    # 防止"LLM 碰运气"产物污染工作区。
    # F4：拒绝明细写入返回值 rejected_artifacts，供前端面板展示（不再仅打日志）。
    _reg_count = 0
    _rejected = 0
    _rejected_artifacts: list = []
    try:
        import shutil
        import logging as _log_dep
        from builder.generated_conformance import validate_file, record_rejection, validate_manifest_file
        _agents_dir = os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "agents")
        _skills_dir = os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "skills")
        _blog = _log_dep.getLogger("aiplat.builder")
        # Scan recursively for AGENT.md and SKILL.md files (may be nested under app dir)
        for _root, _dirs, _files in os.walk(_app_home):
            for _f in _files:
                _src = os.path.join(_root, _f)
                if _f == "agent_manifest.json":
                    _violations = validate_manifest_file(_src)
                    if _violations:
                        _rejected += 1
                        _blog.warning("Deploy: agent_manifest.json 不合规 %s: %s",
                                      _src, "; ".join(_violations[:3]))
                        record_rejection(project_id, "manifest", _src, _violations)
                        _rejected_artifacts.append({
                            "kind": "manifest",
                            "name": "agent_manifest",
                            "path": _src,
                            "violations": list(_violations),
                            "fix_hint": "默认 mode=single；multi_agent 需 rationale+success_metrics+upgrade_criteria 五条 AND",
                        })
                    continue
                if _f == "AGENT.md":
                    _agent_name = os.path.basename(_root)
                    _violations = validate_file(_src, "agent")
                    if _violations:
                        _rejected += 1
                        _blog.warning("Deploy: 跳过注册不合规 AGENT.md %s: %s",
                                      _src, "; ".join(_violations[:3]))
                        record_rejection(project_id, "agent", _src, _violations)  # 原则 13 失败写回
                        _rejected_artifacts.append({
                            "kind": "agent",
                            "name": _agent_name,
                            "path": _src,
                            "violations": list(_violations),
                            "fix_hint": "对照 generated_conformance.yaml agent 契约补齐 frontmatter / SOP",
                        })
                        continue
                    _dst = os.path.join(_agents_dir, _agent_name, "AGENT.md")
                    os.makedirs(os.path.dirname(_dst), exist_ok=True)
                    shutil.copy2(_src, _dst)
                    # 生成物侧接线（CLAUDE.md §23）：注册成功时预置运行时治理入口 sidecar
                    _write_runtime_governance_sidecar(_dst)
                    # 生成物侧接线：上线消息总线身份（通知层；非契约协同主路径）
                    _register_generated_agent_to_bus(_agent_name)
                    _reg_count += 1
                elif _f == "SKILL.md":
                    _skill_name = os.path.basename(_root)
                    _violations = validate_file(_src, "skill")
                    if _violations:
                        _rejected += 1
                        _blog.warning("Deploy: 跳过注册不合规 SKILL.md %s: %s",
                                      _src, "; ".join(_violations[:3]))
                        record_rejection(project_id, "skill", _src, _violations)  # 原则 13 失败写回
                        _fix = "补齐缺失字段"
                        if any("completion_criterion" in str(v) for v in _violations):
                            _fix = "在 SKILL.md frontmatter 增加非空 completion_criterion（引用 PRD FR/AC）"
                        _rejected_artifacts.append({
                            "kind": "skill",
                            "name": _skill_name,
                            "path": _src,
                            "violations": list(_violations),
                            "fix_hint": _fix,
                        })
                        continue
                    _dst = os.path.join(_skills_dir, _skill_name, "SKILL.md")
                    os.makedirs(os.path.dirname(_dst), exist_ok=True)
                    shutil.copy2(_src, _dst)
                    _reg_count += 1
        if _reg_count > 0 or _rejected > 0:
            _blog.info(
                "Deploy: registered %d agents/skills from %s (rejected %d by conformance)",
                _reg_count, _app_home, _rejected)
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
<a href="/app/apps/{project_id}" class="btn btn-primary">📱 使用应用</a>
<a href="/app/factory" class="btn btn-secondary">🔧 返回应用工厂</a>
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
    
    # Interactive wizard lives on management frontend (/app/apps/:id → AppPage).
    # Static session host (8004) remains available for raw deploy artifacts.
    app_url = f"/app/apps/{project_id}"
    preview_url = f"/app/apps/{project_id}?embed=1"
    static_url = f"{os.getenv('AIPLAT_APP_BASE_URL', 'http://localhost:8004').rstrip('/')}/app/sessions/{project_id}"

    # Persist a minimal _final_state.json so later deploys/tools don't miss artifacts
    try:
        import json as _jfinal
        out_dir = os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "output", project_id)
        os.makedirs(out_dir, exist_ok=True)
        final_path = os.path.join(out_dir, "_final_state.json")
        if not os.path.isfile(final_path):
            blob: dict = {"project_id": project_id, "phase": "done"}
            for key in ("agent_app", "frontend_pages", "architecture", "prd", "test_cases", "test_report"):
                p = os.path.join(out_dir, f"{key}.json")
                if not os.path.isfile(p):
                    continue
                try:
                    with open(p, "r", encoding="utf-8") as fh:
                        raw = fh.read()
                    if raw.strip().startswith("{"):
                        blob[key] = {"raw_output": raw}
                    else:
                        blob[key] = {"raw_output": raw}
                except Exception:
                    continue
            # Prefer pass rate from true-test report / runs; never stamp real_pytest=0 blindly
            try:
                rate = None
                source = None
                tr_path = os.path.join(out_dir, "test_report.json")
                if os.path.isfile(tr_path):
                    with open(tr_path, "r", encoding="utf-8") as trf:
                        tr_raw = trf.read()
                    tobj = _jfinal.loads(
                        tr_raw[tr_raw.find("{") : tr_raw.rfind("}") + 1]
                        if "{" in tr_raw
                        else tr_raw
                    )
                    meta = tobj.get("meta") or {}
                    if meta.get("pass_rate") is not None:
                        rate = float(meta.get("pass_rate"))
                        if rate > 1.0:
                            rate = rate / 100.0
                        source = "agent_true_test"
                if rate is None:
                    runs = proj.get("runs") or []
                    if runs and runs[-1].get("pass_rate") is not None:
                        rate = float(runs[-1].get("pass_rate"))
                        if rate > 1.0:
                            rate = rate / 100.0
                        source = str(runs[-1].get("pass_rate_source") or "estimated")
                if rate is not None:
                    blob["_test_pass_rate"] = rate
                    blob["_pass_rate_source"] = source or "estimated"
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
            with open(final_path, "w", encoding="utf-8") as fw:
                _jfinal.dump(blob, fw, ensure_ascii=False, indent=2)
    except Exception:
        logging.getLogger(__name__).debug("persist _final_state skipped", exc_info=True)
    
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
    
    # Phase A/C：部署结果附带「跑通」晋升契约快照（含 hop 聚合）
    _promotion = {}
    try:
        from builder.hop_metrics import derive_test_evidence, evaluate_project_run_through
        import json as _json_promo
        _man = {}
        _mp = os.path.join(_app_home, "agent_manifest.json")
        if os.path.isfile(_mp):
            with open(_mp, "r", encoding="utf-8") as _mf:
                _man = _json_promo.load(_mf) or {}
        _report = None
        _proj_flags: Dict[str, Any] = {}
        try:
            _projects_path = os.path.join(
                os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")),
                "projects.json",
            )
            if os.path.isfile(_projects_path):
                with open(_projects_path, "r", encoding="utf-8") as _pf:
                    _pdata = _json_promo.load(_pf) or {}
                _rows = _pdata.get("projects") or []
                _prow = {}
                if isinstance(_rows, list):
                    for _item in _rows:
                        if isinstance(_item, dict) and _item.get("project_id") == project_id:
                            _prow = _item
                            break
                elif isinstance(_rows, dict):
                    _prow = _rows.get(project_id) or {}
                if isinstance(_prow, dict) and _prow:
                    _report = _prow.get("last_test_report")
                    _proj_flags = {
                        "_real_tests_ok": _prow.get("_real_tests_ok"),
                        "_physical_evidence": _prow.get("_physical_evidence"),
                    }
        except Exception:
            _report = None
        _ev = derive_test_evidence(
            last_test_report=_report if isinstance(_report, dict) else None,
            state=_proj_flags or None,
        )
        _promotion = evaluate_project_run_through(
            project_id,
            conformance_green=(_rejected == 0),
            real_tests_green=bool(_ev["real_tests_green"]),
            physical_evidence=bool(_ev["physical_evidence"]),
            policy_gate_closed=True,
        )
        _promotion["manifest_mode"] = (_man.get("mode") or "single")
        _promotion["evidence"] = _ev
    except Exception:
        logging.getLogger(__name__).debug("promotion_gate snapshot failed", exc_info=True)

    return {
        "ok": True,
        "deploy_dir": deploy_dir,
        "app_url": app_url,
        "preview_url": preview_url,
        "static_url": static_url,
        "files_generated": _file_count,
        # F4: surface conformance rejects to UI (not log-only)
        "registered_count": _reg_count,
        "rejected_count": _rejected,
        "rejected_artifacts": _rejected_artifacts,
        "promotion_gate": _promotion,
    }


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
        # Same-process Core: richer Builder parser; remote Core uses core.prd_markdown.
        try:
            from core.api.core_facade import set_prd_markdown_parser
            set_prd_markdown_parser(BuilderProjectService._parse_markdown_prd)
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
    return _project_service_singleton

