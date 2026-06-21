"""
PipelineCompiler — converts AGENT.md stages[] YAML into PipelineStageConfig[].

v4.0: Enables YAML-driven pipeline agents instead of hand-crafted Python classes.
"""
from typing import Any, Dict, List, Optional

from core.schemas_builder import PipelineStageConfig


class PipelineCompiler:
    """Compile AGENT.md stages array into runnable PipelineStageConfig objects."""

    # Maps AGENT.md stage field names to PipelineStageConfig field names
    _FIELD_MAP = {
        "id": "id",
        "order": "order",
        "node_type": "node_type",
        "pipeline_mode": "pipeline_mode",
        "prompt_template": "prompt_template",
        "prompt_extra": "prompt_extra",
        "depends_on": "depends_on",
        "output_artifact": "output_artifact",
        "input_artifacts": "input_artifacts",
        "required_skills": "required_skills",
        "required_tools": "required_tools",
        "quality_gate": "quality_gate",
        "routing_rules": "routing_rules",
        "retry_policy": "retry_policy",
        "review_gate": "review_gate",
        "failure_strategy": "failure_strategy",
        "max_consecutive_llm_failures": "max_consecutive_llm_failures",
        "knowledge_bases": "knowledge_bases",
        "ontology_class": "ontology_class",
        "expand_subclasses": "expand_subclasses",
        "max_hops": "max_hops",
        "streaming": "streaming",
        "render_upstream": "render_upstream",
        "scene_id": "scene_id",
        "model": "model",
        "temperature": "temperature",
        "max_tokens": "max_tokens",
        "agent_type": "agent_type",
        "hitl": "hitl",
        "execution_mode": "execution_mode",
    }

    @classmethod
    def compile(cls, stages: List[Dict[str, Any]]) -> List[PipelineStageConfig]:
        """Convert AGENT.md stages YAML list to PipelineStageConfig objects."""
        if not stages:
            return []

        configs = []
        for stage_raw in sorted(stages, key=lambda s: s.get("order", 0)):
            config = cls._build_stage(stage_raw)
            if config:
                configs.append(config)

        return configs

    @classmethod
    def _build_stage(cls, raw: Dict[str, Any]) -> Optional[PipelineStageConfig]:
        """Build a single PipelineStageConfig from a stage dict."""
        try:
            kwargs: Dict[str, Any] = {}

            for yaml_field, config_field in cls._FIELD_MAP.items():
                if yaml_field in raw:
                    kwargs[config_field] = raw[yaml_field]

            # Defaults
            kwargs.setdefault("order", 0)
            kwargs.setdefault("node_type", "agent")
            kwargs.setdefault("pipeline_mode", "chain")
            kwargs.setdefault("id", raw.get("id", f"stage_{kwargs['order']}"))
            kwargs.setdefault("agent_id", raw.get("id", f"auto_{kwargs['order']}"))  # required by PipelineStageConfig

            # Convert string values to bool where needed
            for bool_field in ("hitl", "render_upstream", "expand_subclasses", "streaming"):
                if bool_field in kwargs and isinstance(kwargs[bool_field], str):
                    kwargs[bool_field] = kwargs[bool_field].lower() in ("true", "1", "yes")

            # scene_id may have template vars like {{domain_id}}
            if "scene_id" in kwargs:
                kwargs["scene_id"] = str(kwargs["scene_id"])

            return PipelineStageConfig(**kwargs)
        except Exception:
            return None

    @classmethod
    def merge_with_defaults(cls, stages: List[Dict[str, Any]],
                            base_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Merge per-stage config with global agent defaults.
        
        Stages without a specific field inherit from base_config.
        """
        merged = []
        for s in (stages or []):
            m = dict(base_config or {})
            m.update(s)
            # Inherit model from global config if not specified per-stage
            if "model" not in s and base_config:
                m["model"] = base_config.get("model", "")
            merged.append(m)
        return merged
