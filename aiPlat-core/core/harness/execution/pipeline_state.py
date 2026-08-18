"""PipelineStateMixin — state persistence methods for PipelineEngine.

Extracted from pipeline_engine.py (P2-A4 Phase 2, 2026-08-18). Pure structure
move: method bodies unchanged, no API/semantics change. self._collect_files
(a PipelineEngine prompt helper) is resolved via the MRO at runtime.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional


class PipelineStateMixin:
    """State persistence: snapshot / checkpoint / output / artifact handling."""

    def _snapshot(self, state: PipelineState, name: str) -> None:

        sid = state.get("session_id", "")

        if not sid:

            return

        checkpoint = {"name": name, "ts": time.time(), "phase": state.get("phase", ""),

            "stage_idx": state.get("_current_stage_idx"), "last_reason": state.get("_last_action_reason", ""),

            "artifacts": {s.output_artifact: bool(state.get(s.output_artifact)) for s in self._config.stages},

            "tokens_used": state.get("tokens_used", 0), "tokens_budget": state.get("tokens_budget", 0),

            "iteration": state.get("iteration", 0)}

        state.setdefault("_checkpoints", []).append(checkpoint)

        if len(state["_checkpoints"]) > 50:

            state["_checkpoints"] = state["_checkpoints"][-50:]

        base = state.get("output_dir", "") or self._output_root(sid)

        os.makedirs(base, exist_ok=True)

        try:

            with open(os.path.join(base, f"_{name}.json"), "w", encoding="utf-8") as fh:

                json.dump(dict(state), fh, ensure_ascii=False, indent=2, default=str)

        except OSError as e:

            logging.getLogger("pipeline_engine").warning(

                "Failed to persist checkpoint for %s: %s", sid, str(e)[:200])

    def _merge_state(self, state: dict, r_state: dict, stage: Optional[PipelineStageConfig] = None) -> None:

        """Reducer-based state merge — prevents parallel overwrite.

        

        Reads merge_strategies from PipelineStageConfig (or defaults):

          "append"     → extend list fields instead of overwriting

          "overwrite"  → standard dict.update (last writer wins, default)

          "merge_deep" → recursive dict merge for nested structures

        

        Default: _graph_trace, _checkpoints, messages always append.

        """

        # Default append keys (engine-level guarantees)

        default_append = {"_graph_trace", "_checkpoints", "messages", "trace", "sub_agent_results", "_shared_state_board"}

        strategies = {}

        if stage and hasattr(stage, "merge_strategies") and stage.merge_strategies:

            strategies = stage.merge_strategies

        strategies.update({k: "append" for k in default_append if k not in strategies})



        for key, new_value in list(r_state.items()):

            if new_value is None:

                continue

            strategy = strategies.get(key, "overwrite")



            if strategy == "append":

                if key in state and isinstance(state[key], list):

                    if isinstance(new_value, list):

                        state[key].extend(new_value)

                    else:

                        state[key].append(new_value)

                else:

                    state[key] = [new_value] if not isinstance(new_value, list) else list(new_value)

            elif strategy == "merge_deep":

                if key in state and isinstance(state[key], dict) and isinstance(new_value, dict):

                    state[key].update(new_value)

                else:

                    state[key] = new_value

            else:  # "overwrite" (default)

                state[key] = new_value

    def _load_checkpoints_from_disk(self, state: PipelineState) -> List[Dict[str, Any]]:

        """Load checkpoint summaries from disk checkpoint files (survives restart)."""

        checkpoints = []

        sid = state.get("session_id", "")

        base = state.get("output_dir", "") or self._output_root(sid)

        if not sid or not os.path.isdir(base):

            return checkpoints

        try:

            for fname in sorted(os.listdir(base)):

                if fname.startswith("_") and fname.endswith(".json") and fname.startswith("_stage_"):

                    fp = os.path.join(base, fname)

                    try:

                        with open(fp, "r", encoding="utf-8") as fh:

                            saved = json.load(fh)

                        if isinstance(saved, dict):

                            checkpoints.append({

                                "name": fname[1:-5],

                                "stage_idx": saved.get("_current_stage_idx"),

                                "tokens_used": saved.get("tokens_used", 0),

                                "tokens_budget": saved.get("tokens_budget", 0),

                                "iteration": saved.get("iteration", 0),

                                "error": saved.get("error", ""),

                            })

                    except Exception:

                        logging.getLogger("pipeline_engine").warning("best-effort skipped", exc_info=True)

        except Exception:

            logging.getLogger("pipeline_engine").warning("best-effort skipped", exc_info=True)

        return checkpoints

    def _output_root(self, project_id: str, project_name: str = "") -> str:

        """Build a human-readable output directory path.



        When project_name is given, the directory is:

            ~/.aiplat/output/{sanitized_name}-{project_id}/

        Otherwise falls back to the legacy bare-ID directory:

            ~/.aiplat/output/{project_id}/

        """

        import re

        home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))

        if project_name:

            safe = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff-]', '_', project_name).strip('_')[:40]

            return str(os.path.join(home, "output", f"{safe}-{project_id}"))

        return str(os.path.join(home, "output", project_id))

    def _persist_files(self, artifact: Dict[str, Any], output_dir: str = "") -> None:

        if not output_dir:

            return

        for f in self._collect_files(artifact):

            path = f.get("path", "")

            content = f.get("content", "")

            if path and content:

                full = _safe_join(output_dir, path)

                try:

                    os.makedirs(os.path.dirname(full), exist_ok=True)

                    with open(full, "w", encoding="utf-8") as fh:

                        fh.write(content)

                except OSError as e:

                    logging.getLogger("pipeline_engine").warning(

                        "Failed to persist artifact file %s: %s", full, str(e)[:200])

    def _summarize_artifact(val: Any, max_chars: int = 0) -> Dict[str, Any]:

        limit = max_chars or int(os.getenv("AIPLAT_ARTIFACT_SUMMARY_CHARS", "8000"))

        """Structured 7-section summary template (OpenCode pattern).



        Sections: goal, artifacts, quality, key_decisions, next_steps,

        critical_context, relevant_files.

        """

        if not isinstance(val, dict):

            s = str(val)[:limit // 2] if val else "{}"

            return {"summary": s, "artifact_keys": []}

        raw = json.dumps(val, ensure_ascii=False, default=str)

        if len(raw) <= limit:

            return val



        files = val.get("files", []) if isinstance(val.get("files"), list) else []

        file_list = [

            {"path": f.get("path", ""), "purpose": f.get("description", "")[:80]}

            for f in files[:20]

        ]



        tests_data = val.get("test_results", {}) or {}

        pass_count = tests_data.get("passed", 0) if isinstance(tests_data, dict) else 0

        fail_count = tests_data.get("failed", 0) if isinstance(tests_data, dict) else 0

        total_count = pass_count + fail_count

        pass_rate = f"{pass_count}/{total_count}" if total_count > 0 else "N/A"



        issues = val.get("issues", []) if isinstance(val.get("issues"), list) else []

        p0 = sum(1 for i in issues if isinstance(i, dict) and str(i.get("severity", "")).upper() == "P0")

        p1 = sum(1 for i in issues if isinstance(i, dict) and str(i.get("severity", "")).upper() == "P1")



        return {

            "goal": str(val.get("phase_description", "") or val.get("description", "") or "")[:200],

            "artifacts_produced": {

                "keys": list(val.keys())[:20],

                "total_size_chars": len(raw),

                "file_count": len(files),

            },

            "quality_assessment": {

                "tests_run": pass_rate,

                "confidence": val.get("confidence", "N/A") if isinstance(val, dict) else "N/A",

                "issues_found": f"{len(issues)} (P0:{p0}, P1:{p1})" if issues else "none",

            },

            "key_decisions": val.get("decisions", []) if isinstance(val.get("decisions"), list) else [],

            "next_steps": val.get("next_steps", []) if isinstance(val.get("next_steps"), list) else [],

            "critical_context": str(val.get("known_issues", "") or val.get("notes", "") or "")[:500],

            "relevant_files": file_list,

        }