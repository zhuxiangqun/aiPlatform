"""Offline OWL consistency review — suggestion only, never runtime authority.

False-green ban (same as graph_validate):
  If owlready2 (or equivalent) is not installed / check did not run →
  status=unchecked, valid MUST NOT be true.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _aiplat_home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def _find_domain_yaml(domain_id: str) -> Optional[Path]:
    home = _aiplat_home()
    for p in (
        home / "ontologies" / f"{domain_id}.yaml",
        home / "ontologies" / domain_id / f"{domain_id}.yaml",
    ):
        if p.is_file():
            return p
    return None


def review_domain_owl_offline(domain_id: str) -> Dict[str, Any]:
    """Export domain to TTL (best-effort) and optionally run owlready2 consistency.

    Returns:
      status: checked | unchecked | error
      valid: False when unchecked/error; True only if check ran and no violations
      violations: list
      engine: owlready2 | none
    """
    did = (domain_id or "").strip() or "default"
    result: Dict[str, Any] = {
        "domain_id": did,
        "status": "unchecked",
        "valid": False,
        "checks_run": False,
        "violations": [],
        "engine": "none",
        "authority_note": "离线审稿建议；不得直写 GraphIndex；采纳须改 YAML 提案",
        "runtime_authority": False,
    }

    # Prefer knowledge_ontology export when available
    ttl = ""
    try:
        from core.harness.knowledge.knowledge_ontology import export_to_owl_rdf

        ttl = export_to_owl_rdf(format="turtle") or ""
        result["export"] = "knowledge_ontology"
    except Exception:
        logger.debug("OWL export via knowledge_ontology failed", exc_info=True)
        result["export"] = "unavailable"

    yaml_path = _find_domain_yaml(did)
    if yaml_path:
        result["yaml_path"] = str(yaml_path)

    try:
        import owlready2  # type: ignore
    except ImportError:
        result["status"] = "unchecked"
        result["valid"] = False
        result["checks_run"] = False
        result["reason"] = "owlready2_not_installed"
        result["hint"] = "可选依赖未装：pip install owlready2；或用 Protégé 打开导出 TTL"
        return result

    if not ttl.strip():
        result["status"] = "unchecked"
        result["valid"] = False
        result["checks_run"] = False
        result["reason"] = "no_ttl_export"
        result["engine"] = "owlready2"
        return result

    violations: List[Dict[str, str]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="aiplat_owl_") as td:
            ttl_path = Path(td) / f"{did}.ttl"
            ttl_path.write_text(ttl, encoding="utf-8")
            onto = owlready2.get_ontology(ttl_path.as_uri()).load()
            with onto:
                try:
                    # sync_reasoner may require Java; catch and mark unchecked
                    owlready2.sync_reasoner_pellet(infer_property_values=True, infer_data_property_values=True)
                except Exception as reason_err:
                    result["status"] = "unchecked"
                    result["valid"] = False
                    result["checks_run"] = False
                    result["engine"] = "owlready2"
                    result["reason"] = f"reasoner_unavailable:{type(reason_err).__name__}"
                    return result
                # Collect incoherent classes if any
                try:
                    for cls in onto.classes():
                        if owlready2.Nothing in cls.equivalent_to or (
                            hasattr(cls, "is_impossible") and cls.is_impossible()
                        ):
                            violations.append(
                                {
                                    "id": str(cls),
                                    "severity": "error",
                                    "description": "incoherent or unsatisfiable class",
                                }
                            )
                except Exception:
                    logger.debug("class scan after reasoner failed", exc_info=True)

        result["engine"] = "owlready2"
        result["checks_run"] = True
        result["violations"] = violations
        result["status"] = "checked"
        result["valid"] = len(violations) == 0
    except Exception as e:
        logger.warning("offline OWL review error: %s", e, exc_info=True)
        result["status"] = "error"
        result["valid"] = False
        result["checks_run"] = False
        result["engine"] = "owlready2"
        result["reason"] = str(e)[:200]

    # Hard ban: unchecked/error without checks_run never valid=true
    if result["status"] in ("unchecked", "error") and not result.get("checks_run"):
        result["valid"] = False
    return result
