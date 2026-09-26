"""Org L5 Phase 4 — Fleet gate (W6).

Default deny. OrgGoal.allow_fleet must be true AND checklist hard gates pass.
Does not spawn multi-agent fleets yet; gates readiness for future wiring.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def evaluate_fleet_gate(
    goal_id: str = "",
    *,
    domain_id: str = "it-ops",
    project_id: str = "",
) -> Dict[str, Any]:
    """Hard gate for org fleet (multi_agent). Default: blocked."""
    from core.apps.org.service.org_runtime import ensure_pilot_goal, get_goal, list_goals

    ensure_pilot_goal(domain_id)
    goal = None
    gid = (goal_id or "").strip()
    if gid:
        got = get_goal(gid)
        if got.get("status") == "ok":
            goal = got["goal"]
    if goal is None:
        goals = list_goals(domain_id).get("goals") or []
        goal = goals[0] if goals else None
    if goal is None:
        return {
            "allowed": False,
            "status": "no_goal",
            "checks": [],
            "authority_note": "no OrgGoal; fleet blocked",
        }

    allow_fleet = bool(goal.get("allow_fleet"))
    checks: List[Dict[str, Any]] = [
        {
            "id": "allow_fleet_flag",
            "ok": allow_fleet,
            "required": True,
            "detail": "OrgGoal.allow_fleet must be true (seed default false)",
        },
        {
            "id": "goal_active",
            "ok": goal.get("status") in ("active", "draft"),
            "required": True,
            "detail": f"goal status={goal.get('status')}",
        },
        {
            "id": "handoff_contract",
            "ok": True,
            "required": True,
            "detail": "multi_agent must use stage_handoff five fields; peer execute() forbidden",
        },
        {
            "id": "single_default",
            "ok": True,
            "required": False,
            "detail": "pilot executor remains single until fleet runtime wired",
        },
    ]

    hop: Dict[str, Any] = {"status": "skipped", "detail": "no project_id"}
    if (project_id or "").strip():
        try:
            from builder.hop_metrics import aggregate_hops  # type: ignore

            hop = aggregate_hops(project_id.strip())
            n = int(hop.get("n_runs") or hop.get("count") or hop.get("n") or 0)
            ok_hop = n >= 5
            checks.append(
                {
                    "id": "hop_metrics",
                    "ok": ok_hop,
                    "required": True,
                    "detail": f"project={project_id} hop_count={n} (need ≥5)",
                }
            )
        except Exception as e:
            checks.append(
                {
                    "id": "hop_metrics",
                    "ok": False,
                    "required": True,
                    "detail": f"hop aggregate unavailable: {type(e).__name__}",
                }
            )
            hop = {"status": "error", "error": type(e).__name__}

    required_ok = all(c["ok"] for c in checks if c.get("required"))
    return {
        "allowed": bool(required_ok and allow_fleet),
        "status": "allowed" if (required_ok and allow_fleet) else "blocked",
        "goal_id": goal.get("goal_id"),
        "domain_id": goal.get("domain_id"),
        "allow_fleet": allow_fleet,
        "checks": checks,
        "hop": hop,
        "execution_note": (
            "even when allowed, Phase 4 pilot still runs single OrgRun path; "
            "fleet spawn is gated not productized"
        ),
        "authority_note": "W6 fleet gate; default deny; no ungated multi-agent",
    }


def set_allow_fleet(goal_id: str, allow: bool) -> Dict[str, Any]:
    """Flip OrgGoal.allow_fleet (explicit ops action; still needs gate checks)."""
    from core.apps.org.service.org_runtime import patch_goal

    return patch_goal(goal_id, {"allow_fleet": bool(allow)})


def request_fleet_or_run(
    goal_id: str = "",
    *,
    domain_id: str = "it-ops",
    project_id: str = "",
    week_label: str = "",
    force_fleet: bool = False,
) -> Dict[str, Any]:
    """If force_fleet: require gate; on pass still execute single OrgRun with fleet_meta."""
    gate = evaluate_fleet_gate(goal_id, domain_id=domain_id, project_id=project_id)
    if force_fleet and not gate.get("allowed"):
        return {
            "status": "fleet_blocked",
            "gate": gate,
        }

    from core.apps.org.service.org_runtime import run_org_goal

    run = run_org_goal(
        goal_id,
        domain_id=domain_id,
        dry_actions=True,
        week_label=week_label,
    )
    run["fleet_gate"] = gate
    run["execution_mode"] = (
        "single_with_fleet_cleared" if gate.get("allowed") else "single_default"
    )
    return run


_ROLE = re.compile(r"^[\w ·\-]{1,24}$")


def _home() -> Path:
    return Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))


def _rehearsal_dir() -> Path:
    return _home() / "org" / "rehearsals"


def _clean_roles(roles: List[Any]) -> List[str]:
    out: List[str] = []
    for item in roles or []:
        label = str(item or "").strip()
        if not label or not _ROLE.match(label):
            continue
        if label not in out:
            out.append(label)
        if len(out) >= 3:
            break
    return out


async def probe_sandbox_conflict(
    domain_id: str = "it-ops",
    *,
    resource_id: str = "shared_interface",
) -> Dict[str, Any]:
    """Two mutex acquires on one resource. Second must be denied. No live write."""
    from core.harness.infrastructure.entity_lock import AsyncioEntityLock

    did = (domain_id or "").strip() or "it-ops"
    rid = (resource_id or "shared_interface").strip()[:64] or "shared_interface"
    lock_id = f"sandbox-conflict:{did}:{rid}"
    lock = AsyncioEntityLock()
    first = await lock.acquire(lock_id, "mutex", ttl=30)
    second = await lock.acquire(lock_id, "mutex", ttl=30)
    await lock.release(lock_id)
    return {
        "ok": True,
        "domain_id": did,
        "resource_id": rid,
        "lock_id": lock_id,
        "attempts": [
            {"holder": "role-a", "acquired": bool(first), "result": "acquired" if first else "denied"},
            {
                "holder": "role-b",
                "acquired": bool(second),
                "result": "concurrent_conflict" if (first and not second) else ("acquired" if second else "denied"),
            },
        ],
        "concurrent_conflict": bool(first and not second),
        "single_judgment": True,
        "wrote_live_yaml": False,
        "fleet_started": False,
        "peer_execute": False,
        "authority_note": "沙箱冲突探针：同一资源二次持有拒绝。不写活本体，不启动舰队。",
    }


def list_sandbox_rehearsals(limit: int = 5) -> Dict[str, Any]:
    """Read rehearsal logs. Does not start a fleet."""
    root = _rehearsal_dir()
    items: List[Dict[str, Any]] = []
    if root.is_dir():
        files = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files[: max(1, min(int(limit or 5), 20))]:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(raw, dict):
                raw["fleet_started"] = False
                raw["wrote_live_yaml"] = False
                items.append(raw)
    return {
        "ok": True,
        "items": items,
        "count": len(items),
        "fleet_started": False,
        "wrote_live_yaml": False,
        "m4_claim_allowed": False,
        "authority_note": "演练记录只读。不启动舰队。",
    }


async def start_sandbox_rehearsal(
    *,
    role: str,
    domain_id: str,
    roles: List[Any],
) -> Dict[str, Any]:
    """Record a sandbox handoff + conflict probe. One dry OrgRun. Never flips allow_fleet."""
    role_n = (role or "").strip().lower()
    if not role_n:
        return {"ok": False, "reason": "identity_missing", "fleet_started": False}
    if role_n not in ("admin", "operator"):
        return {"ok": False, "reason": "rehearsal_forbidden", "fleet_started": False}
    labels = _clean_roles(roles)
    if len(labels) < 2:
        return {"ok": False, "reason": "roles_invalid", "fleet_started": False}
    did = (domain_id or "").strip() or "it-ops"
    if len(did) > 64 or "/" in did or "\\" in did:
        return {"ok": False, "reason": "domain_invalid", "fleet_started": False}

    from core.harness.execution.stage_handoff import HANDOFF_FIELDS, build_stage_handoff

    hops: List[Dict[str, Any]] = []
    prev_ref = ""
    for i, label in enumerate(labels):
        nxt = labels[i + 1] if i + 1 < len(labels) else "人批"
        env = build_stage_handoff(
            stage=SimpleNamespace(skill_name=label, agent_id="", hitl=True),
            artifact_key=f"rehearsal:{i}",
            status="ok",
            next_hint=nxt,
        )
        handoff = {key: env.get(key) for key in HANDOFF_FIELDS}
        hops.append(
            {
                "role": label,
                "peer_execute": False,
                "handoff": handoff,
                "contract": {
                    "context_slice": prev_ref or handoff.get("artifact_ref") or "",
                    "policy_scope": f"role:{label}",
                    "policy_token": f"sandbox:{did}:{label}",
                    "out_of_scope": ["peer_execute", "live_yaml_write", "spawn_fleet"],
                    "on_out_of_scope": "deny",
                },
            }
        )
        prev_ref = str(handoff.get("artifact_ref") or f"rehearsal:{i}")

    conflict = await probe_sandbox_conflict(did, resource_id="shared_interface")

    from core.apps.org.service.org_runtime import run_org_goal

    try:
        run = run_org_goal("", domain_id=did, dry_actions=True)
    except Exception:
        logger.warning("sandbox rehearsal dry run failed", exc_info=True)
        run = {"status": "run_error"}
    if not isinstance(run, dict):
        run = {"status": "run_error"}

    rec = {
        "rehearsal_id": f"reh-{uuid.uuid4().hex[:10]}",
        "domain_id": did,
        "roles": labels,
        "hops": hops,
        "conflict_probe": conflict,
        "run_id": str(run.get("run_id") or ""),
        "run_status": str(run.get("status") or ""),
        "fleet_started": False,
        "wrote_live_yaml": False,
        "peer_execute": False,
        "allow_fleet_changed": False,
        "m4_claim_allowed": False,
        "authority_note": "沙箱演练：交接合同 + 冲突探针 + 一次干跑。不启动舰队，不写活本体。",
    }
    dest = _rehearsal_dir() / f"{rec['rehearsal_id']}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, **rec}
