"""Code/ER → ontology proposal drafts (Path A suggestion only).

Never applies YAML or writes GraphIndex. Human must approve → apply.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CLASS_HINT = re.compile(
    r"(?:class|entity|表|实体)\s*[:=]?\s*[`\"']?([A-Za-z_][\w]{2,64}|[\u4e00-\u9fff]{2,32})",
    re.IGNORECASE,
)


def suggest_classes_from_snippets(
    domain_id: str,
    *,
    snippets: Optional[List[str]] = None,
    file_paths: Optional[List[str]] = None,
    author: str = "code-suggest",
    enqueue: bool = False,
) -> Dict[str, Any]:
    """Scan text/code snippets for class-like names → proposal draft.

    When enqueue=True, creates a VersionedOntologyStore draft proposal (not applied).
    """
    did = (domain_id or "").strip() or "default"
    texts: List[str] = list(snippets or [])
    for fp in file_paths or []:
        p = Path(fp)
        if p.is_file() and p.stat().st_size < 512_000:
            try:
                texts.append(p.read_text(encoding="utf-8", errors="ignore")[:80_000])
            except Exception:
                logger.debug("skip unreadable %s", fp, exc_info=True)

    found: List[str] = []
    seen = set()
    for t in texts:
        for m in _CLASS_HINT.finditer(t or ""):
            name = (m.group(1) or "").strip()
            if not name or name.lower() in seen:
                continue
            # skip common noise
            if name.lower() in {"self", "true", "false", "none", "null", "type", "string"}:
                continue
            seen.add(name.lower())
            found.append(name)
            if len(found) >= 12:
                break
        if len(found) >= 12:
            break

    if not found and not texts:
        # deterministic demo suggestions when no input (PLAYBOOK)
        found = ["ServiceEndpoint", "AlertEvent"]

    suggestions = []
    for name in found:
        safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)[:64] or "SuggestedClass"
        suggestions.append(
            {
                "kind": "new_class",
                "name": safe,
                "label": name,
                "tier": "edge",
                "description": f"Suggested from code/doc scan for domain {did}",
                "apply_path": "proposal",
                "auto_apply": False,
            }
        )

    proposal_id: Optional[str] = None
    if enqueue and suggestions:
        try:
            import asyncio

            from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore

            store = VersionedOntologyStore(did)
            first = suggestions[0]
            changes = {
                "add": {
                    "class": {
                        "name": first["name"],
                        "label": first["label"],
                        "tier": "edge",
                        "required_fields": ["name"],
                        "description": first["description"],
                    }
                }
            }

            async def _create() -> str:
                return await store.create_proposal(changes, author=author)

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                # caller should use suggest_classes_from_snippets_async
                proposal_id = None
            else:
                proposal_id = asyncio.run(_create())
        except Exception:
            logger.warning("enqueue code suggestion proposal failed", exc_info=True)

    return {
        "status": "draft",
        "domain_id": did,
        "suggestions": suggestions,
        "proposal_id": proposal_id,
        "authority_note": "仅提案草稿；禁止自动 apply；落图须 Action/confirm",
        "auto_apply": False,
    }


async def suggest_classes_from_snippets_async(
    domain_id: str,
    *,
    snippets: Optional[List[str]] = None,
    file_paths: Optional[List[str]] = None,
    author: str = "code-suggest",
    enqueue: bool = True,
) -> Dict[str, Any]:
    """Async variant that can enqueue a draft proposal."""
    base = suggest_classes_from_snippets(
        domain_id,
        snippets=snippets,
        file_paths=file_paths,
        author=author,
        enqueue=False,
    )
    if not enqueue or not base.get("suggestions"):
        return base
    try:
        from core.harness.knowledge.versioned_ontology_store import VersionedOntologyStore

        store = VersionedOntologyStore(domain_id)
        first = base["suggestions"][0]
        proposal_id = await store.create_proposal(
            {
                "add": {
                    "class": {
                        "name": first["name"],
                        "label": first["label"],
                        "tier": "edge",
                        "required_fields": ["name"],
                        "description": first["description"],
                    }
                }
            },
            author=author,
        )
        base["proposal_id"] = proposal_id
        base["enqueue_status"] = "draft"
    except Exception as e:
        logger.warning("async enqueue code suggestion failed", exc_info=True)
        # Still return a local draft id so callers have a review handle (not applied)
        import time

        first = base["suggestions"][0]
        base["proposal_id"] = f"draft_local_{domain_id}_{first['name']}_{int(time.time())}"
        base["enqueue_status"] = "local_draft"
        base["enqueue_error"] = type(e).__name__
    return base
