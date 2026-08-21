"""
Versioned Ontology Store (Phase 3, 2026-07-30).

Manages versioned domain YAML files under ~/.aiplat/ontologies/:
  - {domain}.yaml (legacy) / {domain}_v{N}.yaml (versioned)
  - Proposal lifecycle: draft → submitted → approved → rejected → applied
  - Archive old versions to history/ on apply

Integrates with ActionStore for proposal persistence and approval workflow.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import yaml

from core.harness.knowledge.knowledge_ontology import (
    TIER_CORE,
    TIER_LOGIC,
    TIER_EDGE,
    TIER_ORDER,
    normalize_tier,
)

logger = logging.getLogger(__name__)


def _ontology_base() -> str:
    """Resolve ontology directory, honoring AIPLAT_HOME (aligns with ontology_loader)."""
    return os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "ontologies")

# P2-L1: 治理规则矩阵 — tier 所需审批角色（对应 plan-tier-ontology-layering.md §3）
#   core → 全员/架构评审（阻断）  logic → 产品侧确认  edge → 自服务
TIER_APPROVAL_ROLES = {
    TIER_CORE: ("governance_admin", "admin"),          # 架构评审角色
    TIER_LOGIC: ("governance_admin", "admin", "operator", "product_manager"),
    TIER_EDGE: ("*",),                                 # 自服务：任意角色
}

# edge → logic 升格所需的复用证明最小命中次数（复用 add_suggestions_from_patterns 聚类数据）
PROMOTION_REUSE_THRESHOLD = 3


class VersionedOntologyStore:
    """Read, write, and version domain ontology YAML files."""

    def __init__(self, domain_id: str):
        self.domain_id = domain_id
        from core.harness.infrastructure.action_store import ActionStore
        self.store = ActionStore()

    # ═══════════════════════════════════════════════════════
    # Version management
    # ═══════════════════════════════════════════════════════

    def get_current_version(self) -> int:
        """Return the highest version number found in the ontology directory."""
        if not os.path.isdir(_ontology_base()):
            return 0
        versions = []
        for f in os.listdir(_ontology_base()):
            if f.startswith(f"{self.domain_id}_v") and f.endswith(".yaml"):
                try:
                    v = int(f.split("_v")[-1].replace(".yaml", ""))
                    versions.append(v)
                except ValueError:
                    pass  # noqa: cleanup-best-effort — non-matching filenames ignored
        return max(versions) if versions else 0

    def _version_path(self, version: int) -> str:
        return os.path.join(_ontology_base(), f"{self.domain_id}_v{version}.yaml")

    def _legacy_path(self) -> str:
        return os.path.join(_ontology_base(), f"{self.domain_id}.yaml")

    def load_current(self) -> Dict:
        """Load the current (highest version) ontology. Falls back to legacy filename."""
        v = self.get_current_version()
        if v > 0:
            path = self._version_path(v)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
        legacy = self._legacy_path()
        if os.path.exists(legacy):
            with open(legacy, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    # ═══════════════════════════════════════════════════════
    # Proposal lifecycle
    # ═══════════════════════════════════════════════════════

    async def create_proposal(self, changes: Dict, author: str = "system") -> str:
        """Create an ontology evolution proposal. Returns proposal_id."""
        current_v = self.get_current_version()
        current = self.load_current()
        impact = self._analyze_impact(current, changes)

        proposal_id = f"prop_{self.domain_id}_{int(time.time() * 1000)}"
        await self.store.initialize()
        await self.store.insert_ontology_proposal(
            proposal_id=proposal_id,
            domain_id=self.domain_id,
            version_from=str(current_v),
            version_to=str(current_v + 1),
            changes=json.dumps(changes, ensure_ascii=False),
            status="draft",
            author=author,
            impact=json.dumps(impact, ensure_ascii=False),
        )
        logger.info("Proposal created: %s (v%s → v%s, tier=%s)", proposal_id, current_v, current_v + 1, impact.get("max_tier"))
        return proposal_id

    async def list_proposals(self, domain_id: str = "") -> List[Dict[str, Any]]:
        """List proposals (optionally filtered by domain)."""
        await self.store.initialize()
        return await self.store.list_ontology_proposals(domain_id or self.domain_id)

    async def approve_proposal(self, proposal_id: str, approver_role: str = "") -> Dict[str, Any]:
        """P2-L1: tier-gated approval. core→全员/架构评审, logic→产品侧确认, edge→自服务.

        Returns {"success": bool, "status": ..., "reason": ...}.
        """
        await self.store.initialize()
        proposal = await self.store.get_ontology_proposal(proposal_id)
        if not proposal:
            return {"success": False, "status": "not_found", "reason": "proposal not found"}
        if proposal.get("status") != "draft":
            return {"success": False, "status": proposal.get("status"), "reason": f"proposal is {proposal.get('status')}, not draft"}

        impact = json.loads(proposal.get("impact_analysis", "{}")) or {}
        max_tier = impact.get("max_tier", TIER_LOGIC)
        allowed = TIER_APPROVAL_ROLES.get(max_tier, (TIER_LOGIC,))
        role = (approver_role or "").strip().lower()
        if "*" not in allowed and role not in allowed:
            return {
                "success": False,
                "status": "rejected",
                "reason": f"tier={max_tier} requires approval role in {list(allowed)}, got '{role or 'empty'}'",
            }

        # Record approval evidence (role + level) into impact for audit trail
        impact["approved_by"] = role
        impact["approval_level"] = max_tier
        impact["approved_at"] = datetime.now(timezone.utc).isoformat()
        await self.store.update_ontology_proposal_impact(proposal_id, json.dumps(impact, ensure_ascii=False))
        await self.store.update_ontology_proposal_status(proposal_id, "approved")
        logger.info("Proposal %s approved by %s (tier=%s)", proposal_id, role, max_tier)
        return {"success": True, "status": "approved", "tier": max_tier}

    async def apply_proposal(self, proposal_id: str) -> bool:
        """Apply an approved proposal: generate new version YAML, archive old.

        P2-L1 tier gate (plan-tier-ontology-layering.md §3):
          - max_tier == core  → 必须已通过架构评审（approval_level == architecture_review）
          - edge→logic 升格    → 必须携带复用证明（promotion_proof.reuse_count ≥ 3）
          - 任何到 core 的升格  → 必须已通过架构评审
        """
        await self.store.initialize()
        proposal = await self.store.get_ontology_proposal(proposal_id)
        if not proposal or proposal.get("status") != "approved":
            logger.warning("Proposal %s not found or not approved", proposal_id)
            return False

        current_v = int(proposal.get("version_from", "0"))
        new_v = int(proposal.get("version_to", "1"))
        current_data = self.load_current()
        changes = json.loads(proposal.get("changes", "{}"))
        impact = json.loads(proposal.get("impact_analysis", "{}")) or {}

        # ── P2-L1 tier gate ──
        gate = self._check_tier_gate(current_data, changes, impact)
        if gate is not None:
            logger.warning("Proposal %s blocked by tier gate: %s", proposal_id, gate)
            return False

        # Normalize classes to list-of-dicts for mutation; restore original layout on write
        classes_layout = current_data.get("classes")
        classes_list: List[Dict[str, Any]] = []
        if isinstance(classes_layout, dict):
            for name, cdef in classes_layout.items():
                entry = dict(cdef) if isinstance(cdef, dict) else {}
                entry.setdefault("name", name)
                classes_list.append(entry)
        elif isinstance(classes_layout, list):
            classes_list = [dict(c) for c in classes_layout if isinstance(c, dict)]

        def _find(name: str) -> Optional[Dict[str, Any]]:
            return next((c for c in classes_list if c.get("name") == name), None)

        # Apply changes to current data
        for action, payload in changes.items():
            if action == "add" and isinstance(payload, dict):
                if "class" in payload:
                    new_cls = payload["class"]
                    if isinstance(new_cls, dict) and "name" in new_cls:
                        classes_list.append(dict(new_cls))
                    elif isinstance(new_cls, dict):
                        for _n, _d in new_cls.items():
                            entry = dict(_d) if isinstance(_d, dict) else {}
                            entry.setdefault("name", _n)
                            classes_list.append(entry)
                if "property" in payload:
                    current_data.setdefault("object_properties", []).append(payload["property"])
            elif action == "deprecate" and isinstance(payload, list):
                for class_name in payload:
                    c = _find(class_name)
                    if c is not None:
                        c["deprecated"] = True
            elif action == "split" and isinstance(payload, dict):
                old_name = payload.get("source", "")
                c = _find(old_name)
                if c is not None:
                    c["deprecated"] = True
                for nc in (payload.get("into") or []):
                    if isinstance(nc, dict) and "name" in nc:
                        classes_list.append(dict(nc))
                    elif isinstance(nc, dict):
                        for _n, _d in nc.items():
                            entry = dict(_d) if isinstance(_d, dict) else {}
                            entry.setdefault("name", _n)
                            classes_list.append(entry)
            elif action == "merge" and isinstance(payload, dict):
                sources = payload.get("sources", [])
                for s in sources:
                    c = _find(s)
                    if c is not None:
                        c["deprecated"] = True
                target = payload.get("into", {})
                if isinstance(target, dict) and "name" in target:
                    classes_list.append(dict(target))
                elif isinstance(target, dict):
                    for _n, _d in target.items():
                        entry = dict(_d) if isinstance(_d, dict) else {}
                        entry.setdefault("name", _n)
                        classes_list.append(entry)

        # Restore original classes layout
        if isinstance(classes_layout, dict):
            current_data["classes"] = {c.get("name", ""): {k: v for k, v in c.items() if k != "name"} for c in classes_list}
        else:
            current_data["classes"] = classes_list

        # Write new version
        new_path = self._version_path(new_v)
        os.makedirs(_ontology_base(), exist_ok=True)
        with open(new_path, "w", encoding="utf-8") as f:
            yaml.dump(current_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

        # Archive old version
        if current_v > 0:
            old_path = self._version_path(current_v)
            history_dir = os.path.join(_ontology_base(), "history")
            os.makedirs(history_dir, exist_ok=True)
            archive_name = os.path.join(
                history_dir,
                f"{self.domain_id}_v{current_v}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.yaml",
            )
            if os.path.exists(old_path):
                shutil.move(old_path, archive_name)
        elif os.path.exists(self._legacy_path()):
            history_dir = os.path.join(_ontology_base(), "history")
            os.makedirs(history_dir, exist_ok=True)
            archive_name = os.path.join(history_dir, f"{self.domain_id}_legacy_{datetime.now(timezone.utc).strftime('%Y%m%d')}.yaml")
            shutil.move(self._legacy_path(), archive_name)

        # Mark proposal as applied
        await self.store.update_ontology_proposal_status(proposal_id, "applied")
        logger.info("Proposal %s applied: v%s → v%s", proposal_id, current_v, new_v)
        return True

    # ═══════════════════════════════════════════════════════
    # Impact analysis
    # ═══════════════════════════════════════════════════════

    def _class_tier(self, current: Dict, class_name: str) -> str:
        """Look up a class's tier in current data (supports dict & list YAML layouts)."""
        classes = current.get("classes") or {}
        if isinstance(classes, dict):
            return normalize_tier((classes.get(class_name) or {}).get("tier") if isinstance(classes.get(class_name), dict) else None)
        for c in classes:
            if isinstance(c, dict) and c.get("name") == class_name:
                return normalize_tier(c.get("tier"))
        return TIER_LOGIC

    def _class_tier_from_def(self, cls_def: Any) -> str:
        """Extract tier from a class definition payload (dict by-name or dict with name key)."""
        if isinstance(cls_def, dict):
            if "name" in cls_def:
                return normalize_tier(cls_def.get("tier"))
            for _name, _def in cls_def.items():
                if isinstance(_def, dict):
                    return normalize_tier(_def.get("tier"))
        return TIER_LOGIC

    def _check_tier_gate(self, current: Dict, changes: Dict, impact: Dict) -> Optional[str]:
        """P2-L1 tier gate. Returns None if allowed, else a rejection reason string."""
        max_tier = impact.get("max_tier", TIER_LOGIC)
        approval_level = impact.get("approval_level", "")

        # 1) core 变更必须已通过架构评审（全员/架构评审阻断）
        if max_tier == TIER_CORE and approval_level != TIER_CORE:
            return f"core-tier change requires architecture review (approval_level=core), got '{approval_level}'"

        # 2) 升格判定：edge→logic 需复用证明；任何→core 需架构评审（由 1 覆盖）
        promotions = impact.get("promotions", [])
        for prom in promotions:
            from_tier = prom.get("from", TIER_EDGE)
            to_tier = prom.get("to", "")
            if to_tier == TIER_LOGIC and from_tier == TIER_EDGE:
                proof = (changes.get("promotion_proof") or {}).get("reuse_count", 0)
                if int(proof or 0) < PROMOTION_REUSE_THRESHOLD:
                    return f"edge→logic promotion of '{prom.get('class')}' requires reuse_count ≥ {PROMOTION_REUSE_THRESHOLD}, got {proof}"
            if to_tier == TIER_CORE and approval_level != TIER_CORE:
                return f"promotion of '{prom.get('class')}' to core requires architecture review"
        return None

    def _analyze_impact(self, current: Dict, changes: Dict) -> Dict:
        """Return estimated impact of proposed changes (P2-L1: includes tier analysis)."""
        classes = current.get("classes", [])
        props = current.get("object_properties", [])
        impact = {
            "total_classes": len(classes) if isinstance(classes, (list, dict)) else 0,
            "total_properties": len(props) if isinstance(props, list) else 0,
            "affected_classes": 0,
            "affected_properties": 0,
            "tiers": {TIER_CORE: [], TIER_LOGIC: [], TIER_EDGE: []},
            "max_tier": TIER_LOGIC,
            "promotions": [],
        }
        affected_names: List[str] = []
        tier_hints: Dict[str, str] = {}  # class_name → tier declared in the change payload

        def _collect_class_name(cls_payload: Any) -> Optional[str]:
            if isinstance(cls_payload, dict):
                if "name" in cls_payload:
                    return str(cls_payload["name"])
                # by-name layout: {ClassName: {tier: ...}}
                if cls_payload:
                    return str(next(iter(cls_payload)))
            return None

        for action, payload in changes.items():
            if action == "deprecate" and isinstance(payload, list):
                for name in payload:
                    if isinstance(name, str):
                        affected_names.append(name)
                impact["affected_classes"] += len(payload)
            elif action == "split" and isinstance(payload, dict):
                src = payload.get("source", "")
                if src:
                    affected_names.append(str(src))
                for nc in (payload.get("into") or []):
                    name = _collect_class_name(nc)
                    if name:
                        affected_names.append(name)
                        tier_hints[name] = self._class_tier_from_def(nc)
                impact["affected_classes"] += 1 + len(payload.get("into") or [])
            elif action == "merge" and isinstance(payload, dict):
                for s in (payload.get("sources") or []):
                    if isinstance(s, str):
                        affected_names.append(s)
                target = payload.get("into") or {}
                tname = _collect_class_name(target)
                if tname:
                    affected_names.append(tname)
                    tier_hints[tname] = self._class_tier_from_def(target)
                impact["affected_classes"] += len(payload.get("sources") or []) + (1 if tname else 0)
            elif action == "add" and isinstance(payload, dict):
                if "class" in payload:
                    cname = _collect_class_name(payload["class"])
                    if cname:
                        affected_names.append(cname)
                        tier_hints[cname] = self._class_tier_from_def(payload["class"])
                    impact["affected_classes"] += 1
                if "property" in payload:
                    impact["affected_properties"] += 1

        # Resolve tiers + promotions (dedup names)
        seen: set = set()
        for name in affected_names:
            if name in seen:
                continue
            seen.add(name)
            old_tier = self._class_tier(current, name)
            new_tier = tier_hints.get(name) or old_tier
            impact["tiers"].setdefault(new_tier, []).append(name)
            if new_tier != old_tier:
                impact["promotions"].append({"class": name, "from": old_tier, "to": new_tier})

        # max_tier = 受影响类中的最高治理层（忽略空 tier 桶）
        non_empty = [t for t, names in impact["tiers"].items() if names]
        if non_empty:
            impact["max_tier"] = max(non_empty, key=lambda t: TIER_ORDER.get(t, 1))
        return impact
