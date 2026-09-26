"""
Versioned Ontology Store (Phase 3, 2026-07-30).

Manages versioned domain YAML under ~/.aiplat/ontologies/:
  - Live pointer only: ``{domain}.yaml`` (DomainRouter / UI source of truth)
  - Version archives: ``history/{domain}_v{N}.yaml`` (never listed as domains)
  - Proposal lifecycle: draft → approved → applied / rolled_back

Integrates with ActionStore for proposal persistence and approval workflow.
"""
from __future__ import annotations

import json
import logging
import os
import re
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

# Exact live/history version sidecar: {domain}_v12.yaml (not _v1_20260923 / _v2_rolled_…)
_VERSION_SIDECAR_RE = re.compile(r"^(.+)_v(\d+)\.yaml$")


def _brief(value: Any) -> Any:
    if isinstance(value, dict):
        return sorted(str(k) for k in value.keys())[:12]
    if isinstance(value, list):
        return {"len": len(value)}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:80]


def _class_map(raw: Any) -> Dict[str, Dict[str, Any]]:
    if isinstance(raw, dict):
        return {str(k): v if isinstance(v, dict) else {} for k, v in raw.items()}
    if isinstance(raw, list):
        out: Dict[str, Dict[str, Any]] = {}
        for item in raw:
            if isinstance(item, dict) and item.get("name"):
                out[str(item["name"])] = item
        return out
    return {}


def json_change_diff(before: Any, after: Any, *, limit: int = 40) -> Dict[str, Any]:
    """Shallow before/after of an already-approved apply. Does not write YAML."""
    left = before if isinstance(before, dict) else {}
    right = after if isinstance(after, dict) else {}
    cap = max(1, min(int(limit or 40), 80))
    changes: List[Dict[str, Any]] = []
    for key in list(dict.fromkeys([*left.keys(), *right.keys()])):
        if left.get(key) == right.get(key):
            continue
        if key == "classes":
            bm = _class_map(left.get(key))
            am = _class_map(right.get(key))
            for name in list(dict.fromkeys([*bm.keys(), *am.keys()])):
                if bm.get(name) == am.get(name):
                    continue
                bfields = set((bm.get(name) or {}).keys())
                afields = set((am.get(name) or {}).keys())
                changes.append(
                    {
                        "path": f"classes.{name}",
                        "before": sorted(bfields)[:12],
                        "after": sorted(afields)[:12],
                    }
                )
                if len(changes) >= cap:
                    break
        else:
            changes.append({"path": str(key), "before": _brief(left.get(key)), "after": _brief(right.get(key))})
        if len(changes) >= cap:
            break
    return {
        "kind": "json_diff",
        "full_event_log": False,
        "count": len(changes),
        "truncated": len(changes) >= cap,
        "changes": changes,
        "wrote_live_yaml": False,
    }


def project_ontology_changes(current: Any, changes: Any) -> Dict[str, Any]:
    """In-memory apply of a proposal change dict. Does not write YAML."""
    import copy

    data = copy.deepcopy(current if isinstance(current, dict) else {})
    payload = changes if isinstance(changes, dict) else {}
    classes_layout = data.get("classes")
    classes_list: List[Dict[str, Any]] = []
    if isinstance(classes_layout, dict):
        for name, cdef in classes_layout.items():
            entry = dict(cdef) if isinstance(cdef, dict) else {}
            entry.setdefault("name", name)
            classes_list.append(entry)
    elif isinstance(classes_layout, list):
        classes_list = [dict(c) for c in classes_layout if isinstance(c, dict)]

    add = payload.get("add") if isinstance(payload.get("add"), dict) else {}
    new_cls = add.get("class") if isinstance(add, dict) else None
    if isinstance(new_cls, dict) and new_cls.get("name"):
        classes_list.append(dict(new_cls))
    elif isinstance(new_cls, dict):
        for _n, _d in new_cls.items():
            entry = dict(_d) if isinstance(_d, dict) else {}
            entry.setdefault("name", _n)
            classes_list.append(entry)

    rem = payload.get("remove")
    if isinstance(rem, list) and rem:
        drop = {str(x) for x in rem if x}
        classes_list = [c for c in classes_list if str(c.get("name") or "") not in drop]

    if isinstance(classes_layout, dict):
        data["classes"] = {
            c.get("name", ""): {k: v for k, v in c.items() if k != "name"} for c in classes_list
        }
    else:
        data["classes"] = classes_list
    return data


def _ontology_base() -> str:
    """Resolve ontology directory, honoring AIPLAT_HOME (aligns with ontology_loader)."""
    return os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "ontologies")

# P2-L1: 治理规则矩阵 — tier 所需审批角色（对应 plan-tier-ontology-layering.md §3）
#   core → 全员/架构评审（阻断）  logic → 产品侧确认  edge → 自服务
# 角色矩阵为治理配置，放在同级 tier_approval_roles.yaml（内核无关约束：角色名不写死在 harness 代码）。
_DEFAULT_TIER_APPROVAL_ROLES = {
    TIER_CORE: ("governance_admin", "admin"),
    TIER_LOGIC: ("governance_admin", "admin", "operator"),  # 完整产品侧角色见 YAML 配置
    TIER_EDGE: ("*",),
}


def load_tier_approval_roles() -> Dict[str, tuple]:
    """Load tier→approval-roles matrix from tier_approval_roles.yaml (fallback to safe default)."""
    cfg_path = os.path.join(os.path.dirname(__file__), "tier_approval_roles.yaml")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        roles = raw.get("tier_approval_roles") or {}
        result = {}
        for tier, role_list in roles.items():
            if isinstance(role_list, list):
                result[tier] = tuple(str(r) for r in role_list)
        if result:
            return result
    except Exception:
        logger.debug("Failed to load tier_approval_roles.yaml, using defaults", exc_info=True)
    return dict(_DEFAULT_TIER_APPROVAL_ROLES)


TIER_APPROVAL_ROLES = load_tier_approval_roles()

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

    def _history_dir(self) -> str:
        d = os.path.join(_ontology_base(), "history")
        os.makedirs(d, exist_ok=True)
        return d

    def _parse_version_sidecar(self, filename: str) -> Optional[int]:
        """Return N for ``{domain}_vN.yaml`` belonging to this domain; else None."""
        m = _VERSION_SIDECAR_RE.match(filename)
        if not m:
            return None
        if m.group(1) != self.domain_id:
            return None
        return int(m.group(2))

    def _migrate_live_version_sidecars(self) -> None:
        """Move live ``{domain}_vN.yaml`` into history/ (legacy Path A layout).

        Old apply wrote version sidecars next to the live pointer; domain list
        scanners treated them as separate domains. Keep only ``{domain}.yaml`` live.
        """
        base = _ontology_base()
        if not os.path.isdir(base):
            return
        hist = self._history_dir()
        for f in list(os.listdir(base)):
            ver = self._parse_version_sidecar(f)
            if ver is None:
                continue
            src = os.path.join(base, f)
            if not os.path.isfile(src):
                continue
            dst = os.path.join(hist, f)
            if os.path.exists(dst):
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                dst = os.path.join(hist, f"{self.domain_id}_v{ver}_migrated_{stamp}.yaml")
            try:
                shutil.move(src, dst)
                logger.info("Migrated version sidecar %s → %s", src, dst)
            except OSError:
                logger.debug("migrate sidecar failed for %s", src, exc_info=True)

    def get_current_version(self) -> int:
        """Return the highest version number found in history/ (and migrate live leftovers)."""
        self._migrate_live_version_sidecars()
        versions: List[int] = []
        for directory in (_ontology_base(), self._history_dir()):
            if not os.path.isdir(directory):
                continue
            for f in os.listdir(directory):
                ver = self._parse_version_sidecar(f)
                if ver is not None:
                    versions.append(ver)
        return max(versions) if versions else 0

    def _version_path(self, version: int) -> str:
        """Canonical archive path — always under history/, never the live listing dir."""
        return os.path.join(self._history_dir(), f"{self.domain_id}_v{version}.yaml")

    def _legacy_live_version_path(self, version: int) -> str:
        """Pre-fix accidental live sidecar path (migrated on read)."""
        return os.path.join(_ontology_base(), f"{self.domain_id}_v{version}.yaml")

    def _legacy_path(self) -> str:
        return os.path.join(_ontology_base(), f"{self.domain_id}.yaml")

    def load_current(self) -> Dict:
        """Load the live pointer YAML; fall back to highest history version if missing."""
        self._migrate_live_version_sidecars()
        legacy = self._legacy_path()
        if os.path.exists(legacy):
            with open(legacy, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        v = self.get_current_version()
        if v > 0:
            path = self._version_path(v)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
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

    async def approve_proposal(
        self,
        proposal_id: str,
        approver_role: str = "",
        *,
        gate_passed: bool = False,
    ) -> Dict[str, Any]:
        """Record approval. Role matrix runs only when PolicyGate has not already decided."""
        await self.store.initialize()
        proposal = await self.store.get_ontology_proposal(proposal_id)
        if not proposal:
            return {"success": False, "status": "not_found", "reason": "proposal not found"}
        if proposal.get("status") != "draft":
            return {"success": False, "status": proposal.get("status"), "reason": f"proposal is {proposal.get('status')}, not draft"}

        impact = json.loads(proposal.get("impact_analysis", "{}")) or {}
        max_tier = impact.get("max_tier", TIER_LOGIC)
        role = (approver_role or "").strip().lower()
        if not gate_passed:
            allowed = TIER_APPROVAL_ROLES.get(max_tier, (TIER_LOGIC,))
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

    async def apply_proposal(self, proposal_id: str) -> Dict[str, Any]:
        """Apply an approved proposal: generate new version YAML, archive old.

        Returns receipt ``{ok, proposal_id, version_from, version_to, live_path, reason?}``.

        P2-L1 tier gate (plan-tier-ontology-layering.md §3):
          - max_tier == core  → 必须已通过架构评审（approval_level == architecture_review）
          - edge→logic 升格    → 必须携带复用证明（promotion_proof.reuse_count ≥ 3）
          - 任何到 core 的升格  → 必须已通过架构评审
        """
        await self.store.initialize()
        proposal = await self.store.get_ontology_proposal(proposal_id)
        if not proposal or proposal.get("status") != "approved":
            logger.warning("Proposal %s not found or not approved", proposal_id)
            return {
                "ok": False,
                "proposal_id": proposal_id,
                "reason": "not_found_or_not_approved",
            }

        current_v = int(proposal.get("version_from", "0"))
        new_v = int(proposal.get("version_to", "1"))
        current_data = self.load_current()
        changes = json.loads(proposal.get("changes", "{}"))
        impact = json.loads(proposal.get("impact_analysis", "{}")) or {}

        # ── P2-L1 tier gate ──
        gate = self._check_tier_gate(current_data, changes, impact)
        if gate is not None:
            logger.warning("Proposal %s blocked by tier gate: %s", proposal_id, gate)
            return {
                "ok": False,
                "proposal_id": proposal_id,
                "reason": f"tier_gate:{gate}",
                "version_from": current_v,
                "version_to": new_v,
            }

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

        classes_added: List[str] = []
        # Apply changes to current data
        for action, payload in changes.items():
            if action == "add" and isinstance(payload, dict):
                if "class" in payload:
                    new_cls = payload["class"]
                    if isinstance(new_cls, dict) and "name" in new_cls:
                        classes_list.append(dict(new_cls))
                        classes_added.append(str(new_cls["name"]))
                    elif isinstance(new_cls, dict):
                        for _n, _d in new_cls.items():
                            entry = dict(_d) if isinstance(_d, dict) else {}
                            entry.setdefault("name", _n)
                            classes_list.append(entry)
                            classes_added.append(str(_n))
                if "property" in payload:
                    current_data.setdefault("object_properties", []).append(payload["property"])
            elif action == "deprecate" and isinstance(payload, list):
                for class_name in payload:
                    c = _find(class_name)
                    if c is not None:
                        c["deprecated"] = True
            elif action == "remove" and isinstance(payload, list):
                # Hard-delete classes (dirty-class hygiene). Also drop props that reference them.
                drop = {str(x) for x in payload if x}
                if drop:
                    classes_list = [c for c in classes_list if str(c.get("name") or "") not in drop]
                    props = current_data.get("object_properties")
                    if isinstance(props, list):
                        def _refers(p: Any) -> bool:
                            if not isinstance(p, dict):
                                return False
                            blob = " ".join(
                                str(p.get(k) or "")
                                for k in ("domain", "range", "from", "to", "name", "uri")
                            )
                            return any(n in blob for n in drop)

                        current_data["object_properties"] = [p for p in props if not _refers(p)]
            elif action == "split" and isinstance(payload, dict):
                old_name = payload.get("source", "")
                c = _find(old_name)
                if c is not None:
                    c["deprecated"] = True
                for nc in (payload.get("into") or []):
                    if isinstance(nc, dict) and "name" in nc:
                        classes_list.append(dict(nc))
                        classes_added.append(str(nc["name"]))
                    elif isinstance(nc, dict):
                        for _n, _d in nc.items():
                            entry = dict(_d) if isinstance(_d, dict) else {}
                            entry.setdefault("name", _n)
                            classes_list.append(entry)
                            classes_added.append(str(_n))
            elif action == "merge" and isinstance(payload, dict):
                sources = payload.get("sources", [])
                for s in sources:
                    c = _find(s)
                    if c is not None:
                        c["deprecated"] = True
                target = payload.get("into", {})
                if isinstance(target, dict) and "name" in target:
                    classes_list.append(dict(target))
                    classes_added.append(str(target["name"]))
                elif isinstance(target, dict):
                    for _n, _d in target.items():
                        entry = dict(_d) if isinstance(_d, dict) else {}
                        entry.setdefault("name", _n)
                        classes_list.append(entry)
                        classes_added.append(str(_n))

        # Restore original classes layout
        if isinstance(classes_layout, dict):
            current_data["classes"] = {c.get("name", ""): {k: v for k, v in c.items() if k != "name"} for c in classes_list}
        else:
            current_data["classes"] = classes_list

        # Apply axiom additions (runtime semantic constraints — P2 mid/deep)
        for action, payload in changes.items():
            if action != "add" or not isinstance(payload, dict):
                continue
            axioms_list = current_data.setdefault("axioms", [])
            if not isinstance(axioms_list, list):
                axioms_list = []
                current_data["axioms"] = axioms_list
            if isinstance(payload.get("axiom"), dict):
                axioms_list.append(dict(payload["axiom"]))
            for ax in (payload.get("axioms") or []):
                if isinstance(ax, dict):
                    axioms_list.append(dict(ax))

        # Archive previous version sidecar (history or legacy live) then write new
        # version under history/ + rewrite live pointer only.
        history_dir = self._history_dir()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        # Deterministic pre-apply snapshot for rollback (keyed by proposal_id)
        rollback_snap = os.path.join(history_dir, f"{self.domain_id}_pre_{proposal_id}.yaml")
        pre_apply = self.load_current()
        with open(rollback_snap, "w", encoding="utf-8") as f:
            yaml.dump(pre_apply or {}, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        diff = json_change_diff(pre_apply or {}, current_data)
        safe_id = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(proposal_id))[:80]
        diff_path = os.path.join(history_dir, f"{self.domain_id}_diff_{safe_id}.json")
        with open(diff_path, "w", encoding="utf-8") as f:
            json.dump(diff, f, ensure_ascii=False, indent=2)

        if current_v > 0:
            for old_path in (self._version_path(current_v), self._legacy_live_version_path(current_v)):
                if os.path.exists(old_path):
                    dest = os.path.join(history_dir, f"{self.domain_id}_v{current_v}_{stamp}.yaml")
                    if os.path.abspath(old_path) == os.path.abspath(dest):
                        continue
                    if os.path.exists(dest):
                        dest = os.path.join(
                            history_dir,
                            f"{self.domain_id}_v{current_v}_{stamp}_{int(time.time())}.yaml",
                        )
                    shutil.move(old_path, dest)
                    break
        legacy = self._legacy_path()
        if os.path.exists(legacy):
            # Keep a dated archive; live pointer will be rewritten below
            shutil.copy2(
                legacy,
                os.path.join(history_dir, f"{self.domain_id}_legacy_{stamp}.yaml"),
            )

        new_path = self._version_path(new_v)
        os.makedirs(_ontology_base(), exist_ok=True)
        from core.harness.knowledge.ontology_yaml_gate import allow_live_yaml_write

        with allow_live_yaml_write():
            with open(new_path, "w", encoding="utf-8") as f:
                yaml.dump(current_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
            with open(legacy, "w", encoding="utf-8") as f:
                yaml.dump(current_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

        impact["rollback_snapshot"] = rollback_snap
        impact["change_diff"] = diff_path
        impact["applied_at"] = datetime.now(timezone.utc).isoformat()
        await self.store.update_ontology_proposal_impact(proposal_id, json.dumps(impact, ensure_ascii=False))

        # Mark proposal as applied
        await self.store.update_ontology_proposal_status(proposal_id, "applied")
        logger.info("Proposal %s applied: v%s → v%s", proposal_id, current_v, new_v)
        return {
            "ok": True,
            "proposal_id": proposal_id,
            "domain_id": self.domain_id,
            "version_from": current_v,
            "version_to": new_v,
            "live_path": legacy,
            "version_path": new_path,
            "rollback_snapshot": rollback_snap,
            "change_diff": diff_path,
            "diff_count": diff.get("count"),
            "classes_added": classes_added,
            "path": "A",
        }

    async def rollback_proposal(self, proposal_id: str) -> Dict[str, Any]:
        """Restore live YAML from pre-apply snapshot. Only for status=applied."""
        await self.store.initialize()
        proposal = await self.store.get_ontology_proposal(proposal_id)
        if not proposal:
            return {"ok": False, "proposal_id": proposal_id, "reason": "not_found"}
        if proposal.get("status") != "applied":
            return {
                "ok": False,
                "proposal_id": proposal_id,
                "reason": f"status_is_{proposal.get('status')}",
            }
        impact = json.loads(proposal.get("impact_analysis") or "{}") or {}
        snap = str(impact.get("rollback_snapshot") or "")
        if not snap or not os.path.isfile(snap):
            # Fallback: dated legacy archive is not proposal-keyed; require snapshot
            return {"ok": False, "proposal_id": proposal_id, "reason": "rollback_snapshot_missing"}

        with open(snap, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        version_from = int(proposal.get("version_from") or 0)
        version_to = int(proposal.get("version_to") or 0)
        legacy = self._legacy_path()
        os.makedirs(_ontology_base(), exist_ok=True)
        from core.harness.knowledge.ontology_yaml_gate import allow_live_yaml_write

        with allow_live_yaml_write():
            with open(legacy, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
            if version_from > 0:
                with open(self._version_path(version_from), "w", encoding="utf-8") as f:
                    yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        # Drop rolled-forward version file if present (history or legacy live)
        if version_to > 0:
            history_dir = self._history_dir()
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            for to_path in (self._version_path(version_to), self._legacy_live_version_path(version_to)):
                if os.path.isfile(to_path):
                    shutil.move(
                        to_path,
                        os.path.join(history_dir, f"{self.domain_id}_v{version_to}_rolled_{stamp}.yaml"),
                    )

        impact["rolled_back_at"] = datetime.now(timezone.utc).isoformat()
        await self.store.update_ontology_proposal_impact(proposal_id, json.dumps(impact, ensure_ascii=False))
        await self.store.update_ontology_proposal_status(proposal_id, "rolled_back")
        logger.info("Proposal %s rolled back to v%s", proposal_id, version_from)
        return {
            "ok": True,
            "proposal_id": proposal_id,
            "domain_id": self.domain_id,
            "restored_version": version_from,
            "live_path": legacy,
            "status": "rolled_back",
        }

    async def try_auto_apply_edge_proposal(
        self,
        proposal_id: str,
        *,
        actor: str = "edge-auto",
    ) -> Dict[str, Any]:
        """Opt-in edge-only auto approve→apply. Never for logic/core or promotions upward.

        Gated by caller env check; this method still re-validates max_tier == edge.
        """
        await self.store.initialize()
        proposal = await self.store.get_ontology_proposal(proposal_id)
        if not proposal:
            return {"ok": False, "auto_applied": False, "reason": "not_found", "proposal_id": proposal_id}
        impact = json.loads(proposal.get("impact_analysis") or "{}") or {}
        max_tier = normalize_tier(impact.get("max_tier"))
        if max_tier != TIER_EDGE:
            return {
                "ok": False,
                "auto_applied": False,
                "reason": f"max_tier_not_edge:{max_tier}",
                "proposal_id": proposal_id,
            }
        for prom in impact.get("promotions") or []:
            to_tier = normalize_tier(prom.get("to"))
            if to_tier in (TIER_LOGIC, TIER_CORE):
                return {
                    "ok": False,
                    "auto_applied": False,
                    "reason": "blocks_upward_promotion",
                    "proposal_id": proposal_id,
                }

        if proposal.get("status") == "draft":
            appr = await self.approve_proposal(proposal_id, approver_role=actor or "edge-auto")
            if not appr.get("success"):
                return {
                    "ok": False,
                    "auto_applied": False,
                    "reason": appr.get("reason") or "approve_failed",
                    "proposal_id": proposal_id,
                    "approve": appr,
                }
        proposal = await self.store.get_ontology_proposal(proposal_id) or {}
        status = proposal.get("status")
        if status == "applied":
            return {
                "ok": True,
                "auto_applied": True,
                "already_applied": True,
                "proposal_id": proposal_id,
            }
        if status != "approved":
            return {
                "ok": False,
                "auto_applied": False,
                "reason": f"bad_status:{status}",
                "proposal_id": proposal_id,
            }

        receipt = await self.apply_proposal(proposal_id)
        receipt["auto_applied"] = bool(receipt.get("ok"))
        receipt["auto_apply_actor"] = actor
        return receipt

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
                ax_n = 0
                if isinstance(payload.get("axiom"), dict):
                    ax_n += 1
                ax_n += len([a for a in (payload.get("axioms") or []) if isinstance(a, dict)])
                if ax_n:
                    impact["axioms_added"] = int(impact.get("axioms_added") or 0) + ax_n

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
        elif int(impact.get("axioms_added") or 0) > 0:
            # Axiom-only proposals are edge-tier (self-service) by default
            impact["max_tier"] = TIER_EDGE
        return impact
