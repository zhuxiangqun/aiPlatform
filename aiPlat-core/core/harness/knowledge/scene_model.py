"""
Ontology Scene Model — purpose-driven pipeline templates.

An OntologyScene answers "what business problem does this pipeline solve?".
It ties together:
  - Which ontology entities and relations are in play
  - Which deterministic algorithms to run
  - Where LLM judgment is needed (and where it isn't)
  - What outcomes are expected (for verification)
  - Under what conditions this scene should be triggered

Scenes are stored as templates and instantiated into PipelineConfigs.
They provide the "narrative backbone" that makes ontology-driven pipelines
auditable and composable.

Design pattern: Scene → instantiate → PipelineConfig → execute → verify
The scene is the declarative layer; the pipeline is the operational layer.

callers:
  - wiki.py (CRUD API)
  - core_facade (instantiation, context injection)
  - pipeline_engine (scene_id → Agent prompt enrichment)
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class OntologyScene:
    scene_id: str                          # unique identifier, e.g. "supply_chain_mrp"
    name: str = ""                         # human-readable name
    description: str = ""                  # what business problem this solves

    # Ontology entities involved
    required_entities: List[str] = field(default_factory=list)
    # e.g. ["Material", "BOM", "Order", "Inventory"]

    # Algorithm nodes (deterministic, no LLM)
    algorithm_nodes: List[Dict[str, Any]] = field(default_factory=list)
    # e.g. [{"stage_id": "calc_net_demand", "function_name": "mrp_net_demand",
    #         "function_params": {...}, "expected_outcomes": [...]}]

    # LLM judgment nodes (where fuzzy reasoning is needed)
    llm_judgment_nodes: List[Dict[str, Any]] = field(default_factory=list)
    # e.g. [{"stage_id": "select_supplier", "agent_type": "conversational",
    #         "context": "Evaluate suppliers based on delivery time, quality, price"}]

    # Entry conditions: when should this scene be activated
    entry_conditions: Dict[str, Any] = field(default_factory=dict)
    # e.g. {"trigger_type": "manual" | "schedule" | "event",
    #        "trigger_event": "low_inventory_alert"}

    # Expected outcomes for audit & verification
    expected_outcomes: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    created_at: str = ""
    updated_at: str = ""
    version: int = 1
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "name": self.name,
            "description": self.description,
            "required_entities": self.required_entities,
            "algorithm_nodes": self.algorithm_nodes,
            "llm_judgment_nodes": self.llm_judgment_nodes,
            "entry_conditions": self.entry_conditions,
            "expected_outcomes": self.expected_outcomes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OntologyScene":
        return cls(
            scene_id=data.get("scene_id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            required_entities=data.get("required_entities", []),
            algorithm_nodes=data.get("algorithm_nodes", []),
            llm_judgment_nodes=data.get("llm_judgment_nodes", []),
            entry_conditions=data.get("entry_conditions", {}),
            expected_outcomes=data.get("expected_outcomes", []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            version=data.get("version", 1),
            tags=data.get("tags", []),
        )

    def to_pipeline_stages(self) -> List[Dict[str, Any]]:
        u"""Convert scene nodes into PipelineStageConfig-compatible dicts.

        Algorithm nodes → node_type='algorithm' stages.
        LLM judgment nodes → node_type='agent' stages.
        Returns a list of stage dicts ready for PipelineConfig construction.
        """
        stages = []
        order = 0

        for node in self.algorithm_nodes:
            order += 1
            stage = {
                "id": node.get("stage_id", f"algo_{order}"),
                "node_type": "algorithm",
                "order": order,
                "node_config": {
                    "function_name": node.get("function_name", ""),
                    "function_params": node.get("function_params", {}),
                },
                "output_artifact": node.get("output_artifact", f"algo_result_{order}"),
                "expected_outcomes": node.get("expected_outcomes", []),
            }
            stages.append(stage)

        for node in self.llm_judgment_nodes:
            order += 1
            stage = {
                "id": node.get("stage_id", f"llm_{order}"),
                "node_type": "agent",
                "agent_type": node.get("agent_type", "conversational"),
                "order": order,
                "output_artifact": node.get("output_artifact", f"llm_result_{order}"),
                "prompt_extra": node.get("context", ""),
                "expected_outcomes": node.get("expected_outcomes", []),
                "knowledge_bases": node.get("knowledge_bases", []),
                "ontology_class": node.get("ontology_class", ""),
                "ontology_relations": node.get("ontology_relations", []),
            }
            stages.append(stage)

        return stages

    def to_agent_context(self) -> str:
        u"""Generate a concise natural-language context for Agent prompt injection.

        Tells the Agent what scene it's in, what entities matter,
        and what the expected outputs are.
        """
        lines = [
            f"## Scene: {self.name} ({self.scene_id})",
            f"Purpose: {self.description}" if self.description else "",
        ]
        if self.required_entities:
            lines.append(f"Key entities: {', '.join(self.required_entities)}")
        if self.algorithm_nodes:
            alg_names = [a.get("function_name", "?") for a in self.algorithm_nodes]
            lines.append(f"Deterministic computation stages: {', '.join(alg_names)}")
        if self.llm_judgment_nodes:
            llm_names = [l.get("stage_id", "?") for l in self.llm_judgment_nodes]
            lines.append(f"Your judgment is needed for: {', '.join(llm_names)}")
        if self.expected_outcomes:
            lines.append(f"Expected outcomes: {len(self.expected_outcomes)} constraints defined")
        return "\n".join(line for line in lines if line)


# ══════════════════════════════════════════════════════════════
# Scene Store
# ══════════════════════════════════════════════════════════════

def _scene_path(collection_id: str = "default") -> str:
    home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))
    return _os.path.join(home, "wiki", "collections", collection_id, "scenes.json")


def list_scenes(collection_id: str = "default") -> List[OntologyScene]:
    path = _scene_path(collection_id)
    if not _os.path.exists(path):
        return []
    try:
        data = _json.load(open(path, "r", encoding="utf-8"))
        return [OntologyScene.from_dict(s) for s in data.get("scenes", [])]
    except Exception:
        return []


def get_scene(scene_id: str, *, collection_id: str = "default") -> Optional[OntologyScene]:
    scenes = list_scenes(collection_id)
    for s in scenes:
        if s.scene_id == scene_id:
            return s
    return None


def save_scene(scene: OntologyScene, *, collection_id: str = "default") -> OntologyScene:
    scenes = list_scenes(collection_id)
    existing_idx = next((i for i, s in enumerate(scenes) if s.scene_id == scene.scene_id), None)
    scene.updated_at = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())
    if existing_idx is not None:
        scenes[existing_idx] = scene
    else:
        scene.created_at = scene.created_at or _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())
        scenes.append(scene)

    path = _scene_path(collection_id)
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        _json.dump({
            "version": "v1.0",
            "updated_at": _time.time(),
            "scenes": [s.to_dict() for s in scenes],
        }, f, indent=2, ensure_ascii=False)
    return scene


def delete_scene(scene_id: str, *, collection_id: str = "default") -> bool:
    scenes = list_scenes(collection_id)
    before = len(scenes)
    scenes = [s for s in scenes if s.scene_id != scene_id]
    if len(scenes) == before:
        return False

    path = _scene_path(collection_id)
    with open(path, "w", encoding="utf-8") as f:
        _json.dump({
            "version": "v1.0",
            "updated_at": _time.time(),
            "scenes": [s.to_dict() for s in scenes],
        }, f, indent=2, ensure_ascii=False)
    return True


def instantiate_scene(
    scene_id: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    collection_id: str = "default",
) -> Optional[Dict[str, Any]]:
    u"""Instantiate a scene into a PipelineConfig dict.

    Merges scene template nodes with user-provided parameter overrides.
    Returns a dict compatible with PipelineConfig constructor.
    """
    scene = get_scene(scene_id, collection_id=collection_id)
    if scene is None:
        return None

    stages = scene.to_pipeline_stages()
    params = params or {}

    # Apply parameter overrides to algorithm node params
    for stage in stages:
        if stage.get("node_type") == "algorithm":
            func_params = stage.get("node_config", {}).get("function_params", {})
            for k, v in params.items():
                if k in func_params:
                    func_params[k] = v

    return {
        "stages": stages,
        "max_iterations": params.get("max_iterations", 1),
        "scene_id": scene_id,
        "scene_context": scene.to_agent_context(),
    }


# ══════════════════════════════════════════════════════════════
# Built-in Scene Templates
# ══════════════════════════════════════════════════════════════

def create_builtin_scenes() -> List[OntologyScene]:
    u"""Create built-in scene templates for common enterprise scenarios."""
    return [
        OntologyScene(
            scene_id="supply_chain_mrp",
            name="MRP Net Demand Calculation",
            description="Calculate net material requirements from gross demand, inventory, and BOM.",
            required_entities=["Material", "BOM", "Order", "Inventory"],
            algorithm_nodes=[
                {
                    "stage_id": "calc_net_demand",
                    "function_name": "mrp_net_demand",
                    "function_params": {
                        "gross_demand": 0,
                        "on_hand_inventory": 0,
                        "scheduled_receipts": 0,
                        "safety_stock": 0,
                    },
                    "output_artifact": "net_demand_result",
                    "expected_outcomes": [
                        {"field": "result.net_requirement", "constraint": "range", "expected": [0, 1000000]},
                        {"field": "result.needs_planned_order", "constraint": "in_set", "expected": [True, False]},
                    ],
                },
                {
                    "stage_id": "offset_inventory",
                    "function_name": "inventory_offset",
                    "output_artifact": "allocation_result",
                },
            ],
            llm_judgment_nodes=[
                {
                    "stage_id": "select_supplier",
                    "agent_type": "conversational",
                    "context": "Based on the net demand calculation, recommend the best supplier considering delivery time, quality history, and cost. The deterministic calculation has confirmed the required quantity; your role is to choose WHO supplies it.",
                    "output_artifact": "supplier_decision",
                },
            ],
            entry_conditions={"trigger_type": "manual"},
        ),
        OntologyScene(
            scene_id="order_validation",
            name="Purchase Order Validation",
            description="Validate purchase order quantities, prices, and compliance before approval.",
            required_entities=["Order", "Material", "Supplier"],
            algorithm_nodes=[
                {
                    "stage_id": "validate_qty",
                    "function_name": "validate_quantity",
                    "function_params": {"value": 0, "min_value": 1, "allow_zero": False},
                    "output_artifact": "qty_validation",
                    "expected_outcomes": [
                        {"field": "result.valid", "constraint": "equals", "expected": True},
                    ],
                },
            ],
            llm_judgment_nodes=[
                {
                    "stage_id": "compliance_check",
                    "agent_type": "conversational",
                    "context": "Review the purchase order for compliance with procurement policies. Flag any anomalies.",
                },
            ],
            entry_conditions={"trigger_type": "manual"},
        ),
        OntologyScene(
            scene_id="knowledge_curation",
            name="Knowledge Base Auto-Curation",
            description="Detect stale, contradicted, or low-quality wiki pages and recommend actions.",
            required_entities=["WikiPage", "KBDocument", "WikiRelation"],
            algorithm_nodes=[
                {
                    "stage_id": "health_check",
                    "function_name": "validate_quantity",
                    "function_params": {"value": 0},
                    "output_artifact": "health_baseline",
                },
            ],
            llm_judgment_nodes=[
                {
                    "stage_id": "curation_recommend",
                    "agent_type": "conversational",
                    "context": "Based on the health metrics, recommend which pages need updating, merging, or archiving.",
                    "knowledge_bases": ["default"],
                    "ontology_class": "WikiProposal",
                },
            ],
            entry_conditions={"trigger_type": "schedule", "cron": "0 */6 * * *"},
        ),
        # Phase L4 — AI Learning Coach scene
        OntologyScene(
            scene_id="personal_learning_coach",
            name="AI 学习教练",
            description="结构化学习系统：建体系→找资料→作业评估→定制讲解→项目实战",
            required_entities=["LearningPath", "Chapter", "Exercise", "Assessment", "LearnerProfile"],
            algorithm_nodes=[
                {
                    "stage_id": "mc_grade",
                    "function_name": "validate_quantity",
                    "function_params": {"value": 0},
                    "output_artifact": "mc_result",
                },
            ],
            llm_judgment_nodes=[
                {
                    "stage_id": "open_assessment",
                    "agent_type": "conversational",
                    "context": "根据评分标准（rubric）评估学生的开放题回答。给出分数、是否通过、具体反馈、薄弱点、下一步建议。",
                    "output_artifact": "assessment_result",
                },
                {
                    "stage_id": "learning_navigation",
                    "agent_type": "conversational",
                    "context": "根据学生的 LearnerProfile、已完成章节、掌握度评分，推荐下一步学习路径。当学生提问时，结合学习进度给出定制回答。",
                    "output_artifact": "navigation_advice",
                },
                {
                    "stage_id": "chapter_compilation",
                    "agent_type": "conversational",
                    "context": "你是课程编写助手。根据人工策划的章节骨架（核心概念列表），用中文编写学习者读的课文正文。要求对话式、易读、附带非技术例子。",
                    "output_artifact": "chapter_body",
                    "ontology_class": "Chapter",
                },
            ],
            entry_conditions={"trigger_type": "manual"},
            expected_outcomes=[
                {"field": "assessment_result.score", "constraint": "range", "expected": [0, 100]},
            ],
        ),
    ]
