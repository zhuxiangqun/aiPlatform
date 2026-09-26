"""S3 — install named domain packs. No harness domain-name branches."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List

import yaml

logger = logging.getLogger(__name__)

_SAFE = re.compile(r"^[a-z][a-z0-9-]{1,48}$")


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def packs_root() -> Path:
    return Path(__file__).resolve().parents[4] / "workspace_seeds" / "domain_packs"


def list_domain_packs() -> Dict[str, Any]:
    root = packs_root()
    items: List[Dict[str, Any]] = []
    if root.is_dir():
        for d in sorted(root.iterdir()):
            if not d.is_dir():
                continue
            man = d / "manifest.yaml"
            if not man.is_file():
                continue
            try:
                raw = yaml.safe_load(man.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            items.append(
                {
                    "template_id": d.name,
                    "title": str(raw.get("title") or d.name),
                    "description": str(raw.get("description") or "")[:300],
                    "primary_class": str(raw.get("primary_class") or ""),
                    "action_scaffold": (d / "action_scaffold.yaml").is_file(),
                }
            )
    return {
        "ok": True,
        "items": items,
        "count": len(items),
        "m4_claim_allowed": False,
        "authority_note": "模板安装只复制配置。不是签收。",
    }


def install_domain_pack(
    *,
    role: str,
    template_id: str,
    domain_id: str,
    display_name: str = "",
) -> Dict[str, Any]:
    role_n = (role or "").strip().lower()
    if not role_n:
        return {"ok": False, "reason": "identity_missing"}
    if role_n not in ("admin", "operator"):
        return {"ok": False, "reason": "install_forbidden"}
    tid = (template_id or "").strip()
    did = (domain_id or "").strip().lower()
    if not tid or not (packs_root() / tid).is_dir():
        return {"ok": False, "reason": "template_missing", "template_id": tid}
    if not _SAFE.match(did):
        return {"ok": False, "reason": "domain_invalid", "domain_id": did}

    pack = packs_root() / tid
    name = (display_name or "").strip() or did
    onto_src = pack / "ontology.yaml"
    conn_src = pack / "connector.json"
    goal_src = pack / "org_goal.yaml"
    scaffold_src = pack / "action_scaffold.yaml"
    if not onto_src.is_file():
        return {"ok": False, "reason": "ontology_missing"}

    text = onto_src.read_text(encoding="utf-8")
    text = text.replace("{{domain_id}}", did).replace("{{name}}", name)
    onto_dest = _home() / "ontologies" / f"{did}.yaml"
    onto_dest.parent.mkdir(parents=True, exist_ok=True)
    onto_dest.write_text(text, encoding="utf-8")

    conn_action = "skipped"
    if conn_src.is_file():
        raw = conn_src.read_text(encoding="utf-8")
        raw = raw.replace("{{domain_id}}", did)
        try:
            data = json.loads(raw)
        except Exception:
            data = {"domain_id": did, "source_id": f"{did}-ingest"}
        if isinstance(data, dict):
            data["domain_id"] = did
        dest = _home() / "connectors" / f"{did}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        conn_action = "installed"

    goal_action = "skipped"
    if goal_src.is_file():
        try:
            gtext = goal_src.read_text(encoding="utf-8")
            gtext = gtext.replace("{{domain_id}}", did).replace("{{name}}", name)
            grow = yaml.safe_load(gtext) or {}
            if isinstance(grow, dict) and grow.get("goal_id"):
                grow["domain_id"] = did
                from core.apps.org.service.org_runtime import _goals_path, _read_json, _write_json

                goals = _read_json(_goals_path(), {"goals": []})
                existing = [
                    g for g in (goals.get("goals") or []) if g.get("domain_id") == did
                ]
                if existing:
                    goal_action = "exists"
                else:
                    goals.setdefault("goals", []).append(grow)
                    _write_json(_goals_path(), goals)
                    goal_action = "installed"
        except Exception:
            logger.warning("domain pack goal install failed", exc_info=True)
            goal_action = "goal_error"

    scaffold_action = "skipped"
    if scaffold_src.is_file():
        stext = scaffold_src.read_text(encoding="utf-8")
        stext = stext.replace("{{domain_id}}", did).replace("{{name}}", name)
        draft = _home() / "org" / "action_drafts" / f"{did}.yaml"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(stext, encoding="utf-8")
        scaffold_action = "draft"

    registered = False
    try:
        from core.harness.knowledge.domain_router import DomainRouter

        DomainRouter().register_domain(
            did,
            {"domain_id": did, "name": name, "source": f"domain_pack:{tid}"},
            auto_rebuild=True,
        )
        registered = True
    except Exception:
        logger.warning("domain pack register failed", exc_info=True)

    return {
        "ok": True,
        "template_id": tid,
        "domain_id": did,
        "ontology_path": str(onto_dest),
        "connector": conn_action,
        "goal": goal_action,
        "registered": registered,
        "action_scaffold": scaffold_action,
        "registered_action": False,
        "wrote_live_actions": False,
        "m4_claim_allowed": False,
        "authority_note": "域包已安装。动作只在草稿目录，未登记。不是签收。",
    }
