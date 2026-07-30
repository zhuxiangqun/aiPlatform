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

logger = logging.getLogger(__name__)

ONTOLOGY_BASE = os.path.expanduser("~/.aiplat/ontologies")


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
        if not os.path.isdir(ONTOLOGY_BASE):
            return 0
        versions = []
        for f in os.listdir(ONTOLOGY_BASE):
            if f.startswith(f"{self.domain_id}_v") and f.endswith(".yaml"):
                try:
                    v = int(f.split("_v")[-1].replace(".yaml", ""))
                    versions.append(v)
                except ValueError:
                    pass  # noqa: cleanup-best-effort — non-matching filenames ignored
        return max(versions) if versions else 0

    def _version_path(self, version: int) -> str:
        return os.path.join(ONTOLOGY_BASE, f"{self.domain_id}_v{version}.yaml")

    def _legacy_path(self) -> str:
        return os.path.join(ONTOLOGY_BASE, f"{self.domain_id}.yaml")

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

        proposal_id = f"prop_{self.domain_id}_{int(time.time())}"
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
        logger.info("Proposal created: %s (v%s → v%s)", proposal_id, current_v, current_v + 1)
        return proposal_id

    async def list_proposals(self, domain_id: str = "") -> List[Dict[str, Any]]:
        """List proposals (optionally filtered by domain)."""
        await self.store.initialize()
        return await self.store.list_ontology_proposals(domain_id or self.domain_id)

    async def apply_proposal(self, proposal_id: str) -> bool:
        """Apply an approved proposal: generate new version YAML, archive old."""
        await self.store.initialize()
        proposal = await self.store.get_ontology_proposal(proposal_id)
        if not proposal or proposal.get("status") != "approved":
            logger.warning("Proposal %s not found or not approved", proposal_id)
            return False

        current_v = int(proposal.get("version_from", "0"))
        new_v = int(proposal.get("version_to", "1"))
        current_data = self.load_current()
        changes = json.loads(proposal.get("changes", "{}"))

        # Apply changes to current data
        for action, payload in changes.items():
            if action == "add" and isinstance(payload, dict):
                if "class" in payload:
                    current_data.setdefault("classes", []).append(payload["class"])
                if "property" in payload:
                    current_data.setdefault("object_properties", []).append(payload["property"])
            elif action == "deprecate" and isinstance(payload, list):
                for class_name in payload:
                    for c in current_data.get("classes", []):
                        if c.get("name") == class_name:
                            c["deprecated"] = True
            elif action == "split" and isinstance(payload, dict):
                old_name = payload.get("source", "")
                new_classes = payload.get("into", [])
                for c in current_data.get("classes", []):
                    if c.get("name") == old_name:
                        c["deprecated"] = True
                current_data.setdefault("classes", []).extend(new_classes)
            elif action == "merge" and isinstance(payload, dict):
                sources = payload.get("sources", [])
                target = payload.get("into", {})
                for c in current_data.get("classes", []):
                    if c.get("name") in sources:
                        c["deprecated"] = True
                current_data.setdefault("classes", []).append(target)

        # Write new version
        new_path = self._version_path(new_v)
        os.makedirs(ONTOLOGY_BASE, exist_ok=True)
        with open(new_path, "w", encoding="utf-8") as f:
            yaml.dump(current_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

        # Archive old version
        if current_v > 0:
            old_path = self._version_path(current_v)
            history_dir = os.path.join(ONTOLOGY_BASE, "history")
            os.makedirs(history_dir, exist_ok=True)
            archive_name = os.path.join(
                history_dir,
                f"{self.domain_id}_v{current_v}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.yaml",
            )
            if os.path.exists(old_path):
                shutil.move(old_path, archive_name)
        elif os.path.exists(self._legacy_path()):
            history_dir = os.path.join(ONTOLOGY_BASE, "history")
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

    def _analyze_impact(self, current: Dict, changes: Dict) -> Dict:
        """Return estimated impact of proposed changes."""
        classes = current.get("classes", [])
        props = current.get("object_properties", [])
        impact = {
            "total_classes": len(classes),
            "total_properties": len(props),
            "affected_classes": 0,
            "affected_properties": 0,
        }
        for action, payload in changes.items():
            if action == "deprecate" and isinstance(payload, list):
                impact["affected_classes"] += len(payload)
            elif action in ("split", "merge"):
                impact["affected_classes"] += 1
            elif action == "add":
                impact["affected_classes"] += 1
        return impact
