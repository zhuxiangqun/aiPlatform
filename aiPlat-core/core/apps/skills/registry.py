"""
Skill Registry Module

Provides enhanced SkillRegistry with version management, enable/disable,
and binding statistics.
"""

import os
import math
import logging
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
    # ── Decay tracking (方案五) ──
    recent_results: Any = field(default_factory=lambda: __import__('collections').deque(maxlen=20))
    decayed_at: Optional[float] = None   # timestamp when skill was auto-downgraded
    last_executed_at: Optional[int] = None  # timestamp of last execution (SkillCurator)

    @property
    def recent_pass_rate(self) -> float:
        if not self.recent_results:
            return self.success_count / max(1, self.total_executions)
        return sum(1 for r in self.recent_results if r) / max(1, len(self.recent_results))

    @property
    def is_decayed(self) -> bool:
        """Skill has been auto-downgraded due to low success rate."""
        return self.decayed_at is not None

    def adjust_weight(self, delta: float, *, damping: float = 0.3,
                      clamp_min: float = 0.05, clamp_max: float = 0.95) -> float:
        actual = delta * damping
        current = self.recent_pass_rate
        target = current + actual
        clamped = max(clamp_min, min(clamp_max, target))
        effective = clamped - current
        self.recent_results.append(effective > 0)
        return round(effective, 4)


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
        # Phase 52: embedding cache for semantic skill search
        self._embedding_cache: Dict[str, List[float]] = {}
        self._embedding_adapter = None
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
                            execution_type = str(fm.get("execution_type", ""))
                            protected = bool(fm.get("protected", False))
                            executable = bool(fm.get("executable", False))
                            permissions = fm.get("permissions") or []
                            input_schema = fm.get("input_schema") or {}
                            output_schema = fm.get("output_schema") or {}
                            effects = fm.get("effects") or []
                            submission_criteria = fm.get("submission_criteria") or []  # P1: Action Type
                            side_effects_raw = fm.get("side_effects") or []          # P1: Action Type
                            perm_config = fm.get("permissions") or None              # P1: dict with roles_allowed
                            skill_chain = fm.get("skill_chain") or []
                            skip_conditions = fm.get("skip_when") or fm.get("skip_conditions") or []
                            triggers = fm.get("triggers") or []
                            body = parts[2].strip()
                        except Exception as e:
                            logging.debug(str(e), exc_info=True)

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
                    except Exception as e:
                        logging.debug(str(e), exc_info=True)

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
                        if execution_type:
                            cfg.metadata["execution_type"] = execution_type
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
                            cfg.effects = effects
                            cfg.metadata["effects"] = effects
                            # Re-derive idempotent: __post_init__ ran before effects were injected
                            if any(isinstance(e, dict) and not bool(e.get("idempotent", True)) for e in effects):
                                cfg.idempotent = False
                        if submission_criteria:
                            cfg.submission_criteria = submission_criteria
                            cfg.metadata["submission_criteria"] = submission_criteria
                        if side_effects_raw:
                            cfg.side_effects = side_effects_raw
                            cfg.metadata["side_effects"] = side_effects_raw
                        if perm_config:
                            cfg.permissions = perm_config
                            cfg.metadata["permissions_config"] = perm_config
                        cfg.metadata["filesystem"] = {"skill_md": skill_md}
                    self.register(skill)
                else:
                    config = SkillConfig(
                        name=name,
                        description=description,
                        effects=effects,
                        submission_criteria=submission_criteria,  # P1
                        side_effects=side_effects_raw,            # P1
                        permissions=perm_config,                 # P1
                    metadata={"category": category, "body": body, "version": version,
                              "uses_file_output": uses_file_output,
                              "execution_mode": execution_mode,
                              "protected": protected,
                              "executable": executable,
                              "permissions": permissions,
                              "input_schema": input_schema,
                              "output_schema": output_schema,
                              "skill_chain": skill_chain,
                              "skip_conditions": skip_conditions,
                              "triggers": triggers,
                              "layer_dirs": layer_dirs,
                              "filesystem": {"skill_md": skill_md}}
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
        strict = os.getenv("AIPLAT_SKILL_STRICT_VALIDATION", "true").lower() in ("1", "true", "yes")

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
        if has_write and bool(getattr(cfg, "idempotent", False)):
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

        # ── execution_type validation: handler/hybrid requires handler.py ──
        exec_type = str(meta.get("execution_type") or "").strip()
        if exec_type in ("handler", "hybrid"):
            sd = (meta.get("filesystem", {}) or {}).get("skill_dir", "")
            if not sd or not os.path.isfile(os.path.join(str(sd), "handler.py")):
                _fail(
                    f"Skill '{cfg.name}': execution_type={exec_type} declared but handler.py not found"
                )

    def register(self, skill: BaseSkill) -> None:
        """Register a skill"""
        self._pre_register_validate(skill)

        # P2-20: SkillsGuard — threat scan before registration
        try:
            from core.harness.infrastructure.gates.skills_guard import get_skills_guard
            guard = get_skills_guard()
            cfg = skill.get_config()
            skill_path = getattr(cfg, "skill_path", "") or getattr(cfg, "path", "") or ""
            if skill_path and os.path.isdir(skill_path):
                result = guard.scan_skill(cfg.name, skill_path)
                if not result.passed:
                    msg = f"SkillsGuard BLOCKED registration of '{cfg.name}': {result.blocker_count} blocker(s), {result.critical_count} critical(s)"
                    logging.getLogger("aiplat.skills").error(msg)
                    if result.blocker_count > 0:
                        raise ValueError(msg)
        except ValueError:
            raise
        except Exception:
            pass

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
            except Exception as e:
                logging.debug(str(e), exc_info=True)
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

    def get_stub(self, name: str) -> str:
        u"""Get a one-line stub for Agent prompt injection (progressive disclosure).

        Returns: '<name>: <one-line description>' — ~50 tokens per skill.
        Full body is injected only when the skill is actually called via sys_skill_call.
        """
        body = self._body_cache.get(name, "")
        if body:
            return self._body_cache.get(f"{name}_stub", "") or f"{name}: {body[:80].split(chr(10))[0]}"
        return name

    def get_all_stubs(self) -> str:
        u"""Get all skill stubs as a compressed list for Agent prompt injection.

        Returns a short string of "Available skills: name1: desc1, name2: desc2, ..."
        Limited to ~300 tokens to keep the system prompt lean.
        """
        stubs = []
        for name in sorted(self._skills.keys())[:30]:
            stub = self.get_stub(name)
            stubs.append(stub)
        return "Available skills (" + str(len(stubs)) + "): " + "; ".join(stubs)

    # ── Agentic Skill Router: search → inspect → select ─────

    def search_corpus(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        u"""Agentic search: find ALL skills (incl disabled) by keyword matching.

        Returns candidates with ref, name, description snippet, score, and
        truncated flag so Agent knows when results are cut off.
        """
        query_lower = query.lower()
        terms = [t.strip() for t in query_lower.split() if len(t.strip()) >= 2]
        if not terms:
            terms = [query_lower]

        results = []
        for name, skill in self._skills.items():
            score = 0
            matched_terms = []

            cfg = getattr(skill, "_config", None)
            meta = getattr(cfg, "metadata", None) if cfg else {}
            desc = str(cfg.description if cfg and cfg.description else meta.get("description", ""))
            triggers = meta.get("triggers", []) or meta.get("trigger_keywords", [])
            tags = meta.get("tags", [])
            body = self._body_cache.get(name, "")
            is_disabled = not self._enabled.get(name, True)

            # Name match (highest weight)
            if query_lower in name.lower():
                score += 50
                matched_terms.append(f"name:{name}")
            for t in terms:
                if t in name.lower():
                    score += 20
                    matched_terms.append(f"name:{t}")

            # Description match
            desc_lower = desc.lower()
            if query_lower in desc_lower:
                score += 30
                matched_terms.append("description:full")
            for t in terms:
                if t in desc_lower:
                    score += 8
                    matched_terms.append(f"desc:{t}")

            # Trigger/tag match
            for trigger in [str(tg).lower() for tg in triggers]:
                if query_lower in trigger or any(t in trigger for t in terms):
                    score += 15
                    matched_terms.append(f"trigger:{trigger[:30]}")
                    break
            for tag in [str(t).lower() for t in tags]:
                if any(t in tag for t in terms):
                    score += 10
                    matched_terms.append(f"tag:{tag}")
                    break

            if score > 0:
                # β coefficient: amplify silenced skills with history
                if is_disabled:
                    inspect_count = getattr(self, "_corpus_inspect_counts", {}).get(name, 0)
                    auto_enabled_before = getattr(self, "_corpus_auto_enabled", set())
                    if inspect_count > 0:
                        score += min(20, int(inspect_count * 4))
                        matched_terms.append(f"β:{inspect_count}")
                    if name in auto_enabled_before:
                        score += 10
                        matched_terms.append("β:auto")

                desc_snippet = desc[:200]
                results.append({
                    "ref": f"corpus-{name}",
                    "name": name,
                    "description_snippet": desc_snippet,
                    "score": min(100, score),
                    "matched_terms": matched_terms[:5],
                    "truncated": len(desc) > 200,
                    "disabled": is_disabled,
                })

        results.sort(key=lambda x: x["score"], reverse=True)

        # Phase 52: Embedding-based semantic reranking (best-effort)
        embed_scores = self._embedding_rerank(query, results)
        if embed_scores:
            for i, r in enumerate(results):
                if i < len(embed_scores):
                    boost = int(embed_scores[i] * 30)  # 0-30 bonus
                    r["score"] = min(100, r["score"] + boost)
                    r["matched_terms"].append(f"embed:{embed_scores[i]:.2f}")
            results.sort(key=lambda x: x["score"], reverse=True)

        total = len(results)
        limited = results[:limit]

        # Mark truncation at result-set level
        if total > limit:
            for r in limited:
                r["total_matches"] = total
                r["returned"] = len(limited)

        return limited

    def _embedding_rerank(self, query: str, results: list) -> Optional[List[float]]:
        """Phase 52: Rerank search results via embedding cosine similarity.

        Uses InfraEmbeddingAdapter (lazy init). Returns similarity scores per result.
        Returns None if embedding adapter is unavailable.
        """
        if not results:
            return None
        try:
            if self._embedding_adapter is None:
                from core.harness.utils.model_injection import create_selected_adapter
                self._embedding_adapter = create_selected_adapter(model_name="embedding")
            if self._embedding_adapter is None:
                return None
            query_vec = self._embedding_adapter.encode(query)
            if query_vec is None:
                return None
            scores = []
            for r in results:
                name = r["name"]
                if name not in self._embedding_cache:
                    desc = r.get("description_snippet", "")
                    body = self._body_cache.get(name, "")
                    text = f"{name} {desc} {body[:200]}"
                    try:
                        vec = self._embedding_adapter.encode(text)
                        self._embedding_cache[name] = vec if vec else [0]
                    except Exception:
                        self._embedding_cache[name] = [0]
                cached = self._embedding_cache.get(name, [0])
                if sum(abs(v) for v in cached) == 0:
                    scores.append(0.0)
                else:
                    dot = sum(a * b for a, b in zip(query_vec, cached))
                    na = (sum(a * a for a in query_vec) ** 0.5)
                    nb = (sum(b * b for b in cached) ** 0.5)
                    if na == 0 or nb == 0:
                        scores.append(0.0)
                    else:
                        scores.append(max(0.0, min(1.0, dot / (na * nb))))
            return scores
        except Exception:
            return None

    def inspect_corpus(self, ref: str) -> Optional[Dict[str, Any]]:
        u"""Agentic inspect: return full metadata (NOT body) for a candidate.

        Gives Agent enough detail to decide without loading the full SKILL.md.
        Tracks inspect count for β coefficient amplification.
        """
        name = ref.replace("corpus-", "", 1) if ref.startswith("corpus-") else ref
        skill = self._skills.get(name)
        if not skill:
            return None

        # Track inspect count for β bonus
        if not hasattr(self, "_corpus_inspect_counts"):
            self._corpus_inspect_counts: Dict[str, int] = {}
        self._corpus_inspect_counts[name] = self._corpus_inspect_counts.get(name, 0) + 1

        cfg = getattr(skill, "_config", None)
        meta = getattr(cfg, "metadata", None) if cfg else {}

        return {
            "ref": f"corpus-{name}",
            "name": name,
            "description": str(cfg.description if cfg and cfg.description else meta.get("description", "")),
            "triggers": meta.get("triggers", []) or meta.get("trigger_keywords", []),
            "tags": meta.get("tags", []),
            "execution_type": meta.get("execution_type", "prompt"),
            "category": meta.get("category", "general"),
            "skill_chain": meta.get("skill_chain", []),
            "disabled": not self._enabled.get(name, True),
        }

    def select_corpus(
        self, ref: str, query: str, reason: str, confidence: str = "medium"
    ) -> Dict[str, Any]:
        u"""Agentic select: record audit + return body. Enables skill if auto-threshold met.

        This is the commit point — Agent confirms "I want this skill".
        """
        name = ref.replace("corpus-", "", 1) if ref.startswith("corpus-") else ref
        skill = self._skills.get(name)
        if not skill:
            raise ValueError(f"Skill not found: {ref}")

        # Audit log
        if not hasattr(self, "_routing_audit"):
            self._routing_audit: List[Dict] = []
        self._routing_audit.append({
            "ref": ref,
            "name": name,
            "query": query,
            "reason": reason,
            "confidence": confidence,
            "timestamp": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
        })

        # Auto-enable if this skill gets selected frequently
        count = sum(1 for r in self._routing_audit if r["name"] == name)
        if count >= 3 and not self.is_enabled(name):
            self.enable(name)
            if not hasattr(self, "_corpus_auto_enabled"):
                self._corpus_auto_enabled = set()
            self._corpus_auto_enabled.add(name)
            __import__("logging").getLogger(__name__).info(
                "Auto-enabled '%s' after %d routed selections", name, count,
            )

        # Return body
        body = self._body_cache.get(name, "")
        return {
            "name": name,
            "body": body,
            "audited": True,
            "enabled_after": self.is_enabled(name),
        }

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
        except Exception as e:
            logging.debug(str(e), exc_info=True)
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
                    except Exception as e:
                        logging.debug(str(e), exc_info=True)
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
                except Exception as e:
                    logging.debug(str(e), exc_info=True)

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
                                except Exception as e:
                                    logging.debug(str(e), exc_info=True)

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
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
            self._skills[name] = skill
            # Cache SKILL.md body content if available (lives in config.metadata["body"]).
            md = getattr(target.config, "metadata", None)
            body = ((md.get("body") if isinstance(md, dict) else None) or "").strip()
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

    def apply_convergence(self, skill_name: str, delta: float,
                          *, damping: float = 0.3) -> Dict[str, Any]:
        stats = self._binding_stats.get(skill_name)
        if not stats:
            return {"skill": skill_name, "error": "not_found"}
        old_rate = stats.recent_pass_rate
        effective = stats.adjust_weight(delta, damping=damping)
        return {
            "skill": skill_name,
            "old_pass_rate": round(old_rate, 4),
            "new_pass_rate": round(stats.recent_pass_rate, 4),
            "effective_delta": effective,
        }

    def filter_by_role(self, role_name: str) -> List[str]:
        """Return enabled skill names matching a digital employee role."""
        try:
            from core.harness.knowledge.ontology_bus import load_role_skills
            return [s for s in load_role_skills(role_name) if s in self._skills]
        except Exception:
            return []

    def get_bound_agents(self, name: str) -> List[str]:
        """Get agents bound to a skill"""
        stats = self._binding_stats.get(name)
        return stats.bound_agents if stats else []

    def record_execution(self, name: str, success: bool, latency: float = 0.0) -> None:
        """Record a skill execution with sliding window for decay detection."""
        with self._lock:
            if name in self._binding_stats:
                stats = self._binding_stats[name]
                stats.total_executions += 1
                import time as _time_re
                stats.last_executed_at = int(_time_re.time())
                if success:
                    stats.success_count += 1
                else:
                    stats.error_count += 1
                # Sliding window: keep last 20 results for recent_pass_rate
                if hasattr(stats.recent_results, 'append'):
                    stats.recent_results.append(success)
                    if stats.recent_pass_rate < 0.5:
                        try:
                            from core.harness.memory.metrics import inc_skill_downgraded
                            inc_skill_downgraded(name)
                        except Exception as e:
                            logging.debug(str(e), exc_info=True)
                    if stats.recent_pass_rate < 0.2:
                        try:
                            from core.harness.memory.metrics import inc_skill_alert
                            inc_skill_alert(name)
                        except Exception as e:
                            logging.debug(str(e), exc_info=True)
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
                "recent_pass_rate": round(stats.recent_pass_rate, 3) if stats else 1.0,
                "is_decayed": stats.is_decayed if stats else False,
                "avg_latency": round(stats.avg_latency, 3) if stats else 0.0,
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


_TERM_DEFINITIONS = {
    "文本相似": "基于NLP技术比较文本内容相似程度的方法，常用于文档对比、抄袭检测、语义匹配",
    "相似度": "两个对象在特定维度上的相似程度度量指标",
    "关联图谱": "通过实体间关系构建的可视化知识网络，用于发现隐藏的业务关联",
    "知识图谱": "以图结构组织实体、属性和关系的知识表示方法，支持语义推理",
    "异常检测": "通过统计模型或机器学习识别数据中偏离正常模式的异常行为",
    "风险预警": "基于预设阈值和历史数据，在风险事件发生前自动发出警报",
    "流程自动化": "使用软件机器人自动执行重复性业务操作，减少人工干预",
    "合规审查": "根据法律法规和行业标准对业务流程进行合规性检查",
    "预测分析": "基于历史数据和统计模型预测未来趋势和结果的分析方法",
    "数据标准化": "将不同来源的数据转换为统一格式和规范的过程",
}


def _generate_term_definition(concept: str) -> str:
    for keyword, definition in _TERM_DEFINITIONS.items():
        if keyword in concept.lower():
            return definition
    return ""


def _compute_readiness(params: dict) -> tuple:
    """Compute FDE readiness score (0-100) based on form completeness.
    
    Two-tier threshold:
      ≥ 40: core ready — can generate initial diagnosis
      ≥ 80: fully ready — can generate complete delivery manual
    """
    score = 0
    gaps = []
    # ── Core fields (required for diagnosis) ──
    if params.get('company_name'): score += 15
    else: gaps.append('公司名称')
    if params.get('industry'): score += 15
    else: gaps.append('行业')
    if params.get('pain_points'): score += 25
    else: gaps.append('痛点')
    # ── Supplementary fields (enhance delivery manual quality) ──
    if params.get('team_size'): score += 5
    else: gaps.append('团队规模')
    if params.get('existing_tech_stack') or params.get('tech_stack'): score += 5
    else: gaps.append('现有技术栈')
    if params.get('budget'): score += 5
    else: gaps.append('预算范围')
    if params.get('internal_data_sources') or params.get('external_data_sources') or params.get('data_sources'): score += 5
    else: gaps.append('数据源')
    if params.get('compliance_requirements'): score += 5
    else: gaps.append('合规要求')
    if params.get('poc_timeline') or params.get('production_timeline') or params.get('timeline'): score += 5
    else: gaps.append('时间线')
    return min(score + 15, 100), gaps


def _dedup_table_rows(text: str) -> str:
    """Deduplicate rows in markdown tables."""
    import re
    lines = text.split('\n')
    seen = set()
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('|') and not stripped.startswith('| :---'):
            if stripped in seen:
                continue
            seen.add(stripped)
        result.append(line)
    return '\n'.join(result)


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


async def _bg_curator_scan(interval_hours: int = 6):
    u"""Background curator: periodically scan workspace for new/updated SKILL.md files.

    Runs every N hours, scanning ~/.aiplat/skills/ for changes.
    """
    import asyncio, os as _os

    while True:
        await asyncio.sleep(interval_hours * 3600)
        try:
            workspace = _os.path.expanduser(_os.getenv("AIPLAT_WORKSPACE_SKILLS", "~/.aiplat/skills"))
            _global_registry.scan_folder(workspace)
        except Exception as e:
            logging.debug(str(e), exc_info=True)


def start_bg_curator(interval_hours: int = 6):
    u"""Start the background curator task. Safe to call multiple times."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_bg_curator_scan(interval_hours))
    except RuntimeError:
        pass  # no event loop yet — will start when loop starts


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
        # ── Resolve execution_type FIRST (handler-type skills don't need an LLM) ──
        meta = (self._config.metadata or {})
        exec_type = meta.get("execution_type", "")
        if not exec_type:
            # Auto-detect: check for handler.py + SOP complexity
            handler_exists = False
            skill_dir = ""
            fs_check = meta.get("filesystem", {}) or {}
            sd = fs_check.get("skill_dir", "")
            if sd:
                skill_dir = str(sd)
                if os.path.isfile(os.path.join(sd, "handler.py")):
                    handler_exists = True

            _log = __import__('logging').getLogger(__name__)
            if handler_exists:
                sop = meta.get("sop_markdown", "") or self._config.description or ""
                sop_lower = sop.lower()
                complex_kw = ("step 1", "plan", "search", "query", "retriev",
                             "synthesi", "multi-source", "multi_step", "cross_platform",
                             "judge agent", "子任务", "步骤1", "规划")
                is_complex = any(k in sop_lower for k in complex_kw) or sop.count("\n##") >= 3
                exec_type = "hybrid" if is_complex else "handler"
                _log.info(
                    "Skill '%s': auto-detected execution_type='%s' (handler=%s sop_complex=%s). "
                    "Add explicit execution_type to SKILL.md to suppress this.",
                    self._config.name, exec_type, handler_exists, is_complex
                )
            else:
                exec_type = "prompt"
                _log.info(
                    "Skill '%s': no handler.py, auto-detected execution_type='prompt' (LLM simulation).",
                    self._config.name
                )
            meta["execution_type"] = exec_type  # cache for subsequent calls

        # Require model for non-handler execution types (handler uses real code, no LLM needed)
        if exec_type != "handler" and not self._model:
            return SkillResult(
                success=False,
                error=f"No LLM adapter configured for skill '{self._config.name}'"
            )

        # Warn if prompt mode but handler.py exists (likely misconfiguration)
        if exec_type == "prompt":
            fs_check = meta.get("filesystem", {}) or {}
            sd = fs_check.get("skill_dir", "")
            if sd:
                hp = os.path.join(str(sd), "handler.py")
                if os.path.isfile(hp):
                    _log2 = __import__('logging').getLogger(__name__)
                    _log2.warning(
                        "Skill '%s' has execution_type='prompt' but handler.py exists. "
                        "Consider changing to execution_type: handler for real execution.",
                        self._config.name
                    )
        if exec_type == "handler":
            handler_path = meta.get("handler_path")
            if not handler_path:
                fs = meta.get("filesystem", {}) or {}
                skill_dir = fs.get("skill_dir", "")
                if skill_dir:
                    hp = os.path.join(str(skill_dir), "handler.py")
                    if os.path.isfile(hp):
                        handler_path = hp
            if handler_path and os.path.isfile(str(handler_path)):
                try:
                    import importlib.util as _iu
                    spec = _iu.spec_from_file_location(f"skill_handler_{self._config.name}", str(handler_path))
                    if spec and spec.loader:
                        hmod = _iu.module_from_spec(spec)
                        spec.loader.exec_module(hmod)
                        if hasattr(hmod, "execute") and callable(hmod.execute):
                            result = hmod.execute(params)
                            import asyncio
                            if asyncio.iscoroutine(result):
                                result = await result
                            if isinstance(result, dict):
                                return SkillResult(
                                    success=not result.get("error"),
                                    output=result,
                                    error=result.get("error"),
                                    metadata={"skill": self._config.name, "handler_executed": True},
                                )
                except Exception as e:
                    return SkillResult(success=False, error=str(e), metadata={"skill": self._config.name, "handler_failed": True})
            else:
                # exec_type=handler but no valid handler.py → fail explicitly
                return SkillResult(
                    success=False,
                    error=f"Handler execution declared but handler.py not found or invalid for skill '{self._config.name}'. "
                          f"Add a valid handler.py or change execution_type to 'prompt'.",
                    metadata={"skill": self._config.name, "expected_handler": True},
                )

        # ── Hybrid execution: LLM planning + handler real execution ──
        if exec_type == "hybrid":
            # Resolve handler path (same logic as handler mode)
            handler_path = meta.get("handler_path")
            if not handler_path:
                fs = meta.get("filesystem", {}) or {}
                skill_dir = fs.get("skill_dir", "")
                if skill_dir:
                    hp = os.path.join(str(skill_dir), "handler.py")
                    if os.path.isfile(hp):
                        handler_path = hp
            if not handler_path or not os.path.isfile(str(handler_path)):
                return SkillResult(
                    success=False,
                    error=f"Hybrid execution declared but handler.py not found for skill '{self._config.name}'.",
                    metadata={"skill": self._config.name, "expected_handler": True},
                )

            # Step 1: LLM generates execution plan from SOP + user input
            sop = ""
            try:
                sop = meta.get("sop_markdown", "")
            except Exception:
                sop = ""
            user_input = params.get("prompt", params.get("input", ""))
            if not user_input:
                user_input = f"Execute skill '{self._config.name}': {self._config.description}\nInput(JSON): {params}"

            # Use SOP as system prompt — it already contains full instructions 
            # including --plan format, just like Claude Code reads it.
            plan_system_prompt = sop or self._config.description
            _log = __import__('logging').getLogger(__name__)
            _log.warning("Hybrid mode: LLM planning for skill '%s'", self._config.name)
            try:
                from ...harness.syscalls.llm import sys_llm_generate
                plan_response = await sys_llm_generate(
                    self._model,
                    [
                        {"role": "system", "content": plan_system_prompt},
                        {"role": "user", "content": f"Task: {user_input}"},
                    ],
                )
                plan_text = getattr(plan_response, "content", "") or ""
                from core.utils.json_utils import parse_json
                plan = parse_json(plan_text)
                if not isinstance(plan, dict):
                    plan = {}
                _log.warning(
                    "Hybrid LLM plan for skill '%s': args=%s plan_text_preview=%s",
                    self._config.name,
                    plan.get("args") or plan.get("arguments") or "(empty)",
                    (plan_text or "")[:300]
                )
            except Exception as e:
                return SkillResult(success=False, error=f"LLM planning failed: {e}", metadata={"skill": self._config.name})

            # Step 2: Call handler with the LLM-generated plan
            try:
                import importlib.util as _iu
                spec = _iu.spec_from_file_location(f"skill_handler_{self._config.name}", str(handler_path))
                if spec and spec.loader:
                    hmod = _iu.module_from_spec(spec)
                    spec.loader.exec_module(hmod)
                    if hasattr(hmod, "execute") and callable(hmod.execute):
                        # Merge plan args into params for handler
                        handler_params = dict(params or {})
                        handler_params["_plan"] = plan
                        handler_params["_plan_args"] = plan.get("args") or plan.get("arguments") or []
                        result = hmod.execute(handler_params)
                        import asyncio
                        if asyncio.iscoroutine(result):
                            result = await result
                        if isinstance(result, dict):
                            return SkillResult(
                                success=not result.get("error"),
                                output=result,
                                error=result.get("error"),
                                metadata={"skill": self._config.name, "handler_executed": True, "llm_planned": True},
                            )
                return SkillResult(success=False, error="Handler execution failed", metadata={"skill": self._config.name})
            except Exception as e:
                return SkillResult(success=False, error=str(e), metadata={"skill": self._config.name, "handler_failed": True})

        # Canonical JSON extraction via CoreFacade (replaces local _extract_json).
        from core.utils.json_utils import parse_json

        prompt = params.get("prompt", params.get("input", ""))
        if not prompt:
            prompt = str(self._config.description) + "\nInput: " + str(params) if params else ""

        # Organization-level coding policy profile (Phase-1).
        coding_profile = str((params or {}).get("_coding_policy_profile") or "karpathy_v1").strip().lower()
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

            if not allowed_tools:
                try:
                    from core.harness.kernel.execution_context import get_active_workspace_context
                    from core.harness.tools.toolsets import resolve_toolset
                    ws = get_active_workspace_context()
                    active_toolset = getattr(ws, 'toolset', None) if ws else None
                    if active_toolset:
                        policy = resolve_toolset(str(active_toolset))
                        allowed_tools = list(policy.allow)
                except Exception as e:
                    logging.debug(str(e), exc_info=True)

            from core.harness.utils.prompt_loader import _sync_resolve

            # Check output_schema BEFORE building system prompt — JSON output
            # instruction MUST come first to override any formatting rules in SOP
            out_schema = {}
            try:
                out_schema = self._config.output_schema or {}
            except Exception:
                out_schema = {}
            out_keys = list(out_schema.keys()) if isinstance(out_schema, dict) and out_schema else []

            system_parts = []
            if out_keys and not allowed_tools:
                system_parts.append(
                    _sync_resolve("skill-executor-json-override", keys=str(out_keys))
                )
            system_parts.append(
                _sync_resolve("skill-executor-inline",
                    sop=(sop if sop else f"Skill: {self._config.name}\n{self._config.description}"),
                ),
            )
            if policy_block:
                system_parts.append(policy_block)

            # If tools are available, run as a tool-capable ReAct agent (SkillTool-like orchestration).
            if allowed_tools:
                from ...apps.agents.react import create_react_agent, ReActAgentConfig
                from ...harness.interfaces import AgentConfig, AgentContext

                max_steps = int((self._config.config or {}).get("max_steps", 50))
                agent = create_react_agent(
                    config=AgentConfig(
                        name=f"skill-inline-{self._config.name}",
                        model=str(getattr(self._model, "model", None) or ""),
                        metadata={"role": "skill-agent", "skill": self._config.name},
                    ),
                    model=self._model,
                    loop_config=ReActAgentConfig(max_steps=max_steps),
                )

                task = "\n".join(system_parts) + "\n\n用户输入：\n" + prompt
                msgs = [{"role": "system", "content": "\n".join(system_parts)}, {"role": "user", "content": prompt}]
                agent_ctx = AgentContext(
                    session_id=getattr(context, "session_id", "skill"),
                    user_id=getattr(context, "user_id", "system"),
                    messages=[{"role": "user", "content": task}],
                    variables={"messages": msgs,
                               **(getattr(context, "variables", {}) or {}),
                               "_run_id": getattr(context, "session_id", ""),
                    },
                    tools=allowed_tools,
                )
                result = await agent.execute(agent_ctx)
                # Log stop reason for debugging skill execution limits
                try:
                    import logging
                    _log = logging.getLogger("aiplat.skills")
                    sr = getattr(result, "metadata", {}) or {}
                    sr = sr.get("stop_reason", "unknown") if isinstance(sr, dict) else "unknown"
                    sc = getattr(result, "metadata", {}) or {}
                    sc = sc.get("steps", 0) if isinstance(sc, dict) else 0
                    _log.info("skill=%s stop_reason=%s steps=%s max_steps=%s",
                               self._config.name, sr, sc, max_steps)
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
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
                        success=True,
                        output={out_keys[0]: str(result.output)} if out_keys else {"text": result.output},
                        metadata={"skill": self._config.name, "agent": result.metadata, "tools": allowed_tools, "parsed_json": False},
                    )
                return SkillResult(success=bool(result.success), output={"text": result.output}, error=result.error, metadata={"skill": self._config.name, "agent": result.metadata, "tools": allowed_tools})

            # Fallback: plain LLM generation (no tools)
            from ...harness.syscalls.llm import sys_llm_generate

            run_id = ((getattr(context, "variables", {}) or {}).get("_run_id")
                      or getattr(context, "session_id", ""))
            parent_span_id = (getattr(context, "metadata", {}) or {}).get("_span_id")

            # ContextBus: inject 10-layer domain knowledge for field-assessment
            if self._config.name == "field-assessment":
                try:
                    from core.harness.knowledge.context_bus import assemble_field_assessment
                    system_parts, diag = assemble_field_assessment(params, system_parts)
                    failed = [k for k, v in diag.items() if v != "ok" and not k.startswith("_")]
                    if failed:
                        __import__("logging").getLogger(__name__).warning(
                            "ContextBus layers degraded: %s", ", ".join(f"{k}={v}" for k, v in diag.items() if v != "ok")
                        )
                except Exception:
                    pass

            response = await sys_llm_generate(
                self._model,
                [
                    {"role": "system", "content": "\n".join(system_parts)},
                    {"role": "user", "content": prompt},
                ],
                trace_context={"run_id": run_id, "parent_span_id": parent_span_id},
            )
            # ── Post-generation: field-assessment metadata extraction ──
            if self._config.name == "field-assessment":
                import time as _time_sid
                company = (params.get("company_name") or "").strip()
                ts = int(_time_sid.time())
                sid = f"session_{company}_{ts}" if company else f"session_diag_{ts}"
                meta = {"model": getattr(response, "model", None), "skill": self._config.name, "session_id": sid}
                report_text = str(getattr(response, "content", "") or "")

                # ── SessionMeta persistence (independent of report processing) ──
                sid = meta.get("session_id", "")
                if sid and report_text:
                    try:
                        import json as _json_sm
                        from core.harness.ontology_engine.graph_index import GraphIndex
                        fd_g = GraphIndex.load("fde-delivery")
                        fd_g.add_entity(sid, _json_sm.dumps(
                            {"report_text": report_text[:8000],
                             "readiness_score": 0, "industry": params.get("industry", ""),
                             "pain_points": (params.get("pain_points") or "")[:200]},
                            ensure_ascii=False)[:8000], "SessionMeta")
                    except Exception as e:
                        import logging as _log_sm
                        _log_sm.warning(f"SessionMeta persist failed: {e}")
                if report_text:
                    try:
                        import re as _re_pg, json as _json_pg, os as _os_pg
                        from core.harness.knowledge.domain_router import DomainRouter
                        from core.harness.ontology_engine.graph_index import GraphIndex

                        did = DomainRouter().classify(
                            (params.get("industry") or params.get("company_name") or "").strip()
                        ) if (params.get("industry") or params.get("company_name")) else ""

                        # C0: evidence_map extraction
                        rows = _re_pg.findall(
                            r'^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(?:本体实例|历史案例|LLM推测)\s*\|',
                            report_text, _re_pg.MULTILINE
                        )
                        evidence_map = []
                        for i, r in enumerate(rows):
                            if len(r) >= 5:
                                evidence_map.append({
                                    "index": i, "pain_point": r[0].strip(),
                                    "ai_opportunity": r[1].strip(), "confidence": r[2].strip(),
                                    "dependency": r[3].strip(), "source": r[4].strip(),
                                })
                        if evidence_map:
                            meta["evidence_map"] = evidence_map

                        # G: knowledge_gaps + S: term auto-seeding
                        opps = _re_pg.findall(r'\|\s*[^|]+\|\s*([^|]+)\|\s*[^|]+\|\s*[^|]+\|\s*[^|]+', report_text)
                        gaps = []
                        if did:
                            known_labels = set()
                            onto_path = _os_pg.path.expanduser(f"~/.aiplat/ontologies/{did}.yaml")
                            if _os_pg.path.exists(onto_path):
                                from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
                                dom = load_ontology_from_yaml(onto_path)
                                for cls in dom.classes:
                                    known_labels.add(cls.label.lower())
                            for opp in opps:
                                name = opp.strip()[:100]
                                if not name or len(name) < 6:
                                    continue
                                matched = any(kl in name.lower() for kl in known_labels if len(kl) > 2)
                                if not matched:
                                    gaps.append({"concept": name, "domain": did})
                            if gaps:
                                meta["knowledge_gaps"] = gaps
                                # S: term auto-seeding
                                try:
                                    tg = GraphIndex.load("enterprise-terms")
                                    for gap in gaps[:5]:
                                        name = gap["concept"][:100]
                                        tid = f"term_{did}_{gap['concept'].replace(' ', '_')[:60]}"

                                        # Cross-domain dedup: check for existing similar term
                                        existing_id = None
                                        for eid, enode in list(tg._nodes.items()):
                                            if getattr(enode, "class_name", "") == "Term":
                                                e_name = enode.entity_name.lower()
                                                if name.lower() in e_name or e_name in name.lower():
                                                    existing_id = eid
                                                    break

                                        tg.add_entity(tid, name, "Term", source_doc_id=params.get("_run_id", ""))

                                        # Link to existing term across domains
                                        if existing_id and existing_id != tid:
                                            tg.add_relation(tid, existing_id, "similar_to",
                                                           relation_label="跨域同名概念", confidence=0.85)

                                        definition = _generate_term_definition(name)
                                        if definition:
                                            def_id = f"def_{tid}"
                                            tg.add_entity(def_id, definition[:500], "Term", source_doc_id=tid)
                                            tg.add_relation(tid, def_id, "derived_from", relation_label="定义", confidence=0.7)
                                except Exception:
                                    pass

                        # O: Evidence entity binding
                        if sid and evidence_map:
                            try:
                                fd_g = GraphIndex.load("fde-delivery")
                                for ei, ev in enumerate(evidence_map):
                                    ev_id = f"evidence_{sid}_{ei}"
                                    ev_name = f"{ev.get('ai_opportunity', '')[:60]} | {ev.get('source', '')[:40]}"
                                    fd_g.add_entity(ev_id, ev_name, "Evidence", source_doc_id=sid)
                            except Exception:
                                pass
                    except Exception:
                        pass

                return SkillResult(success=True, output={"text": report_text}, metadata=meta)

            if isinstance(out_schema, dict) and out_schema:
                parsed = parse_json(str(getattr(response, "content", "") or ""))
                if isinstance(parsed, dict):
                    return SkillResult(success=True, output=parsed, metadata={"model": getattr(response, "model", None), "skill": self._config.name, "parsed_json": True})
                return SkillResult(
                    success=True,
                    output={out_keys[0]: str(getattr(response, "content", ""))} if out_keys else {"text": getattr(response, "content", None)},
                    metadata={"model": getattr(response, "model", None), "skill": self._config.name, "parsed_json": False},
                )
            return SkillResult(success=True, output={"text": response.content}, metadata={"model": response.model, "skill": self._config.name})
        except Exception as e:
            return SkillResult(success=False, error=str(e))

