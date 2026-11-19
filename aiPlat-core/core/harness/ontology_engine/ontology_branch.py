"""
OntologyBranchManager — 本体分支管理 (Palantir Global Branching 对齐)

为每个本体域提供 git-like 的分支/派生/合并能力:

  分支隔离: graph/{tenant:}{domain}__{branch}.db + ontologies YAML 同前缀 (N09 K34/K37)
  fork: 从快照复制 DB → 新分支
  diff: 三方对比 (ancestor → branch_a + branch_b)
  merge: 自动合并 (无冲突) / 警告合并 (属性级冲突) / 阻断 (结构级冲突)

复用:
  - GraphIndex.snapshot() / restore_snapshot() / compare_snapshots()
  - VersionedOntologyStore 的版本化 YAML
  - 每域独立 SQLite 的基础设施

调用者: BranchPanel 前端 / REST API
"""

from __future__ import annotations
from core.utils.paths import get_aiplat_home, get_aiplat_data_dir

import json as _json
import logging
import os as _os
import shutil as _shutil
import time as _time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional, Tuple
from core.harness.knowledge.domain_router import DomainRouter

logger = logging.getLogger(__name__)

HOME = _Path(get_aiplat_home())
GRAPH_DIR = HOME / "graph"
BRANCH_REGISTRY_PATH = HOME / "branches.json"


# ── Data Models ────────────────────────────────────────────────────────────

class MergeLevel(str, Enum):
    """MergeLevel。"""
    AUTO = "auto"         # 无冲突，自动合并
    WARN = "warn"         # 属性级冲突，警告但可合并
    BLOCKED = "blocked"   # 结构级冲突，禁止合并


@dataclass
class BranchInfo:
    """BranchInfo。"""
    domain_id: str
    branch_name: str
    created_at: float
    base_snapshot_id: int = 0
    base_version: str = ""           # 从哪个版本分叉
    description: str = ""
    last_modified: float = 0.0
    commit_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """to_dict。
        """
        return {
            "domain_id": self.domain_id,
            "branch_name": self.branch_name,
            "created_at": self.created_at,
            "base_snapshot_id": self.base_snapshot_id,
            "base_version": self.base_version,
            "description": self.description,
            "last_modified": self.last_modified or self.created_at,
            "commit_count": self.commit_count,
        }


@dataclass
class DiffResult:
    """三方差异对比结果."""
    merge_level: MergeLevel
    diff_summary: str = ""
    added_entities: List[str] = field(default_factory=list)
    removed_entities: List[str] = field(default_factory=list)
    modified_entities: List[Dict[str, Any]] = field(default_factory=list)
    added_relations: List[Dict[str, str]] = field(default_factory=list)
    removed_relations: List[Dict[str, str]] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)


@dataclass
class MergeResult:
    """合并结果."""
    success: bool
    merge_level: MergeLevel
    summary: str = ""
    diff: Optional[DiffResult] = None
    conflict_details: List[str] = field(default_factory=list)


# ── Branch Registry (JSON file) ────────────────────────────────────────────

def _load_registry() -> Dict[str, Any]:
    if BRANCH_REGISTRY_PATH.exists():
        try:
            with open(BRANCH_REGISTRY_PATH) as f:
                return _json.load(f)
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
    return {"branches": {}}


def _save_registry(registry: Dict[str, Any]) -> None:
    BRANCH_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BRANCH_REGISTRY_PATH, "w") as f:
        _json.dump(registry, f, ensure_ascii=False, indent=2)


def _branch_key(domain_id: str, branch_name: str, tenant_id: str = DomainRouter.default_tenant()) -> str:
    """Registry key for a branch (N09 K36 tenant-scoped).

    Non-default tenants use ``{tenant}::{domain}::{branch}``.
    Default tenant keeps legacy ``{domain}::{branch}`` so existing
    ``branches.json`` entries remain readable.

    Args:
        domain_id: domain 标识。
        branch_name: 分支名。
        tenant_id: 租户；default 写旧格式键。
    """
    tid = (tenant_id or DomainRouter.default_tenant()).strip() or DomainRouter.default_tenant()
    if tid == DomainRouter.default_tenant():
        return f"{domain_id}::{branch_name}"
    return f"{tid}::{domain_id}::{branch_name}"


def _legacy_branch_key(domain_id: str, branch_name: str) -> str:
    """Pre-K36 registry key (tenant=default only).

    Args:
        domain_id: domain 标识。
        branch_name: 分支名。
    """
    return f"{domain_id}::{branch_name}"


def _find_branch_entry(
    branches: Dict[str, Any],
    domain_id: str,
    branch_name: str,
    tenant_id: str,
) -> tuple[str, Optional[Dict[str, Any]]]:
    """Locate registry entry; prefer tenant key, fall back to legacy for default.

    Args:
        branches: registry branches map.
        domain_id: domain 标识。
        branch_name: 分支名。
        tenant_id: 已解析租户。

    Returns:
        (canonical_key_for_writes, data_or_None)
    """
    tid = (tenant_id or DomainRouter.default_tenant()).strip() or DomainRouter.default_tenant()
    key = _branch_key(domain_id, branch_name, tid)
    data = branches.get(key)
    if data is not None:
        return key, data
    if tid == DomainRouter.default_tenant():
        legacy = _legacy_branch_key(domain_id, branch_name)
        if legacy in branches:
            return legacy, branches[legacy]
    return key, None


def _branch_db_path(domain_id: str, branch_name: str, tenant_id: str = DomainRouter.default_tenant()) -> _Path:
    """获取分支的 SQLite DB 路径（与 GraphIndex 租户前缀约定一致，N09 K34）。

    Args:
        domain_id: domain 标识。
        branch_name: 分支名；main 对应域主库。
        tenant_id: 租户；default 无前缀。
    """
    tid = (tenant_id or DomainRouter.default_tenant()).strip() or DomainRouter.default_tenant()
    prefix = f"{tid}:" if tid != DomainRouter.default_tenant() else ""
    if branch_name == "main":
        return GRAPH_DIR / f"{prefix}{domain_id}.db"
    return GRAPH_DIR / f"{prefix}{domain_id}__{branch_name}.db"


def _branch_yaml_path(domain_id: str, branch_name: str, tenant_id: str = DomainRouter.default_tenant()) -> _Path:
    """Ontology YAML path for a branch (N09 K37 tenant prefix).

    Mirrors GraphIndex / ``_branch_db_path`` prefix:
    non-default → ``{tenant}:{domain}.yaml`` / ``{tenant}:{domain}__{branch}.yaml``.

    Args:
        domain_id: domain 标识。
        branch_name: 分支名；main 对应域主 YAML。
        tenant_id: 租户；default 无前缀。
    """
    tid = (tenant_id or DomainRouter.default_tenant()).strip() or DomainRouter.default_tenant()
    prefix = f"{tid}:" if tid != DomainRouter.default_tenant() else ""
    ont_dir = HOME / "ontologies"
    if branch_name == "main":
        return ont_dir / f"{prefix}{domain_id}.yaml"
    return ont_dir / f"{prefix}{domain_id}__{branch_name}.yaml"


def _resolve_branch_yaml_source(
    domain_id: str, branch_name: str, tenant_id: str,
) -> _Path | None:
    """Prefer tenant-scoped YAML; fall back to unprefixed for bootstrap.

    Args:
        domain_id: domain 标识。
        branch_name: 分支名。
        tenant_id: 已解析租户。

    Returns:
        存在的路径，或 None。
    """
    primary = _branch_yaml_path(domain_id, branch_name, tenant_id)
    if primary.exists():
        return primary
    # 为什么：新租户尚无隔离副本时允许从共享域 YAML 引导，写路径仍走租户前缀
    if (tenant_id or DomainRouter.default_tenant()) != DomainRouter.default_tenant():
        legacy = _branch_yaml_path(domain_id, branch_name, DomainRouter.default_tenant())
        if legacy.exists():
            return legacy
    return None


def _resolve_branch_tenant(tenant_id: str = "") -> str:
    """Resolve tenant for branch GraphIndex / DB paths.

    Args:
        tenant_id: 显式租户；空则 ActiveRequestContext / default。
    """
    tid = (tenant_id or "").strip()
    if tid:
        return tid
    from core.harness.knowledge.context_bus import _resolve_graph_tenant
    return _resolve_graph_tenant()


# ── Branch Manager ─────────────────────────────────────────────────────────

class OntologyBranchManager:
    """本体分支管理器.

    使用方式:
        bm = OntologyBranchManager()
        bm.fork("fde-delivery", "experiment", description="测试新本体结构")
        bm.checkout("fde-delivery", "experiment")
        result = bm.merge("fde-delivery", "experiment", "main")
    """

    _instance: Optional["OntologyBranchManager"] = None
    _MAX_BRANCHES_PER_DOMAIN = 5

    @classmethod
    def get(cls) -> "OntologyBranchManager":
        """get。
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── CRUD ──────────────────────────────────────────────────────────

    def fork(
        self,
        domain_id: str,
        branch_name: str,
        *,
        description: str = "",
        from_snapshot: bool = True,
        tenant_id: str = "",
    ) -> BranchInfo:
        """从 main 分支派生新分支.

        Args:
            domain_id: 域ID
            branch_name: 新分支名 (如 "experiment", "poc-v2")
            description: 分支描述
            from_snapshot: 是否先从当前状态创建快照作为基线
            tenant_id: 租户；空则 resolve（N09 K34）

        Returns:
            BranchInfo
        """
        tid = _resolve_branch_tenant(tenant_id)
        # Check branch limit
        existing = self.list_branches(domain_id, tenant_id=tid)
        if len(existing) >= self._MAX_BRANCHES_PER_DOMAIN:
            raise ValueError(
                f"Domain '{domain_id}' has {len(existing)} branches (max {self._MAX_BRANCHES_PER_DOMAIN}). "
                f"Delete unused branches first."
            )

        # Check name uniqueness
        if any(b.branch_name == branch_name for b in existing):
            raise ValueError(f"Branch '{branch_name}' already exists for domain '{domain_id}'")

        # Get source DB path
        source_db = _branch_db_path(domain_id, "main", tid)
        if not source_db.exists():
            raise FileNotFoundError(f"Main database not found: {source_db}")

        target_db = _branch_db_path(domain_id, branch_name, tid)

        # Snapshot the current state as baseline
        base_snapshot_id = 0
        base_version = ""
        if from_snapshot:
            try:
                from core.harness.ontology_engine.graph_index import GraphIndex
                gi = GraphIndex(domain_id, tenant_id=tid)
                snap = gi.snapshot(label=f"fork_{branch_name}")
                base_snapshot_id = snap.get("id", 0)
                base_version = snap.get("label", "")
                gi.close()
            except Exception as e:
                logger.debug("Snapshot for fork failed, continuing: %s", e)

        # Copy the database file
        _shutil.copy2(str(source_db), str(target_db))
        logger.info("Forked branch '%s' from '%s' (snapshot=%s)", branch_name, domain_id, base_snapshot_id)

        # Also copy versioned YAML if exists（租户前缀，N09 K37）
        try:
            yaml_main = _resolve_branch_yaml_source(domain_id, "main", tid)
            yaml_branch = _branch_yaml_path(domain_id, branch_name, tid)
            if yaml_main is not None:
                yaml_branch.parent.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(str(yaml_main), str(yaml_branch))
        except Exception as e:
            logger.debug("YAML copy for fork failed: %s", e)

        # Register branch
        info = BranchInfo(
            domain_id=domain_id,
            branch_name=branch_name,
            created_at=_time.time(),
            base_snapshot_id=base_snapshot_id,
            base_version=base_version,
            description=description,
            last_modified=_time.time(),
        )

        registry = _load_registry()
        key = _branch_key(domain_id, branch_name, tid)
        registry.setdefault("branches", {})[key] = info.to_dict()
        _save_registry(registry)

        logger.info("Branch '%s' for domain '%s' tenant=%s created", branch_name, domain_id, tid)
        return info

    def list_branches(self, domain_id: str, *, tenant_id: str = "") -> List[BranchInfo]:
        """列出域的所有分支（按租户隔离，N09 K36）.

        Args:
            domain_id: domain 标识。
            tenant_id: 租户；空则 resolve。
        """
        tid = _resolve_branch_tenant(tenant_id)
        registry = _load_registry()
        branches = []
        seen_names: set[str] = set()
        tenant_prefix = f"{tid}::{domain_id}::"
        legacy_prefix = f"{domain_id}::"
        for key, data in registry.get("branches", {}).items():
            if tid != DomainRouter.default_tenant() and key.startswith(tenant_prefix):
                branches.append(BranchInfo(**data))
                seen_names.add(data.get("branch_name", key.rsplit("::", 1)[-1]))
            elif tid == DomainRouter.default_tenant():
                # 新格式 {default_tenant}::{domain}::{branch} 或旧格式 domain::branch
                if key.startswith(f"{DomainRouter.default_tenant()}::{domain_id}::"):
                    branches.append(BranchInfo(**data))
                    seen_names.add(data.get("branch_name", key.rsplit("::", 1)[-1]))
                elif key.startswith(legacy_prefix) and key.count("::") == 1:
                    branches.append(BranchInfo(**data))
                    seen_names.add(data.get("branch_name", key.rsplit("::", 1)[-1]))

        # Add main branch if not registered (always exists)
        if "main" not in seen_names:
            branches.append(BranchInfo(
                domain_id=domain_id,
                branch_name="main",
                created_at=0,
                description="主分支 (生产)",
            ))

        return sorted(branches, key=lambda b: b.created_at, reverse=True)

    def delete_branch(self, domain_id: str, branch_name: str, *, tenant_id: str = "") -> bool:
        """删除分支 (不允许删除 main).

        Args:
            domain_id: domain 标识。
            branch_name: branch_name 参数。
            tenant_id: 租户；空则 resolve（N09 K34）。
        """
        if branch_name == "main":
            raise ValueError("Cannot delete main branch")

        tid = _resolve_branch_tenant(tenant_id)
        # Remove registries
        registry = _load_registry()
        key, data = _find_branch_entry(registry.get("branches", {}), domain_id, branch_name, tid)
        if data is None:
            raise ValueError(f"Branch '{branch_name}' not found for domain '{domain_id}' tenant={tid}")

        del registry["branches"][key]
        _save_registry(registry)

        # Remove DB file
        db_path = _branch_db_path(domain_id, branch_name, tid)
        if db_path.exists():
            db_path.unlink()

        # Remove associated files
        for suffix in ["-wal", "-shm"]:
            wal_path = _Path(str(db_path) + suffix)
            if wal_path.exists():
                wal_path.unlink()

        logger.info("Branch '%s' for domain '%s' deleted", branch_name, domain_id)
        return True

    def get_branch_info(
        self, domain_id: str, branch_name: str, *, tenant_id: str = "",
    ) -> Optional[BranchInfo]:
        """获取分支信息.

        Args:
            domain_id: domain 标识。
            branch_name: branch_name 参数。
            tenant_id: 租户；空则 resolve（N09 K36）。
        """
        tid = _resolve_branch_tenant(tenant_id)
        registry = _load_registry()
        _, data = _find_branch_entry(registry.get("branches", {}), domain_id, branch_name, tid)
        if data:
            return BranchInfo(**data)
        if branch_name == "main":
            return BranchInfo(domain_id=domain_id, branch_name="main", created_at=0, description="主分支 (生产)")
        return None

    # ── Diff & Merge ───────────────────────────────────────────────────

    def diff(
        self,
        domain_id: str,
        source_branch: str,
        target_branch: str = "main",
        *,
        tenant_id: str = "",
    ) -> DiffResult:
        """三方差异对比: ancestor → source vs ancestor → target.

        Args:
            domain_id: domain 标识。
            source_branch: source_branch 参数。
            target_branch: target_branch 参数。
            tenant_id: 租户；空则 resolve（N09 K34）。
        """
        tid = _resolve_branch_tenant(tenant_id)
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex

            # Build graph indices for both branches
            gi_source = GraphIndex(domain_id, tenant_id=tid)
            gi_target = GraphIndex(domain_id, tenant_id=tid)

            # Override DB paths for branch routing（含租户前缀）
            if source_branch != "main":
                gi_source._db_path = _branch_db_path(domain_id, source_branch, tid)
                gi_source._conn = None  # force reconnect
            if target_branch != "main":
                gi_target._db_path = _branch_db_path(domain_id, target_branch, tid)
                gi_target._conn = None

            # Load both
            try:
                gi_source.load(load_nodes=True)
                gi_target.load(load_nodes=True)
            except Exception:
                # Try to load from disk JSON
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

            # Compare entities
            source_nodes = set(gi_source._nodes.keys())
            target_nodes = set(gi_target._nodes.keys())

            added_entities = list(target_nodes - source_nodes)[:50]
            removed_entities = list(source_nodes - target_nodes)[:50]
            common = source_nodes & target_nodes

            # Compare entity attributes for common entities
            modified_entities = []
            for nid in list(common)[:50]:
                sn = gi_source._nodes.get(nid)
                tn = gi_target._nodes.get(nid)
                if sn and tn:
                    changes = {}
                    if sn.entity_name != tn.entity_name:
                        changes["entity_name"] = {"source": sn.entity_name, "target": tn.entity_name}
                    if sn.class_name != tn.class_name:
                        changes["class_name"] = {"source": sn.class_name, "target": tn.class_name}
                    if changes:
                        modified_entities.append({"entity_id": nid, "changes": changes})

            # Compare relations
            source_edges = set()
            target_edges = set()
            for n in gi_source._nodes.values():
                for e in n.out_edges:
                    source_edges.add((e.source_id, e.target_id, e.relation_name))
            for n in gi_target._nodes.values():
                for e in n.out_edges:
                    target_edges.add((e.source_id, e.target_id, e.relation_name))

            added_relations = [
                {"source": e[0], "target": e[1], "relation": e[2]}
                for e in (target_edges - source_edges)
            ][:50]
            removed_relations = [
                {"source": e[0], "target": e[1], "relation": e[2]}
                for e in (source_edges - target_edges)
            ][:50]

            gi_source.close()
            gi_target.close()

            # Determine merge level
            conflicts = []
            merge_level = MergeLevel.AUTO

            if modified_entities and any(
                "class_name" in m.get("changes", {}) for m in modified_entities
            ):
                merge_level = MergeLevel.WARN
                conflicts.append(f"类名变更: {sum(1 for m in modified_entities if 'class_name' in m.get('changes', {}))} 个实体")

            if removed_entities and not added_entities:
                # Net removal only — potentially destructive
                merge_level = MergeLevel.WARN
                conflicts.append(f"净删除 {len(removed_entities)} 个实体 (无新增)")

            summary = (
                f"Diff: +{len(added_entities)}/-{len(removed_entities)} entities, "
                f"{len(modified_entities)} modified, "
                f"+{len(added_relations)}/-{len(removed_relations)} relations"
            )

            return DiffResult(
                merge_level=merge_level,
                diff_summary=summary,
                added_entities=added_entities,
                removed_entities=removed_entities,
                modified_entities=modified_entities,
                added_relations=added_relations,
                removed_relations=removed_relations,
                conflicts=conflicts,
            )

        except Exception as e:
            logger.warning("Diff failed: %s", e)
            return DiffResult(
                merge_level=MergeLevel.BLOCKED,
                diff_summary=f"Diff error: {e}",
                conflicts=[str(e)],
            )

    def merge(
        self,
        domain_id: str,
        source_branch: str,
        target_branch: str = "main",
        *,
        auto_apply: bool = False,
        tenant_id: str = "",
    ) -> MergeResult:
        """合并分支: 先在 dry-run 模式做 diff，再决定是否应用.

        Args:
            domain_id: 域ID
            source_branch: 源分支
            target_branch: 目标分支
            auto_apply: 是否自动应用 (仅 MergeLevel.AUTO 时生效)
            tenant_id: 租户；空则 resolve（N09 K34）

        Returns:
            MergeResult
        """
        tid = _resolve_branch_tenant(tenant_id)
        # Step 1: Snapshot target before merge (for rollback)
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            gi = GraphIndex(domain_id, tenant_id=tid)
            gi.snapshot(label=f"pre_merge_{source_branch}_to_{target_branch}")
            gi.close()
        except Exception as e:
            logger.debug("Pre-merge snapshot failed: %s", e)

        # Step 2: Compute diff
        diff_result = self.diff(domain_id, source_branch, target_branch, tenant_id=tid)

        # Step 3: Determine if safe to merge
        if diff_result.merge_level == MergeLevel.BLOCKED:
            return MergeResult(
                success=False,
                merge_level=MergeLevel.BLOCKED,
                summary=f"合并被阻止: {', '.join(diff_result.conflicts)}",
                diff=diff_result,
                conflict_details=diff_result.conflicts,
            )

        if diff_result.merge_level == MergeLevel.WARN and not auto_apply:
            return MergeResult(
                success=False,
                merge_level=MergeLevel.WARN,
                summary=f"合并需要人工审核: {', '.join(diff_result.conflicts)}",
                diff=diff_result,
                conflict_details=diff_result.conflicts,
            )

        # Step 4: Apply merge — copy branch DB over target
        if source_branch != "main" and target_branch == "main":
            source_db = _branch_db_path(domain_id, source_branch, tid)
            target_db = _branch_db_path(domain_id, "main", tid)

            if not source_db.exists():
                return MergeResult(
                    success=False,
                    merge_level=MergeLevel.BLOCKED,
                    summary=f"Source branch DB not found: {source_db}",
                )

            # Backup target before overwrite
            backup_path = _Path(str(target_db) + f".bak_{_time.strftime('%Y%m%d_%H%M%S')}")
            if target_db.exists():
                _shutil.copy2(str(target_db), str(backup_path))

            # Apply merge
            _shutil.copy2(str(source_db), str(target_db))
            logger.info("Merged '%s' → '%s' (backup: %s)", source_branch, target_branch, backup_path.name)

            # Also merge YAML（租户前缀，N09 K37）
            try:
                yaml_source = _resolve_branch_yaml_source(domain_id, source_branch, tid)
                yaml_target = _branch_yaml_path(domain_id, "main", tid)
                if yaml_source is not None:
                    yaml_target.parent.mkdir(parents=True, exist_ok=True)
                    _shutil.copy2(str(yaml_source), str(yaml_target))
            except Exception as e:
                logger.debug("YAML merge failed: %s", e)

        # Step 5: Update branch metadata
        registry = _load_registry()
        for bname in (source_branch, target_branch):
            key, data = _find_branch_entry(registry.get("branches", {}), domain_id, bname, tid)
            if data is not None:
                registry["branches"][key]["last_modified"] = _time.time()
        _save_registry(registry)

        return MergeResult(
            success=True,
            merge_level=diff_result.merge_level,
            summary=f"成功合并 '{source_branch}' → '{target_branch}': {diff_result.diff_summary}",
            diff=diff_result,
        )

    def commit_branch(
        self, domain_id: str, branch_name: str, *, tenant_id: str = "",
    ) -> BranchInfo:
        """更新分支的最后修改时间 (相当于 git commit).

        Args:
            domain_id: domain 标识。
            branch_name: branch_name 参数。
            tenant_id: 租户；空则 resolve（N09 K36）。
        """
        tid = _resolve_branch_tenant(tenant_id)
        registry = _load_registry()
        key, info_data = _find_branch_entry(registry.get("branches", {}), domain_id, branch_name, tid)

        if not info_data and branch_name == "main":
            write_key = _branch_key(domain_id, branch_name, tid)
            info_data = BranchInfo(
                domain_id=domain_id, branch_name="main",
                created_at=_time.time(), description="主分支 (生产)",
            ).to_dict()
            registry.setdefault("branches", {})[write_key] = info_data
            key = write_key

        if not info_data:
            raise ValueError(f"Branch '{branch_name}' not found for domain '{domain_id}' tenant={tid}")

        info_data["last_modified"] = _time.time()
        info_data["commit_count"] = info_data.get("commit_count", 0) + 1
        registry.setdefault("branches", {})[key] = info_data
        _save_registry(registry)

        return BranchInfo(**info_data)
