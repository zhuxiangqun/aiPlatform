"""
Skill Registry Module

Provides enhanced SkillRegistry with version management, enable/disable,
and binding statistics.
"""

import os
import math
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timezone

from .base import BaseSkill, SkillMetadata, TextGenerationSkill, CodeGenerationSkill, DataAnalysisSkill, register_skill_factory
from ...harness.interfaces import SkillConfig, SkillResult


# Generic tool name patterns for compatibility scanning.
# These are regex-ish keywords found in Skill SOP bodies — the actual
# tool availability is determined dynamically via ToolRegistry.query().
_TOOL_SCAN_PATTERNS: Dict[str, str] = {
    "read": "file read",
    "write": "file write",
    "edit": "file edit",
    "glob": "file pattern search",
    "grep": "code search",
    "bash": "shell command",
    "browser": "web browser",
    "web_search": "web search",
}


def check_tool_compatibility(skill_body: str) -> Dict[str, Dict[str, Any]]:
    """Scan Skill SOP body for referenced tools and return availability via ToolRegistry.

    Dynamically queries ToolRegistry for each detected tool name — no hardcoded
    availability map. Unknown tools show as unavailable with a hint.
    """
    body_lower = skill_body.lower()
    result: Dict[str, Dict[str, Any]] = {}
    try:
        from core.apps.tools.base import get_tool_registry
        reg = get_tool_registry()
        all_tools = {t.lower(): t for t in (reg.list_tools() if hasattr(reg, 'list_tools') else [])}
    except Exception:
        all_tools = {}

    for keyword, description in _TOOL_SCAN_PATTERNS.items():
        if keyword not in body_lower:
            continue
        # Check if any registered tool name contains this keyword
        matched = [t for t in all_tools if keyword in t.lower()]
        if matched:
            result[keyword] = {"available": True, "mapped_to": matched[0],
                                "all_matches": matched[:5]}
        else:
            result[keyword] = {"available": False,
                                "hint": f"需要配置支持 {description} 的 MCP server 或 tool"}

    return result


@dataclass
class SkillVersion:
    version: str
    config: SkillConfig
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_active: bool = True


@dataclass
class SkillBindingStats:
    skill_id: str
    bound_agents: List[str] = field(default_factory=list)
    total_executions: int = 0
    success_count: int = 0
    error_count: int = 0
    avg_latency: float = 0.0


class SkillRegistry:
    """
    Enhanced Skill Registry

    Manages skill registration, versioning, enable/disable,
    and agent binding statistics.
    """

    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}
        self._categories: Dict[str, List[str]] = {}
        self._versions: Dict[str, List[SkillVersion]] = {}
        self._enabled: Dict[str, bool] = {}
        self._binding_stats: Dict[str, SkillBindingStats] = {}
        self._stats_override: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        # Cached SKILL.md body content (keyed by skill name)
        self._body_cache: Dict[str, str] = {}
        # Adaptive skill routing (SkillRouter: arXiv:2603.22455)
        self.SKILL_EMBED_THRESHOLD = 500
        self._body_vectors: Dict[str, List[float]] = {}
        self._body_idf: Dict[str, float] = {}
        self._body_vocab: List[str] = []

    def seed_data(self, data: Dict[str, Dict[str, Any]] = None) -> None:
        """Seed the registry with built-in skill instances from engine skills dir.

        Skill metadata (name, display_name, category, description, enabled)
        is loaded from SKILL.md files under core/engine/skills/<name>/,
        NOT hardcoded in Python lists. See CLAUDE.md §5.29.
        """
        import os as _os
        import yaml as _yaml

        engine_skills_root = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
            "engine", "skills"
        )

        if not _os.path.isdir(engine_skills_root):
            return

        _skill_type_map = {
            "text_generation": TextGenerationSkill,
            "code_generation": CodeGenerationSkill,
            "data_analysis": DataAnalysisSkill,
            "skill_eval_trigger": None,
            "skill_eval_quality": None,
            "skill_apply_engine_skill_md_patch": None,
        }

        with self._lock:
            for dirname in sorted(_os.listdir(engine_skills_root)):
                skill_dir = _os.path.join(engine_skills_root, dirname)
                skill_md = _os.path.join(skill_dir, "SKILL.md")
                if not _os.path.isfile(skill_md):
                    continue

                try:
                    with open(skill_md, "r", encoding="utf-8") as f:
                        raw = f.read()
                except Exception:
                    continue

                name = dirname
                display_name = name.replace("_", " ").title()
                category = "general"
                description = ""
                enabled = True
                uses_file_output = False
                body = raw

                if raw.startswith("---"):
                    parts = raw.split("---", 2)
                    if len(parts) >= 3:
                        try:
                            fm = _yaml.safe_load(parts[1]) or {}
                            name = str(fm.get("name", dirname))
                            display_name = str(fm.get("display_name", display_name))
                            category = str(fm.get("category", "general"))
                            description = str(fm.get("description", ""))
                            enabled = str(fm.get("status", "enabled")) != "disabled"
                            uses_file_output = bool(fm.get("uses_file_output"))
                            version = str(fm.get("version", "1.0.0"))
                            execution_mode = str(fm.get("execution_mode", "inline"))
                            protected = bool(fm.get("protected", False))
                            executable = bool(fm.get("executable", False))
                            permissions = fm.get("permissions") or []
                            input_schema = fm.get("input_schema") or {}
                            output_schema = fm.get("output_schema") or {}
                            effects = fm.get("effects") or []
                            skip_conditions = fm.get("skip_when") or fm.get("skip_conditions") or []
                            triggers = fm.get("triggers") or []
                            body = parts[2].strip()
                        except Exception:
                            pass

                if self.get(name) is not None:
                    continue

                skill_cls = _skill_type_map.get(name) if name in _skill_type_map else None
                if skill_cls is None and name == "skill_eval_trigger":
                    import importlib
                    skill_cls = importlib.import_module(f"{__package__}.eval_trigger").SkillEvalTriggerSkill
                if skill_cls is None and name == "skill_eval_quality":
                    import importlib
                    skill_cls = importlib.import_module(f"{__package__}.eval_quality").SkillEvalQualitySkill
                if skill_cls is None and name == "skill_apply_engine_skill_md_patch":
                    import importlib
                    skill_cls = importlib.import_module(f"{__package__}.apply_engine_skill_md_patch").ApplyEngineSkillMdPatchSkill

                # Code-First Skills: auto-discover handler.py in skill directory
                handler_path = _os.path.join(skill_dir, "handler.py")
                if skill_cls is None and _os.path.isfile(handler_path):
                    try:
                        import importlib.util as _iu
                        spec = _iu.spec_from_file_location(f"skill_handler_{name}", handler_path)
                        if spec and spec.loader:
                            handler_mod = _iu.module_from_spec(spec)
                            spec.loader.exec_module(handler_mod)
                            build_fn = getattr(handler_mod, 'build_skill', None)
                            if callable(build_fn):
                                skill_cls = type(build_fn())  # use returned instance's class
                    except Exception:
                        pass

                # Detect layered subdirectories for engine skills
                layer_dirs: Dict[str, str] = {}
                for sub in ("references", "assets", "scripts"):
                    sub_path = _os.path.join(skill_dir, sub)
                    if _os.path.isdir(sub_path):
                        layer_dirs[sub] = _os.path.realpath(sub_path)

                if skill_cls:
                    skill = skill_cls()
                    register_skill_factory(name, type(skill))
                    if uses_file_output:
                        cfg = getattr(skill, "_config", None)
                        if cfg and hasattr(cfg, "metadata"):
                            cfg.metadata["uses_file_output"] = True
                    # Inject skip_conditions and triggers from SKILL.md frontmatter
                    if skip_conditions or triggers:
                        cfg = getattr(skill, "_config", None)
                        if cfg and hasattr(cfg, "metadata"):
                            if skip_conditions:
                                cfg.metadata["skip_conditions"] = skip_conditions
                            if triggers:
                                cfg.metadata["triggers"] = triggers
                    if layer_dirs:
                        cfg = getattr(skill, "_config", None)
                        if cfg and hasattr(cfg, "metadata"):
                            cfg.metadata["layer_dirs"] = layer_dirs
                    # Inject additional frontmatter fields
                    cfg = getattr(skill, "_config", None)
                    if cfg and hasattr(cfg, "metadata"):
                        if execution_mode:
                            cfg.metadata["execution_mode"] = execution_mode
                        if protected:
                            cfg.metadata["protected"] = protected
                        if executable:
                            cfg.metadata["executable"] = executable
                        if permissions:
                            cfg.metadata["permissions"] = permissions
                        if input_schema:
                            cfg.metadata["input_schema"] = input_schema
                        if output_schema:
                            cfg.metadata["output_schema"] = output_schema
                        if effects:
                            cfg.metadata["effects"] = effects
                    self.register(skill)
                else:
                    config = SkillConfig(
                        name=name,
                        description=description,
                    metadata={"category": category, "body": body, "version": version,
                              "uses_file_output": uses_file_output,
                              "execution_mode": execution_mode,
                              "protected": protected,
                              "executable": executable,
                              "permissions": permissions,
                              "input_schema": input_schema,
                              "output_schema": output_schema,
                              "effects": effects,
                              "skip_conditions": skip_conditions,
                              "triggers": triggers,
                              "layer_dirs": layer_dirs}
                    )
                    skill = _GenericSkill(config)
                    self.register(skill)

                if not enabled:
                    self.disable(name)

    def _pre_register_validate(self, skill: BaseSkill) -> None:
        cfg = skill.get_config()
        import logging
        import os
        logger = logging.getLogger("aiplat.skills")
        strict = os.getenv("AIPLAT_SKILL_STRICT_VALIDATION", "false").lower() in ("1", "true", "yes")

        def _fail(msg: str):
            if strict:
                raise ValueError(msg)
            logger.warning("Skill registration advisory: %s", msg)

        effects = list(getattr(cfg, "effects", []) or [])
        if not effects:
            _fail(
                f"Skill '{cfg.name}': effects declaration missing. "
                f"See CLAUDE.md §5.19. Set AIPLAT_SKILL_STRICT_VALIDATION=true to enforce."
            )
            return
        for e in effects:
            if "type" not in e:
                _fail(f"Skill '{cfg.name}': effects[].type required")
            if "idempotent" not in e:
                _fail(f"Skill '{cfg.name}': effects[].idempotent required")
        has_write = any(e.get("type") in ("write", "execute", "both") for e in effects)
        if has_write and bool(getattr(cfg, "idempotent", True)):
            _fail(
                f"Skill '{cfg.name}': has write/execute effects but idempotent=true. "
                f"Set idempotent=false or remove write effects."
            )
        meta = getattr(cfg, "metadata", {}) or {}
        risk_level = str(meta.get("risk_level") or "low")
        permissions = list(meta.get("permissions") or [])
        if risk_level in ("high", "critical") and not permissions:
            _fail(
                f"Skill '{cfg.name}': risk_level={risk_level} requires explicit permissions"
            )
        for e in effects:
            e_type = str(e.get("type") or "")
            if e_type in ("write", "execute", "both") and not bool(e.get("rollback_available")):
                _fail(
                    f"Skill '{cfg.name}': effects[].type={e_type} requires rollback_available=true"
                )

    def register(self, skill: BaseSkill) -> None:
        """Register a skill"""
        self._pre_register_validate(skill)
        with self._lock:
            cfg = skill.get_config()
            name = cfg.name
            # P0-1: normalize governance contract fields and attach a stable digest.
            try:
                from core.apps.skills.contract import build_contract_and_digest

                meta = dict(getattr(cfg, "metadata", {}) or {})
                kind = str(meta.get("skill_kind") or meta.get("kind") or "rule")
                version = str(meta.get("version") or "1.0.0")
                contract, digest = build_contract_and_digest(
                    name=name,
                    version=version,
                    kind=kind,
                    input_schema=getattr(cfg, "input_schema", {}) or {},
                    output_schema=getattr(cfg, "output_schema", {}) or {},
                    metadata=meta,
                )
                # Keep contract fields both in metadata (for legacy access) and as a digest.
                meta["permissions"] = contract.get("permissions") or []
                meta["risk_level"] = contract.get("risk_level") or "low"
                meta["auto_trigger_allowed"] = bool(contract.get("auto_trigger_allowed"))
                meta["requires_approval"] = bool(contract.get("requires_approval"))
                meta["contract_digest"] = digest
                # Verify integrity: if this skill was previously registered, check digest hasn't changed
                existing = self._skills.get(name)
                if existing:
                    existing_cfg = getattr(existing, "get_config", lambda: None)()
                    existing_meta = getattr(existing_cfg, "metadata", {}) or {} if existing_cfg else {}
                    stored_digest = existing_meta.get("contract_digest")
                    if stored_digest and stored_digest != digest:
                        import logging
                        logging.getLogger("aiplat.skills").warning(
                            "Skill integrity warning: contract digest changed for '%s' (version=%s). "
                            "Stored: %s..., Computed: %s...",
                            name, version, stored_digest[:16], digest[:16]
                        )
                setattr(cfg, "metadata", meta)
            except Exception:
                pass
            category = self._get_category(skill)
            self._skills[name] = skill
            if category not in self._categories:
                self._categories[category] = []
            if name not in self._categories[category]:
                self._categories[category].append(name)
            version = cfg.metadata.get("version", "1.0.0")
            self._add_version(name, version, cfg)
            self._enabled[name] = True
            self._binding_stats[name] = SkillBindingStats(skill_id=name)
            # Invalidate body vectors cache — new skill may push count past threshold
            self._invalidate_body_vectors()

    def get(self, name: str) -> Optional[BaseSkill]:
        """Get skill by name"""
        return self._skills.get(name)

    def get_body(self, name: str) -> str:
        """Get cached SKILL.md body content for a skill."""
        return self._body_cache.get(name, "")

    def seed_for_platform(self) -> None:
        """Seed skills for platform process: built-in + discovered workspace skills."""
        self.seed_data()
        try:
            import os
            workspace = os.path.expanduser(os.getenv("AIPLAT_WORKSPACE_SKILLS", "~/.aiplat/skills"))
            from core.apps.skills.discovery import SkillDiscovery
            discovery = SkillDiscovery(base_path="", workspace_path=workspace)
            for name, skill in discovery._discovered.items():
                if self.get(name) is None:
                    from core.apps.skills.registry import _GenericSkill as GenSkill
                    from core.harness.interfaces import SkillConfig as SC
                    sc = SC(
                        name=skill.name,
                        description=skill.description or "",
                        metadata={"category": skill.category or "general", "body": skill.sop_markdown or ""},
                    )
                    s = GenSkill(config=sc)
                    self.register(s)
        except Exception:
            pass
        # Folder scan fallback: auto-discover *.md files in ~/.aiplat/skills/
        self.scan_folder(os.path.expanduser(os.getenv("AIPLAT_WORKSPACE_SKILLS", "~/.aiplat/skills")))

    def scan_folder(self, skills_dir: str) -> int:
        """Scan a folder for *.md files and auto-register them as Skills.

        Each .md file becomes a rule-type Skill with:
        - name = filename (without .md extension)
        - body = file content (after YAML frontmatter if present)
        - description = frontmatter 'description' field or auto-generated

        This enables 'just drop a .md file' skill creation — no API
        registration, no mandatory permissions/effects/version fields.

        Args:
            skills_dir: Path to a directory containing *.md skill files.

        Returns:
            int: Number of skills discovered and registered.
        """
        import os
        import yaml as _yaml
        from core.apps.skills.registry import _GenericSkill as GenSkill
        from core.harness.interfaces import SkillConfig as SC

        if not os.path.isdir(skills_dir):
            return 0

        count = 0
        for fname in sorted(os.listdir(skills_dir)):
            if not fname.endswith(".md"):
                continue
            fullpath = os.path.join(skills_dir, fname)
            if not os.path.isfile(fullpath):
                continue
            try:
                with open(fullpath, "r", encoding="utf-8") as f:
                    raw = f.read()
            except Exception:
                continue

            name = fname[:-3]  # strip .md
            if self.get(name) is not None:
                continue  # already registered

            body = raw
            description = ""
            category = "general"
            if raw.startswith("---"):
                parts = raw.split("---", 2)
                if len(parts) >= 3:
                    try:
                        fm = _yaml.safe_load(parts[1]) or {}
                        description = str(fm.get("description", ""))
                        category = str(fm.get("category", "general"))
                    except Exception:
                        pass
                    body = parts[2].strip()
            if not description:
                description = name.replace("_", " ").title()

            # Detect layered subdirectories (references/assets/scripts)
            layer_dirs: Dict[str, str] = {}
            for sub in ("references", "assets", "scripts"):
                sub_path = os.path.join(skills_dir, sub)
                if os.path.isdir(sub_path):
                    layer_dirs[sub] = os.path.realpath(sub_path)

            # Code-First Skills: auto-discover handler.py alongside .md file
            skill_cls = None
            handler_path = os.path.join(skills_dir, "handler.py") if os.path.isfile(os.path.join(skills_dir, "handler.py")) else None
            if not handler_path:
                base = os.path.splitext(fullpath)[0]
                hp = f"{base}.py"
                if os.path.isfile(hp):
                    handler_path = hp
            if handler_path and os.path.isfile(handler_path):
                try:
                    import importlib.util as _iu
                    spec = _iu.spec_from_file_location(f"ws_skill_{name}", handler_path)
                    if spec and spec.loader:
                        mod = _iu.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        build_fn = getattr(mod, 'build_skill', None)
                        if callable(build_fn):
                            skill_cls = type(build_fn())
                except Exception:
                    pass

            config = SC(
                name=name,
                description=description,
                metadata={"category": category, "body": body, "layer_dirs": layer_dirs} if layer_dirs else {"category": category, "body": body},
            )
            if skill_cls:
                skill = skill_cls()
                skill._config = config
            else:
                skill = GenSkill(config=config)
            self.register(skill)
            count += 1

        return count

    def import_skills_from_dir(self, source_dir: str, auto_install_deps: bool = True) -> Dict[str, Any]:
        """Batch import all .md skills from a directory (GenericAgent skill library).

        Each .md file in the directory is parsed as a skill:
        - YAML frontmatter → skill metadata (category, description, tags, effects)
        - Body → skill content (SOP, instructions)
        - If auto_install_deps=True and frontmatter declares requirements, pip install

        Skills are classified by category frontmatter field, defaulting to 'general'.

        Args:
            source_dir: Path to directory containing .md skill files.
            auto_install_deps: If True, auto-detect and pip install dependencies.

        Returns:
            Dict with keys: 'imported' (count), 'skipped' (count), 'errors' (list),
            'categories' (dict of category→count).
        """
        import os as _os
        import subprocess
        import yaml as _yaml
        from core.apps.skills.registry import _GenericSkill as GenSkill
        from core.harness.interfaces import SkillConfig as SC

        result = {"imported": 0, "skipped": 0, "errors": [], "categories": {}}

        if not _os.path.isdir(source_dir):
            return result

        for fname in sorted(_os.listdir(source_dir)):
            if not fname.endswith(".md"):
                continue
            fullpath = _os.path.join(source_dir, fname)
            if not _os.path.isfile(fullpath):
                continue
            try:
                with open(fullpath, "r", encoding="utf-8") as f:
                    raw = f.read()
            except Exception as e:
                result["errors"].append(f"{fname}: read error: {e}")
                continue

            name = fname[:-3]
            if self.get(name) is not None:
                result["skipped"] += 1
                continue

            category = "general"
            description = ""
            tags = []
            body = raw
            if raw.startswith("---"):
                parts = raw.split("---", 2)
                if len(parts) >= 3:
                    try:
                        fm = _yaml.safe_load(parts[1]) or {}
                        category = str(fm.get("category", "general"))
                        description = str(fm.get("description", ""))
                        tags = fm.get("tags", []) if isinstance(fm.get("tags"), list) else []

                        if auto_install_deps and fm.get("requires"):
                            deps = fm["requires"]
                            if isinstance(deps, str):
                                deps = [deps]
                            if isinstance(deps, list):
                                try:
                                    subprocess.run(
                                        ["pip", "install", *deps],
                                        capture_output=True, timeout=60
                                    )
                                except Exception:
                                    pass

                    except Exception as e:
                        result["errors"].append(f"{fname}: yaml parse error: {e}")
                        continue
                    body = parts[2].strip()

            if not description:
                description = name.replace("_", " ").title()

            # Detect layered subdirectories (references/assets/scripts)
            layer_dirs: Dict[str, str] = {}
            for sub in ("references", "assets", "scripts"):
                sub_path = _os.path.join(source_dir, sub)
                if _os.path.isdir(sub_path):
                    layer_dirs[sub] = _os.path.realpath(sub_path)

            config = SC(
                name=name,
                description=description,
                metadata={
                    "category": category,
                    "body": body,
                    "tags": tags,
                    "source_file": fullpath,
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                    "layer_dirs": layer_dirs,
                },
            )
            skill = GenSkill(config=config)
            self.register(skill)
            result["imported"] += 1
            result["categories"][category] = result["categories"].get(category, 0) + 1

        return result

    def get_version(self, name: str, version: str) -> Optional[SkillConfig]:
        """Get a specific version of a skill's config"""
        versions = self._versions.get(name, [])
        for v in versions:
            if v.version == version:
                return v.config
        return None

    def get_versions(self, name: str) -> List[SkillVersion]:
        """Get all versions of a skill"""
        return self._versions.get(name, [])

    def get_active_version(self, name: str) -> Optional[str]:
        """Get currently active version for a skill."""
        versions = self._versions.get(name, [])
        for v in versions:
            if v.is_active:
                return v.version
        return versions[-1].version if versions else None

    def rollback_version(self, name: str, version: str) -> bool:
        """Rollback skill to a specific version"""
        with self._lock:
            versions = self._versions.get(name, [])
            target = None
            for v in versions:
                if v.version == version:
                    target = v
                    break
            if target is None:
                return False
            for v in versions:
                v.is_active = (v.version == version)
            skill = self._skills.get(name)
            if skill:
                # Apply target config to the skill instance so rollback affects subsequent execution.
                try:
                    setattr(skill, "_config", target.config)
                except Exception:
                    pass
            self._skills[name] = skill
            # Cache SKILL.md body content if available
            body = (getattr(cfg, "body", None) or "").strip()
            if body:
                self._body_cache[name] = body
            return True

    def _add_version(self, name: str, version: str, config: SkillConfig) -> None:
        """Add a version entry"""
        if name not in self._versions:
            self._versions[name] = []
        sv = SkillVersion(version=version, config=config)
        self._versions[name].append(sv)

    def _get_category(self, skill: BaseSkill) -> str:
        """Extract category from skill config"""
        config = skill.get_config()
        return config.metadata.get("category", "general") if hasattr(config, 'metadata') else "general"

    def list_skills(self, category: Optional[str] = None, enabled_only: bool = False) -> List[str]:
        """List skills, optionally filtered by category and enabled status"""
        with self._lock:
            if category:
                names = self._categories.get(category, [])
            else:
                names = list(self._skills.keys())
            if enabled_only:
                names = [n for n in names if self._enabled.get(n, True)]
            return names

    def unregister(self, name: str) -> None:
        """Unregister a skill"""
        with self._lock:
            if name in self._skills:
                skill = self._skills[name]
                category = self._get_category(skill)
                if category in self._categories and name in self._categories[category]:
                    self._categories[category].remove(name)
                del self._skills[name]
            self._versions.pop(name, None)
            self._enabled.pop(name, None)
            self._binding_stats.pop(name, None)

    def enable(self, name: str) -> bool:
        """Enable a skill"""
        with self._lock:
            if name in self._skills:
                self._enabled[name] = True
                return True
            return False

    def disable(self, name: str) -> bool:
        """Disable a skill"""
        with self._lock:
            if name in self._skills:
                self._enabled[name] = False
                return True
            return False

    def is_enabled(self, name: str) -> bool:
        """Check if a skill is enabled"""
        return self._enabled.get(name, False)

    def bind_agent(self, skill_name: str, agent_id: str) -> None:
        """Bind a skill to an agent"""
        with self._lock:
            if skill_name in self._binding_stats:
                stats = self._binding_stats[skill_name]
                if agent_id not in stats.bound_agents:
                    stats.bound_agents.append(agent_id)

    def unbind_agent(self, skill_name: str, agent_id: str) -> None:
        """Unbind a skill from an agent"""
        with self._lock:
            if skill_name in self._binding_stats:
                stats = self._binding_stats[skill_name]
                if agent_id in stats.bound_agents:
                    stats.bound_agents.remove(agent_id)

    def get_binding_stats(self, name: str) -> Optional[SkillBindingStats]:
        """Get binding statistics for a skill"""
        return self._binding_stats.get(name)

    def get_bound_agents(self, name: str) -> List[str]:
        """Get agents bound to a skill"""
        stats = self._binding_stats.get(name)
        return stats.bound_agents if stats else []

    def record_execution(self, name: str, success: bool, latency: float = 0.0) -> None:
        """Record a skill execution"""
        with self._lock:
            if name in self._binding_stats:
                stats = self._binding_stats[name]
                stats.total_executions += 1
                if success:
                    stats.success_count += 1
                else:
                    stats.error_count += 1
                if latency > 0:
                    prev_avg = stats.avg_latency
                    count = stats.success_count + stats.error_count
                    stats.avg_latency = (prev_avg * (count - 1) + latency) / count

    def get_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all skills"""
        if self._stats_override:
            return self._stats_override
        result = {}
        for name, skill in self._skills.items():
            stats = self._binding_stats.get(name)
            result[name] = {
                "enabled": self._enabled.get(name, True),
                "category": self._get_category(skill),
                "bound_agents": len(stats.bound_agents) if stats else 0,
                "total_executions": stats.total_executions if stats else 0,
                "success_count": stats.success_count if stats else 0,
                "error_count": stats.error_count if stats else 0,
                "avg_latency": stats.avg_latency if stats else 0.0,
                "versions": [v.version for v in self._versions.get(name, [])],
            }
        return result


    # ── Adaptive Skill Routing (SkillRouter-style, §5.4) ─────────────────

    def _ensure_body_vectors(self):
        """Lazy-build TF-IDF body vectors when skill count exceeds threshold.

        Only activated when len(self._skills) >= SKILL_EMBED_THRESHOLD.
        After first build, subsequent calls are no-ops until invalidated.
        """
        if len(self._skills) < self.SKILL_EMBED_THRESHOLD:
            return
        if self._body_vectors:
            return  # already computed

        # Build vocabulary: tokenize all skill bodies
        body_texts: Dict[str, str] = {}
        df: Dict[str, Set[str]] = {}  # term → set of skill names containing it
        for name, skill in self._skills.items():
            text = f"{skill.get_config().name} {skill.get_config().description}"
            body = getattr(skill.get_config(), "body", None) or ""
            if body:
                text += " " + str(body)[:5000]  # cap body for TF-IDF
            tokens = _tokenize(text)
            body_texts[name] = " ".join(tokens)
            for t in set(tokens):
                df.setdefault(t, set()).add(name)

        self._body_vocab = sorted(df.keys())
        n = len(self._skills)

        # Compute IDF
        self._body_idf = {
            term: math.log((n + 1) / (len(docs) + 1)) + 1.0
            for term, docs in df.items()
        }

        # Compute TF-IDF vectors for each skill
        for name, text in body_texts.items():
            tokens = _tokenize(text)
            tf = _compute_tf(tokens)
            vec = [tf.get(term, 0.0) * self._body_idf.get(term, 1.0) for term in self._body_vocab]
            norm = math.sqrt(sum(v * v for v in vec))
            if norm > 0:
                vec = [v / norm for v in vec]
            self._body_vectors[name] = vec

    def _invalidate_body_vectors(self):
        """Clear cached body vectors (called on register)."""
        self._body_vectors.clear()
        self._body_idf.clear()
        self._body_vocab.clear()

    def get_candidates(self, query: str, limit: int = 10) -> List[str]:
        """Get top-K skill candidates for a query, adaptive to skill pool size.

        ≤ SKILL_EMBED_THRESHOLD skills → metadata-based (name + description)
        > SKILL_EMBED_THRESHOLD  skills → body TF-IDF cosine similarity

        The body-based path is zero-dependency TF-IDF (pure Python math) and
        activates automatically when the pool crosses the threshold.
        """
        self._ensure_body_vectors()

        if self._body_vectors:
            return self._retrieve_by_body(query, limit)

        # Small pool: metadata-based (name + description substring scan)
        candidates = []
        q = query.lower()
        for name, skill in self._skills.items():
            cfg = skill.get_config()
            text = f"{cfg.name} {cfg.description}".lower()
            score = 1.0 if q in text else 0.0
            candidates.append((name, score))
        candidates.sort(key=lambda x: -x[1])
        return [c[0] for c in candidates[:limit]]

    def _retrieve_by_body(self, query: str, limit: int) -> List[str]:
        """TF-IDF cosine similarity retrieval using precomputed body vectors."""
        tokens = _tokenize(query)
        tf = _compute_tf(tokens)
        qv = [tf.get(t, 0.0) * self._body_idf.get(t, 1.0) for t in self._body_vocab]
        qn = math.sqrt(sum(v * v for v in qv))
        if qn > 0:
            qv = [v / qn for v in qv]

        scores = []
        for name, sv in self._body_vectors.items():
            dot = sum(a * b for a, b in zip(qv, sv))
            scores.append((name, dot))
        scores.sort(key=lambda x: -x[1])
        return [s[0] for s in scores[:limit]]


def _tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alphanumeric tokens."""
    import re
    return re.findall(r'[a-zA-Z0-9_\u4e00-\u9fff]{2,}', str(text).lower())


def _compute_tf(tokens: List[str]) -> Dict[str, float]:
    """Compute normalized term frequency."""
    tf: Dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0.0) + 1.0
    total = max(len(tokens), 1)
    return {t: c / total for t, c in tf.items()}


# Global registry
_global_registry = SkillRegistry()


def get_skill_registry() -> SkillRegistry:
    """Get global skill registry"""
    return _global_registry
class _GenericSkill(BaseSkill):
    """Generic skill for skills without a dedicated subclass.
    
    Represents skills that need an LLM adapter to execute but don't 
    have specialized logic. Uses a prompt template derived from the
    skill's description and category.
    """
    
    def __init__(self, config: SkillConfig):
        super().__init__(config)
        self._model = None
    
    def set_model(self, model):
        self._model = model
    
    async def execute(self, context, params):
        if not self._model:
            return SkillResult(
                success=False,
                error=f"No LLM adapter configured for skill '{self._config.name}'"
            )

        # Canonical JSON extraction via CoreFacade (replaces local _extract_json).
        from core.api.core_facade import parse_json

        prompt = params.get("prompt", params.get("input", ""))
        if not prompt:
            # Prefer schema-driven prompt: feed the full params as JSON so SOP can reference fields.
            prompt = f"Execute skill '{self._config.name}': {self._config.description}\nInput(JSON): {params}"

        # Organization-level coding policy profile (Phase-1).
        coding_profile = str((params or {}).get("_coding_policy_profile") or "").strip().lower()
        policy_block = ""
        if coding_profile == "karpathy_v1":
            policy_block = (
                "编码行为规范（karpathy_v1，必须遵循）：\n"
                "1) 编码前思考：不要做未证实假设；遇到歧义/缺参，先在输出中列出需要确认的问题与可选方案。\n"
                "2) 简洁优先：坚持最小可行实现；不要引入未经请求的抽象/架构/额外功能。\n"
                "3) 精准修改：像外科手术一样，只改必须改的地方；避免无关格式化/无关文件改动。\n"
                "4) 目标驱动：把任务转成可验证目标；在输出中给出验收标准（测试/复现步骤/检查清单）。\n"
            )
        
        try:
            sop = ""
            try:
                sop = (self._config.metadata or {}).get("sop_markdown", "") if hasattr(self._config, "metadata") else ""
            except Exception:
                sop = ""

            allowed_tools = []
            try:
                # Prefer runtime context.tools, fallback to config metadata.tools.
                if context and getattr(context, "tools", None):
                    allowed_tools = list(getattr(context, "tools") or [])
                else:
                    allowed_tools = list((self._config.metadata or {}).get("tools", []) if hasattr(self._config, "metadata") else [])
                allowed_tools = [str(t) for t in allowed_tools if str(t).strip()]
            except Exception:
                allowed_tools = []

            system_parts = [
                "你是一个可复用技能（Skill）执行器。",
                f"技能名称：{self._config.name}",
                f"技能描述：{self._config.description}",
            ]
            if policy_block:
                system_parts.append(policy_block)
            if sop:
                system_parts.append("下面是该技能的SOP（必须严格遵循）：")
                system_parts.append(sop)

            # If output_schema exists, require strict JSON output with those top-level keys.
            out_schema = {}
            try:
                out_schema = self._config.output_schema or {}
            except Exception:
                out_schema = {}
            if isinstance(out_schema, dict) and out_schema:
                keys = list(out_schema.keys())
                system_parts.append("输出要求：你必须返回严格 JSON（不要输出任何额外文本/解释/代码块外内容）。")
                system_parts.append(f"JSON 顶层字段必须包含：{keys}")
                system_parts.append("如果某字段无法给出，请给出空值（空数组/空对象/空字符串），但不要遗漏字段。")

            # If tools are available, run as a tool-capable ReAct agent (SkillTool-like orchestration).
            if allowed_tools:
                from ...apps.agents.react import create_react_agent
                from ...harness.interfaces import AgentConfig, AgentContext

                agent = create_react_agent(
                    config=AgentConfig(
                        name=f"skill-inline-{self._config.name}",
                        model=str(getattr(self._model, "model", None) or "deepseek-chat"),
                        metadata={"role": "skill-agent", "skill": self._config.name},
                    ),
                    model=self._model,
                )

                task = "\n".join(system_parts) + "\n\n用户输入：\n" + prompt
                msgs = [{"role": "system", "content": "\n".join(system_parts)}, {"role": "user", "content": prompt}]
                agent_ctx = AgentContext(
                    session_id=getattr(context, "session_id", "skill"),
                    user_id=getattr(context, "user_id", "system"),
                    messages=[{"role": "user", "content": task}],
                    variables={"messages": msgs, **(getattr(context, "variables", {}) or {})},
                    tools=allowed_tools,
                )
                result = await agent.execute(agent_ctx)
                if isinstance(out_schema, dict) and out_schema:
                    parsed = parse_json(str(result.output or ""))
                    if isinstance(parsed, dict):
                        return SkillResult(
                            success=bool(result.success),
                            output=parsed,
                            error=result.error,
                            metadata={"skill": self._config.name, "agent": result.metadata, "tools": allowed_tools, "parsed_json": True},
                        )
                    return SkillResult(
                        success=False,
                        output={"raw": result.output},
                        error="json_parse_failed",
                        metadata={"skill": self._config.name, "agent": result.metadata, "tools": allowed_tools},
                    )
                return SkillResult(success=bool(result.success), output={"text": result.output}, error=result.error, metadata={"skill": self._config.name, "agent": result.metadata, "tools": allowed_tools})

            # Fallback: plain LLM generation (no tools)
            from ...harness.syscalls.llm import sys_llm_generate

            response = await sys_llm_generate(
                self._model,
                [
                    {"role": "system", "content": "\n".join(system_parts)},
                    {"role": "user", "content": prompt},
                ],
            )
            if isinstance(out_schema, dict) and out_schema:
                parsed = parse_json(str(getattr(response, "content", "") or ""))
                if isinstance(parsed, dict):
                    return SkillResult(success=True, output=parsed, metadata={"model": getattr(response, "model", None), "skill": self._config.name, "parsed_json": True})
                return SkillResult(success=False, output={"raw": getattr(response, "content", None)}, error="json_parse_failed", metadata={"model": getattr(response, "model", None), "skill": self._config.name})
            return SkillResult(success=True, output={"text": response.content}, metadata={"model": response.model, "skill": self._config.name})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

