from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Dict, Optional

from core.apps.skills.base import BaseSkill
from core.governance.changeset import record_changeset
from core.harness.interfaces import SkillConfig, SkillContext, SkillResult
from core.harness.kernel.runtime import get_kernel_runtime


class ApplyEngineSkillMdPatchSkill(BaseSkill):
    """
    Apply an engine SKILL.md patch proposed by /skill-evals/.../apply-skill-suggestion.

    Input: {"change_id": "..."}
    """

    def __init__(self):
        cfg = SkillConfig(
            name="skill_apply_engine_skill_md_patch",
            description="应用 engine skill 的 SKILL.md 补丁（来自 change-control changeset），用于变更治理闭环。",
            input_schema={"change_id": {"type": "string"}},
            output_schema={"ok": {"type": "boolean"}, "change_id": {"type": "string"}, "skill_id": {"type": "string"}},
            metadata={
                "category": "ops",
                "version": "1.0.0",
                "tags": ["ops", "evaluation", "change_control"],
                "skill_kind": "executable",
                "permissions": ["execute"],
                "requires_approval": False,
                "risk_level": "low",
            },
        )
        super().__init__(cfg)

    async def execute(self, context: SkillContext, params: Dict[str, Any]) -> SkillResult:
        rt = get_kernel_runtime()
        store = getattr(rt, "execution_store", None) if rt else None
        if store is None:
            return SkillResult(success=False, error="ExecutionStore not initialized")

        change_id = str((params or {}).get("change_id") or "").strip()
        if not change_id:
            return SkillResult(success=False, error="missing_change_id")

        cc = await store.get_change_control(change_id=change_id, limit=50, offset=0, tenant_id=None)
        ev = (cc.get("events") or {}).get("items") if isinstance(cc.get("events"), dict) else None
        ev = ev if isinstance(ev, list) else []
        if not ev:
            # fallback to latest
            latest = cc.get("latest") if isinstance(cc, dict) else None
            ev = [latest] if isinstance(latest, dict) else []
        # If already applied, stop (idempotent safety)
        if any(isinstance(it, dict) and str(it.get("name") or "") == "skill_eval.engine_skill_md_patch_applied" for it in ev):
            return SkillResult(success=False, error="already_applied")
        # Find the latest proposed patch event
        proposed = None
        for it in ev:
            if isinstance(it, dict) and str(it.get("name") or "") == "skill_eval.engine_skill_md_patch_proposed":
                proposed = it
                break
        if not proposed:
            return SkillResult(success=False, error="unsupported_change_type")

        args = proposed.get("args") if isinstance(proposed.get("args"), dict) else {}
        result = proposed.get("result") if isinstance(proposed.get("result"), dict) else {}
        skill_id = str(args.get("skill_id") or "").strip()
        path0 = str(result.get("path") or "").strip()
        updated_raw = result.get("updated_raw")
        base_hash = str(result.get("base_hash") or args.get("base_hash") or "").strip()

        if not skill_id or not path0 or not isinstance(updated_raw, str) or not updated_raw.strip():
            return SkillResult(success=False, error="missing_patch_payload")

        path = Path(path0).expanduser().resolve()
        if not path.exists():
            return SkillResult(success=False, error="skill_md_not_found")

        # Drift check (best-effort)
        cur_raw = path.read_text(encoding="utf-8")
        cur_hash = hashlib.sha256(cur_raw.encode("utf-8")).hexdigest()[:16]
        if base_hash and cur_hash != base_hash:
            return SkillResult(success=False, error="engine_skill_md_drift", metadata={"base_hash": base_hash, "current_hash": cur_hash})

        path.write_text(updated_raw, encoding="utf-8")

        # Governance record: append applied changeset + audit log
        try:
            diff = str(result.get("diff") or "")
            diff_hash = hashlib.sha256(diff.encode("utf-8")).hexdigest()[:16] if diff else None
            await record_changeset(
                store=store,
                name="skill_eval.engine_skill_md_patch_applied",
                target_type="change",
                target_id=str(change_id),
                status="success",
                args={
                    "skill_id": skill_id,
                    "targets": [{"type": "skill", "id": skill_id}],
                    "diff_hash": diff_hash,
                    "base_hash": cur_hash,
                },
                result={"path": str(path), "updated_at": time.time()},
                user_id=str(getattr(context, "user_id", None) or "system"),
                tenant_id=None,
                session_id=str(getattr(context, "session_id", None) or "") or None,
            )
        except Exception:
            pass
        try:
            await store.add_audit_log(
                action="engine_skill_md_patch_applied",
                status="success",
                tenant_id=None,
                actor_id=str(getattr(context, "user_id", None) or "system"),
                resource_type="skill",
                resource_id=skill_id,
                change_id=str(change_id),
                detail={"path": str(path), "base_hash": cur_hash},
            )
        except Exception:
            pass

        return SkillResult(success=True, output={"ok": True, "change_id": change_id, "skill_id": skill_id, "path": str(path), "base_hash": cur_hash})


def build_skill(*args, **kwargs):
    return ApplyEngineSkillMdPatchSkill()
