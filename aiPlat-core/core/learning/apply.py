"""
Phase 6.7: LearningApplier (behavior-preserving by default).

This layer reads published learning artifacts (especially release_candidate) and produces
an "active release" view that can be attached to execution metadata.

Important:
- This module MUST NOT execute tools/skills or change runtime behavior directly.
- Applying changes to runtime behavior should be a separate, gated phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import os
import hashlib


@dataclass
class ActiveRelease:
    candidate_id: str
    version: str
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"candidate_id": self.candidate_id, "version": self.version, "summary": self.summary}


class LearningApplier:
    def __init__(self, execution_store: Any):
        self._store = execution_store

    async def resolve_active_release(self, *, target_type: str, target_id: str) -> Optional[ActiveRelease]:
        """
        Resolve the active published release_candidate for a target.

        Selection policy (Phase 6.7 minimal):
        - Choose the latest created_at among published release_candidate artifacts for the target.
        """
        if not self._store or not hasattr(self._store, "list_learning_artifacts"):
            return None

        page = await self._store.list_learning_artifacts(target_type=target_type, target_id=target_id, limit=50, offset=0)
        items = page.get("items") or []

        published_candidates = [i for i in items if i.get("kind") == "release_candidate" and i.get("status") == "published"]
        if not published_candidates:
            return None

        # Stable selection: latest created_at among published candidates.
        published_candidates.sort(key=lambda x: float(x.get("created_at") or 0.0), reverse=True)
        stable = published_candidates[0]

        # PR-10: rollout override (tenant-scoped)
        if os.getenv("AIPLAT_ENABLE_RELEASE_ROLLOUTS", "false").lower() in ("1", "true", "yes", "y"):
            try:
                from core.harness.kernel.execution_context import get_active_request_context

                rctx = get_active_request_context()
                tenant_id = getattr(rctx, "tenant_id", None) if rctx else None
                actor_id = getattr(rctx, "actor_id", None) if rctx else None
                if tenant_id and actor_id and hasattr(self._store, "get_release_rollout"):
                    rr = await self._store.get_release_rollout(
                        tenant_id=str(tenant_id), target_type=str(target_type), target_id=str(target_id)
                    )
                    if isinstance(rr, dict) and int(rr.get("enabled") or 0) == 1:
                        inc = rr.get("include_actor_ids") if isinstance(rr.get("include_actor_ids"), list) else []
                        exc = rr.get("exclude_actor_ids") if isinstance(rr.get("exclude_actor_ids"), list) else []
                        if inc and str(actor_id) not in {str(x) for x in inc}:
                            rr = None
                        if rr and exc and str(actor_id) in {str(x) for x in exc}:
                            rr = None
                    if isinstance(rr, dict):
                        mode = str(rr.get("mode") or "percentage").lower()
                        pct = rr.get("percentage")
                        choose = False
                        if mode == "all":
                            choose = True
                        else:
                            try:
                                p = int(pct) if pct is not None else 0
                            except Exception:
                                p = 0
                            seed = f"{tenant_id}:{target_type}:{target_id}:{actor_id}"
                            bucket = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % 100
                            choose = bucket < max(0, min(100, p))
                        if choose and rr.get("candidate_id"):
                            cand_id = str(rr.get("candidate_id"))
                            cand = await self._store.get_learning_artifact(cand_id)
                            if isinstance(cand, dict) and cand.get("kind") == "release_candidate" and cand.get("status") == "published":
                                payload = cand.get("payload") if isinstance(cand.get("payload"), dict) else {}
                                return ActiveRelease(
                                    candidate_id=str(cand.get("artifact_id") or cand_id),
                                    version=str(cand.get("version") or ""),
                                    summary=str(payload.get("summary") or ""),
                                )
            except Exception:
                pass

        payload = stable.get("payload") if isinstance(stable.get("payload"), dict) else {}
        return ActiveRelease(
            candidate_id=str(stable.get("artifact_id") or ""),
            version=str(stable.get("version") or ""),
            summary=str(payload.get("summary") or ""),
        )

    async def resolve_prompt_revision_patch(
        self, *, target_type: str, target_id: str
    ) -> Dict[str, Any]:
        """
        Resolve a merged prompt revision patch for the target from the active release.

        Return schema:
          {
            "patch": {"prepend": "...", "append": "..."},
            "artifact_ids": ["..."]
            "conflicts": [{"type": "...", "artifact_ids":[...], "details": {...}}],
            "ignored_artifact_ids": ["..."]
          }
        """
        active = await self.resolve_active_release(target_type=target_type, target_id=target_id)
        if not active:
            return {"patch": {}, "artifact_ids": [], "conflicts": [], "ignored_artifact_ids": []}

        cand = await self._store.get_learning_artifact(active.candidate_id) if hasattr(self._store, "get_learning_artifact") else None
        if not cand or cand.get("kind") != "release_candidate" or cand.get("status") != "published":
            return {"patch": {}, "artifact_ids": [], "conflicts": [], "ignored_artifact_ids": []}

        ids = (cand.get("payload") or {}).get("artifact_ids") if isinstance(cand.get("payload"), dict) else []
        if not isinstance(ids, list):
            return {"patch": {}, "artifact_ids": [], "conflicts": [], "ignored_artifact_ids": []}

        prepend_parts = []
        append_parts = []
        applied_ids: list[str] = []
        ignored_ids: list[str] = []
        conflicts: list[dict] = []

        strict = os.getenv("AIPLAT_PROMPT_REVISION_STRICT", "false").lower() in ("1", "true", "yes", "y")
        # Collect candidates first so we can apply deterministic ordering.
        candidates: list[dict] = []
        for idx, aid in enumerate(ids):
            if not isinstance(aid, str) or not aid:
                continue
            rec = await self._store.get_learning_artifact(aid) if hasattr(self._store, "get_learning_artifact") else None
            if not rec:
                continue
            if rec.get("kind") != "prompt_revision" or rec.get("status") != "published":
                continue
            payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
            patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else {}
            meta = rec.get("metadata") if isinstance(rec.get("metadata"), dict) else {}
            prio = meta.get("priority")
            try:
                prio_i = int(prio) if prio is not None else 0
            except Exception:
                prio_i = 0
            group = meta.get("exclusive_group")
            candidates.append(
                {
                    "artifact_id": aid,
                    "idx": idx,  # preserve release order for tie-break
                    "priority": prio_i,
                    "exclusive_group": group if isinstance(group, str) and group else None,
                    "patch": patch if isinstance(patch, dict) else {},
                }
            )

        # Freeze deterministic order: higher priority first, tie by release order.
        candidates.sort(key=lambda x: (-int(x.get("priority") or 0), int(x.get("idx") or 0)))

        # Handle exclusive_group conflicts.
        by_group: Dict[str, list[dict]] = {}
        for c in candidates:
            g = c.get("exclusive_group")
            if isinstance(g, str) and g:
                by_group.setdefault(g, []).append(c)

        # Record conflicts (all groups with >1 entries)
        for g, arr in by_group.items():
            if len(arr) > 1:
                conflicts.append(
                    {
                        "type": "exclusive_group",
                        "artifact_ids": [a["artifact_id"] for a in arr],
                        "details": {
                            "group": g,
                            "priorities": [a.get("priority", 0) for a in arr],
                            "order": [a.get("idx", 0) for a in arr],
                        },
                    }
                )

        selected: list[dict] = []
        if strict:
            # Strict mode: keep only one per group (highest priority; tie by release order due to sort).
            chosen_groups: set[str] = set()
            for c in candidates:
                g = c.get("exclusive_group")
                if isinstance(g, str) and g:
                    if g in chosen_groups:
                        ignored_ids.append(c["artifact_id"])
                        continue
                    chosen_groups.add(g)
                selected.append(c)
        else:
            # Non-strict: still apply all (but conflicts recorded).
            selected = candidates

        for c in selected:
            patch = c.get("patch") if isinstance(c.get("patch"), dict) else {}
            pre = patch.get("prepend")
            app = patch.get("append")
            if isinstance(pre, str) and pre.strip():
                prepend_parts.append(pre.strip())
            if isinstance(app, str) and app.strip():
                append_parts.append(app.strip())
            applied_ids.append(c["artifact_id"])

        merged_patch: Dict[str, Any] = {}
        if prepend_parts:
            merged_patch["prepend"] = "\n".join(prepend_parts)
        if append_parts:
            merged_patch["append"] = "\n".join(append_parts)
        return {
            "patch": merged_patch,
            "artifact_ids": applied_ids,
            "conflicts": conflicts,
            "ignored_artifact_ids": ignored_ids,
        }
