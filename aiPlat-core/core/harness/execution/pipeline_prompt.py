"""PipelinePromptMixin — prompt building / parsing methods for PipelineEngine.

Extracted from pipeline_engine.py (P2-A4 Phase 3, 2026-08-18). Pure structure
move: method bodies unchanged, no API/semantics change. Cross-domain helpers
(self._config / self._summarize_artifact / self._task_progress) resolve via
the MRO at runtime.
"""

from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.harness.execution.phase import PipelinePhase
from core.schemas_builder import PipelineStageConfig


class PipelinePromptMixin:
    """Prompt assembly + artifact/JSON parsing helpers."""

    def _build_prompt(self, stage: PipelineStageConfig, state: PipelineState) -> str:

        skill_corpus_context = (

            "[SKILL CORPUS: If you need a capability not found in the enabled skills above, "

            "you can search disabled skills via:\n"

            "  1. sys_skill_corpus_search(query, limit=10) → candidate list with ref/name/score\n"

            "  2. sys_skill_corpus_inspect(ref) → full metadata (NOT body) for a candidate\n"

            "  3. sys_skill_corpus_select(ref, query, reason, confidence) → returns body + records audit\n"

            "Remember: inspect before select. Never select without checking metadata first.]\n"

        )

        feedback = state.get("_reject_feedback", "")

        if feedback:
            fb = (
                "\n## 🛑 REGENERATE WITH FEEDBACK — YOU MUST FIX THESE ISSUES\n"
                "You were rejected and must regenerate. Address EVERY issue below.\n"
                "Before generating your final output, list how you will fix each one.\n\n"
                f"{feedback}\n"
                "\n---\n"
            )
        else:
            fb = ""

        ctx = {}

        constraint_text = ""

        handoff_text = ""

        for artifact_name in stage.input_artifacts:

            val = state.get(artifact_name)

            if val:

                # Compact downstream artifacts: only the first artifact gets full detail.

                # Saves ~90% of token overhead for non-PRD upstream summaries.

                is_first = artifact_name == (stage.input_artifacts[0] if stage.input_artifacts else "")

                primary_chars = int(os.getenv("AIPLAT_ARTIFACT_SUMMARY_CHARS", "8000"))

                secondary_chars = int(os.getenv("AIPLAT_ARTIFACT_SUMMARY_SECONDARY_CHARS", "2000"))

                max_chars = primary_chars if is_first else secondary_chars

                ctx[artifact_name] = self._summarize_artifact(val, max_chars=max_chars)

                if isinstance(val, dict) and val.get("constraints"):

                    parts = "\n".join(f"- {c}" for c in val["constraints"])

                    if parts:

                        constraint_text = f"\n## Constraints (from {artifact_name})\n{parts}"

        if stage.input_artifacts and ctx:

            handoff_parts = []

            for artifact_name, val in ctx.items():

                if isinstance(val, dict):

                    summary = str(val.get("description") or f"{artifact_name} completed")[:120]

                    handoff_parts.append(f"1. What was done ({artifact_name}): {summary}")

                    handoff_parts.append(f"2. Where ({artifact_name}): state[\"{artifact_name}\"]")

                    verify = val.get("verify") or val.get("acceptance_criteria") or ""

                    if verify:

                        handoff_parts.append(f"3. How to verify ({artifact_name}): {str(verify)[:120]}")

                    for s in self._config.stages:

                        if artifact_name in s.input_artifacts:

                            handoff_parts.append(f"5. Next ({artifact_name}): {(s.agent_name or s.agent_id)} continues")

                            break

            if handoff_parts:

                handoff_text = "\n## Handoff (upstream output summary)\n" + "\n".join(handoff_parts)

        prev_issues = state.get("issues") or []

        iss = f"\n## Previous Issues\n{json.dumps(prev_issues[:3], ensure_ascii=False, indent=2)}" if prev_issues else ""

        agent_list = ""

        if stage.retry_target_id or stage.generate_test_plan:

            agents_info = [{"id": s.agent_id, "name": s.agent_name, "role": s.phase}

                          for s in self._config.stages]

            agent_list = f"\n## Available Agents\n{json.dumps(agents_info, ensure_ascii=False, indent=2)}"

        stage_hints = ""

        if stage.prompt_extra and stage.prompt_extra.strip():

            stage_hints = f"\n## Stage Instructions\n{stage.prompt_extra}"



        # Phase A: scene context injection — tells Agent what business problem we're solving

        scene_context = ""

        scene_id = getattr(stage, 'scene_id', '') or state.get("scene_id", "")

        if scene_id:

            try:

                from core.harness.knowledge.scene_model import get_scene

                scene = get_scene(scene_id)

                if scene:

                    scene_context = f"\n## Business Context (Scene: {scene.name})\n{scene.to_agent_context()}\n"

            except Exception as e:

                logging.warning(str(e), exc_info=True)



        # Cross-session memory: inject previous SESSION_NOTES so Agent remembers past context

        previous_notes = ""

        try:

            import os as _os, glob as _glob

            from core.utils.paths import get_aiplat_data_dir

            output_root = get_aiplat_data_dir("output")

            note_files = sorted(

                _glob.glob(_os.path.join(output_root, "*", "SESSION_NOTES.md")),

                key=_os.path.getmtime, reverse=True,

            )

            if note_files:

                summaries = []

                for f in note_files[:5]:

                    with open(f) as fh:

                        text = fh.read()

                    first_lines = "\n".join(text.split("\n")[:5])

                    summaries.append(f"## {_os.path.basename(_os.path.dirname(f))}\n{first_lines}")

                previous_notes = "\n## Recent Session Context\n" + "\n---\n".join(summaries) + "\n"

        except Exception as e:

            logging.warning(str(e), exc_info=True)



        # Plur: collective learnings shared across all agent instances

        collective_context = ""

        try:

            from core.harness.memory.shared_memory import get_learnings_context

            collective_context = get_learnings_context()

        except Exception as e:

            logging.warning(str(e), exc_info=True)



        # Phase D: knowledge gap context — tell Agent what we don't know

        gaps_context = ""

        try:

            from core.harness.syscalls.ontology_context import sys_ontology_context

            onto_ctx = sys_ontology_context(question=state.get("description", ""), include_gaps=True)

            gaps = onto_ctx.get("knowledge_gaps", {})

            if gaps and gaps.get("total_gaps", 0) > 0:

                gap_lines = []

                if gaps.get("source_less_count"):

                    gap_lines.append(f"- {gaps['source_less_count']} concepts lack source documents")

                if gaps.get("unmined_count"):

                    gap_lines.append(f"- {gaps['unmined_count']} KB documents have not been mined into wiki pages")

                if gaps.get("unidirectional_count"):

                    gap_lines.append(f"- {gaps['unidirectional_count']} citations are one-way")

                if gaps.get("orphan_count"):

                    gap_lines.append(f"- {gaps['orphan_count']} pages have no connections to other knowledge")

                if gap_lines:

                    gaps_context = "\n## Knowledge Gaps\n" + "\n".join(gap_lines) + "\n\nWhen producing knowledge artifacts, consider filling these gaps."

        except Exception as e:

            logging.warning(str(e), exc_info=True)



        # Progressive disclosure: skill stubs only (~50 tokens/skill)

        skill_stubs_context = ""

        try:

            from core.harness.integration import get_skill_registry, _start_bg_curator

            reg = get_skill_registry()

            _start_bg_curator()

            skill_stubs_context = "\n" + reg.get_all_stubs() + "\n"

            skill_stubs_context += (

                "[SKILL RECOMMENDATION: When you identify that the current task matches "

                "one of the available skills above, proactively describe how you would use it "

                "before invoking sys_skill_call. This helps the user understand your approach.]\n"

            )

        except Exception as e:

            logging.warning(str(e), exc_info=True)



        # Ponytail: Lazy Senior Developer constraint (via PONytail_MODE env)

        ponytail_context = ""

        ponytail_mode = os.getenv("PONytail_MODE", "full").lower()

        if ponytail_mode != "off":

            try:

                import os as _os

                skill_path = _os.path.expanduser("~/.aiplat/skills/ponytail-lazy/SKILL.md")

                if _os.path.exists(skill_path):

                    with open(skill_path, "r") as f:

                        body = f.read()

                    ponytail_context = f"\n## Ponytail: Lazy Senior Developer ({ponytail_mode} mode)\n{body}\n"

            except Exception as e:

                logging.warning(str(e), exc_info=True)



        # Output format instruction for code-generating stages

        fmt_text = ""

        if stage.uses_file_output:

            fmt_text = (

                "\n## Output Format\n"

                "Use ## FILE: path/to/file.py format for EACH file.\n"

                "Do NOT wrap files in ``` fences. Each ## FILE: header starts a new file.\n"

                "Example:\n## FILE: main.py\n[content]\n## FILE: models/user.py\n[content]"

            )

            # Inject existing scaffold files as context (prevent regeneration)

            scaffold = state.get("project_scaffold")

            if isinstance(scaffold, dict) and self._collect_files(scaffold):

                existing = [f["path"] for f in self._collect_files(scaffold)]

                fmt_text += (

                    f"\n\n## Existing Project Files (reference only — DO NOT regenerate)\n"

                    + "\n".join(f"- {p}" for p in existing[:30])

                    + f"\n\n{len(existing)} files exist. Generate only NEW files or modifications."

                )

        progress_text = ""

        progress = self._task_progress(state)

        if progress and not progress.startswith("0/"):

            progress_text = f"\n## Progress\n{progress}\nCheck `task_list` in the upstream output for details (passes=true|false)."

        # Repository map: inject compact structural view for code stages on existing repos

        repo_map_text = ""

        if stage.uses_file_output and state.get("output_dir"):

            repo_map_text = self._build_repo_map_text(state["output_dir"])

            if repo_map_text:

                repo_map_text = f"\n## Repository Structure (existing files — reference only)\n{repo_map_text}"

        # Test plan injection: QA stage gets test_plan as primary input

        test_plan_text = ""

        if not stage.uses_file_output and stage.generate_test_plan:

            # This is the test_plan generator stage — no upstream test_plan to inject

            pass

        elif stage.test_result_key and not stage.generate_test_plan:

            # This is the QA test execution stage — inject test_plan + upstream code

            test_plan_key = ""

            for s in self._config.stages:

                if s.generate_test_plan and s.output_artifact:

                    test_plan_key = s.output_artifact

                    break

            if test_plan_key:

                test_plan = state.get(test_plan_key)

                if isinstance(test_plan, dict):

                    test_plan_text = f"\n## Test Plan (Acceptance Criteria)\n{json.dumps(self._summarize_artifact(test_plan), ensure_ascii=False, indent=2)}"



        # Build Jinja2 render context from upstream artifacts

        jinja_ctx = {}

        for s in self._config.stages:

            val = state.get(s.output_artifact)

            if val:

                # Support file-type variables: read content from path

                if isinstance(val, dict) and val.get('type') == 'file' and val.get('path'):

                    try:

                        with open(val['path'], 'r') as ff:

                            val['_content'] = ff.read()[:10000]

                    except Exception: logging.warning('best-effort operation', exc_info=True)  # noqa: intentional — best-effort operation, logged at debug

                # Save execution state snapshot for history

                try:

                    snapshot_dir = os.path.expanduser("~/.aiplat/traces/history")

                    os.makedirs(snapshot_dir, exist_ok=True)

                    ts = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')

                    snap = {"ts": ts, "phase": state.get("phase",""), "tokens": state.get("tokens_used",0),

                            "stages": {s.id: {"status": "completed" if state.get(f"_stage_{s.id}_done") else "pending",

                            "output": str(state.get(s.output_artifact,""))[:1000]} for s in self._config.stages}}

                    snap_path = os.path.join(snapshot_dir, f"{state.get('session_id','unknown')}_{ts}.json")

                    with open(snap_path, 'w') as sf: json.dump(snap, sf, ensure_ascii=False, indent=2)

                except Exception: logging.warning('best-effort operation', exc_info=True)  # noqa: intentional — best-effort operation, logged at debug

                jinja_ctx[s.output_artifact or s.id] = val

        jinja_ctx.update({k: v for k, v in state.items() if not k.startswith('_') and k not in jinja_ctx})

        # Conversation state: cross-stage persistent memory

        conv = state.get('conversation_state') or state.get('_conversation_state') or {}

        jinja_ctx['conversation'] = conv if isinstance(conv, dict) else {}

        # Inject workflow environment variables (secrets) into Jinja2 context

        env_path = os.path.expanduser(os.getenv('AIPLAT_WORKFLOW_ENV_PATH', '~/.aiplat/workflow_env.json'))

        try:

            if os.path.exists(env_path):

                with open(env_path, 'r') as f:

                    wf_env = json.load(f)

                jinja_ctx['env'] = wf_env

        except Exception:

            jinja_ctx['env'] = {}

        # Inject per-node config env override

        ncf = getattr(stage, 'node_config', None) or {}

        node_env = ncf.get('env', {})

        if isinstance(node_env, dict) and node_env:

            jinja_ctx['env'] = {**jinja_ctx.get('env', {}), **node_env}



        raw = f"""You are {stage.agent_name or stage.id}.
{fb}
{scene_context}

{previous_notes}

{collective_context}

{gaps_context}

{skill_stubs_context}

{skill_corpus_context}  # noqa

{ponytail_context}

{stage_hints}

Complete your work based on upstream output.{constraint_text}{handoff_text}{iss}{agent_list}{fmt_text}{progress_text}{test_plan_text}



## Upstream Artifacts

{json.dumps(ctx, ensure_ascii=False, indent=2)}



## Task Description

{state.get('description', '')}



## Output Format

For non-code stages: Output JSON with artifact, confidence, issues, decision.

For code stages: Use ## FILE: path/to/file.py format (see Scope section above).

JSON format: {{"artifact": {{}},"confidence": "HIGH","issues": [{{"severity": "P1","description": "description","target_agent": "agent_id","suggestion": "suggestion"}}],"decision": "PROCEED"}}

"""

        return self._render_jinja2(raw, jinja_ctx)

    def _render_jinja2(self, template: str, context: dict) -> str:

        """Render {{var.path}} patterns in prompt via Jinja2, if available."""

        if '{{' not in template:

            return template

        try:

            from jinja2 import Template

            # Build nested dict from dotted keys (e.g. 'start.question' → {'start': {'question': ...}})

            nested: dict = {}

            for k, v in context.items():

                parts = k.split('.')

                d = nested

                for part in parts[:-1]:

                    d = d.setdefault(part, {})

                d[parts[-1]] = v

            return Template(template).render(**nested)

        except Exception:

            return template  # fallback: return unrendered

    def _collect_files(artifact: Dict) -> List[Dict[str, str]]:

        files = []

        for f in (artifact.get("files") or []):

            if isinstance(f, dict):

                files.append({"path": f.get("path", ""), "content": f.get("content", "")})

        return files

    def _store_artifacts(self, session_id: str, state: PipelineState) -> None:

        """Persist pipeline artifacts to ArtifactRegistry for versioned retrieval."""

        try:

            from core.harness.artifacts.registry import get_artifact_registry

            reg = get_artifact_registry()

            for s in self._config.stages:

                val = state.get(s.output_artifact)

                if not isinstance(val, dict):

                    continue

                files = self._collect_files(val)

                if files:

                    reg.store(

                        project_id=session_id,

                        name=s.output_artifact,

                        files=files,

                        session_id=session_id,

                        tags=["pipeline_crystal", s.id],

                        metadata={"agent_id": s.agent_id},

                    )

        except Exception:

            logging.getLogger("pipeline_engine").warning("best-effort skipped", exc_info=True)

    def _collect_upstream_code(self, state: PipelineState) -> Dict[str, Any]:

        """Collect code files from all upstream code-generating stages.

        

        FIX A: Only merge 'files' lists, skipping raw_output artifacts.

        Raw outputs (when _extract_files_delimiter finds no ## FILE: blocks)

        indicate the LLM didn't produce structured code — ingesting them would

        produce empty code_graph and misleading REJECTED evaluations.

        """

        all_files: List[Dict[str, str]] = []

        for s in self._config.stages:

            if s.uses_file_output and state.get(s.output_artifact):

                artifact = state[s.output_artifact]

                if isinstance(artifact, dict):

                    stage_files = self._collect_files(artifact)

                    if stage_files:

                        all_files.extend(stage_files)

        return {"files": all_files}

    def _extract_json(text: str) -> str:

        import re

        m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)

        if m:

            return m.group(1).strip()

        m = re.search(r'\{[\s\S]*\}', text)

        if m:

            return m.group(0).strip()

        return ""

    def _extract_files_delimiter(text: str) -> List[Dict[str, str]]:

        files = []

        import re



        # Preprocess: strip leading/trailing markdown fences that wrap the entire output

        text = re.sub(r'^```\w*\n', '', text.strip())

        text = re.sub(r'\n```$', '', text)



        # 1) ## FILE: path syntax (primary format)

        # Path must NOT contain spaces — use hyphens/underscores.

        # Example: ## FILE: backend/models/user.py

        for m in re.finditer(r'#{2,4}\s*FILE:\s*(\S+)[\s\S]*?\n(.*?)(?=\n##\s*FILE:|\Z)', text, re.MULTILINE):

            files.append({"path": m.group(1).strip(), "content": m.group(2).strip()})



        # 2) ```language path\n...\n``` syntax (fallback)

        # Captures optional language tag + optional file path

        for m in re.finditer(r'```(\w+)\s*(\S+)?\n([\s\S]*?)```', text):

            lang = m.group(1).strip().lower() if m.group(1) else ""

            path = m.group(2).strip() if m.group(2) else ""

            content = m.group(3).strip() if m.group(3) else ""

            # Skip pure language markers (e.g. ```python with no path)

            if not path and lang:

                continue

            # Use lang as path only if it looks like a file path

            if not path and ("/" in lang or "." in lang):

                path = lang

            if path and content and not any(f["path"] == path for f in files):

                if "/" in path or "." in path:

                    files.append({"path": path, "content": content})



        # 3) JSON {"files": [...]} format (fallback)

        json_str = PipelineEngine._extract_json(text)

        if json_str:

            try:

                import json

                data = json.loads(json_str)

                if isinstance(data.get("files"), list):

                    for f in data["files"]:

                        if isinstance(f, dict) and f.get("path") and f.get("content"):

                            if not any(e["path"] == f["path"] for e in files):

                                files.append({"path": f["path"], "content": f["content"]})

            except (json.JSONDecodeError, TypeError) as e:

                logging.warning(str(e), exc_info=True)



        # 4) ## PATCH: path with <<< ORIGINAL / === / >>> UPDATED blocks (incremental edit)

        for m in re.finditer(r'##\s*PATCH:\s*(\S+)\s*\n(.*?)(?=\n##\s*(?:FILE|PATCH):|\Z)', text, re.DOTALL):

            patch_path = m.group(1).strip()

            patch_content = m.group(2).strip()

            if patch_path and patch_content and not any(f["path"] == patch_path for f in files):

                files.append({"path": patch_path, "content": patch_content, "_is_patch": True})



        return files

    def _parse_output(raw: str) -> AgentOutput:

        json_str = PipelineEngine._extract_json(raw)

        if json_str:

            try:

                data = json.loads(json_str)

                artifact = data.get("artifact") if isinstance(data.get("artifact"), dict) else data

                issues = [Issue(severity=IssueSeverity(i.get("severity", "P1")) if i.get("severity") in {"P0","P1","P2"} else "P1",

                                 description=i.get("description", ""),

                                 target_agent=i.get("target_agent", ""),

                                 suggestion=i.get("suggestion", ""))

                           for i in (data.get("issues") or []) if isinstance(i, dict)]

                return AgentOutput(artifact=artifact if isinstance(artifact, dict) else {},

                                  issues=issues,

                                  confidence=AgentConfidence(data.get("confidence", "MEDIUM")),

                                  decision=AgentDecision(data.get("decision", "PROCEED")))

            except (json.JSONDecodeError, TypeError) as e:

                logging.warning(str(e), exc_info=True)

        return AgentOutput(artifact={"raw_output": raw[:5000]}, issues=[], confidence=AgentConfidence.LOW, decision=AgentDecision.PROCEED)