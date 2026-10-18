"""W6 — Agent architecture health checks (config + static evidence).

Surfaced via production_depth report / diagnostics UI.
Metrics: policy fail_mode, LLM bypass allowlist, architecture_profile pilot,
DynamicRouter opt-in, CRAG entrypoints, autonomous GoalExecutor default-off.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_WORKSPACE = Path(__file__).resolve().parents[4]  # aiPlat-core/core/harness/observability → repo? 
# __file__ = .../aiPlat-core/core/harness/observability/architecture_health.py
# parents[0]=observability [1]=harness [2]=core [3]=aiPlat-core [4]=workspace
if not (_WORKSPACE / "scripts").is_dir():
    _WORKSPACE = Path(__file__).resolve().parents[3]  # fallback if layout differs


def _status(ok: bool, *, warn: bool = False) -> str:
    if ok:
        return "pass"
    return "warn" if warn else "fail"


def _run_script(rel: str, *args: str, timeout: float = 15.0) -> Dict[str, Any]:
    script = _WORKSPACE / rel
    if not script.is_file():
        return {"ok": False, "detail": f"missing {rel}", "code": -1}
    try:
        proc = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=str(_WORKSPACE),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        summary = ""
        for line in out.strip().splitlines()[::-1]:
            if line.startswith("summary:"):
                summary = line
                break
        return {
            "ok": proc.returncode == 0,
            "code": proc.returncode,
            "detail": summary or out.strip()[-400:],
        }
    except Exception as e:
        return {"ok": False, "detail": f"{type(e).__name__}: {e}", "code": -1}


def _count_security_degraded(limit: int = 50) -> Dict[str, Any]:
    try:
        from core.services.execution_store import get_execution_store

        store = get_execution_store()
        if store is None:
            return {"available": False, "count": 0, "blocked": 0}
        # Best-effort: stores vary; prefer dedicated API if present
        if hasattr(store, "count_audit_by_action"):
            n = int(store.count_audit_by_action("security_degraded") or 0)
            return {"available": True, "count": n, "blocked": 0}
        if hasattr(store, "list_audit_log"):
            rows = store.list_audit_log(action="security_degraded", limit=limit) or []
            blocked = sum(
                1
                for r in rows
                if (r.get("status") == "blocked")
                or (isinstance(r.get("detail"), dict) and r["detail"].get("blocked"))
            )
            return {"available": True, "count": len(rows), "blocked": blocked}
    except Exception as e:
        return {"available": False, "count": 0, "blocked": 0, "error": f"{type(e).__name__}"}
    return {"available": False, "count": 0, "blocked": 0}


def _seed_plan_execute_pilot() -> Dict[str, Any]:
    path = _WORKSPACE / "aiPlat-core/core/workspace_seeds/teams/code_split.yaml"
    if not path.is_file():
        return {"ok": False, "detail": "code_split.yaml missing"}
    try:
        import yaml

        from core.schemas_builder import PipelineStageConfig, file_stage_control_stack

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rows = [s for s in (data.get("stages") or []) if s.get("uses_file_output")]
        stacks = []
        for row in rows:
            fields = PipelineStageConfig.model_fields
            kwargs = {k: v for k, v in row.items() if k in fields}
            kwargs["id"] = kwargs.get("id") or str(row.get("agent_id") or "stage")
            kwargs.setdefault("agent_id", kwargs["id"])
            stacks.append(file_stage_control_stack(PipelineStageConfig(**kwargs)))
        # Require external quality; do NOT require execute==react — that locked in
        # the uses_file_output→react override as a false-green health signal.
        ok = bool(stacks) and all(s.get("quality") == "external" for s in stacks)
        planned = any(
            "plan_execute" in str(s.get("schedule") or "")
            or str(s.get("execute") or "") == "plan_execute"
            for s in stacks
        )
        return {
            "ok": ok and planned,
            "detail": (
                f"code_split file stages={len(stacks)} external "
                f"plan_execute={'yes' if planned else 'no'}"
            ),
        }
    except Exception as e:
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}


def _e2e_recon_wiring() -> Dict[str, Any]:
    """UI E2E: skill norms + shared browser gather (no silent locator greenwash)."""
    skill = _WORKSPACE / "aiPlat-core/core/engine/skills/e2e_test/SKILL.md"
    loc = _WORKSPACE / "aiPlat-core/core/engine/skills/e2e_test/references/locator-rules.md"
    wait = _WORKSPACE / "aiPlat-core/core/engine/skills/e2e_test/references/waiting-rules.md"
    handler = _WORKSPACE / "aiPlat-core/core/engine/skills/e2e_test/handler.py"
    validate = _WORKSPACE / "aiPlat-core/core/engine/skills/e2e_test/validate.py"
    flow = _WORKSPACE / "aiPlat-core/core/engine/skills/e2e_test/flow.py"
    flow_ref = _WORKSPACE / "aiPlat-core/core/engine/skills/e2e_test/references/flow-rules.md"
    browser = _WORKSPACE / "aiPlat-core/core/apps/tools/browser.py"
    seal = _WORKSPACE / "aiPlat-core/core/harness/execution/execution_seal.py"
    try:
        if not skill.is_file():
            return {"ok": False, "detail": "e2e_test/SKILL.md missing"}
        if not loc.is_file() or not wait.is_file() or not flow_ref.is_file():
            return {"ok": False, "detail": "e2e_test references missing"}
        if not handler.is_file() or not validate.is_file() or not flow.is_file():
            return {"ok": False, "detail": "e2e_test handler/validate/flow missing"}
        skill_src = skill.read_text(encoding="utf-8")
        if "execution_type: handler" not in skill_src:
            return {"ok": False, "detail": "e2e_test must be execution_type: handler"}
        if "list_elements" not in skill_src or "定位变更回执" not in skill_src:
            return {"ok": False, "detail": "e2e_test missing recon/receipt gate"}
        if "禁止改绑" not in skill_src:
            return {"ok": False, "detail": "e2e_test missing anti silent-rebind"}
        if "action=flow" not in skill_src and "action=flow" not in handler.read_text(encoding="utf-8"):
            return {"ok": False, "detail": "e2e_test missing flow action"}
        flow_src = flow.read_text(encoding="utf-8")
        if "def parse_flow" not in flow_src or "def scaffold_flow_spec" not in flow_src:
            return {"ok": False, "detail": "e2e flow parse/scaffold missing"}
        if "MISSING_SNAPSHOT_TARGET" not in flow_src:
            return {"ok": False, "detail": "flow scaffold still invents locators off snapshot"}
        if "action_elements" not in flow_src or "action_elements" not in handler.read_text(encoding="utf-8"):
            return {"ok": False, "detail": "flow locators must use pre-action snapshot"}
        if not browser.is_file():
            return {"ok": False, "detail": "browser.py missing"}
        src = browser.read_text(encoding="utf-8")
        if ").format(max_items)" in src:
            return {"ok": False, "detail": "list_elements still str.formats gather JS"}
        if "_ELEMENT_SELECTORS_JS" not in src or "__aiplatCollectDom" not in src:
            return {"ok": False, "detail": "browser missing shared collectDom selectors"}
        # Prefer one selector source: no second hardcoded interactive list.
        if src.count("'[role=button]', '[role=link]'") > 1:
            return {"ok": False, "detail": "browser still duplicates interactive selector lists"}
        seal_src = seal.read_text(encoding="utf-8") if seal.is_file() else ""
        if "_E2E_SKILLS" not in seal_src or "validate_e2e_deliverable" not in seal_src:
            return {"ok": False, "detail": "execution_seal missing e2e deliverable veto"}
        pipe = _WORKSPACE / "aiPlat-core/core/harness/execution/pipeline_engine.py"
        pipe_src = pipe.read_text(encoding="utf-8") if pipe.is_file() else ""
        if '_hres.get("error")' not in pipe_src and "_hres.get('error')" not in pipe_src:
            return {"ok": False, "detail": "pipeline handler error still completes the stage"}
        return {"ok": True, "detail": "e2e_test handler+recon+seal veto+stage fail-closed"}
    except Exception as e:
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}


def _execution_seal_wiring() -> Dict[str, Any]:
    """Finish paths must enter via execution_seal (not raw bind_completion)."""
    root = _WORKSPACE / "aiPlat-core/core/harness/execution"
    seal = root / "execution_seal.py"
    facade = root / "loop" / "_facade.py"
    gate = root / "done_verify.py"
    if not seal.is_file():
        return {"ok": False, "detail": "execution_seal.py missing"}
    try:
        facade_src = facade.read_text(encoding="utf-8") if facade.is_file() else ""
        gate_src = gate.read_text(encoding="utf-8") if gate.is_file() else ""
        # Production finish paths: seal helper, not direct bind (record_tool_receipt OK).
        seal_src = seal.read_text(encoding="utf-8")
        if "apply_repair_selection" not in seal_src or "note_prediction_outcome" not in seal_src:
            return {"ok": False, "detail": "seal missing repair-candidate selection"}
        receipt_src = (root / "completion_receipt.py").read_text(encoding="utf-8")
        if "def ingest_repair_candidates" not in receipt_src or "ingest_repair_candidates(context)" not in receipt_src:
            return {"ok": False, "detail": "repair candidates are not ingested before selection"}
        if "def block_extra_repair_verify" not in receipt_src or "block_extra_repair_verify(" not in facade_src:
            return {"ok": False, "detail": "extra repair verifies are not refused"}
        if "verifying another patch" not in receipt_src:
            return {"ok": False, "detail": "a second divergent patch can still be verified before candidates exist"}
        if "Bare ``python``" not in receipt_src or "python3?\\s+-m\\s+(?:pytest|ruff|mypy)" not in receipt_src:
            return {"ok": False, "detail": "python -c can bypass the divergent patch hold"}
        if "_VERIFY_SKILLS" not in receipt_src or "test_executor" not in receipt_src:
            return {"ok": False, "detail": "verify skills can still re-run after the one-shot is spent"}
        if "_last_post_selection_verify_status" not in receipt_src or 'last == "failed"' not in receipt_src:
            return {"ok": False, "detail": "a failed winner verify cannot be retried"}
        if "def block_skipped_repair_write" not in receipt_src or "block_skipped_repair_write(" not in facade_src:
            return {"ok": False, "detail": "skipped repair candidates can still be written to disk"}
        if "def revert_skipped_repair_writes" not in receipt_src or "revert_skipped_repair_writes(context)" not in receipt_src:
            return {"ok": False, "detail": "files written before selection are not reverted"}
        if "prior_content" not in receipt_src or 'reason="repair_write"' not in receipt_src:
            return {"ok": False, "detail": "overwritten files lack a restore snapshot before selection"}
        if "def note_repair_writes_from_code" not in receipt_src or "Path.write_text" not in receipt_src:
            return {"ok": False, "detail": "code-tool open()/write_text writes are not tracked for revert"}
        if "def capture_repair_fs_baseline" not in receipt_src or "def note_repair_writes_from_fs_delta" not in receipt_src:
            return {"ok": False, "detail": "variable path writes via code tool are not tracked by fs delta"}
        if "def _repair_workdir" not in receipt_src or "_deploy_files_dir" not in receipt_src:
            return {"ok": False, "detail": "fs baseline still requires an explicit cwd key"}
        if "source_script" not in receipt_src or "def _write_tied_to_skipped" not in receipt_src:
            return {"ok": False, "detail": "writes from a skipped script are not tied for revert"}
        if "prior_b64" not in receipt_src:
            return {"ok": False, "detail": "overwritten binaries have no restore bytes"}
        if '"\\x00" in text' not in receipt_src and "'\\x00' in text" not in receipt_src:
            return {"ok": False, "detail": "NUL-bearing files can still be snapshotted as text"}
        if 'reason="repair_fs_baseline"' not in receipt_src:
            return {"ok": False, "detail": "fs baseline does not checkpoint files before code overwrite"}
        if "maybe_note_repair_fs_delta(" not in facade_src:
            return {"ok": False, "detail": "ReAct does not note fs delta after tools"}
        if "_SHELL_TOOLS" not in receipt_src or "_is_repair_shell_body" not in receipt_src:
            return {"ok": False, "detail": "shell/bash can bypass the repair verify one-shot"}
        if "_SHELL_REDIRECT" not in receipt_src or "acceptance_checker" not in receipt_src:
            return {"ok": False, "detail": "shell redirects or acceptance_checker can bypass repair gates"}
        if "skipped repair candidate" not in receipt_src:
            return {"ok": False, "detail": "one code call can still execute skipped repairs"}
        if "pre_selection" not in receipt_src:
            return {"ok": False, "detail": "pre-selection code receipts can still certify the winner"}
        if "def remember_repair_candidates" not in receipt_src or "remember_repair_candidates(" not in facade_src:
            return {"ok": False, "detail": "repair candidates are dropped when reasoning is replaced"}
        graph = root / "langgraph" / "compiled_graphs" / "react.py"
        graph_src = graph.read_text(encoding="utf-8") if graph.is_file() else ""
        if "block_extra_repair_verify(" not in graph_src:
            return {"ok": False, "detail": "compiled react bypasses the repair verify gate"}
        if "block_skipped_repair_write(" not in graph_src:
            return {"ok": False, "detail": "compiled react can still write skipped repair candidates"}
        if "maybe_note_repair_fs_delta(" not in graph_src:
            return {"ok": False, "detail": "compiled react does not note fs delta after tools"}
        if "def settle_repair_prediction" not in seal_src or "settle_repair_prediction" not in facade_src:
            return {"ok": False, "detail": "ReAct finish missing repair prediction settle"}
        if "seal_answer_with_receipts" not in facade_src:
            return {"ok": False, "detail": "facade missing seal_answer_with_receipts"}
        if "seal_before_finish" not in facade_src:
            return {"ok": False, "detail": "facade missing seal_before_finish"}
        if "_record_plan_step_receipt" not in facade_src:
            return {"ok": False, "detail": "PlanExecute missing step receipts"}
        if "check_done_verify" not in facade_src:
            return {"ok": False, "detail": "facade missing check_done_verify"}
        # llm oneshot gate must use the same receipt entry (not raw bind).
        if "seal_answer_with_receipts" not in gate_src:
            return {"ok": False, "detail": "gate_llm missing seal_answer_with_receipts"}
        if "_commit_react_finish" not in facade_src:
            return {"ok": False, "detail": "facade missing _commit_react_finish"}
        if "_finalize_plan_or_block" not in facade_src:
            return {"ok": False, "detail": "facade missing _finalize_plan_or_block"}
        if "_force_failed_status" not in facade_src:
            return {"ok": False, "detail": "facade missing _force_failed_status"}
        stage = root / "langgraph" / "stage_runner.py"
        stage_src = stage.read_text(encoding="utf-8") if stage.is_file() else ""
        if "coding defaults failed" not in stage_src:
            return {"ok": False, "detail": "stage_runner missing coding-defaults fail-closed"}
        if "not loadable" not in stage_src:
            return {"ok": False, "detail": "stage_runner missing autoreview load fail-closed"}
        sess = _WORKSPACE / "aiPlat-core/core/harness/utils/execute_session.py"
        sess_src = sess.read_text(encoding="utf-8") if sess.is_file() else ""
        if "def _sealed_failure_status" not in sess_src:
            return {"ok": False, "detail": "execute_session missing _sealed_failure_status"}
        trace = _WORKSPACE / "aiPlat-core/core/api/routers/executions_trace.py"
        trace_src = trace.read_text(encoding="utf-8") if trace.is_file() else ""
        if "def _apply_sealed_failure_status" not in trace_src:
            return {"ok": False, "detail": "executions_trace missing sealed-failure apply"}
        if "Blank run_end status is not a success seal." not in trace_src:
            return {"ok": False, "detail": "executions_trace missing blank run_end guard"}
        # Forbid finish-path direct bind (allow only inside comments / record imports).
        bad = 0
        for src in (facade_src, gate_src):
            for line in src.splitlines():
                s = line.strip()
                if s.startswith("#") or s.startswith('"""') or s.startswith("'''"):
                    continue
                if "bind_completion_to_receipts(" in s:
                    bad += 1
        if bad:
            return {
                "ok": False,
                "detail": f"finish path still calls bind_completion_to_receipts ({bad})",
            }
        return {
            "ok": True,
            "detail": "execution_seal wired (ReAct+PlanExecute+llm gate+force_failed)",
        }
    except Exception as e:
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}


def _seed_coding_closed_loop() -> Dict[str, Any]:
    """Workspace seeds + ~/.aiplat/teams runtime: L2 SOP / code_split tdd."""
    root = _WORKSPACE / "aiPlat-core/core/workspace_seeds/teams"
    if not root.is_dir():
        return {"ok": False, "detail": "workspace_seeds/teams missing"}
    try:
        import yaml

        from core.schemas_builder import PipelineStageConfig

        def _load(name: str) -> list:
            path = root / f"{name}.yaml"
            if not path.is_file():
                return []
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return [s for s in (data.get("stages") or []) if isinstance(s, dict)]

        def _as_stage(row: dict) -> PipelineStageConfig:
            fields = PipelineStageConfig.model_fields
            kwargs = {k: v for k, v in row.items() if k in fields}
            kwargs["id"] = kwargs.get("id") or str(row.get("agent_id") or "stage")
            kwargs.setdefault("agent_id", kwargs["id"])
            return PipelineStageConfig(**kwargs)

        gaps: List[str] = []
        for name in ("code", "hybrid"):
            file_rows = [r for r in _load(name) if r.get("uses_file_output")]
            if not file_rows:
                gaps.append(f"seed:{name}:no_file_stage")
                continue
            for row in file_rows:
                st = _as_stage(row)
                if not st.refactor_sop or not st.done_verify.get("require_feature_flag"):
                    gaps.append(f"seed:{name}:{st.agent_id}:refactor_sop")
        split_rows = [r for r in _load("code_split") if r.get("uses_file_output")]
        if not split_rows:
            gaps.append("seed:code_split:no_file_stage")
        for row in split_rows:
            st = _as_stage(row)
            if not st.tdd_enforce and not st.done_verify.get("require_tdd"):
                gaps.append(f"seed:code_split:{st.agent_id}:tdd")

        runtime_detail = "runtime=unchecked"
        try:
            from core.harness.team_factory_seeds import coding_closed_loop_runtime_gaps

            rt = coding_closed_loop_runtime_gaps()
            runtime_detail = (
                f"runtime_checked={rt.get('checked', 0)}"
                if not rt.get("gaps")
                else "runtime_gaps=" + ",".join((rt.get("gaps") or [])[:6])
            )
            for g in rt.get("gaps") or []:
                gaps.append(str(g))
        except Exception as e:
            runtime_detail = f"runtime_err={type(e).__name__}"

        return {
            "ok": not gaps,
            "detail": (
                f"coding closed-loop ok ({runtime_detail})"
                if not gaps
                else "gaps=" + ",".join(gaps[:10])
            ),
        }
    except Exception as e:
        return {"ok": False, "detail": f"{type(e).__name__}: {e}"}


def build_architecture_health_checks() -> List[Dict[str, Any]]:
    """Return check rows compatible with production_depth UI."""
    checks: List[Dict[str, Any]] = []
    profile = (os.getenv("AIPLAT_PROFILE") or "").strip().lower()
    fail_mode = (os.getenv("AIPLAT_POLICY_FAIL_MODE") or "open").strip().lower()
    crit_mode = (os.getenv("AIPLAT_POLICY_FAIL_CRITICAL_MODE") or "").strip().lower()
    prodish = profile == "production"

    # 1) Policy fail_mode
    if prodish:
        mode_ok = fail_mode in ("ask", "closed") or crit_mode in ("ask", "closed")
        checks.append({
            "id": "policy_fail_mode",
            "title": "架构健康 · PolicyGate 降级策略",
            "status": _status(mode_ok, warn=True),
            "detail": f"FAIL_MODE={fail_mode} CRITICAL_MODE={crit_mode or '(unset)'} profile=production",
            "hint": "生产建议 AIPLAT_POLICY_FAIL_MODE=ask，关键路径 AIPLAT_POLICY_FAIL_CRITICAL_MODE=closed",
        })
    else:
        checks.append({
            "id": "policy_fail_mode",
            "title": "架构健康 · PolicyGate 降级策略",
            "status": "pass",
            "detail": f"FAIL_MODE={fail_mode} (non-production default open OK)",
            "hint": "生产切换 profile=production 后改 ask/closed",
        })

    # 2) security_degraded volume (observability)
    deg = _count_security_degraded()
    if deg.get("available"):
        # warn if many degraded opens
        ok = int(deg.get("count") or 0) < 20
        checks.append({
            "id": "policy_degraded_count",
            "title": "架构健康 · security_degraded 审计量",
            "status": _status(ok, warn=True),
            "detail": f"recent≈{deg.get('count')} blocked≈{deg.get('blocked')}",
            "hint": "降级飙升时检查权限 DB；回滚: AIPLAT_POLICY_FAIL_MODE=open",
        })
    else:
        # Store API optional — do not fail non-prod dashboards; warn only in production.
        checks.append({
            "id": "policy_degraded_count",
            "title": "架构健康 · security_degraded 审计量",
            "status": "warn" if prodish else "pass",
            "detail": deg.get("error") or "execution_store 无审计查询接口（可选）",
            "hint": "生产建议接线 count_audit_by_action / list_audit_log(action=security_degraded)",
        })

    # 3) LLM bypass allowlist
    bypass = _run_script("scripts/check_pipeline_llm_bypass.py", "--ci")
    checks.append({
        "id": "llm_bypass_allowlist",
        "title": "架构健康 · pipeline LLM 旁路台账",
        "status": _status(bool(bypass.get("ok"))),
        "detail": str(bypass.get("detail") or ""),
        "hint": "新增 sys_llm_generate 须 # bypass-ok + allowlist（A2）",
    })

    # 4) architecture_profile pilot
    pilot = _seed_plan_execute_pilot()
    checks.append({
        "id": "architecture_profile_pilot",
        "title": "架构健康 · plan_execute 试点",
        "status": _status(bool(pilot.get("ok")), warn=True),
        "detail": str(pilot.get("detail") or ""),
        "hint": "code_split.yaml backend_developer.architecture_profile=plan_execute（B1）",
    })

    # 4b) coding closed-loop / AI refactor SOP on team seeds
    coding = _seed_coding_closed_loop()
    checks.append({
        "id": "coding_closed_loop_seeds",
        "title": "架构健康 · 编码闭环 / 重构 SOP 种子",
        "status": _status(bool(coding.get("ok")), warn=True),
        "detail": str(coding.get("detail") or ""),
        "hint": "种子+~/.aiplat/teams：code/hybrid→refactor_sop，code_split→tdd；修：sync_coding_closed_loop_team_seeds",
    })

    # 4c) execution seal single entry (ReAct / PlanExecute)
    seal = _execution_seal_wiring()
    checks.append({
        "id": "execution_seal_wiring",
        "title": "架构健康 · 执行封存单入口",
        "status": _status(bool(seal.get("ok")), warn=True),
        "detail": str(seal.get("detail") or ""),
        "hint": "完成路径走 execution_seal；PlanExecute 须记工具回执；见 execution-decision-matrix §2.6",
    })

    # 4d) UI E2E recon norms (skill + shared browser gather)
    e2e = _e2e_recon_wiring()
    checks.append({
        "id": "e2e_recon_wiring",
        "title": "架构健康 · UI E2E 侦察/定位规范",
        "status": _status(bool(e2e.get("ok")), warn=True),
        "detail": str(e2e.get("detail") or ""),
        "hint": "规范在 e2e_test；list_elements 与 click_index 共用 __aiplatCollectDom；Pi 不重做",
    })

    # 5) DynamicRouter opt-in
    enabled = (os.getenv("AIPLAT_DYNAMIC_ROUTER_ENABLED") or "0").lower() in ("1", "true", "yes", "y")
    pct = (os.getenv("AIPLAT_DYNAMIC_ROUTER_PERCENTAGE") or "0").strip()
    try:
        pct_i = int(pct)
    except ValueError:
        pct_i = 0
    router_scan = _run_script("scripts/check_team_routing_mode.py", "--ci")
    # Production: must not have ENABLED without intentional grayscale
    if prodish and enabled and pct_i >= 100:
        router_ok = False
        router_detail = "production + ENABLED + 100% — 过宽，建议灰度 PERCENTAGE<100"
    else:
        router_ok = bool(router_scan.get("ok")) and (not enabled or pct_i > 0)
        # default-off is pass
        if not enabled:
            router_ok = bool(router_scan.get("ok"))
        router_detail = (
            f"ENABLED={enabled} PERCENTAGE={pct_i} seeds={router_scan.get('detail')}"
        )
    checks.append({
        "id": "dynamic_router_opt_in",
        "title": "架构健康 · DynamicRouter 默认关",
        "status": _status(router_ok, warn=True),
        "detail": router_detail,
        "hint": "开启须 ENABLED=1 + PERCENTAGE>0 + MIN_STAGES；种子须 static 或 # routing-ok",
    })

    # 6) CRAG entrypoints
    crag = _run_script("scripts/check_retrieval_entrypoints.py", "--ci")
    checks.append({
        "id": "retrieval_crag_entry",
        "title": "架构健康 · 问答检索走 CRAG",
        "status": _status(bool(crag.get("ok"))),
        "detail": str(crag.get("detail") or ""),
        "hint": "用户侧用 kb_qa_retrieve；GraphRAG 仅 CRAG L0（W4）",
    })

    # 7) Autonomous GoalExecutor default off
    try:
        import inspect

        from core.harness.optimization.goal_executor import GoalExecutor

        gsrc = inspect.getsource(GoalExecutor.__init__)
        default_off = "enabled: bool = False" in gsrc or "enabled=False" in gsrc
        env_auto = (os.getenv("AIPLAT_GOAL_AUTO_EXECUTE") or "0").lower() in (
            "1", "true", "yes", "y",
        )
        auto_ok = default_off and not env_auto
        auto_detail = f"default_off={default_off} AIPLAT_GOAL_AUTO_EXECUTE={env_auto}"
    except Exception as e:
        auto_ok = False
        auto_detail = f"{type(e).__name__}: {e}"
    checks.append({
        "id": "autonomous_default_off",
        "title": "架构健康 · Autonomous 默认关闭",
        "status": _status(auto_ok, warn=True),
        "detail": auto_detail,
        "hint": "GoalExecutor 默认 enabled=False；开启需人工确认 + MFA（admin）",
    })

    # 8) Factory / builder default mode=single (anti Multi-Agent sprawl)
    try:
        conf = (
            _WORKSPACE
            / "aiPlat-platform/builder/generated_conformance.py"
        )
        conf_ok = False
        detail = "generated_conformance.py missing"
        if conf.is_file():
            src = conf.read_text(encoding="utf-8")
            conf_ok = 'mode = data.get("mode") or "single"' in src
            detail = (
                "builder default manifest.mode=single (+ multi_agent 五条件 AND)"
                if conf_ok
                else "default mode=single 字面量未找到"
            )
        checks.append({
            "id": "multi_agent_default_single",
            "title": "架构健康 · Multi-Agent 默认 single",
            "status": _status(conf_ok, warn=True),
            "detail": detail,
            "hint": "能单不双；升 multi_agent 须 rationale + upgrade_criteria 五条件",
        })
    except Exception as e:
        checks.append({
            "id": "multi_agent_default_single",
            "title": "架构健康 · Multi-Agent 默认 single",
            "status": "warn",
            "detail": f"{type(e).__name__}: {e}",
            "hint": "aiPlat-platform/builder/generated_conformance.py",
        })

    return checks


def build_architecture_health_report() -> Dict[str, Any]:
    checks = build_architecture_health_checks()
    passed = sum(1 for c in checks if c["status"] == "pass")
    warned = sum(1 for c in checks if c["status"] == "warn")
    failed = sum(1 for c in checks if c["status"] == "fail")
    overall = "pass" if failed == 0 and warned == 0 else ("warn" if failed == 0 else "fail")
    return {
        "status": overall,
        "score": int(round(100.0 * passed / max(len(checks), 1))),
        "summary": {"pass": passed, "warn": warned, "fail": failed, "total": len(checks)},
        "checks": checks,
    }
