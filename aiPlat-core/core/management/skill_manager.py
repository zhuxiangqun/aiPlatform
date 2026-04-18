"""
Skill Manager - Manages Skill instances

Provides CRUD operations for skills and execution management.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid
import os
from pathlib import Path

import yaml
import re
import shutil


@dataclass
class SkillInfo:
    """Skill information"""
    id: str
    name: str
    type: str  # generation, analysis, transformation, retrieval, execution
    description: str
    status: str  # enabled, disabled, deprecated
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    config: Dict[str, Any]
    dependencies: List[Dict[str, Any]]
    version: str
    created_at: datetime
    updated_at: datetime
    created_by: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillStats:
    """Skill execution statistics"""
    total_calls: int = 0
    success_count: int = 0
    failed_count: int = 0
    avg_duration_ms: float = 0.0
    success_rate: float = 0.0


@dataclass
class SkillExecution:
    """Skill execution record"""
    id: str
    skill_id: str
    status: str  # pending, running, completed, failed
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]]
    error: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]
    duration_ms: float


@dataclass
class SkillVersion:
    """Skill version"""
    version: str
    status: str  # current, historical
    created_at: datetime
    changes: str


class SkillManager:
    """
    Skill Manager - Manages Skill instances
    
    Provides:
    - Skill CRUD operations
    - Skill version management
    - Skill execution
    - Skill statistics
    """
    
    def __init__(
        self,
        seed: bool = True,
        *,
        scope: str = "engine",
        reserved_ids: Optional[set] = None,
    ):
        self._skills: Dict[str, SkillInfo] = {}
        self._stats: Dict[str, SkillStats] = {}
        self._executions: Dict[str, List[SkillExecution]] = {}
        self._versions: Dict[str, List[SkillVersion]] = {}
        # skill_id -> [agent_ids]
        self._bound_agents: Dict[str, List[str]] = {}
        self._scope = scope  # "engine" | "workspace"
        self._reserved_ids = reserved_ids or set()
        if seed:
            self._seed_data()
        else:
            # Prefer directory-based skills (<base>/skills/<skill_id>/SKILL.md) as source of truth.
            self._load_directory_skills()

    def _load_directory_skills(self) -> None:
        """Load directory-based skills from filesystem into management plane."""
        try:
            now = datetime.utcnow()
            # Load low priority first, then allow high priority (repo) to override
            for base_dir in self._resolve_skills_paths():
                if not base_dir.exists():
                    continue
                for item in base_dir.iterdir():
                    if not item.is_dir():
                        continue
                    if item.name.startswith(".") or item.name in ["__pycache__", "scripts", "references", "assets"]:
                        continue
                    skill_md = item / "SKILL.md"
                    if not skill_md.exists():
                        continue

                    raw = skill_md.read_text(encoding="utf-8")
                    fm, _body = self._split_front_matter(raw)
                    fm = fm or {}

                    skill_id = str(fm.get("name") or item.name)
                    display_name = str(fm.get("display_name") or fm.get("displayName") or skill_id)
                    description = str(fm.get("description") or "")
                    category = str(fm.get("category") or "general")
                    version = str(fm.get("version") or "1.0.0")
                    status = str(fm.get("status") or ("enabled")).lower()
                    if status not in ["enabled", "disabled", "deprecated"]:
                        status = "enabled"

                    input_schema = fm.get("input_schema") or {}
                    output_schema = fm.get("output_schema") or {}
                    if not isinstance(input_schema, dict):
                        input_schema = {}
                    if not isinstance(output_schema, dict):
                        output_schema = {}

                    metadata = dict(fm)
                    metadata.setdefault("filesystem", {})
                    if isinstance(metadata["filesystem"], dict):
                        metadata["filesystem"]["skill_dir"] = str(item)
                        metadata["filesystem"]["skill_md"] = str(skill_md)
                        metadata["filesystem"]["source"] = str(base_dir)

                    self._skills[skill_id] = SkillInfo(
                        id=skill_id,
                        name=display_name,
                        type=category,
                        description=description,
                        status=status,
                        input_schema=input_schema,
                        output_schema=output_schema,
                        config={"version": version},
                        dependencies=[],
                        version=version,
                        created_at=now,
                        updated_at=now,
                        created_by="filesystem",
                        metadata=metadata,
                    )
                    self._stats.setdefault(skill_id, SkillStats())
                    self._executions.setdefault(skill_id, [])
                    self._versions.setdefault(skill_id, [SkillVersion(version=version, status="current", created_at=now, changes="Loaded from filesystem")])
                    self._bound_agents.setdefault(skill_id, [])

            # Bridge to execution-layer registry
            for _id, info in self._skills.items():
                self._bridge_to_registry(info)
                if info.status == "disabled":
                    try:
                        from core.apps.skills import get_skill_registry

                        get_skill_registry().disable(_id)
                    except Exception:
                        pass
        except Exception:
            return

    def _find_skill_md(self, skill_id: str) -> Optional[Path]:
        """Find SKILL.md by searching skills paths from high priority to low."""
        for base_dir in reversed(self._resolve_skills_paths()):
            p = base_dir / skill_id / "SKILL.md"
            if p.exists():
                return p
        return None
    
    def _seed_data(self):
        now = datetime.utcnow()
        demo_skills = [
            ("text_generation", "文本生成", "generation", "根据提示生成各类文本内容", "enabled"),
            ("code_generation", "代码生成", "generation", "根据需求描述生成代码", "disabled"),
            ("data_analysis", "数据分析", "analysis", "分析数据并提供洞察", "enabled"),
            ("task_planning", "任务规划", "execution", "根据目标拆解为可执行的子任务步骤", "enabled"),
            ("information_search", "信息检索", "retrieval", "从知识库和互联网中检索相关信息", "enabled"),
            ("knowledge_retrieval", "知识召回", "retrieval", "从向量数据库中召回相关文档片段", "enabled"),
            ("summarization", "内容摘要", "transformation", "将长文本压缩为简洁的摘要", "enabled"),
            ("task_decomposition", "任务分解", "analysis", "将复杂任务分解为简单子任务", "enabled"),
            ("api_calling", "API调用", "execution", "调用外部API接口获取数据", "enabled"),
            ("chitchat", "闲聊", "generation", "处理日常闲聊和简单问答", "enabled"),
            ("code_review", "代码审查", "analysis", "审查代码质量并给出改进建议", "enabled"),
            ("translation", "多语言翻译", "transformation", "在多语言之间进行翻译", "enabled"),
        ]
        for skill_id, name, skill_type, desc, status in demo_skills:
            self._skills[skill_id] = SkillInfo(
                id=skill_id, name=name, type=skill_type, description=desc,
                status=status, input_schema={}, output_schema={},
                config={"version": "1.0.0"}, dependencies=[],
                version="1.0.0", created_at=now, updated_at=now, created_by="system"
            )
            self._stats[skill_id] = SkillStats()
            self._executions[skill_id] = []
            self._versions[skill_id] = [SkillVersion(version="1.0.0", status="current", created_at=now, changes="初始版本")]
        self._bound_agents = {}  # skill_id -> [agent_ids]
        
        for skill_id, skill_info in self._skills.items():
            self._bridge_to_registry(skill_info)
    
    async def create_skill(
        self,
        name: str,
        skill_type: str,
        description: str,
        input_schema: Dict[str, Any],
        output_schema: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
        dependencies: Optional[List[Dict[str, Any]]] = None,
        created_by: str = "system",
        metadata: Optional[Dict[str, Any]] = None
    ) -> SkillInfo:
        """Create a new skill"""
        skill_id = name.lower().replace(" ", "_").replace("-", "_")
        if self._reserved_ids and skill_id in self._reserved_ids:
            raise ValueError(f"Skill id '{skill_id}' is reserved by engine scope and cannot be created in workspace.")
        now = datetime.utcnow()
        
        skill = SkillInfo(
            id=skill_id,
            name=name,
            type=skill_type,
            description=description,
            status="enabled",
            input_schema=input_schema,
            output_schema=output_schema,
            config=config or {
                "timeout_seconds": 60,
                "max_concurrent": 10,
                "retry_count": 3
            },
            dependencies=dependencies or [],
            version="v1.0.0",
            created_at=now,
            updated_at=now,
            created_by=created_by,
            metadata=metadata or {}
        )
        
        self._skills[skill_id] = skill
        self._stats[skill_id] = SkillStats()
        self._executions[skill_id] = []
        self._versions[skill_id] = [
            SkillVersion(
                version="v1.0.0",
                status="current",
                created_at=now,
                changes="Initial version"
            )
        ]
        self._bound_agents[skill_id] = []

        # Materialize directory-based skill on filesystem (SKILL.md + skeleton).
        # This makes skill definitions explicit, versionable, and compatible with Agent Skill / SOP mode.
        try:
            base_dir = self._resolve_skills_base_path()
            skill_dir = base_dir / skill_id
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "references").mkdir(exist_ok=True)
            (skill_dir / "scripts").mkdir(exist_ok=True)
            (skill_dir / "assets").mkdir(exist_ok=True)

            skill_md_path = skill_dir / "SKILL.md"
            if not skill_md_path.exists():
                # Prefer clean semver without leading "v" for SKILL.md.
                semver = str(skill.version or "v1.0.0")
                if semver.startswith("v"):
                    semver = semver[1:]

                trigger_conditions = []
                if isinstance(skill.metadata, dict):
                    tc = skill.metadata.get("trigger_conditions")
                    if isinstance(tc, list):
                        trigger_conditions = [str(x) for x in tc if isinstance(x, (str, int, float)) and str(x).strip()]

                manifest = {
                    "name": skill_id,
                    "display_name": name,
                    "description": description or "",
                    "category": skill_type or "general",
                    "version": semver,
                    "execution_mode": (skill.metadata or {}).get("execution_mode", "inline") if isinstance(skill.metadata, dict) else "inline",
                    "trigger_conditions": trigger_conditions,
                    "input_schema": input_schema or {},
                    "output_schema": output_schema or {},
                }

                header = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).strip()
                body = f"""

# {name}

## 目标
用 1-3 句话说明此技能要达成的目标。

## 输入
- 说明参数含义与默认值策略
- 若依赖外部资源/路径/权限，请写清楚

## 输出
- 输出物是什么（文本/文件/报告）
- 输出位置与命名规则（如适用）

## 工作流程（SOP）
1. 第一步……
2. 第二步……
3. 第三步……

## 质量要求（Checklist）
- [ ] 覆盖所有输入范围与边界情况
- [ ] 输出包含可追溯证据（如 trace_id/run_id/链接）
- [ ] 遇到失败要给出原因与下一步建议
"""
                skill_md_path.write_text(f"---\n{header}\n---\n{body.lstrip()}", encoding="utf-8")

            # Record filesystem location (best effort)
            if isinstance(skill.metadata, dict):
                skill.metadata.setdefault("filesystem", {})
                if isinstance(skill.metadata["filesystem"], dict):
                    skill.metadata["filesystem"]["skill_dir"] = str(skill_dir)
                    skill.metadata["filesystem"]["skill_md"] = str(skill_md_path)
        except Exception as e:
            # Do not fail the management operation due to filesystem issues;
            # record the error for operators.
            if isinstance(skill.metadata, dict):
                skill.metadata.setdefault("filesystem", {})
                if isinstance(skill.metadata["filesystem"], dict):
                    skill.metadata["filesystem"]["error"] = str(e)

        # Register in execution-layer after filesystem materialization (so SOP can be injected)
        self._bridge_to_registry(skill)
        
        return skill

    def _resolve_skills_base_path(self) -> Path:
        """
        Resolve primary base path for directory-based skills (SKILL.md).

        Scope:
        - engine: <repo_root>/core/engine/skills
        - workspace: ~/.aiplat/skills

        Override:
        - AIPLAT_ENGINE_SKILLS_PATHS / AIPLAT_WORKSPACE_SKILLS_PATHS: pathsep-separated list (write target = last)
        - AIPLAT_ENGINE_SKILLS_PATH / AIPLAT_WORKSPACE_SKILLS_PATH: single path (write target)
        """
        paths = self._resolve_skills_paths()
        # last one is highest priority (write target)
        return paths[-1] if paths else (Path(__file__).resolve().parents[2] / "skills")

    def _resolve_skills_paths(self) -> List[Path]:
        """Resolve all skills paths in increasing priority order (low -> high) within current scope."""
        repo_root = Path(__file__).resolve().parents[2]  # aiPlat-core/
        engine_default = repo_root / "core" / "engine" / "skills"
        workspace_default = Path.home() / ".aiplat" / "skills"

        scope = (self._scope or "engine").strip().lower()
        if scope not in {"engine", "workspace"}:
            scope = "engine"

        paths_env = os.environ.get(f"AIPLAT_{scope.upper()}_SKILLS_PATHS")
        if paths_env:
            parts = [p.strip() for p in paths_env.split(os.pathsep) if p.strip()]
            out = [Path(p).expanduser() for p in parts]
            return [p.resolve() for p in out]

        single = os.environ.get(f"AIPLAT_{scope.upper()}_SKILLS_PATH")
        if single:
            return [Path(single).expanduser().resolve()]

        return [engine_default.resolve()] if scope == "engine" else [workspace_default.resolve()]
    
    def _bridge_to_registry(self, skill_info: SkillInfo) -> None:
        """Bridge: register skill in execution-layer SkillRegistry."""
        try:
            from core.apps.skills import get_skill_registry, create_skill as create_skill_instance
            from core.apps.skills.base import TextGenerationSkill, CodeGenerationSkill, DataAnalysisSkill
            from core.apps.skills.registry import _GenericSkill
            from core.harness.interfaces import SkillConfig
            
            registry = get_skill_registry()
            skill_id = skill_info.id
            
            _builtin_map = {
                "text_generation": TextGenerationSkill,
                "code_generation": CodeGenerationSkill,
                "data_analysis": DataAnalysisSkill,
            }
            
            skill_cls = _builtin_map.get(skill_id)
            if skill_cls:
                skill_instance = skill_cls()
                # Override builtin config from directory-based SKILL.md if present
                try:
                    md_path = self._find_skill_md(skill_id)
                    sop_markdown = ""
                    if md_path and md_path.exists():
                        raw = md_path.read_text(encoding="utf-8")
                        fm, body = self._split_front_matter(raw)
                        fm = fm or {}
                        sop_markdown = body.strip()
                        # Apply overrides to builtin config
                        cfg = getattr(skill_instance, "_config", None)
                        if cfg is not None:
                            cfg.description = skill_info.description
                            if hasattr(cfg, "metadata") and isinstance(cfg.metadata, dict):
                                cfg.metadata["category"] = skill_info.type
                                cfg.metadata["version"] = skill_info.version
                                cfg.metadata["sop_markdown"] = sop_markdown
                                cfg.metadata["filesystem"] = (skill_info.metadata or {}).get("filesystem", {}) if isinstance(skill_info.metadata, dict) else {}
                                # Optional: tools allowlist from SKILL.md
                                if isinstance(fm, dict) and isinstance(fm.get("tools"), list):
                                    cfg.metadata["tools"] = list(fm.get("tools") or [])
                except Exception:
                    pass
            else:
                sop_markdown = ""
                try:
                    md_path = self._find_skill_md(skill_id)
                    if md_path and md_path.exists():
                        raw = md_path.read_text(encoding="utf-8")
                        _fm, body = self._split_front_matter(raw)
                        sop_markdown = body.strip()
                except Exception:
                    sop_markdown = ""

                config = SkillConfig(
                    name=skill_id,
                    description=skill_info.description,
                    metadata={
                        "category": skill_info.type,
                        "version": skill_info.version,
                        # L2: SOP injection (SKILL.md body)
                        "sop_markdown": sop_markdown,
                        "filesystem": (skill_info.metadata or {}).get("filesystem", {}) if isinstance(skill_info.metadata, dict) else {},
                    }
                )
                skill_instance = _GenericSkill(config)
            
            registry.register(skill_instance)
            
            if skill_info.status == "disabled":
                registry.disable(skill_id)
        except Exception:
            pass
    
    async def get_skill(self, skill_id: str) -> Optional[SkillInfo]:
        """Get skill by ID"""
        return self._skills.get(skill_id)
    
    async def list_skills(
        self,
        skill_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[SkillInfo]:
        """List skills with filters"""
        skills = list(self._skills.values())
        
        if skill_type:
            skills = [s for s in skills if s.type == skill_type]
        if status:
            skills = [s for s in skills if s.status == status]
        
        return skills[offset:offset + limit]
    
    async def update_skill(
        self,
        skill_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[SkillInfo]:
        """Update skill configuration"""
        skill = self._skills.get(skill_id)
        if not skill:
            return None

        # Engine skills marked as protected are core capabilities and should not be edited via API.
        # Use versions/rollback and enable/disable instead.
        if (self._scope or "engine").strip().lower() == "engine":
            if isinstance(getattr(skill, "metadata", None), dict) and skill.metadata.get("protected") is True:
                raise PermissionError("Protected engine skill cannot be edited")
        
        if name:
            skill.name = name
        if description:
            skill.description = description
        if input_schema:
            skill.input_schema.update(input_schema)
        if output_schema:
            skill.output_schema.update(output_schema)
        if config:
            skill.config.update(config)
        if metadata:
            skill.metadata.update(metadata)
        
        skill.updated_at = datetime.utcnow()

        # Best-effort: keep execution-layer registry config in sync
        self._sync_registry_config(skill)

        # Best-effort: persist updates back to directory-based SKILL.md (keep SOP body unchanged)
        try:
            base_dir = self._resolve_skills_base_path()
            skill_dir = base_dir / skill.id
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "references").mkdir(exist_ok=True)
            (skill_dir / "scripts").mkdir(exist_ok=True)
            (skill_dir / "assets").mkdir(exist_ok=True)

            skill_md_path = skill_dir / "SKILL.md"
            if not skill_md_path.exists():
                # If the file doesn't exist yet, materialize using the same template as create_skill.
                # (create_skill writes only when absent, so safe to call by reusing logic here)
                # Write minimal content so future updates preserve SOP.
                manifest = self._build_skill_manifest(skill)
                header = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).strip()
                skill_md_path.write_text(f"---\n{header}\n---\n\n# {skill.name}\n\n## 目标\n（待补充）\n", encoding="utf-8")
            else:
                raw = skill_md_path.read_text(encoding="utf-8")
                fm, body = self._split_front_matter(raw)
                fm = fm or {}
                fm.update(self._build_skill_manifest(skill))
                header = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
                skill_md_path.write_text(f"---\n{header}\n---\n{body.lstrip()}", encoding="utf-8")

            # Record filesystem location (best effort)
            if isinstance(skill.metadata, dict):
                skill.metadata.setdefault("filesystem", {})
                if isinstance(skill.metadata["filesystem"], dict):
                    skill.metadata["filesystem"]["skill_dir"] = str(skill_dir)
                    skill.metadata["filesystem"]["skill_md"] = str(skill_md_path)
        except Exception as e:
            if isinstance(skill.metadata, dict):
                skill.metadata.setdefault("filesystem", {})
                if isinstance(skill.metadata["filesystem"], dict):
                    skill.metadata["filesystem"]["error"] = str(e)
        
        return skill

    def _split_front_matter(self, content: str) -> tuple[dict | None, str]:
        """
        Split SKILL.md into (front_matter_dict, body).
        If not found, returns (None, original_content).
        """
        if not content.startswith("---"):
            return None, content
        # Find the second '---' on its own line.
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, flags=re.DOTALL)
        if not m:
            return None, content
        yaml_part = m.group(1)
        body = m.group(2)
        try:
            data = yaml.safe_load(yaml_part) or {}
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        return data, body

    def _build_skill_manifest(self, skill: "SkillInfo") -> dict:
        """Build YAML frontmatter for directory-based skill."""
        semver = str(getattr(skill, "version", "") or "v1.0.0")
        if semver.startswith("v"):
            semver = semver[1:]
        trigger_conditions = []
        if isinstance(getattr(skill, "metadata", None), dict):
            tc = skill.metadata.get("trigger_conditions")
            if isinstance(tc, list):
                trigger_conditions = [str(x) for x in tc if isinstance(x, (str, int, float)) and str(x).strip()]
        execution_mode = "inline"
        if isinstance(getattr(skill, "metadata", None), dict):
            em = skill.metadata.get("execution_mode")
            if isinstance(em, str) and em.strip():
                execution_mode = em.strip()
        return {
            "name": skill.id,
            "display_name": getattr(skill, "name", skill.id),
            "description": getattr(skill, "description", "") or "",
            "category": getattr(skill, "type", "general") or "general",
            "version": semver,
            "status": getattr(skill, "status", "enabled") or "enabled",
            "execution_mode": execution_mode,
            "trigger_conditions": trigger_conditions,
            "input_schema": getattr(skill, "input_schema", {}) or {},
            "output_schema": getattr(skill, "output_schema", {}) or {},
        }

    def _sync_registry_config(self, skill: "SkillInfo") -> None:
        """Best-effort: sync SkillRegistry config for an existing skill instance."""
        try:
            from core.apps.skills import get_skill_registry

            registry = get_skill_registry()
            inst = registry.get(skill.id)
            if not inst:
                return
            cfg = getattr(inst, "_config", None)
            if not cfg:
                return
            try:
                cfg.description = skill.description
            except Exception:
                pass
            try:
                cfg.input_schema = skill.input_schema or {}
            except Exception:
                pass
            try:
                cfg.output_schema = skill.output_schema or {}
            except Exception:
                pass
            try:
                if hasattr(cfg, "metadata") and isinstance(cfg.metadata, dict):
                    cfg.metadata["category"] = skill.type
                    cfg.metadata["version"] = skill.version
            except Exception:
                pass
            # Refresh SOP from filesystem (L2)
            try:
                md_path = self._find_skill_md(skill.id)
                if md_path and md_path.exists():
                    raw = md_path.read_text(encoding="utf-8")
                    _fm, body = self._split_front_matter(raw)
                    if hasattr(cfg, "metadata") and isinstance(cfg.metadata, dict):
                        cfg.metadata["sop_markdown"] = body.strip()
                        cfg.metadata["filesystem"] = (skill.metadata or {}).get("filesystem", {}) if isinstance(skill.metadata, dict) else {}
            except Exception:
                pass
        except Exception:
            return
    
    async def delete_skill(self, skill_id: str, *, delete_files: bool = False) -> bool:
        """
        Delete skill from management plane.

        Default behavior is **soft delete**:
        - keep skills/<skill_id>/ on disk
        - mark SKILL.md frontmatter status=deprecated, add deprecated_at

        If delete_files=True:
        - recursively remove skills/<skill_id>/ directory (hard delete)
        """
        skill = self._skills.get(skill_id)
        if not skill:
            return False

        if (self._scope or "engine").strip().lower() == "engine":
            if isinstance(getattr(skill, "metadata", None), dict) and skill.metadata.get("protected") is True:
                raise PermissionError("Protected engine skill cannot be deleted")

        now_iso = datetime.utcnow().isoformat()

        if delete_files:
            # Hard delete: remove directory + unregister + remove from memory
            try:
                base_dir = self._resolve_skills_base_path()
                skill_dir = base_dir / skill.id
                if skill_dir.exists():
                    shutil.rmtree(skill_dir)
            except Exception:
                pass

            try:
                from core.apps.skills import get_skill_registry

                get_skill_registry().unregister(skill_id)
            except Exception:
                pass

            self._skills.pop(skill_id, None)
            self._stats.pop(skill_id, None)
            self._executions.pop(skill_id, None)
            self._versions.pop(skill_id, None)
            self._bound_agents.pop(skill_id, None)
            return True

        # Soft delete: keep skill in memory and on disk, mark deprecated and disable at runtime
        skill.status = "deprecated"
        if isinstance(skill.metadata, dict):
            skill.metadata["deprecated_at"] = now_iso
        skill.updated_at = datetime.utcnow()

        try:
            from core.apps.skills import get_skill_registry

            get_skill_registry().disable(skill_id)
        except Exception:
            pass

        self._writeback_skill_md(skill, extra_frontmatter={"deprecated_at": now_iso})
        return True
    
    async def enable_skill(self, skill_id: str) -> bool:
        """Enable skill"""
        skill = self._skills.get(skill_id)
        if not skill:
            return False
        if skill.status == "deprecated":
            # Must use restore_skill to un-deprecate (keeps intent explicit).
            return False
        skill.status = "enabled"
        skill.updated_at = datetime.utcnow()
        self._sync_registry_config(skill)
        try:
            from core.apps.skills import get_skill_registry

            get_skill_registry().enable(skill_id)
        except Exception:
            pass
        self._writeback_skill_md(skill, remove_frontmatter_keys=["deprecated_at"])
        return True
    
    async def disable_skill(self, skill_id: str) -> bool:
        """Disable skill"""
        skill = self._skills.get(skill_id)
        if not skill:
            return False
        skill.status = "disabled"
        skill.updated_at = datetime.utcnow()
        self._sync_registry_config(skill)
        try:
            from core.apps.skills import get_skill_registry

            get_skill_registry().disable(skill_id)
        except Exception:
            pass
        self._writeback_skill_md(skill)
        return True

    async def restore_skill(self, skill_id: str) -> bool:
        """Restore a deprecated skill (status -> enabled) and re-enable runtime registry."""
        skill = self._skills.get(skill_id)
        if not skill:
            return False
        # Only meaningful for deprecated, but allow restoring disabled as "enable" if needed.
        skill.status = "enabled"
        if isinstance(skill.metadata, dict):
            skill.metadata.pop("deprecated_at", None)
        skill.updated_at = datetime.utcnow()

        # Ensure registered
        try:
            from core.apps.skills import get_skill_registry

            registry = get_skill_registry()
            if not registry.get(skill_id):
                self._bridge_to_registry(skill)
            registry.enable(skill_id)
        except Exception:
            pass

        self._sync_registry_config(skill)
        self._writeback_skill_md(skill, remove_frontmatter_keys=["deprecated_at"])
        return True

    def _writeback_skill_md(
        self,
        skill: "SkillInfo",
        *,
        extra_frontmatter: Optional[Dict[str, Any]] = None,
        remove_frontmatter_keys: Optional[List[str]] = None,
    ) -> None:
        """Best-effort writeback of SKILL.md YAML frontmatter while preserving SOP body."""
        try:
            base_dir = self._resolve_skills_base_path()
            skill_dir = base_dir / skill.id
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "references").mkdir(exist_ok=True)
            (skill_dir / "scripts").mkdir(exist_ok=True)
            (skill_dir / "assets").mkdir(exist_ok=True)

            skill_md_path = skill_dir / "SKILL.md"
            if not skill_md_path.exists():
                fm = self._build_skill_manifest(skill)
                if extra_frontmatter:
                    fm.update(extra_frontmatter)
                header = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
                skill_md_path.write_text(f"---\n{header}\n---\n\n# {skill.name}\n\n（待补充 SOP）\n", encoding="utf-8")
            else:
                raw = skill_md_path.read_text(encoding="utf-8")
                fm, body = self._split_front_matter(raw)
                fm = fm or {}
                fm.update(self._build_skill_manifest(skill))
                if extra_frontmatter:
                    fm.update(extra_frontmatter)
                if remove_frontmatter_keys:
                    for k in remove_frontmatter_keys:
                        fm.pop(k, None)
                header = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
                skill_md_path.write_text(f"---\n{header}\n---\n{body.lstrip()}", encoding="utf-8")

            if isinstance(skill.metadata, dict):
                skill.metadata.setdefault("filesystem", {})
                if isinstance(skill.metadata["filesystem"], dict):
                    skill.metadata["filesystem"]["skill_dir"] = str(skill_dir)
                    skill.metadata["filesystem"]["skill_md"] = str(skill_md_path)
        except Exception:
            return
    
    async def execute_skill(
        self,
        skill_id: str,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        mode: str = "inline"
    ) -> SkillExecution:
        """Execute skill via SkillExecutor and record audit trail."""
        import time
        execution_id = f"exec-{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow()
        
        execution = SkillExecution(
            id=execution_id,
            skill_id=skill_id,
            status="running",
            input_data=input_data,
            output_data=None,
            error=None,
            start_time=now,
            end_time=None,
            duration_ms=0.0
        )
        
        self._executions[skill_id].append(execution)
        
        stats = self._stats.get(skill_id, SkillStats())
        stats.total_calls += 1
        
        try:
            from core.apps.skills import get_skill_executor, get_skill_registry
            from core.harness.interfaces import SkillContext
            
            executor = get_skill_executor()
            registry = get_skill_registry()
            skill = registry.get(skill_id)
            
            if skill and hasattr(skill, 'set_model'):
                try:
                    from core.adapters.llm import create_adapter
                    model = create_adapter(provider="openai", model="gpt-4o")
                    skill.set_model(model)
                except Exception:
                    pass
            
            skill_tools = context.get("tools", []) if context else []
            skill_context = SkillContext(
                session_id=execution_id,
                user_id=context.get("user_id", "system") if context else "system",
                variables=input_data,
                tools=skill_tools,
            )
            
            timeout = context.get("timeout") if context else None
            
            result = await executor.execute(
                skill_id,
                input_data,
                context=skill_context,
                timeout=timeout,
                mode=mode
            )
            
            duration_ms = (datetime.utcnow() - now).total_seconds() * 1000
            
            if result.success:
                await self.complete_execution(execution_id, result.output or {}, duration_ms)
            else:
                await self.fail_execution(execution_id, result.error or "Unknown error", duration_ms)
            
        except Exception as e:
            duration_ms = (datetime.utcnow() - now).total_seconds() * 1000
            await self.fail_execution(execution_id, str(e), duration_ms)
        
        updated = await self.get_execution(execution_id)
        return updated if updated else execution
    
    async def complete_execution(
        self,
        execution_id: str,
        output_data: Dict[str, Any],
        duration_ms: float
    ) -> bool:
        """Complete execution"""
        for skill_id, executions in self._executions.items():
            for exec_ in executions:
                if exec_.id == execution_id:
                    exec_.status = "completed"
                    exec_.output_data = output_data
                    exec_.end_time = datetime.utcnow()
                    exec_.duration_ms = duration_ms
                    
                    # Update stats
                    stats = self._stats[skill_id]
                    stats.success_count += 1
                    stats.success_rate = stats.success_count / stats.total_calls
                    stats.avg_duration_ms = (
                        (stats.avg_duration_ms * (stats.success_count - 1) + duration_ms)
                        / stats.success_count
                    )
                    
                    return True
        return False
    
    async def fail_execution(
        self,
        execution_id: str,
        error: str,
        duration_ms: float
    ) -> bool:
        """Fail execution"""
        for skill_id, executions in self._executions.items():
            for exec_ in executions:
                if exec_.id == execution_id:
                    exec_.status = "failed"
                    exec_.error = error
                    exec_.end_time = datetime.utcnow()
                    exec_.duration_ms = duration_ms
                    
                    # Update stats
                    stats = self._stats[skill_id]
                    stats.failed_count += 1
                    stats.success_rate = stats.success_count / stats.total_calls
                    
                    return True
        return False
    
    async def get_execution(self, execution_id: str) -> Optional[SkillExecution]:
        """Get execution by ID"""
        for executions in self._executions.values():
            for exec_ in executions:
                if exec_.id == execution_id:
                    return exec_
        return None
    
    async def get_execution_history(
        self,
        skill_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[SkillExecution]:
        """Get execution history for skill"""
        history = self._executions.get(skill_id, [])
        return history[offset:offset + limit]
    
    async def get_stats(self, skill_id: str) -> Optional[SkillStats]:
        """Get skill statistics"""
        return self._stats.get(skill_id)
    
    async def get_versions(self, skill_id: str) -> List[SkillVersion]:
        """Get skill versions"""
        return self._versions.get(skill_id, [])
    
    async def create_version(
        self,
        skill_id: str,
        changes: str
    ) -> Optional[SkillVersion]:
        """Create new version"""
        skill = self._skills.get(skill_id)
        if not skill:
            return None
        
        # Parse current version
        current_version = skill.version
        major, minor, patch = map(int, current_version[1:].split('.'))
        
        # Increment patch version
        new_version = f"v{major}.{minor}.{patch +1}"
        
        # Update current version to historical
        for v in self._versions[skill_id]:
            if v.status == "current":
                v.status = "historical"
        
        # Create new version
        version = SkillVersion(
            version=new_version,
            status="current",
            created_at=datetime.utcnow(),
            changes=changes
        )
        
        self._versions[skill_id].append(version)
        skill.version = new_version
        skill.updated_at = datetime.utcnow()
        
        return version
    
    async def rollback_version(self, skill_id: str, version: str) -> bool:
        """Rollback to specific version"""
        skill = self._skills.get(skill_id)
        if not skill:
            return False
        
        versions = self._versions.get(skill_id, [])
        target_version = None
        for v in versions:
            if v.version == version:
                target_version = v
                break
        
        if not target_version:
            return False
        
        # Update current version
        for v in versions:
            v.status = "historical" if v.version != version else "current"
        
        skill.version = version
        skill.updated_at = datetime.utcnow()
        
        return True
    
    async def get_bound_agents(self, skill_id: str) -> List[str]:
        """Get agents bound to this skill"""
        return self._bound_agents.get(skill_id, [])
    
    def get_skill_count(self) -> Dict[str, int]:
        """Get skill count by status"""
        counts = {"total": len(self._skills), "enabled": 0, "disabled": 0, "deprecated": 0}
        for skill in self._skills.values():
            if skill.status in counts:
                counts[skill.status] += 1
        return counts

    def get_skill_ids(self) -> List[str]:
        """Get all skill ids currently loaded."""
        return list(self._skills.keys())
