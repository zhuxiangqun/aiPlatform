"""
Industry Playbook — export and import industry-specific AI capabilities.

A Playbook bundles Skills, Ontology domains, Pipeline definitions, Policy
rules, and Cleanup rules into a portable .aipb archive (zip format).

v1: Pipeline functions are registered by name (not serialized graphs).
    Upgrade path for cross-environment serialization planned for v2.

Manifest Format (manifest.json):
  {
    "playbook_version": "1.0.0",
    "min_platform_version": "2.3.0",
    "id": "insurance-claims",
    "name": "保险理赔 Playbook",
    "industry": "insurance",
    "version": "1.0.0",
    ...
  }
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("aiplat.playbook")


@dataclass
class PlaybookManifest:
    """Industry Playbook manifest — describes what's in the bundle."""

    id: str
    name: str
    industry: str                           # "insurance" | "finance" | "gov" | "general"
    version: str                            # semantic version
    playbook_version: str = "1.0.0"         # Playbook format version
    min_platform_version: str = "2.3.0"     # Minimum aiPlat version required
    skills: List[str] = field(default_factory=list)
    ontology: List[str] = field(default_factory=list)
    pipelines: List[str] = field(default_factory=list)   # function names (v1)
    policies: List[str] = field(default_factory=list)
    cleanup_rules: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    tags: List[str] = field(default_factory=list)

    # ── Industries ──
    VALID_INDUSTRIES = {"insurance", "finance", "gov", "healthcare",
                         "manufacturing", "retail", "education", "general"}

    def validate(self) -> List[str]:
        """Return list of validation errors. Empty = valid."""
        errors = []
        if not self.id or not re.match(r'^[a-z0-9_-]+$', self.id):
            errors.append("id must be non-empty alphanumeric with dashes")
        if not self.name:
            errors.append("name is required")
        if self.industry not in self.VALID_INDUSTRIES:
            errors.append(f"industry must be one of {self.VALID_INDUSTRIES}")
        if not self.version:
            errors.append("version is required")
        return errors

    def to_dict(self) -> dict:
        return {
            "playbook_version": self.playbook_version,
            "min_platform_version": self.min_platform_version,
            "id": self.id,
            "name": self.name,
            "industry": self.industry,
            "version": self.version,
            "skills": self.skills,
            "ontology": self.ontology,
            "pipelines": self.pipelines,
            "policies": self.policies,
            "cleanup_rules": self.cleanup_rules,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> "PlaybookManifest":
        return cls(
            id=data["id"],
            name=data["name"],
            industry=data.get("industry", "general"),
            version=data.get("version", "1.0.0"),
            playbook_version=data.get("playbook_version", "1.0.0"),
            min_platform_version=data.get("min_platform_version", "2.3.0"),
            skills=data.get("skills", []),
            ontology=data.get("ontology", []),
            pipelines=data.get("pipelines", []),
            policies=data.get("policies", []),
            cleanup_rules=data.get("cleanup_rules", []),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            tags=data.get("tags", []),
        )


# ════════════════════════════════════════════════════════════
# Export / Import
# ════════════════════════════════════════════════════════════

async def pack_playbook(manifest: PlaybookManifest, output_path: str = "") -> str:
    """
    Package skills, ontology, pipelines, policies, and cleanup rules
    into a .aipb zip archive.

    Returns the path to the generated archive.
    """
    manifest.updated_at = time.time()
    errors = manifest.validate()
    if errors:
        raise ValueError(f"Invalid manifest: {errors}")

    export_dir = tempfile.mkdtemp(prefix="playbook_")
    archive_path = output_path or os.path.join(
        tempfile.gettempdir(), f"{manifest.id}-{manifest.version}.aipb"
    )

    try:
        # ── manifest.json ──
        (Path(export_dir) / "manifest.json").write_text(manifest.to_json(), encoding="utf-8")

        # ── Skills ──
        if manifest.skills:
            skills_dir = Path(export_dir) / "skills"
            skills_dir.mkdir(parents=True, exist_ok=True)
            for skill_id in manifest.skills:
                try:
                    from core.apps.skills.registry import SkillRegistry
                    registry = SkillRegistry()
                    skill = registry.get(skill_id)
                    if skill:
                        (skills_dir / f"{skill_id}.json").write_text(
                            json.dumps(skill.to_dict(), indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                except Exception as e:
                    logger.warning("Failed to export skill '%s': %s", skill_id, e)

        # ── Ontology ──
        if manifest.ontology:
            ont_dir = Path(export_dir) / "ontology"
            ont_dir.mkdir(parents=True, exist_ok=True)
            for domain_id in manifest.ontology:
                src = Path(os.path.expanduser(f"~/.aiplat/ontologies/{domain_id}.yaml"))
                if src.exists():
                    import shutil
                    shutil.copy(src, ont_dir / f"{domain_id}.yaml")

        # ── Pipelines (v2: topology JSON, v1: .txt fallback) ──
        if manifest.pipelines:
            pipe_dir = Path(export_dir) / "pipelines"
            pipe_dir.mkdir(parents=True, exist_ok=True)
            for pipe_name in manifest.pipelines:
                try:
                    from core.harness.execution.pipeline_engine import pipeline_to_dict
                    graph_def = pipeline_to_dict(pipe_name)
                    if graph_def:
                        (pipe_dir / f"{pipe_name}.json").write_text(
                            json.dumps(graph_def, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                    else:
                        (pipe_dir / f"{pipe_name}.txt").write_text(pipe_name)
                except Exception as e:
                    logger.warning("Failed to export pipeline '%s': %s", pipe_name, e)

        # ── Policies ──
        if manifest.policies:
            pol_dir = Path(export_dir) / "policies"
            pol_dir.mkdir(parents=True, exist_ok=True)
            for policy_id in manifest.policies:
                (pol_dir / f"{policy_id}.json").write_text(
                    json.dumps({"id": policy_id, "description": f"Policy {policy_id}"}, indent=2),
                    encoding="utf-8",
                )

        # ── Cleanup rules ──
        if manifest.cleanup_rules:
            clean_dir = Path(export_dir) / "cleanup_rules"
            clean_dir.mkdir(parents=True, exist_ok=True)
            for rules_name in manifest.cleanup_rules:
                src = Path(os.path.expanduser(f"~/.aiplat/cleanup_rules/{rules_name}.yaml"))
                if src.exists():
                    import shutil
                    shutil.copy(src, clean_dir / f"{rules_name}.yaml")

        # ── Package as zip ──
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(export_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    arcname = os.path.relpath(fpath, export_dir)
                    zf.write(fpath, arcname)

        logger.info("Playbook exported: %s (%d skills, %d ontologies)",
                      archive_path, len(manifest.skills), len(manifest.ontology))
        return archive_path

    finally:
        import shutil
        shutil.rmtree(export_dir, ignore_errors=True)


async def unpack_playbook(archive_path: str, *,
                          on_conflict: str = "skip") -> Dict[str, Any]:
    """
    Import a .aipb Playbook archive.

    Args:
        archive_path: Path to the .aipb file
        on_conflict: "skip" (default) | "overwrite" | "merge" (YAML only)

    Returns:
        {"imported": {"skills": [...], "ontology": [...], ...}, "skipped": [...]}
    """
    if not os.path.exists(archive_path):
        raise FileNotFoundError(f"Playbook not found: {archive_path}")

    import_dir = tempfile.mkdtemp(prefix="playbook_import_")
    imported = {"skills": [], "ontology": [], "pipelines": [], "policies": [], "cleanup_rules": []}
    skipped = []

    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(import_dir)

        # ── Load and validate manifest ──
        manifest_path = os.path.join(import_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            raise ValueError("Playbook missing manifest.json")

        manifest = PlaybookManifest.from_json(Path(manifest_path).read_text(encoding="utf-8"))

        # Version check
        try:
            from aiplat_sdk import __version__ as platform_ver
        except ImportError:
            platform_ver = "2.0.0"
        if _version_lt(platform_ver, manifest.min_platform_version):
            raise ValueError(
                f"Playbook requires aiPlat >= {manifest.min_platform_version}, "
                f"current: {platform_ver}"
            )

        # ── Import Skills ──
        skills_dir = os.path.join(import_dir, "skills")
        if os.path.isdir(skills_dir):
            from core.apps.skills.registry import SkillRegistry
            registry = SkillRegistry()
            for fname in os.listdir(skills_dir):
                if not fname.endswith(".json"):
                    continue
                skill_id = fname.replace(".json", "")
                if registry.get(skill_id) and on_conflict == "skip":
                    skipped.append(f"skill:{skill_id}")
                    continue
                data = json.loads(Path(skills_dir / fname).read_text(encoding="utf-8"))
                # Store skill definition for later registration
                dest = Path(os.path.expanduser(f"~/.aiplat/skills/{skill_id}"))
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "SKILL.md").write_text(
                    _skill_to_yaml(data), encoding="utf-8",
                )
                imported["skills"].append(skill_id)

        # ── Import Ontology ──
        ont_dir = os.path.join(import_dir, "ontology")
        if os.path.isdir(ont_dir):
            import shutil
            dest_ont = Path(os.path.expanduser("~/.aiplat/ontologies"))
            dest_ont.mkdir(parents=True, exist_ok=True)
            for fname in os.listdir(ont_dir):
                if not fname.endswith(".yaml"):
                    continue
                domain_id = fname.replace(".yaml", "")
                dest = dest_ont / fname
                if dest.exists() and on_conflict == "skip":
                    skipped.append(f"ontology:{domain_id}")
                    continue
                shutil.copy(ont_dir / fname, dest)
                imported["ontology"].append(domain_id)

        # ── Import Pipelines (v2 JSON + v1 .txt fallback) ──
        pipe_dir = os.path.join(import_dir, "pipelines")
        if os.path.isdir(pipe_dir):
            for fname in sorted(os.listdir(pipe_dir)):
                if fname.endswith(".json"):
                    try:
                        graph_def = json.loads(Path(pipe_dir / fname).read_text(encoding="utf-8"))
                        name = graph_def.get("name", fname.replace(".json", ""))
                        # Namespace: {playbook_id}.{pipeline_name} unless overwrite
                        target_name = f"{manifest.id}.{name}" if on_conflict != "overwrite" else name
                        from core.harness.execution.pipeline_engine import register_pipeline_from_desc
                        graph_def["name"] = target_name
                        register_pipeline_from_desc(graph_def)
                        imported["pipelines"].append(target_name)
                    except Exception as e:
                        skipped.append(f"pipeline:{fname}: {e}")
                elif fname.endswith(".txt"):
                    name = fname.replace(".txt", "")
                    from core.harness.execution.pipeline_engine import get_pipeline_builder
                    if get_pipeline_builder(name):
                        imported["pipelines"].append(name)
                    else:
                        skipped.append(f"pipeline:{name} (not registered)")

        # ── Import Policies ──
        pol_dir = os.path.join(import_dir, "policies")
        if os.path.isdir(pol_dir):
            for fname in os.listdir(pol_dir):
                if not fname.endswith(".json"):
                    continue
                pol_id = fname.replace(".json", "")
                imported["policies"].append(pol_id)

        # ── Import Cleanup Rules ──
        clean_dir = os.path.join(import_dir, "cleanup_rules")
        if os.path.isdir(clean_dir):
            import shutil
            dest_clean = Path(os.path.expanduser("~/.aiplat/cleanup_rules"))
            dest_clean.mkdir(parents=True, exist_ok=True)
            for fname in os.listdir(clean_dir):
                dest = dest_clean / fname
                if dest.exists() and on_conflict == "skip":
                    skipped.append(f"cleanup:{fname}")
                    continue
                shutil.copy(clean_dir / fname, dest)
                imported["cleanup_rules"].append(fname.replace(".yaml", ""))

        logger.info("Playbook '%s' imported: %s, skipped: %s",
                      manifest.id, imported, skipped)
        return {"manifest": manifest.to_dict(), "imported": imported, "skipped": skipped}

    finally:
        import shutil
        shutil.rmtree(import_dir, ignore_errors=True)


def _version_lt(a: str, b: str) -> bool:
    """Compare semantic versions: True if a < b."""
    try:
        pa = [int(x) for x in a.split(".")]
        pb = [int(x) for x in b.split(".")]
        while len(pa) < len(pb):
            pa.append(0)
        while len(pb) < len(pa):
            pb.append(0)
        return pa < pb
    except Exception:
        return False


def _skill_to_yaml(data: dict) -> str:
    """Convert skill dict to SKILL.md YAML frontmatter format."""
    lines = ["---"]
    lines.append(f"name: {data.get('name', '')}")
    lines.append(f"version: {data.get('version', '1.0.0')}")
    lines.append(f"description: {data.get('description', '')}")
    lines.append(f"category: {data.get('category', 'general')}")
    if data.get("tags"):
        lines.append(f"tags: [{', '.join(data['tags'])}]")
    lines.append("---")
    lines.append("")
    lines.append(f"# {data.get('name', 'Skill')}")
    lines.append("")
    lines.append(data.get("description", ""))
    return "\n".join(lines)

    @classmethod
    def from_json(cls, json_str: str) -> "PlaybookManifest":
        return cls.from_dict(json.loads(json_str))
