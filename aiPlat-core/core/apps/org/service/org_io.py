"""Org L5 I/O facade — migratable path off FDE routes (D4).

Phase 1: wraps abox_connector fetch/preview; no live customer DB.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def fetch_by_entity(
    domain_id: str,
    entity_id: str,
    *,
    purpose: str = "org_pilot",
) -> Dict[str, Any]:
    """Ontology-anchored sandbox fetch (Core entry for org module)."""
    from core.apps.fde.service.abox_connector import fetch_entity_snapshot

    return fetch_entity_snapshot(domain_id, entity_id, purpose=purpose)


def preview_write(
    domain_id: str,
    entity_id: str,
    patch: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Dry-run write preview; default blocked (D3)."""
    from core.apps.fde.service.abox_connector import preview_entity_write

    return preview_entity_write(domain_id, entity_id, patch or {})
