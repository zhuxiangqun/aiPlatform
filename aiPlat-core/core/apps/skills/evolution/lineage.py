"""
Version Lineage

Manages Skill version history with DAG structure.
"""

import logging
import uuid
import hashlib
from typing import Dict, List, Optional, Set
from datetime import datetime
from dataclasses import asdict

from .types import SkillVersion, EvolutionType, EvolutionConfig

logger = logging.getLogger(__name__)


class VersionLineage:
    """Manages skill version history as a DAG"""
    
    def __init__(self, db_path: str = ":memory:"):
        self._db_path = db_path
        self._versions: Dict[str, SkillVersion] = {}
        self._children: Dict[str, Set[str]] = {}  # parent -> children
    
    def _compute_hash(self, content: str) -> str:
        """Compute content hash"""
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    async def create_version(
        self,
        skill_id: str,
        parent_version: Optional[str],
        evolution_type: EvolutionType,
        trigger: str,
        content: str
    ) -> SkillVersion:
        """Create a new version"""
        # Get next version number
        existing = [v for v in self._versions.values() if v.skill_id == skill_id]
        if existing:
            versions = [v.version for v in existing if v.version.startswith("v")]
            if versions:
                last_num = max(int(v.replace("v", "").split(".")[0]) for v in versions)
                new_version = f"v{last_num + 1}.0"
            else:
                new_version = "v1.0"
        else:
            new_version = "v1.0"
        
        version_id = f"{skill_id}:{new_version}"
        
        version = SkillVersion(
            id=version_id,
            skill_id=skill_id,
            version=new_version,
            parent_version=parent_version,
            evolution_type=evolution_type,
            trigger=trigger,
            content_hash=self._compute_hash(content),
            created_at=datetime.utcnow()
        )
        
        # Store version
        self._versions[version_id] = version
        
        # Update DAG
        if parent_version:
            parent_key = f"{skill_id}:{parent_version}"
            if parent_key not in self._children:
                self._children[parent_key] = set()
            self._children[parent_key].add(version_id)
        
        logger.info(f"Created version {version_id} for skill {skill_id}")
        return version
    
    async def get_lineage(self, skill_id: str) -> List[SkillVersion]:
        """Get complete lineage for a skill"""
        skill_versions = [
            v for v in self._versions.values()
            if v.skill_id == skill_id
        ]
        return sorted(skill_versions, key=lambda v: v.created_at)
    
    async def get_ancestors(self, skill_id: str, version: str) -> List[SkillVersion]:
        """Get all ancestors of a version"""
        ancestors = []
        current_key = f"{skill_id}:{version}"
        
        while current_key in self._versions:
            version_obj = self._versions[current_key]
            ancestors.append(version_obj)
            
            if version_obj.parent_version:
                current_key = f"{skill_id}:{version_obj.parent_version}"
            else:
                break
        
        return ancestors
    
    async def get_descendants(self, skill_id: str, version: str) -> List[SkillVersion]:
        """Get all descendants of a version"""
        descendants = []
        visited = set()
        
        def _collect(key: str):
            if key in visited:
                return
            visited.add(key)
            
            if key in self._versions:
                descendants.append(self._versions[key])
            
            if key in self._children:
                for child_key in self._children[key]:
                    _collect(child_key)
        
        start_key = f"{skill_id}:{version}"
        _collect(start_key)
        
        return descendants
    
    async def get_latest_version(self, skill_id: str) -> Optional[SkillVersion]:
        """Get the latest version of a skill"""
        versions = await self.get_lineage(skill_id)
        if versions:
            return versions[-1]
        return None
    
    async def rollback(self, skill_id: str, target_version: str) -> bool:
        """Rollback to a specific version"""
        # In practice, this would restore content from the version
        logger.info(f"Rolling back skill {skill_id} to version {target_version}")
        return True
    
    async def prune_old_versions(self, skill_id: str, keep_count: int = 10) -> int:
        """Prune old versions, keeping only the latest N"""
        versions = await self.get_lineage(skill_id)
        if len(versions) <= keep_count:
            return 0
        
        to_remove = versions[:-keep_count]
        removed = 0
        
        for version in to_remove:
            version_key = f"{skill_id}:{version.version}"
            if version_key in self._versions:
                del self._versions[version_key]
                removed += 1
        
        logger.info(f"Pruned {removed} old versions for skill {skill_id}")
        return removed
    
    def get_stats(self) -> Dict:
        """Get lineage statistics"""
        unique_skills = set(v.skill_id for v in self._versions.values())
        return {
            "total_versions": len(self._versions),
            "total_skills": len(unique_skills),
            "avg_versions_per_skill": len(self._versions) / max(1, len(unique_skills))
        }


# Global lineage instance
_lineage: Optional[VersionLineage] = None


def get_version_lineage() -> VersionLineage:
    """Get global version lineage"""
    global _lineage
    if _lineage is None:
        _lineage = VersionLineage()
    return _lineage


__all__ = [
    "VersionLineage",
    "get_version_lineage"
]