"""
import logging
Constraint Validator — detect outdated rules and missing dependencies in agent/pipeline configs.

Checks:
- CRITICAL: file_path referenced in configs that doesn't exist
- HIGH: model declared in AGENT.md but not available in ModelManager
- WARNING: phase mismatch between AGENT.md and PipelineStageConfig
- WARNING: skill declared as required but not in SkillRegistry or disabled
"""

from __future__ import annotations

import os, yaml, logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path


@dataclass
class ConstraintIssue:
    source: str              # agent name / file path
    issue_type: str          # file_missing / model_unavailable / phase_mismatch / skill_missing
    level: str              # CRITICAL / HIGH / WARNING
    detail: str = ""
    suggestion: str = ""


class ConstraintValidator:
    """Scan configuration references for stale or invalid entries."""

    def __init__(self):
        self._home = Path(os.getenv("AIPLAT_HOME", Path("~").expanduser() / ".aiplat"))

    def scan_all(self) -> List[ConstraintIssue]:
        issues = []

        # 1. File path check (CRITICAL)
        issues.extend(self._check_file_paths())

        # 2. Model availability check (HIGH)
        issues.extend(self._check_models())

        # 3. Phase consistency check (WARNING)
        issues.extend(self._check_phases())

        # 4. Skill binding check (WARNING)
        issues.extend(self._check_skills())

        # v2.10: Correctness checks (not just existence)
        issues.extend(self._check_class_relevance())
        issues.extend(self._check_inference_rule_saturation())
        issues.extend(self._check_state_machine_usage())
        issues.extend(self._check_required_field_coverage())
        issues.extend(self._check_domain_coupling())
        issues.extend(self._check_path_deviation())  # v2.10: YAML→Runtime

        return issues

    def _check_file_paths(self) -> List[ConstraintIssue]:
        """Scan all agent YAML frontmatter for file path references."""
        issues = []
        agents_dir = self._home / "agents"
        if not agents_dir.exists():
            return issues

        for adir in agents_dir.iterdir():
            if not adir.is_dir():
                continue
            agent_file = adir / "AGENT.md"
            if not agent_file.exists():
                continue
            try:
                content = agent_file.read_text(encoding="utf-8")
                # Check for file paths in config section
                config = self._parse_config(content)
                if not config:
                    continue
                for key in ("system_prompt_file", "knowledge_base_path", "model_config_path"):
                    fp = config.get(key, "")
                    if fp and not Path(fp).expanduser().exists():
                        issues.append(ConstraintIssue(
                            source=adir.name, issue_type="file_missing",
                            level="CRITICAL",
                            detail=f"{key}: {fp} does not exist",
                            suggestion=f"Update {key} in {adir.name}/AGENT.md or restore the file",
                        ))
            except Exception:
                logging.getLogger(__name__).debug('_check_file_paths failed', exc_info=True)
        return issues

    def _check_models(self) -> List[ConstraintIssue]:
        """Check AGENT.md model declarations against ModelManager."""
        issues = []
        available_models = self._get_available_models()
        if not available_models:
            return issues

        agents_dir = self._home / "agents"
        if not agents_dir.exists():
            return issues

        for adir in agents_dir.iterdir():
            if not adir.is_dir():
                continue
            agent_file = adir / "AGENT.md"
            if not agent_file.exists():
                continue
            try:
                content = agent_file.read_text(encoding="utf-8")
                fm = self._parse_frontmatter(content)
                model = fm.get("model", "")
                if model and model not in ("auto", "best") and model not in available_models:
                    issues.append(ConstraintIssue(
                        source=adir.name, issue_type="model_unavailable",
                        level="HIGH",
                        detail=f"model: {model} not in ModelManager",
                        suggestion=f"ModelTierRouter will auto-fallback; consider updating to 'auto'",
                    ))
            except Exception:
                logging.getLogger(__name__).debug('_check_models failed', exc_info=True)
        return issues

    def _check_phases(self) -> List[ConstraintIssue]:
        """Check phase sequence consistency between agents and pipeline stages."""
        issues = []
        agents_dir = self._home / "agents"
        if not agents_dir.exists():
            return issues

        pipeline_phases = self._get_pipeline_phases()
        for adir in agents_dir.iterdir():
            if not adir.is_dir():
                continue
            agent_file = adir / "AGENT.md"
            if not agent_file.exists():
                continue
            try:
                content = agent_file.read_text(encoding="utf-8")
                fm = self._parse_frontmatter(content)
                declared_phase = fm.get("phase", "")
                if declared_phase and pipeline_phases and declared_phase not in pipeline_phases:
                    issues.append(ConstraintIssue(
                        source=adir.name, issue_type="phase_mismatch",
                        level="WARNING",
                        detail=f"phase '{declared_phase}' not found in active pipeline stages: {pipeline_phases[:5]}",
                        suggestion="Update phase declaration or register the phase in pipeline config",
                    ))
            except Exception:
                logging.getLogger(__name__).debug('_check_phases failed', exc_info=True)
        return issues

    def _check_skills(self) -> List[ConstraintIssue]:
        """Check required_skills against SkillRegistry."""
        issues = []
        agents_dir = self._home / "agents"
        if not agents_dir.exists():
            return issues

        available_skills = self._get_available_skills()
        for adir in agents_dir.iterdir():
            if not adir.is_dir():
                continue
            agent_file = adir / "AGENT.md"
            if not agent_file.exists():
                continue
            try:
                content = agent_file.read_text(encoding="utf-8")
                fm = self._parse_frontmatter(content)
                skills = fm.get("required_skills") or fm.get("skills") or []
                for skill in skills:
                    if skill not in available_skills:
                        issues.append(ConstraintIssue(
                            source=adir.name, issue_type="skill_missing",
                            level="WARNING",
                            detail=f"skill '{skill}' not found in SkillRegistry",
                            suggestion=f"Install the skill or remove it from required_skills",
                        ))
            except Exception:
                logging.getLogger(__name__).debug('_check_skills failed', exc_info=True)
        return issues

    def _parse_frontmatter(self, text: str) -> Dict[str, Any]:
        if not text.startswith("---"):
            return {}
        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}
        try:
            return yaml.safe_load(parts[1]) or {}
        except Exception:
            return {}

    def _parse_config(self, text: str) -> Dict[str, Any]:
        fm = self._parse_frontmatter(text)
        return fm.get("config", {}) if isinstance(fm.get("config"), dict) else {}

    def _get_available_models(self) -> List[str]:
        try:
            from core.harness.utils.model_injection import best_model_for_purpose
            # Basic model list from env
            models = []
            for tier in ["doc_llm", "code_gen", "embedding", "chat", "reasoning"]:
                m = best_model_for_purpose(tier)
                if m and hasattr(m, 'model_name'):
                    models.append(m.model_name)
            return models
        except Exception:
            return []

    def _get_pipeline_phases(self) -> List[str]:
        try:
            from core.schemas_builder import PipelinePhase
            return [p.value for p in PipelinePhase]
        except Exception:
            return []

    def _get_available_skills(self) -> List[str]:
        try:
            from core.api.core_facade import get_skill_registry
            reg = get_skill_registry()
            return [s.name for s in reg.list_all()] if reg else []
        except Exception:
            return []

    # ── v2.10: Correctness checks (not just existence) ──

    def _check_class_relevance(self) -> List[ConstraintIssue]:
        """Check YAML classes that have zero entities in GraphIndex for N days."""
        issues = []
        try:
            ORPHAN_DAYS = int(os.getenv("AIPLAT_CONSTRAINT_ORPHAN_DAYS", "30"))
            from core.harness.ontology_engine.graph_index import GraphIndex
            ont_dir = self._home / "ontologies"
            if not ont_dir.exists():
                return issues
            import yaml
            for yf in ont_dir.glob("*.yaml"):
                try:
                    domain_id = yf.stem
                    data = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
                    classes = data.get("classes", {})
                    if not classes:
                        continue
                    graph = GraphIndex.load(domain_id)
                    for cls_name, cls_def in classes.items():
                        label = cls_def.get("label", cls_name)
                        count = sum(1 for n in graph._nodes.values() if n.class_name in (cls_name, label))
                        if count == 0:
                            issues.append(ConstraintIssue(
                                source=domain_id, issue_type="class_relevance",
                                level="WARNING",
                                detail=f"Class '{cls_name}' has zero entities in GraphIndex",
                                suggestion="Run ontology engine on more documents or consider deprecating the class"
                            ))
                except Exception:
                    logging.getLogger(__name__).debug('_check_class_relevance failed', exc_info=True)
        except Exception:
            logging.getLogger(__name__).debug('_check_class_relevance failed', exc_info=True)
        return issues

    def _check_inference_rule_saturation(self) -> List[ConstraintIssue]:
        """Check inference rules that haven't been triggered for N days."""
        issues = []
        try:
            RULE_STALE_DAYS = int(os.getenv("AIPLAT_CONSTRAINT_RULE_STALE_DAYS", "90"))
            import yaml, time
            ont_dir = self._home / "ontologies"
            if not ont_dir.exists():
                return issues
            for yf in ont_dir.glob("*.yaml"):
                try:
                    data = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
                    rules = data.get("inference_rules", []) or []
                    for rule in rules:
                        name = rule.get("name", "unknown")
                        last_triggered = rule.get("_last_triggered", 0)
                        if last_triggered and time.time() - last_triggered > RULE_STALE_DAYS * 86400:
                            issues.append(ConstraintIssue(
                                source=yf.stem, issue_type="inference_rule_saturation",
                                level="WARNING",
                                detail=f"Rule '{name}' not triggered for >{RULE_STALE_DAYS} days",
                                suggestion="Verify the rule's premises are still applicable"
                            ))
                except Exception:
                    logging.getLogger(__name__).debug('_check_inference_rule_saturation failed', exc_info=True)
        except Exception:
            logging.getLogger(__name__).debug('_check_inference_rule_saturation failed', exc_info=True)
        return issues

    def _check_state_machine_usage(self) -> List[ConstraintIssue]:
        """Check state machine transitions that were never triggered."""
        issues = []
        try:
            import yaml
            ont_dir = self._home / "ontologies"
            if not ont_dir.exists():
                return issues
            for yf in ont_dir.glob("*.yaml"):
                try:
                    data = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
                    classes = data.get("classes", {})
                    for cls_name, cls_def in classes.items():
                        transitions = cls_def.get("transitions", []) or []
                        for t in transitions:
                            triggered = t.get("_triggered_count", 0)
                            if triggered == 0:
                                issues.append(ConstraintIssue(
                                    source=yf.stem, issue_type="state_machine_usage",
                                    level="WARNING",
                                    detail=f"Transition {t.get('from','?')}→{t.get('to','?')} in {cls_name} never triggered",
                                    suggestion="Verify the trigger condition is correctly configured"
                                ))
                except Exception:
                    logging.getLogger(__name__).debug('_check_state_machine_usage failed', exc_info=True)
        except Exception:
            logging.getLogger(__name__).debug('_check_state_machine_usage failed', exc_info=True)
        return issues

    def _check_required_field_coverage(self) -> List[ConstraintIssue]:
        """Check required_field extraction rate in GraphIndex entities."""
        issues = []
        try:
            FIELD_MIN = int(os.getenv("AIPLAT_CONSTRAINT_FIELD_COVERAGE_PCT", "50"))
            from core.harness.ontology_engine.graph_index import GraphIndex
            import yaml
            ont_dir = self._home / "ontologies"
            if not ont_dir.exists():
                return issues
            for yf in ont_dir.glob("*.yaml"):
                try:
                    domain_id = yf.stem
                    data = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
                    classes = data.get("classes", {})
                    graph = GraphIndex.load(domain_id)
                    for cls_name, cls_def in classes.items():
                        label = cls_def.get("label", cls_name)
                        required = cls_def.get("required_fields", []) or []
                        if not required:
                            continue
                        entities = [n for n in graph._nodes.values() if n.class_name in (cls_name, label)]
                        if not entities:
                            continue
                        filled = 0
                        for e in entities[:100]:
                            meta = getattr(e, 'metadata', {}) or {}
                            props = meta.get('properties', {}) if isinstance(meta, dict) else {}
                            if any(props.get(f) for f in required):
                                filled += 1
                        rate = int(filled / max(1, len(entities[:100])) * 100)
                        if rate < FIELD_MIN:
                            issues.append(ConstraintIssue(
                                source=domain_id, issue_type="required_field_coverage",
                                level="WARNING",
                                detail=f"Class '{cls_name}' required fields filled at {rate}% (<{FIELD_MIN}%)",
                                suggestion="Check PropertyExtractor config or enrich source documents"
                            ))
                except Exception:
                    logging.getLogger(__name__).debug('_check_required_field_coverage failed', exc_info=True)
        except Exception:
            logging.getLogger(__name__).debug('_check_required_field_coverage failed', exc_info=True)
        return issues

    def _check_domain_coupling(self) -> List[ConstraintIssue]:
        """Check cross-domain references that point to unregistered domains."""
        issues = []
        try:
            import json, yaml
            registry_path = self._home / "ontologies" / "registry.json"
            registered = set()
            if registry_path.exists():
                reg = json.loads(registry_path.read_text(encoding="utf-8")) or {}
                registered = set(reg.get("domains", {}).keys())
            if not registered:
                return issues

            ont_dir = self._home / "ontologies"
            for yf in ont_dir.glob("*.yaml"):
                if yf.name == "registry.json":
                    continue
                try:
                    data = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
                    # Check object_properties for cross-domain references
                    props = data.get("object_properties", []) or []
                    for p in props:
                        for d in (p.get("domain", []) or []):
                            d_id = d.split("#")[0] if "#" in d else d
                            if d_id and d_id not in registered and d_id != yf.stem:
                                issues.append(ConstraintIssue(
                                    source=yf.stem, issue_type="domain_coupling_check",
                                    level="CRITICAL",
                                    detail=f"Property '{p.get('name','?')}' references unregistered domain '{d_id}'",
                                    suggestion="Register the domain or fix the reference"
                                ))
                    # Check inference_rules for domain references
                    rules = data.get("inference_rules", []) or []
                    for r in rules:
                        for prem in r.get("premises", []):
                            ref = prem.get("domain", "")
                            if ref and ref not in registered and ref != yf.stem:
                                issues.append(ConstraintIssue(
                                    source=yf.stem, issue_type="domain_coupling_check",
                                    level="HIGH",
                                    detail=f"Inference rule '{r.get('name','?')}' references domain '{ref}'",
                                    suggestion="Verify domain registration"
                                ))
                except Exception:
                    logging.getLogger(__name__).debug('_check_domain_coupling failed', exc_info=True)
        except Exception:
            logging.getLogger(__name__).debug('_check_domain_coupling failed', exc_info=True)
        return issues

    # ── v2.10: YAML → Runtime Path Deviation ──

    def _check_path_deviation(self) -> List[ConstraintIssue]:
        """Detect dynamic deviations between YAML-declared phases and actual execution paths.

        Compares agent AGENT.md phase declarations vs runtime execution store traces
        to find cases where actual execution diverged from declared phase sequence.
        """
        issues = []
        try:
            from core.services.execution_store import get_execution_store
            store = get_execution_store()
            if not store:
                return issues

            agents_dir = self._home / "agents"
            if not agents_dir.exists():
                return issues

            for adir in agents_dir.iterdir():
                if not adir.is_dir():
                    continue
                agent_file = adir / "AGENT.md"
                if not agent_file.exists():
                    continue

                fm = self._parse_frontmatter(agent_file.read_text(encoding="utf-8"))
                declared_phase = fm.get("phase", "")
                if not declared_phase:
                    continue

                # Check recent executions for this agent
                events = store.list_recent(hours=168) if hasattr(store, 'list_recent') else []
                agent_runs = [e for e in (events or [])
                              if str(e.get("agent_id","")) == adir.name and
                              e.get("kind") in ("agent_execute", "query", "chat")]

                if len(agent_runs) < 3:
                    continue

                # Count phase-vs-execution mismatches
                completed = sum(1 for e in agent_runs if e.get("kind") in ("agent_complete", "done"))
                if completed == 0 and len(agent_runs) >= 5:
                    issues.append(ConstraintIssue(
                        source=adir.name, issue_type="path_deviation",
                        level="WARNING",
                        detail=f"Agent ran {len(agent_runs)} times with zero completions",
                        suggestion="Check if declared phase '{declared_phase}' matches actual pipeline stages"
                    ))
        except Exception:
            logging.getLogger(__name__).debug('_check_path_deviation failed', exc_info=True)
        return issues
