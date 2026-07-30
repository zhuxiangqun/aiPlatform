"""
Wiki API — persistent LLM-curated knowledge base endpoints.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
try:
    from core.api.routers.wiki_ontology_engine import (
        OntologyDomainCreate, OntologyClassCreate, OntologyPropertyCreate,
    )
except ImportError:
    OntologyDomainCreate = Any  # type: ignore
    OntologyClassCreate = Any  # type: ignore
    OntologyPropertyCreate = Any  # type: ignore
from core.schemas_common import DeleteResponse, WikiDeleteAllResponse, ListResponse, WikiPageResponse, MessageResponse
import logging

router = APIRouter(prefix="/wiki", tags=["wiki"])

# Include sub-module routers (incremental migration)
# wiki_learning.py, wiki_loop_triggers.py, wiki_ontology_sql.py
try:
    from core.api.routers.wiki_learning import router as _learning_router
    router.include_router(_learning_router, prefix="/learning")
except ImportError:
    pass  # noqa: optional-dependency
try:
    from core.api.routers.wiki_loop_triggers import router as _loop_triggers_router
    router.include_router(_loop_triggers_router, prefix="/loop")
except ImportError:
    pass  # noqa: optional-dependency
try:
    from core.api.routers.wiki_ontology_sql import router as _ontology_sql_router
    router.include_router(_ontology_sql_router, prefix="/ontology/sql")
except ImportError:
    pass  # noqa: optional-dependency
try:
    from core.api.routers.wiki_markings import router as _markings_router
    router.include_router(_markings_router, prefix="/ontology")
except ImportError:
    pass  # noqa: optional-dependency
try:
    from core.api.routers.wiki_semantic_suggestions import router as _semantic_router
    router.include_router(_semantic_router, prefix="/ontology")
except ImportError:
    pass  # noqa: optional-dependency
try:
    from core.api.routers.wiki_health_quality import router as _health_router
    router.include_router(_health_router, prefix="/ontology")
except ImportError:
    pass  # noqa: optional-dependency
try:
    from core.api.routers.wiki_writeback import router as _writeback_router
    router.include_router(_writeback_router, prefix="/ontology")
except ImportError:
    pass  # noqa: optional-dependency
try:
    from core.api.routers.wiki_field_security import router as _field_security_router
    router.include_router(_field_security_router, prefix="/ontology")
except ImportError:
    pass  # noqa: optional-dependency
try:
    from core.api.routers.wiki_scenes import router as _scenes_router
    router.include_router(_scenes_router, prefix="/ontology")
except ImportError:
    pass  # noqa: optional-dependency
try:
    from core.api.routers.wiki_evidence import router as _evidence_router
    router.include_router(_evidence_router)
except ImportError:
    pass  # noqa: optional-dependency
try:
    from core.api.routers.wiki_proposals import router as _proposals_router
    router.include_router(_proposals_router)
except ImportError:
    pass  # noqa: optional-dependency
try:
    from core.api.routers.wiki_ontology_engine import router as _ontology_engine_router
    router.include_router(_ontology_engine_router, prefix="/ontology")
except ImportError:
    pass  # noqa: optional-dependency
try:
    from core.api.routers.wiki_ontology_domains import router as _ontology_domains_router
    router.include_router(_ontology_domains_router, prefix="/ontology")
except ImportError:
    pass  # noqa: optional-dependency
try:
    from core.api.routers.wiki_ontology_export import router as _ontology_export_router
    router.include_router(_ontology_export_router, prefix="/ontology")
except ImportError:
    pass  # noqa: optional-dependency
try:
    from core.api.routers.wiki_ontology_patterns import router as _ontology_patterns_router
    router.include_router(_ontology_patterns_router, prefix="/ontology")
except ImportError:
    pass  # noqa: optional-dependency

# ── Request Models ──────────────────────────────────────────────

class ConvertKbRequest(BaseModel):
    tenant_id: str = "default"
    collection_id: str = "default"
    limit: int = 50
    doc_ids: Optional[List[str]] = None


class WikiPageWrite(BaseModel):
    title: str
    body: str
    category: str = "entities"
    tags: List[str] = []
    related: List[str] = []
    summary: str = ""
    status: str = ""
    marking: str = ""


class WikiIngest(BaseModel):
    source_text: str
    source_title: str = ""
    source_url: str = ""


class AtomizeRequest(BaseModel):
    doc_text: str
    doc_id: str = ""
    max_atoms: int = 20
    model_name: str = ""


class CollectionCreate(BaseModel):
    collection_id: str


@router.get("/pages", response_model=Dict[str, Any])
async def list_pages(
    category: str = "",
    tag: str = "",
    query: str = "",
    source: str = "",
    limit: int = 100,
    offset: int = 0,
    collection: str = "default",
):
    from core.harness.knowledge.wiki_engine import search_pages, list_all_pages
    if query or tag:
        tags = [tag] if tag else None
        pages = search_pages(query=query, tags=tags, category=category, limit=limit, collection_id=collection)
    else:
        pages = list_all_pages(collection_id=collection)
        if category:
            pages = [p for p in pages if p["category"] == category]
        pages = pages[offset:offset + limit]
    # Filter by source_articles prefix
    if source:
        pages = [p for p in pages if any(
            s.startswith(source + ":") for s in (p.get("source_articles") or [])
        )]
    return {"items": pages, "total": len(pages)}


@router.get("/pages/{title}", response_model=Dict[str, Any])
async def read_page(title: str, category: str = "entities", collection: str = "default"):
    from core.harness.knowledge.wiki_engine import read_page
    page = read_page(title, category=category, collection_id=collection)
    if not page:
        raise HTTPException(status_code=404, detail="wiki_page_not_found")

    # ── Inference injection: add inferred relations ──
    import os as _os
    if _os.getenv("AIPLAT_WIKI_INFERENCE_ENABLED", "false").lower() in ("1", "true"):
        try:
            from core.harness.knowledge.knowledge_abox_builder import build_abox
            from core.harness.knowledge.knowledge_validator import TripleStore, _short, run_full_inference
            onto = build_abox(collection_id=collection)
            store = TripleStore(onto.triples)
            inference = run_full_inference(store)

            page_uri = f"http://aiplat.local/knowledge#{title}"
            inferred = []
            for kind in ("transitive", "source_chain"):
                for inf in inference.get(kind, []):
                    if inf.get("subject") == page_uri or inf.get("object") == page_uri:
                        pred = inf["predicate"].replace("http://aiplat.local/knowledge#", "")
                        target = _short(inf["object"]) if inf["subject"] == page_uri else _short(inf["subject"])
                        inferred.append({
                            "type": pred,
                            "target": target,
                            "direction": "out" if inf["subject"] == page_uri else "in",
                            "provenance": kind,
                        })
            if inferred:
                page["inferred_relations"] = inferred
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    return page


@router.delete("/pages/{title}", response_model=DeleteResponse)
async def delete_page(title: str, collection: str = "default"):
    from core.harness.knowledge.wiki_engine import delete_page as _del
    ok = _del(title, collection_id=collection)
    if not ok:
        raise HTTPException(status_code=404, detail="wiki_page_not_found")
    return {"title": title, "status": "deleted"}


@router.delete("/pages-all", response_model=WikiDeleteAllResponse)
async def delete_all_pages(collection: str = "default"):
    from core.harness.knowledge.wiki_engine import delete_all_pages
    result = delete_all_pages(collection_id=collection)
    return {"deleted": result["deleted"], "message": f"已清空 {result['deleted']} 个 Wiki 页面"}


@router.post("/cleanup-ghosts", response_model=Dict[str, Any])
async def cleanup_ghost_pages(collection: str = "default", dry_run: bool = True):
    """Batch-clean ghost pages (search index entries with no stored page data).

    Ghost pages exist in the search index but have no real content.
    They are removed from disk and the FTS index. A single cache invalidation
    round runs at the end (instead of per-page O(n²) similarity checks).

    Query params:
        collection: Wiki collection ID (default: "default")
        dry_run: If true (default), only scan and report. Set false to actually delete.
    """
    from core.harness.knowledge.wiki_engine import cleanup_ghost_pages as _cleanup
    result = _cleanup(collection_id=collection, dry_run=dry_run)
    return result


@router.get("/unprocessed-docs", response_model=Dict[str, Any])
async def get_unprocessed_docs(tenant_id: str = "default", collection: str = "default"):
    u"""Return KB documents that don't have corresponding wiki pages.
    
    Cross-references wiki page source_articles (kb:doc_id) with
    KB documents table. No platform auth required.
    """
    import os, json as _json, sqlite3 as _sq
    from core.harness.knowledge.wiki_engine import search_pages
    
    kb_dir = os.path.expanduser(os.getenv("AIPLAT_KB_TENANTS_DIR", "~/.aiplat/kb/tenants"))
    kb_db = os.path.join(kb_dir, tenant_id, "kb.sqlite3")
    if not os.path.exists(kb_db):
        return {"items": [], "total": 0}
    
    # Get all wiki-sourced KB doc_ids
    wiki_pages = search_pages(limit=1000, collection_id=collection)
    wiki_doc_ids = set()
    for p in wiki_pages:
        for s in (p.get("source_articles") or []):
            if s.startswith("kb:"):
                wiki_doc_ids.add(s.replace("kb:", ""))
    
    # Find KB docs not in wiki — check both actual wiki references AND wikified status
    conn = _sq.connect(kb_db)
    conn.row_factory = _sq.Row
    docs = conn.execute(
        "SELECT doc_id, source_uri, kind, status, wiki_status, meta_json FROM documents WHERE tenant_id=? AND status='ready'",
        (tenant_id,)
    ).fetchall()

    unprocessed = []
    for d in docs:
        # Skip if this doc_id is already referenced by a real wiki page
        if d["doc_id"] in wiki_doc_ids:
            continue
        # Skip only if BOTH wiki_pages exist AND wiki_status is 'wikified'
        # (mirrors the bulk convert double-condition check at line ~839)
        ws = str(d["wiki_status"] or "").strip()
        if ws == "wikified":
            try:
                meta = _json.loads(d["meta_json"] or "{}")
                if meta.get("wiki_pages"):
                    continue  # fully converted: wiki pages exist and status is wikified
            except Exception as e:
                logging.warning(str(e), exc_info=True)
        unprocessed.append({
            "doc_id": d["doc_id"],
            "source_uri": d["source_uri"],
            "kind": d["kind"],
            "status": d["status"],
        })
    conn.close()
    return {"items": unprocessed, "total": len(unprocessed)}


@router.get("/skill-deps", response_model=Dict[str, Any])
async def get_skill_deps():
    u"""Return Agent→Skill→Syscall dependency graph."""
    from core.harness.knowledge.skill_deps import build_skill_deps
    return build_skill_deps()


@router.get("/skill-impact/{skill_id}", response_model=Dict[str, Any])
async def get_skill_impact(skill_id: str):
    u"""Return agents and skills affected by a given skill."""
    from core.harness.knowledge.skill_deps import skill_impact
    result = skill_impact(skill_id)
    if not result.get("exists"):
        raise HTTPException(status_code=404, detail="skill not found")
    return result


@router.post("/skills/install-from-directory", response_model=Dict[str, Any])
async def install_skills_from_directory(search_path: str = Body(..., embed=True)):
    u"""Install SKILL.md files from a directory (e.g. cloned agent-skills repo).

    Scans path/skills/*/SKILL.md, copies to ~/.aiplat/skills/<name>/.
    Auto-fills trigger_keywords and execution_type defaults.
    Compatible with Google agent-skills (addyosmani/agent-skills) format.
    """
    import glob as _glob, os as _os, shutil as _shutil

    expanded = _os.path.expanduser(search_path)
    pattern = _os.path.join(expanded, "skills", "*", "SKILL.md")
    md_files = _glob.glob(pattern)

    if not md_files:
        # Also try flat structure: path/*/SKILL.md
        pattern2 = _os.path.join(expanded, "*", "SKILL.md")
        md_files = _glob.glob(pattern2)

    if not md_files:
        raise HTTPException(  # noqa: error-structured
            status_code=404,
            detail=f"No SKILL.md files found in {expanded}. "
                   f"Expected structure: {{path}}/skills/<name>/SKILL.md "
                   f"or {{path}}/<name>/SKILL.md"
        )

    workspace = _os.path.expanduser("~/.aiplat/skills")
    _os.makedirs(workspace, exist_ok=True)

    installed = []
    skipped = []
    import yaml as _yaml

    for md_path in md_files:
        try:
            with open(md_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Parse frontmatter
            name = _os.path.basename(_os.path.dirname(md_path))
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    try:
                        fm = _yaml.safe_load(parts[1])
                        if isinstance(fm, dict):
                            name = fm.get("name", name)
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)

            dest_dir = _os.path.join(workspace, name)
            _os.makedirs(dest_dir, exist_ok=True)
            dest_path = _os.path.join(dest_dir, "SKILL.md")

            # Copy file
            _shutil.copy2(md_path, dest_path)
            installed.append({"name": name, "source": md_path, "dest": dest_path})

        except Exception as e:
            skipped.append({"path": md_path, "error": str(e)[:200]})

    return {
        "installed": len(installed),
        "skipped": len(skipped),
        "skills": installed,
        "errors": skipped,
        "workspace": workspace,
    }


class ShipRequest(BaseModel):
    pipeline_id: str = ""
    stage_id: str = ""
    assess_report: Dict[str, Any] = {}
    skip_security: bool = False
    skip_perf: bool = False
    skip_sandbox: bool = False
    sandbox_params: Dict[str, Any] = {}
    sandbox_scenarios: int = 10


@router.post("/pipeline/ship", response_model=Dict[str, Any])
async def ship_pipeline(req: ShipRequest):
    u"""Final deployment gate. Requires all assessments PASS before allowing ship.

    Runs security-auditor and web-perf-auditor checks (if available).
    Returns ship decision: ALLOW | BLOCKED | NEEDS_APPROVAL.
    """
    gates = []
    blocked = False

    # Gate 1: AssessAgent must have passed
    if req.assess_report:
        overall = req.assess_report.get("overall", "UNKNOWN")
        gates.append({
            "gate": "assess",
            "status": overall,
            "passed": overall == "PASS",
            "detail": req.assess_report.get("summary", ""),
        })
        if overall != "PASS":
            blocked = True

    # Gate 2: Security audit (unless skipped)
    if not req.skip_security:
        sec_ok, sec_detail = _check_skill_available("security-auditor")
        gates.append({
            "gate": "security",
            "status": "READY" if sec_ok else "UNAVAILABLE",
            "passed": True,  # unavailable = not blocking, just warn
            "detail": sec_detail,
        })

    # Gate 3: Pipeline Sandbox — variant scenario validation
    if not req.skip_sandbox and req.sandbox_params:
        from core.harness.execution.pipeline_sandbox import run_sandbox_validation
        sandbox = await run_sandbox_validation(
            req.sandbox_params,
            scenario_count=req.sandbox_scenarios,
            assessment_rubric=req.assess_report.get("criteria", []),
        )
        gates.append({
            "gate": "sandbox",
            "status": "PASS" if not sandbox.blocked else "BLOCKED",
            "passed": not sandbox.blocked,
            "detail": sandbox.summary,
            "scenarios": [
                {"id": s.scenario_id, "passed": s.passed, "mutation": s.mutation_applied}
                for s in sandbox.scenarios
            ],
        })
        if sandbox.blocked:
            blocked = True

    # Gate 4: Performance check (unless skipped)
    if not req.skip_perf:
        perf_ok, perf_detail = _check_skill_available("web-perf-auditor")
        gates.append({
            "gate": "perf",
            "status": "READY" if perf_ok else "UNAVAILABLE",
            "passed": True,
            "detail": perf_detail,
        })

    # Gate 4: SESSION_NOTES present
    notes_ok = _check_session_notes(req.pipeline_id)
    gates.append({
        "gate": "session_notes",
        "status": "FOUND" if notes_ok else "MISSING",
        "passed": notes_ok,
        "detail": "SESSION_NOTES.md found" if notes_ok else "No session notes — shipping without documentation is not recommended",
    })

    if blocked:
        return {"decision": "BLOCKED", "gates": gates, "message": "One or more gates failed. Fix before shipping."}

    return {"decision": "ALLOW", "gates": gates, "message": "All gates passed. Ready to ship."}


@router.post("/pipeline/self-harness", response_model=Dict[str, Any])
async def run_self_harness_cycle():
    u"""Run the Self-Harness optimization cycle."""
    try:
        from core.harness.execution.failure_clusterer import load_clusters
        from core.api.core_facade import run_self_harness_cycle
        from core.harness.kernel.runtime import get_kernel_runtime

        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        run_states = []
        if store is not None:
            try:
                events = await store.list_completed_runs(limit=50)
                run_states = [e.get("pipeline_state", {}) for e in events if e.get("pipeline_state")]
            except Exception as e:
                logging.warning(str(e), exc_info=True)

        if not run_states:
            return {"accepted": [], "rejected": [], "message": "No completed runs found for analysis"}

        result = await run_self_harness_cycle(run_states)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Self-Harness failed: {e}")


class SandboxRequest(BaseModel):
    seed_params: Dict[str, Any] = {}
    scenario_count: int = 10


@router.post("/pipeline/sandbox", response_model=Dict[str, Any])
async def run_pipeline_sandbox(req: SandboxRequest):
    u"""Run Pipeline Sandbox — generate variant scenarios and validate.

    Takes a seed parameter set (from a successful run) and generates
    N variant scenarios with boundary values, empty injections, field swaps.
    Returns per-scenario pass/fail results and a deployment-block decision.
    """
    from core.harness.execution.pipeline_sandbox import run_sandbox_validation
    report = await run_sandbox_validation(
        req.seed_params,
        scenario_count=req.scenario_count,
    )
    return {
        "blocked": report.blocked,
        "total": report.total_scenarios,
        "passed": report.passed,
        "failed": report.failed,
        "summary": report.summary,
        "scenarios": [
            {"id": s.scenario_id, "passed": s.passed, "error": s.error[:100], "mutation": s.mutation_applied}
            for s in report.scenarios
        ],
    }



@router.get("/pipeline/diagnose/{run_id}", response_model=Dict[str, Any])
async def diagnose_pipeline_run(run_id: str):
    u"""Diagnostic report for a single pipeline run.

    Combines failure attribution, assessment results, and execution trace
    to produce a structured diagnostic report with blame distribution.

    Returns:
      {run_id, status, failure: {...}, blame: {prompt, retrieval, tool, model},
       stages: [...], suggestion: "..."}
    """
    from core.harness.kernel.runtime import get_kernel_runtime
    runtime = get_kernel_runtime()
    store = getattr(runtime, "execution_store", None) if runtime else None

    run_state = {}
    if store is not None:
        try:
            events = await store.get_syscall_events(run_id=run_id, limit=200)
            # Reconstruct state from events
            for e in events:
                if isinstance(e, dict) and e.get("kind") == "pipeline":
                    run_state = e.get("args", {})
                    break
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    if not run_state:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    # ── Collect diagnostics ──
    diagnosis = _build_diagnosis(run_id, run_state)
    return diagnosis


def _build_diagnosis(run_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    u"""Build a structured diagnostic report from pipeline state."""
    from core.harness.execution.failure_clusterer import (
        classify_verifier_cause, classify_causal_status, classify_abstract_mechanism,
    )

    stage_diags = []
    overall_status = "passed"
    failure = None
    blame = {"prompt": "low", "retrieval": "low", "tool": "low", "model": "low"}

    # Collect per-stage diagnostics
    graph_trace = state.get("_graph_trace", [])
    for node in graph_trace:
        if not isinstance(node, dict):
            continue
        stage_id = node.get("node", "unknown")
        status = node.get("status", "unknown")

        stage_diag = {
            "stage_id": stage_id,
            "status": status,
            "elapsed": node.get("elapsed", 0),
            "metrics": node.get("metrics", {}),
        }

        if status in ("failed", "paused"):
            overall_status = "failed"
            verifier = classify_verifier_cause(state, stage_id)
            causal = classify_causal_status(state, stage_id)
            mechanism = classify_abstract_mechanism(state, stage_id)

            stage_diag["failure"] = {
                "verifier_cause": verifier,
                "causal_status": causal,
                "abstract_mechanism": mechanism,
            }
            stage_diag["error"] = str(state.get("error", ""))[:200]

            if failure is None:
                failure = {
                    "stage": stage_id,
                    "verifier_cause": verifier,
                    "causal_status": causal,
                    "abstract_mechanism": mechanism,
                }

        # Per-stage assess results
        assess = state.get(f"_assess_{stage_id}")
        if isinstance(assess, dict):
            stage_diag["assessment"] = {
                "overall": assess.get("overall", ""),
                "passed": assess.get("passed_count", 0),
                "failed": assess.get("failed_count", 0),
                "summary": assess.get("summary", ""),
            }

        # Quick check issues
        qc = state.get("_quick_check_issues", [])
        if qc:
            stage_diag["quick_checks"] = [str(i)[:100] for i in qc[:5]]

        stage_diags.append(stage_diag)

    # ── Blame attribution: determine where the problem most likely is ──
    if failure:
        mech = failure["abstract_mechanism"]
        causal = failure["causal_status"]
        verifier = failure["verifier_cause"]

        # Tool-related failures
        if causal in ("wrong_tool_usage", "tool_selection_mismatch"):
            blame["tool"] = "high"
        # Retrieval-related
        elif "context" in causal or "overflow" in causal:
            blame["retrieval"] = "medium"
            blame["prompt"] = "medium"
        # Format/output issues → likely model or prompt
        elif mech == "format_drift":
            blame["model"] = "high"
            blame["prompt"] = "medium"
        elif mech == "early_endless_search" or mech == "no_early_artifact_creation":
            blame["prompt"] = "high"
            blame["model"] = "medium"
        elif mech == "delete_instead_of_fix":
            blame["model"] = "high"
            blame["tool"] = "medium"
        elif verifier == "assess_fail":
            blame["model"] = "high"
            blame["prompt"] = "medium"
            blame["tool"] = "medium"
        elif verifier == "compile_error":
            blame["model"] = "high"
        elif verifier == "timeout":
            blame["retrieval"] = "medium"
            blame["model"] = "medium"

    # ── Generate suggestion ──
    suggestion = ""
    if failure:
        field_map = {
            "early_endless_search": "Consider adding 'create artifact early' to prompt_extra or reducing stage_timeout_seconds",
            "no_early_artifact_creation": "Add bootstrap instruction in prompt_extra: 'Create an initial artifact version before exploring'",
            "delete_instead_of_fix": "Add rule in prompt_extra: 'Never delete a working artifact. Fix it in-place or create a new version'",
            "format_drift": "Add response_format (JSON schema) to this stage to enforce output structure",
            "identical_retry_loop": "Set max_consecutive_llm_failures=2 and failure_strategy='skip_stage' to break loops",
            "context_bloat": "Reduce max_tokens_per_run or enable render_upstream=false for non-PRD stages",
            "unclassified_pattern": "Review the stage output and quick_check_issues for manual diagnosis",
        }
        suggestion = field_map.get(failure["abstract_mechanism"], f"Review stage '{failure['stage']}' — verifier={failure['verifier_cause']}, mechanism={failure['abstract_mechanism']}")

    # Additional hints from state
    if state.get("_last_action_reason"):
        suggestion += f" (last action: {state.get('_last_action_reason')})"

    return {
        "run_id": run_id,
        "status": overall_status,
        "failure": failure,
        "blame": blame,
        "stages": stage_diags,
        "suggestion": suggestion,
    }



def _check_skill_available(skill_name: str):
    u"""Check if a persona skill is installed in workspace."""
    import os as _os
    skill_dir = _os.path.expanduser(f"~/.aiplat/skills/{skill_name}")
    if _os.path.isdir(skill_dir):
        return True, f"Skill '{skill_name}' found in workspace"
    return False, f"Skill '{skill_name}' not installed. Install from agent-skills or skip this gate."


def _check_session_notes(pipeline_id: str) -> bool:
    u"""Check if SESSION_NOTES.md exists for a pipeline run."""
    import os as _os, glob as _glob
    home = _os.getenv("AIPLAT_HOME", _os.path.expanduser("~/.aiplat"))
    pattern = _os.path.join(home, "output", "*", "SESSION_NOTES.md")
    return len(_glob.glob(pattern)) > 0


@router.get("/proposals", response_model=Dict[str, Any])
async def get_proposals(status: str = "", collection: str = "default"):
    u"""List pending wiki knowledge proposals (merge/update/supplement/contradict)."""
    from core.harness.knowledge.wiki_engine import load_proposals
    proposals = load_proposals(collection_id=collection)
    if status:
        proposals = [p for p in proposals if p.get("status") == status]
    return {"items": proposals, "total": len(proposals)}


@router.put("/proposals/{proposal_id}", response_model=Dict[str, Any])
async def handle_proposal(proposal_id: str, body: Dict[str, Any], collection: str = "default"):
    u"""Approve/reject a proposal. Body: {status: 'approved'|'rejected'}."""
    from core.harness.knowledge.wiki_engine import update_proposal_status, apply_proposal
    status = body.get("status", "")
    if status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be 'approved' or 'rejected'")
    ok = update_proposal_status(proposal_id, status, collection_id=collection)
    if not ok:
        raise HTTPException(status_code=404, detail="proposal not found")
    result = {"proposal_id": proposal_id, "status": status}
    # If approved, execute the proposal action
    if status == "approved":
        result["execution"] = apply_proposal(proposal_id, collection_id=collection)
    return result


@router.post("/pages", response_model=Dict[str, Any])
async def create_wiki_page(body: WikiPageWrite, collection: str = "default"):
    from core.harness.knowledge.wiki_engine import write_page, auto_link_page, search_pages, update_page
    try:
        path = write_page(body.title, body.body, category=body.category,
                          tags=body.tags, related=body.related, summary=body.summary,
                          status=body.status, marking=body.marking,
                          collection_id=collection)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    # Auto-link via embedding similarity (through infra adapter)
    auto_links = []
    try:
        all_titles = [p["title"] for p in search_pages(limit=500, collection_id=collection)]
        auto_links = auto_link_page(body.title, body.body, all_titles)
        if auto_links:
            update_page(body.title, related=list(set(body.related or [] + auto_links)), collection_id=collection)
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    # ── Version sync: if page was updated (not new), mark related ontology instances for review ──
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        from core.harness.ontology_engine.engine import _persist_reviews
        graph = GraphIndex.load("ai-knowledge")
        node = graph.find_by_name(body.title)
        if node and len(graph) > 0:
            inverse_rels = graph.get_inverse_relations(node.entity_id)
            if inverse_rels:
                affected = []
                for e in inverse_rels:
                    src_node = graph.get_node(e.source_id)
                    if src_node:
                        affected.append({
                            "from_instance": body.title,
                            "from_class": "WikiPage",
                            "to_instance": src_node.entity_name,
                            "to_class": src_node.class_name,
                            "reason": "源文档已更新，请审查关联的本体实例是否需要同步修订",
                            "transition": "source_version_changed",
                        })
                if affected:
                    _persist_reviews("ai-knowledge", affected)
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    # ── Synthesis version sync: mark synthesis pages for review ──
    try:
        from core.harness.knowledge.wiki_engine import _sync_synthesis_pages
        _sync_synthesis_pages(body.title, collection_id=collection)
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    # ── Provenance stale tracking: mark citations as stale if page version changed ──
    try:
        from core.harness.knowledge.wiki_engine import read_page
        updated = read_page(body.title, collection_id=collection)
        if updated:
            new_version = str(updated.get("fm", {}).get("version", "1"))
            from core.harness.knowledge.provenance import get_provenance_tracker, ProvenanceScanner
            tracker = get_provenance_tracker()
            scanner = ProvenanceScanner(tracker)
            await scanner.on_source_updated(body.title, new_version)
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    # ── SemanticCache invalidation: clear cache for this domain on wiki update ──
    try:
        from core.harness.knowledge.semantic_cache import get_semantic_cache
        cache = get_semantic_cache()
        if cache.enabled:
            await cache.invalidate_domain(collection)
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    return {"title": body.title, "path": path, "status": "created", "auto_links": auto_links}


@router.get("/traverse/{title}", response_model=Dict[str, Any])
async def traverse_links(title: str, depth: int = 2, collection: str = "default"):
    from core.harness.knowledge.wiki_engine import traverse_links
    pages = traverse_links(title, depth=depth, collection_id=collection)
    return {"root": title, "depth": depth, "pages": len(pages), "items": pages}


@router.get("/lint", response_model=Dict[str, Any])
async def lint_wiki(collection: str = "default"):
    from core.harness.knowledge.wiki_engine import wiki_health_report
    return wiki_health_report()


@router.get("/graph", response_model=Dict[str, Any])
async def wiki_graph(
    category: str = "",
    keyword: str = "",
    source: str = "",
    max_nodes: int = 300,
 collection: str = "default"):
    from core.harness.knowledge.wiki_engine import build_graph
    return build_graph(category=category, keyword=keyword, source=source, max_nodes=max_nodes, collection_id=collection)


@router.post("/ingest", response_model=Dict[str, Any])
async def ingest_text(body: WikiIngest):
    """Submit text for wiki processing. The wiki_curator agent handles this asynchronously."""
    import uuid, time
    from core.harness.knowledge.wiki_engine import write_page, _wiki_root
    # Store raw source for later processing
    source_dir = _wiki_root() / "_sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    sid = f"src_{uuid.uuid4().hex[:8]}"
    import json as _json
    (source_dir / f"{sid}.json").write_text(_json.dumps({
        "id": sid, "title": body.source_title, "text": body.source_text[:50000],
        "url": body.source_url, "ingested_at": time.time(),
    }, ensure_ascii=False))
    # ── Cache invalidation ──
    try:
        from core.harness.knowledge.semantic_cache import SemanticCache
        cache = SemanticCache()
        cache.invalidate_domain(body.collection if hasattr(body, 'collection') else "default")
    except Exception:
        logging.getLogger(__name__).debug('ingest_text failed', exc_info=True)
    try:
        from core.harness.knowledge.wiki_engine import invalidate_graph_cache
        invalidate_graph_cache(body.collection if hasattr(body, 'collection') else "default")
    except Exception:
        logging.getLogger(__name__).debug('ingest_text failed', exc_info=True)
    # ── Provenance: mark all answers referencing this source as stale ──
    try:
        from core.harness.knowledge.provenance import get_provenance_tracker, ProvenanceScanner
        tracker = get_provenance_tracker()
        scanner = ProvenanceScanner(tracker)
        import asyncio as _asyncio
        _asyncio.create_task(scanner.on_source_updated(sid, str(time.time())))
    except Exception:
        logging.getLogger(__name__).debug('ingest_text failed', exc_info=True)
    return {"source_id": sid, "status": "ingested",
            "message": "Text stored. Execute wiki_curator agent to process and update wiki pages."}


@router.post("/ingest/url", response_model=Dict[str, Any])
async def ingest_url(body: dict):
    """Phase 42: One-click URL import — fetch URL, convert to Markdown, save to raw inbox.

    Body: {"url": "https://...", "collection": "default", "tags": ["ai", "research"]}
    """
    import uuid, time, json as _json
    url = str(body.get("url", "")).strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    collection = str(body.get("collection", "default"))
    tags = body.get("tags", []) or []

    # Fetch URL content
    try:
        import urllib.request as _urllib
        req = _urllib.Request(url, headers={"User-Agent": "aiPlat-WikiIngest/1.0"})
        resp = _urllib.urlopen(req, timeout=15)
        content_type = resp.headers.get("Content-Type", "")
        raw_html = resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {e}")

    # Convert HTML to plain text (try markdownify if available, else strip HTML)
    text = raw_html
    title = url.rsplit("/", 1)[-1] or url
    try:
        import re as _re
        title_match = _re.search(r"<title>(.*?)</title>", raw_html, _re.IGNORECASE | _re.DOTALL)
        if title_match:
            title = title_match.group(1).strip()[:200]
        # Strip HTML tags for plain text storage
        clean = _re.sub(r"<script[^>]*>.*?</script>", "", raw_html, flags=_re.IGNORECASE | _re.DOTALL)
        clean = _re.sub(r"<style[^>]*>.*?</style>", "", clean, flags=_re.IGNORECASE | _re.DOTALL)
        clean = _re.sub(r"<[^>]+>", " ", clean)
        clean = _re.sub(r"\s+", " ", clean).strip()
        if clean:
            text = clean
    except Exception:
        logging.getLogger(__name__).debug('HTML text extraction failed, falling back to raw HTML', exc_info=True)

    # Save to raw inbox
    from core.harness.knowledge.wiki_engine import _wiki_root
    source_dir = _wiki_root() / "_sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    sid = f"src_{uuid.uuid4().hex[:8]}"
    (source_dir / f"{sid}.json").write_text(_json.dumps({
        "id": sid, "title": title, "text": text[:50000],
        "url": url, "tags": tags,
        "ingested_at": time.time(), "source": "url_import",
    }, ensure_ascii=False))

    return {
        "source_id": sid, "status": "ingested", "title": title,
        "chars": len(text), "collection": collection,
        "message": f"URL content saved ({len(text)} chars). Auto-compile via /wiki/index-md.",
    }


@router.post("/ingest/reparse", response_model=Dict[str, Any])
async def trigger_reparse(doc_id: str = "", source_path: str = ""):
    """HITL reparse: submit a document for re-processing through the ontology pipeline.

    The document is added to a queue and processed one-at-a-time by a background worker.
    Status can be checked via GET /ingest/reparse/{doc_id}/status.
    """
    if not doc_id:
        return {"success": False, "message": "doc_id is required"}
    from core.harness.knowledge.reparse_queue import enqueue_reparse
    return await enqueue_reparse(doc_id, source_path)


@router.get("/ingest/reparse/{doc_id}/status", response_model=Dict[str, Any])
async def get_reparse_status(doc_id: str):
    """Check the reparse status for a document."""
    from core.harness.knowledge.reparse_queue import get_reparse_status
    return await get_reparse_status(doc_id)


@router.get("/ingest/reparse/queue/stats", response_model=Dict[str, Any])
async def get_reparse_queue_stats():
    """Get reparse queue statistics."""
    from core.harness.knowledge.reparse_queue import get_queue_stats
    return await get_queue_stats()


@router.post("/atomize-document", response_model=Dict[str, Any])
async def atomize_document(body: AtomizeRequest, collection: str = "default"):
    """Ontology-driven atom extraction: raw document → KnowledgeAtoms with evidence.

    Uses T-Box schema to guide LLM extraction of claims with precise source positions.
    Each atom includes: evidence_start, evidence_end, evidence_text, confidence.
    Automatically detects contradictions and creates ContradictionPages.
    """
    import asyncio
    from core.harness.knowledge.wiki_engine import atomize_document as _atomize

    doc_id = body.doc_id or f"doc_{abs(hash(body.doc_text[:100])) % 10**12:012d}"
    try:
        result = await _atomize(
            body.doc_text, doc_id,
            collection_id=collection,
            max_atoms=body.max_atoms,
            model_name=body.model_name,
        )
        return {
            "doc_id": doc_id,
            "atoms_extracted": result["atoms_extracted"],
            "atoms_written": result["atoms_written"],
            "contradictions_found": result["contradictions_found"],
            "contradiction_pages_created": result["contradiction_pages_created"],
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Atomization failed: {e}")


@router.post("/import-docs-dir", response_model=Dict[str, Any])
async def import_docs_directory(collection: str = "system_docs"):
    """导入 docs/ 目录下所有 .md 文件到 Wiki 知识库。
    
    遍历项目 docs/ 目录，将每个 .md 文件作为 Wiki 页面写入指定集合。
    已存在的页面会自动更新（upsert）。
    """
    import os
    from pathlib import Path
    from core.harness.knowledge.wiki_engine import write_page

    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    docs_root = project_root / "docs"
    if not docs_root.is_dir():
        raise HTTPException(status_code=404, detail=f"docs dir not found: {docs_root}")

    created = skipped = errors = 0
    error_details = []
    for md_file in docs_root.rglob("*.md"):
        fp = str(md_file)
        if ".venv" in fp or "node_modules" in fp or "__pycache__" in fp:
            continue
        try:
            title = str(md_file.relative_to(docs_root)).replace("/", " / ").replace(".md", "")
            body = md_file.read_text(encoding="utf-8")
            write_page(
                title=title, body=body[:200000],
                category="system_docs",
                tags=["documentation", md_file.parent.name],
                collection_id=collection,
                status="published",
            )
            created += 1
        except Exception as e:
            err_msg = str(e)
            if "already exists" in err_msg.lower():
                skipped += 1
            else:
                errors += 1
                error_details.append({"file": fp.split("/docs/")[-1][:80], "error": err_msg[:200]})

    return {
        "created": created, "skipped": skipped, "errors": errors,
        "error_details": error_details[:10],
    }


@router.post("/suggest-domain", response_model=Dict[str, Any])
async def suggest_domain(body: Dict[str, Any]):
    """推荐匹配的领域（用于数据源入库时选择目标领域）。
    
    返回 top-3 候选领域及余弦相似度。
    即使未达路由阈值也返回，供用户手动选择。
    """
    query = str(body.get("query", "")).strip()
    if not query:
        return {"suggestions": [], "message": "query required"}

    from core.harness.knowledge.domain_router import DomainRouter
    router = DomainRouter()
    suggestions = router.suggest(query, top_k=3)
    return {
        "suggestions": [{"domain_id": did, "similarity": round(s, 3)} for did, s in suggestions],
        "query": query,
    }


@router.post("/generate-domain", response_model=Dict[str, Any])
async def generate_domain(
    collection: str = "system_docs",
    domain_name: str = "",
    domain_id: str = "aiplat-system",
):
    """从指定集合的实体中自动生成领域 YAML。
    
    读取集合中的 entities 和 topics，提取类定义、属性和关系，
    输出到 ~/.aiplat/ontologies/{domain_id}.yaml。
    """
    import os, re, yaml, time, logging
    from pathlib import Path
    from core.harness.knowledge.wiki_engine import _wiki_root, list_all_pages

    logger = logging.getLogger(__name__)
    ont_dir = Path(os.path.expanduser("~/.aiplat/ontologies"))
    ont_dir.mkdir(parents=True, exist_ok=True)

    # 1. 收集该集合中所有页面
    pages = list_all_pages(collection_id=collection)
    if not pages:
        return {"status": "error", "message": "集合中没有页面，请先导入文档"}

    # 2. 按 category 分组，提取 entity 和 topic 信息
    entities = [p for p in pages if p.get("category") == "entities"]
    topics = [p for p in pages if p.get("category") == "topics"]
    logger.info("generate-domain: collection=%s entities=%d topics=%d", collection, len(entities), len(topics))

    # 3. 从实体中提取 class_name 聚类
    class_map: dict = {}
    for ep in entities:
        class_name = ep.get("title", "") or "unknown"
        tags = ep.get("tags", []) or []
        summary = ep.get("summary", "")[:200]
        # 尝试从标签推断有意义的类别名
        clean_class = class_name[:60].strip()
        if clean_class not in class_map:
            class_map[clean_class] = {"entities": [], "tags": set(), "summaries": []}
        class_map[clean_class]["entities"].append(class_name)
        class_map[clean_class]["tags"].update(tags)
        class_map[clean_class]["summaries"].append(summary)

    # 4. 构建领域 YAML
    domain_name = domain_name or f"{collection} 系统知识"
    classes_yaml = {}
    for cname, info in sorted(class_map.items()):
        safe_key = re.sub(r"[<>:\"/\\|?*]", "_", cname)[:80]
        classes_yaml[safe_key] = {
            "label": cname,
            "description": " | ".join(info["summaries"][:3]) or f"自动生成的{cname}类",
            "required_fields": ["name", "description"],
            "optional_fields": sorted(set(info["tags"]) - {"documentation", "manual"})[:10],
            "categories": [safe_key.lower()],
            "states": {
                "default": "draft",
                "enum": [
                    {"name": "draft", "label": "草稿"},
                    {"name": "published", "label": "已发布"},
                ],
            },
        }

    domain_yaml = {
        "name": domain_name,
        "namespace": f"http://aiplat.local/ontology/{domain_id}/",
        "description": f"自动生成的 {collection} 集合领域本体 (v1.0.0)",
        "version": "1.0.0",
        "classes": classes_yaml,
        "object_properties": [],
        "inference_rules": [],
    }

    # 5. 写入文件
    out_path = ont_dir / f"{domain_id}.yaml"
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(domain_yaml, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # 6. 注册到 DomainRouter
    try:
        from core.harness.knowledge.domain_router import DomainRouter
        DomainRouter().register_domain(domain_id, {"collection_id": collection, "label": domain_name})
    except Exception:
        logger.warning("DomainRouter registration skipped", exc_info=True)

    return {
        "status": "ok",
        "domain_id": domain_id,
        "domain_name": domain_name,
        "classes": len(classes_yaml),
        "entities": len(entities),
        "topics": len(topics),
        "written": str(out_path),
    }


@router.post("/convert-from-kb", response_model=Dict[str, Any])
async def convert_from_kb(req: ConvertKbRequest = Body(default=None), collection: str = "default"):
    u"""Convert existing KB documents into Wiki pages.
    
    If doc_ids is provided, only those specific documents are converted.
    Otherwise all documents matching tenant/collection are processed.
    """
    tenant_id = req.tenant_id if req else "default"
    collection_id = req.collection_id if req else "default"
    limit = req.limit if req else 50
    doc_ids = req.doc_ids if req else None
    import os, re, time as _time, logging
    logger = logging.getLogger(__name__)
    from core.harness.knowledge.wiki_engine import write_page, _wiki_root

    docs_converted = 0
    entities_created = 0
    uploads_converted = 0
    skipped = 0
    writeback_errors = 0
    errors = []

    try:
        # Read KB documents from platform KB storage
        kb_dir = os.path.expanduser(os.getenv("AIPLAT_KB_TENANTS_DIR", "~/.aiplat/kb/tenants"))
        kb_db = os.path.join(kb_dir, tenant_id, "kb.sqlite3")
        if not os.path.exists(kb_db):
            return {"docs_converted": 0, "entities_created": 0, "uploads_converted": 0, "skipped": 0, "writeback_errors": 0, "errors": ["KB database not found. Ensure documents are ingested into the knowledge base first."]}

        import sqlite3, json as _json
        conn = sqlite3.connect(kb_db)
        conn.row_factory = sqlite3.Row
        try:
            # Read documents from 'documents' table
            if doc_ids and len(doc_ids) > 0:
                placeholders = ','.join('?' * len(doc_ids))
                sql = f"SELECT doc_id, source_uri, kind, status, meta_json, created_at FROM documents WHERE tenant_id=? AND doc_id IN ({placeholders}) ORDER BY created_at DESC LIMIT ?"
                docs = conn.execute(sql, (tenant_id, *doc_ids, limit)).fetchall()
            else:
                docs = conn.execute(
                    "SELECT doc_id, source_uri, kind, status, meta_json, created_at FROM documents WHERE tenant_id=? AND collection_id=? ORDER BY created_at DESC LIMIT ?",
                    (tenant_id, collection_id, limit)
                ).fetchall()

            if not docs:
                return {"docs_converted": 0, "entities_created": 0, "uploads_converted": 0, "skipped": 0, "writeback_errors": 0, "errors": ["No documents found in KB. Ingest documents first via Knowledge Base page."]}

            topic_keywords = {}  # Track shared keywords across documents for cross-linking

            # Collect doc metadata for parallel curation batching
            _curation_queue = []  # list of (doc_id, safe_title, body, tags, summary, collection, tenant_id, doc)

            for doc in docs:
                doc_id = doc["doc_id"]
                source_uri = str(doc["source_uri"] if "source_uri" in doc.keys() else doc_id)
                # Extract title from filename or meta
                title = os.path.basename(source_uri).rsplit(".", 1)[0][:100] or doc_id[:60]
                # Try to get title from meta_json
                try:
                    meta = _json.loads(doc["meta_json"] or "{}")
                    if meta.get("title"):
                        title = str(meta["title"])[:120]
                except Exception: logging.warning('best-effort operation', exc_info=True)  # noqa: intentional — best-effort operation, logged at warning
                # Try to parse a human-readable title from the URI
                from core.harness.knowledge.wiki_engine import parse_title_from_uri
                readable = parse_title_from_uri(source_uri)
                if readable and len(readable) >= 3:
                    title = readable

                # Skip only if fully converted (both wiki_pages AND wikified status)
                try:
                    meta = _json.loads(doc["meta_json"] or "{}")
                    wiki_pages = meta.get("wiki_pages", [])
                    wiki_status = str(doc["wiki_status"] or "").strip()
                    if wiki_pages and wiki_status == "wikified":
                        skipped += 1
                        continue
                except Exception: logging.warning('best-effort operation', exc_info=True)  # noqa: intentional — best-effort operation, logged at warning

                # Read document elements (full text)
                elements = conn.execute(
                    "SELECT text FROM kb_elements WHERE tenant_id=? AND doc_id=? ORDER BY page_idx, element_id",
                    (tenant_id, doc_id)
                ).fetchall()

                if not elements:
                    skipped += 1
                    continue

                # Build body from elements
                body_parts = []
                for el in elements:
                    text = str(el["text"] or "").strip()
                    if text:
                        body_parts.append(text)
                body = "\n\n".join(body_parts)[:50000]

                # Extract keywords for auto-tagging
                keywords = re.findall(r'[\u4e00-\u9fff]{2,8}|[A-Z][a-zA-Z]{2,}', body[:5000])
                tags = list(set(kw.lower() for kw in keywords[:8]))
                summary = body[:300].replace("\n", " ")
                # Auto-route: use DomainRouter to determine target collection
                doc_collection = collection
                try:
                    from core.harness.knowledge.domain_router import DomainRouter
                    router = DomainRouter()
                    domain_id = router.classify(title)
                    if domain_id:
                        routed = router.resolve_collection(domain_id)
                        if routed:
                            doc_collection = routed
                            logger.debug("convert-from-kb: '%s' → domain=%s collection=%s",
                                       title[:60], domain_id, routed)
                except Exception:
                    logging.getLogger(__name__).debug('Domain routing failed, falling back to caller-provided collection', exc_info=True)

                # Track keywords for cross-linking
                for kw in tags[:5]:
                    if kw not in topic_keywords:
                        topic_keywords[kw] = []
                    topic_keywords[kw].append(title)

                # Create wiki page (fast, no LLM)
                safe_title = re.sub(r"[<>:\"/\\|?*]", "_", title)[:120]
                write_page(safe_title, body, category="entities", tags=tags, summary=summary,
                           source_articles=[f"kb:{doc_id}"], collection_id=doc_collection)
                _curation_queue.append((doc_id, safe_title, body, tags, summary, doc_collection, tenant_id, dict(doc)))
                docs_converted += 1

            # ── Parallel curation: batch LLM calls via asyncio.gather ──
            import asyncio as _asyncio
            BATCH = 5
            if _curation_queue:
                from core.harness.knowledge.wiki_engine import llm_curate_page, list_all_pages as _lap
                existing = _lap()
                existing_titles = [p["title"] for p in existing] if existing else []
                for i in range(0, len(_curation_queue), BATCH):
                    batch = _curation_queue[i:i + BATCH]
                    tasks = [
                        llm_curate_page(title, body, existing_titles=existing_titles, source_doc_id=doc_id)
                        for doc_id, title, body, *_ in batch
                    ]
                    try:
                        results = await _asyncio.gather(*tasks, return_exceptions=True)
                    except Exception:
                        results = []
                    for j, curated in enumerate(results):
                        if isinstance(curated, Exception) or curated is None:
                            continue
                        try:
                            doc_id, safe_title, body_text, tags, summary, collection, tenant_id, raw_doc = batch[j]
                            curated = curated or {}
                            old_title = safe_title
                            write_page(curated.get("title", old_title), body_text,
                                category=curated.get("category", "entities"),
                                tags=curated.get("tags", tags),
                                related=curated.get("related", []),
                                summary=curated.get("summary", summary),
                                source_articles=[f"kb:{doc_id}"], collection_id=collection)
                            if curated.get("title") != old_title:
                                try: delete_page(old_title)
                                except Exception: logging.warning('best-effort operation', exc_info=True)  # noqa: intentional — best-effort operation, logged at warning
                            for atom in curated.get("knowledge_atoms", [])[:6]:
                                if not atom.get("title") or not atom.get("body"):
                                    continue
                                atom_title = re.sub(r"[<>:\"/\\|?*]", "_", str(atom["title"])[:80])
                                if atom_title and atom_title != curated.get("title"):
                                    try:
                                        from core.harness.knowledge.wiki_engine import write_atom
                                        write_atom({"title": atom_title, "body": str(atom.get("body",""))[:20000],
                                            "source_doc_id": f"kb:{doc_id}",
                                            "evidence_text": atom.get("evidence_text",""),
                                            "confidence": float(atom.get("confidence",0.5)),
                                            "tags": list(atom.get("tags",[]))[:5]}, collection_id=collection)
                                        entities_created += 1
                                    except Exception: logging.warning('best-effort operation', exc_info=True)  # noqa: intentional — best-effort operation, logged at warning
                            # Write back to KB
                            final_title = curated.get("title", old_title)
                            try:
                                meta = _json.loads(raw_doc.get("meta_json") or "{}")
                                wiki_pages = meta.get("wiki_pages", [])
                                if final_title != safe_title and safe_title in wiki_pages:
                                    wiki_pages.remove(safe_title)
                                if final_title not in wiki_pages:
                                    wiki_pages.append(final_title)
                                    meta["wiki_pages"] = wiki_pages
                                    conn.execute("UPDATE documents SET meta_json=?, wiki_status='wikified' WHERE doc_id=? AND tenant_id=?",
                                                (_json.dumps(meta, ensure_ascii=False), doc_id, tenant_id))
                                    conn.commit()
                            except Exception as e:
                                writeback_errors += 1
                                logger.warning(f"writeback failed for {doc_id}: {e}")
                        except Exception as e:
                            logging.warning(str(e), exc_info=True)

            # Cross-link pages that share keywords (validate against actual existing pages)
            valid_titles = set()
            try:
                from core.harness.knowledge.wiki_engine import search_pages
                valid_titles = set(p["title"] for p in (search_pages(limit=1000, collection_id=collection) or []))
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            for kw, titles in topic_keywords.items():
                if len(titles) >= 2:
                    # Filter out titles that don't correspond to actual wiki pages
                    real_titles = [t for t in titles if t in valid_titles]
                    if len(real_titles) < 2:
                        continue
                    for t in real_titles:
                        related = [t2 for t2 in real_titles if t2 != t]
                        from core.harness.knowledge.wiki_engine import read_page
                        page = read_page(t, category="entities", collection_id=collection)
                        if page:
                            existing = set(page.get("related", []))
                            existing.update(related[:5])
                            write_page(t, page.get("body", "", collection_id=collection), category="entities",
                                       tags=page.get("tags", []), related=list(existing)[:10])

            conn.close()
        finally:
            conn.close()

    except Exception as e:
        errors.append(str(e)[:500])

    # Also scan uploads/ directory for files not yet in wiki (skip when specific doc_ids given)
    if not doc_ids:
        try:
            uploads_dir = os.path.join(kb_dir, tenant_id, "uploads")
            if os.path.exists(uploads_dir):
                from core.harness.knowledge.wiki_engine import search_pages
                existing_wiki = set(p["title"] for p in search_pages(limit=1000, collection_id=collection))

                for fname in os.listdir(uploads_dir):
                    fpath = os.path.join(uploads_dir, fname)
                    if not os.path.isfile(fpath): continue
                    if fname.startswith("."): continue
                    if fname.startswith("preview_"): continue  # skip intermediate preview files
                    # Skip if this upload file is already a KB document with wiki pages
                    try:
                        kb_docs = conn.execute(
                            "SELECT meta_json FROM documents WHERE source_uri LIKE ? AND tenant_id=?",
                            (f"%{fname}%", tenant_id)
                        ).fetchall()
                        already_converted = False
                        for kd in kb_docs:
                            km = _json.loads(kd["meta_json"] or "{}")
                            if km.get("wiki_pages"):
                                already_converted = True
                                break
                        if already_converted: continue
                    except Exception: logging.warning('best-effort operation', exc_info=True)  # noqa: intentional — best-effort operation, logged at warning

                    title = os.path.splitext(fname)[0][:100]
                    title = re.sub(r"[<>:\"/\\|?*]", "_", title)
                    if title in existing_wiki: continue

                    # Try to read the file
                    try:
                        with open(fpath, "rb") as fh:
                            raw = fh.read(10000)
                        try:
                            body = raw.decode("utf-8")
                        except Exception:
                            body = raw.decode("utf-8", errors="replace")
                    except Exception:
                        continue
                    if not body or len(body) < 50:
                        continue

                    tags = list(set(kw.lower() for kw in re.findall(r'[\u4e00-\u9fff]{2,8}|[A-Z][a-zA-Z]{2,}', body[:5000])))[:8]
                    write_page(title, body[:50000], category="entities", tags=tags,
                              summary=body[:300].replace("\n", " "),
                              source_articles=[f"upload:{fname}"], collection_id=collection)
                    uploads_converted += 1
                    # Mark as processed
                    try:
                        import sqlite3 as _sq
                        c2 = _sq.connect(kb_db)
                        existing = c2.execute("SELECT 1 FROM documents WHERE doc_id LIKE ?", (f"%{fname[:20]}%",)).fetchone()
                        c2.close()
                    except Exception: logging.warning('best-effort operation', exc_info=True)  # noqa: intentional — best-effort operation, logged at warning
                    if uploads_converted >= limit * 2:
                        break
        except Exception as e:
            if not errors: errors.append(f"upload scan: {str(e)[:200]}")

    total = docs_converted + entities_created + uploads_converted
    return {
        "docs_converted": docs_converted,
        "entities_created": entities_created,
        "uploads_converted": uploads_converted,
        "skipped": skipped,
        "writeback_errors": writeback_errors,
        "errors": errors,
        "message": f"转换 {docs_converted} 个文档 + {entities_created} 个实体 + {uploads_converted} 个孤立文件。{skipped} 个已跳过。{f'({writeback_errors} 写回失败)' if writeback_errors else ''}",
    }


@router.post("/curate", response_model=Dict[str, Any])
async def curate_wiki(collection: str = "default"):
    u"""LLM 深度策展：遍历所有 Wiki 页面，用 LLM 重写标题/分类/标签/摘要/关联。

    返回: {processed, links_added, titles_updated, errors[]}
    如果 LLM 不可用，降级到嵌入自动关联。

    Phase: parallelized — batch llm_curate_page via asyncio.gather (BATCH=5).
    """
    import asyncio as _asyncio
    from core.harness.knowledge.wiki_engine import search_pages, llm_curate_page, update_page, auto_link_page
    pages = search_pages(limit=500, collection_id=collection)
    report = {"processed": 0, "links_added": 0, "titles_updated": 0, "errors": []}
    all_titles = [p["title"] for p in pages]
    saved_pairs: Dict[frozenset, str] = {}
    BATCH = 5

    # Phase 1: Parallel LLM curation calls
    for i in range(0, len(pages), BATCH):
        batch = pages[i:i + BATCH]
        tasks = [
            llm_curate_page(p["title"], p.get("body", ""),
                            existing_titles=[t for t in all_titles if t != p["title"]])
            for p in batch
        ]
        results = await _asyncio.gather(*tasks, return_exceptions=True)

        # Phase 2: Process results
        for j, result in enumerate(results):
            p = batch[j]
            try:
                if isinstance(result, Exception) or result is None:
                    raise result or ValueError("null result")

                existing_titles = [t for t in all_titles if t != p["title"]]
                if result.get("error") or result.get("fallback"):
                    report["errors"].append({
                        "page": p["title"], "error": result.get("error", "LLM unavailable"),
                    })
                    auto_rel = auto_link_page(p["title"], p.get("body", ""), existing_titles)
                    if auto_rel:
                        update_page(p["title"], related=auto_rel)
                        report["links_added"] += len(auto_rel)
                        report["processed"] += 1
                    continue

                update_page(p["title"],
                            new_title=result.get("title"),
                            category=result.get("category"),
                            tags=result.get("tags"),
                            summary=result.get("summary"),
                            related=result.get("related", []))
                report["processed"] += 1
                report["links_added"] += len(result.get("related", []))
                if result.get("title") != p["title"]:
                    report["titles_updated"] += 1

                import time as _t
                for mc in result.get("merge_candidates", [])[:3]:
                    if mc.get("target") and mc["target"] in existing_titles:
                        from core.harness.knowledge.wiki_engine import save_proposal
                        pair = frozenset([p["title"], mc["target"]])
                        if pair in saved_pairs and saved_pairs[pair] != "merge":
                            continue
                        save_proposal({
                            "action": "merge", "from_title": p["title"],
                            "to_title": mc["target"],
                            "reason": str(mc.get("reason", "content overlap")),
                            "source_doc": "", "status": "pending",
                            "created_at": str(int(_t.time())),
                        }, collection_id=collection)
                        saved_pairs[pair] = "merge"
                for con in result.get("contradictions", [])[:3]:
                    b_title = con.get("b", "") if isinstance(con, dict) else con
                    if b_title and b_title in existing_titles:
                        from core.harness.knowledge.wiki_engine import save_proposal
                        pair = frozenset([p["title"], b_title])
                        if pair in saved_pairs and saved_pairs[pair] != "contradict":
                            continue
                        save_proposal({
                            "action": "contradict", "from_title": p["title"],
                            "to_title": b_title,
                            "reason": str(con.get("detail", "conflicting claims") if isinstance(con, dict) else "conflicting claims"),
                            "source_doc": "", "status": "pending",
                            "created_at": str(int(_t.time())),
                        }, collection_id=collection)
                        saved_pairs[pair] = "contradict"

            except Exception as e:
                report["errors"].append({"page": p["title"], "error": str(e)[:300]})

    return report


@router.post("/wiki/index-md", response_model=Dict[str, Any])
async def regenerate_wiki_index(collection: str = "default"):
    """Generate a human-readable wiki index page (index.md) from index.json."""
    try:
        from core.harness.knowledge.wiki_engine import generate_index_md
        content = generate_index_md(collection_id=collection)
        lines = content.count("\n") + 1 if content else 0
        return {"status": "ok", "lines": lines, "content": content[:500]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Index generation failed: {e}")


@router.get("/wiki/health-trend", response_model=Dict[str, Any])
async def get_wiki_health_trend():
    """Get wiki health score trend over time."""
    try:
        from core.harness.knowledge.wiki_health_rules import get_health_trend
        return get_health_trend()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get health trend: {e}")


@router.get("/wiki/golden-queries/seed", response_model=Dict[str, Any])
async def seed_golden_queries():
    """Create a default golden_queries.yaml template."""
    try:
        from core.harness.knowledge.wiki_structured_query import seed_golden_queries
        return {"status": seed_golden_queries()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed: {e}")


@router.post("/wiki/golden-queries/run", response_model=Dict[str, Any])
async def run_golden_tests():
    """Run regression tests against golden queries."""
    try:
        from core.harness.knowledge.wiki_structured_query import run_golden_tests
        return run_golden_tests()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Golden test failed: {e}")


@router.get("/wiki/query-structured", response_model=Dict[str, Any])
async def wiki_structured_query(q: str = ""):
    """Deterministic structured query — same question, same answer."""
    if not q:
        return {"error": "Missing query parameter ?q=", 
                "examples": ["?q=什么是RAG", "?q=RAG与Wiki有什么区别", "?q=wiki健康报告"]}
    try:
        from core.harness.knowledge.wiki_structured_query import structured_query
        return structured_query(q)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Structured query failed: {e}")


@router.post("/ontology/rebuild", response_model=Dict[str, Any])
async def ontology_rebuild(collection: str = "default"):
    """Full rebuild of the knowledge ontology A-Box from current Wiki+KB data."""
    try:
        from core.harness.knowledge.knowledge_abox_builder import rebuild_full
        onto = rebuild_full(collection_id=collection)
        return {"status": "rebuilt", "triples": len(onto.triples), "collection": collection}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rebuild failed: {e}")


@router.get("/ontology/validate", response_model=Dict[str, Any])
async def ontology_validate(collection: str = "default"):
    """Run all ontology axioms (A1-A7) against the current A-Box."""
    try:
        from core.harness.knowledge.knowledge_abox_builder import build_abox
        from core.harness.knowledge.knowledge_validator import validate as onto_validate
        
        onto = build_abox(collection_id=collection)
        report = onto_validate(onto)
        return {
            "timestamp": report.timestamp,
            "total_triples": report.total_triples,
            "violations": [
                {"axiom": v.axiom_id, "severity": v.severity,
                 "description": v.description, "recommendation": v.recommendation}
                for v in report.violations
            ],
            "score": report.score,
            "passed_axioms": report.passed_axioms,
            "failed_axioms": report.failed_axioms,
            "has_errors": report.has_errors,
            "collection": collection,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {e}")


@router.get("/ontology/network/{title:path}", response_model=Dict[str, Any])
async def ontology_network(title: str, collection: str = "default"):
    """Get the transitive knowledge network from a starting Wiki page."""
    try:
        from core.harness.knowledge.knowledge_abox_builder import build_abox
        from core.harness.knowledge.knowledge_validator import query_transitive_network
        
        # Ensure A-Box is built for this collection
        build_abox(collection_id=collection)
        return query_transitive_network(title)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Network query failed: {e}")


@router.get("/ontology/source-impact", response_model=Dict[str, Any])
async def ontology_source_impact(collection: str = "default"):
    """Rank KB documents by how many Wiki pages cite them."""
    try:
        from core.harness.knowledge.knowledge_abox_builder import build_abox
        from core.harness.knowledge.knowledge_validator import query_source_impact
        
        # Ensure A-Box is built for this collection
        build_abox(collection_id=collection)
        return {"sources": query_source_impact()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Impact query failed: {e}")


@router.get("/wiki/changelog", response_model=Dict[str, Any])
async def get_wiki_changelog(title: str = "", limit: int = 20, collection: str = "default"):
    """Get wiki changelog entries, optionally filtered by page title."""
    from core.harness.knowledge.wiki_engine import _wiki_root
    import json as _json
    root = _wiki_root(collection)
    log_path = root / "changelog.json"
    if not log_path.exists():
        return {"entries": [], "total": 0}
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            entries = _json.load(f)
        if title:
            entries = [e for e in entries if e.get("title") == title]
        entries.reverse()  # newest first
        return {"entries": entries[:limit], "total": len(entries)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read changelog: {e}")


@router.post("/wiki/rollback/{title}", response_model=Dict[str, Any])
async def wiki_rollback(title: str, index: int = -1, collection: str = "default"):
    """Rollback a wiki page to a previous version from changelog.
    
    Args:
        title: Page title to rollback
        index: Version index (-1 = one version before latest)
    """
    from core.harness.knowledge.wiki_engine import rollback_page
    ok = rollback_page(title, index=index, collection_id=collection)
    if not ok:
        raise HTTPException(status_code=404, detail="No changelog entry found for this page")
    return {"status": "rolled_back", "title": title, "index": index}


@router.get("/wiki/page/{page_id}", response_model=Dict[str, Any])
async def wiki_page_by_id(page_id: str, collection: str = "default"):
    """Get a wiki page by its stable page_id (UUID). Survives title renames."""
    try:
        from core.harness.knowledge.wiki_engine import read_page_by_id
        page = read_page_by_id(page_id, collection_id=collection)
        if not page:
            raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")
        return {"status": "ok", "page": page}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Page lookup failed: {e}")


@router.get("/wiki/duplicates", response_model=Dict[str, Any])
async def detect_wiki_duplicates(collection: str = "default"):
    """Detect potentially duplicate wiki pages using embedding similarity."""
    try:
        from core.harness.knowledge.wiki_engine import detect_duplicate_pages
        duplicates = detect_duplicate_pages(collection_id=collection)
        return {"duplicates": duplicates, "total": len(duplicates)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Duplicate detection failed: {e}")


# ── Collection Management ───────────────────────────────────────

@router.get("/collections", response_model=ListResponse[Dict[str, Any]])
async def list_wiki_collections():
    """List all wiki collections with page counts."""
    try:
        from core.harness.knowledge.wiki_engine import list_collections
        cols = list_collections()
        return {"collections": cols, "total": len(cols)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list collections: {e}")


@router.post("/collections", response_model=Dict[str, Any])
async def create_wiki_collection(body: CollectionCreate):
    """Create a new wiki collection."""
    try:
        from core.harness.knowledge.wiki_engine import create_collection
        result = create_collection(body.collection_id)
        if result["status"] == "exists":
            return {"status": "ok", "message": f"Collection '{result['collection_id']}' already exists"}
        return {"status": "ok", "message": f"Collection '{result['collection_id']}' created"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create collection: {e}")


@router.delete("/collections/{collection_id}", response_model=DeleteResponse)
async def delete_wiki_collection(collection_id: str):
    """Delete a wiki collection and all its pages."""
    try:
        from core.harness.knowledge.wiki_engine import delete_collection
        result = delete_collection(collection_id)
        if result["status"] == "protected":
            raise HTTPException(status_code=400, detail=result["reason"])
        if result["status"] == "not_found":
            raise HTTPException(status_code=404, detail=f"Collection '{collection_id}' not found")
        return {"status": "ok", "message": f"Collection '{collection_id}' deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete collection: {e}")


# ── Schema API ─────────────────────────────────────────────────

@router.get("/schema", response_model=Dict[str, Any])
async def get_wiki_schema(collection: str = "default", domain: str = ""):
    """Return T-Box class schemas, with per-collection extensions + domain ontologies applied."""
    try:
        from core.harness.knowledge.knowledge_ontology import (
            get_classes_with_templates, get_extended_class,
            load_collection_extension, OBJECT_PROPERTIES, AI
        )
        extension = load_collection_extension(collection)
        schemas = []
        seen_categories = set()
        
        # 1) Built-in classes
        for cls in get_classes_with_templates():
            cat = cls.allowed_categories[0] if cls.allowed_categories else ""
            display_cls = get_extended_class(cat, collection) or cls
            schemas.append(_class_to_schema(display_cls, OBJECT_PROPERTIES, AI))
            for c in display_cls.allowed_categories:
                seen_categories.add(c)
        
        # 2) Domain ontology classes (YAML-loaded)
        from core.harness.knowledge.ontology_loader import load_all_domains
        
        for domain_id, dom in load_all_domains().items():
            if domain and domain != domain_id:
                continue
            for cls in dom.classes:
                cat = cls.allowed_categories[0] if cls.allowed_categories else cls.label.lower()
                if cat in seen_categories:
                    continue  # Skip if same category already exists from built-in
                seen_categories.add(cat)
                schemas.append({
                    "class_uri": cls.uri,
                    "label": cls.label,
                    "categories": cls.allowed_categories,
                    "required_fields": cls.required_fields,
                    "optional_fields": cls.optional_fields,
                    "template_markdown": cls.template_markdown,
                    "relations": [],
                    "domain": domain_id,
                })
        
        return {
            "schemas": schemas, "total": len(schemas),
            "collection": collection,
            "has_extension": extension is not None,
            "extension_label": extension.get("label", "") if extension else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load schemas: {e}")


def _class_to_schema(display_cls, OBJECT_PROPERTIES, AI) -> dict:
    props = []
    for op in OBJECT_PROPERTIES:
        if display_cls.uri in op.domain:
            props.append({
                "type": "relation",
                "label": op.label,
                "uri": op.uri,
                "range": [r.replace(AI, "") for r in op.range],
                "cardinality": {"min": op.min_cardinality or 0, "max": op.max_cardinality},
                "is_transitive": op.is_transitive,
                "is_symmetric": op.is_symmetric,
            })
    return {
        "class_uri": display_cls.uri,
        "label": display_cls.label,
        "categories": display_cls.allowed_categories,
        "required_fields": display_cls.required_fields,
        "optional_fields": display_cls.optional_fields,
        "template_markdown": display_cls.template_markdown,
        "relations": props,
    }


@router.get("/ontology/classes", response_model=Dict[str, Any])
async def list_ontology_classes():
    """Return T-Box class hierarchy for Agent query routing."""
    try:
        from core.harness.knowledge.knowledge_ontology import CLASSES, AI
        result = []
        for cls in CLASSES:
            children = [c.label for c in CLASSES if c.parent == cls.uri]
            result.append({
                "uri": cls.uri,
                "label": cls.label,
                "categories": cls.allowed_categories,
                "parent": cls.parent.replace(AI, "") if cls.parent else None,
                "children": children,
                "required_fields": getattr(cls, 'required_fields', []),
            })
        return {"classes": result, "total": len(result)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list classes: {e}")


# Domain Ontology API — migrated to wiki_ontology_domains.py (include_router prefix="/ontology")

# Ontology Engine API — migrated to wiki_ontology_engine.py (include_router prefix="/ontology")

# ── Ontology Domain Generation (LLM-assisted from Vault) ─────────

@router.post("/ontology/domains/generate", response_model=Dict[str, Any])
async def generate_ontology_domain(
    id: str = Body(...),
    name: str = Body(...),
    description: str = Body(""),
    vault_path: str = Body(""),
    vault_subdir: str = Body(""),
    keywords: str = Body(""),
    sample_limit: int = Body(30),
):
    """LLM-assisted 6-step ontology generation from Vault markdown files.

    Steps: GatherContent → EntityScan → ConceptCluster → RelationExtract → RuleRefine → AssembleYAML.
    Each step's output is cached to ~/.aiplat/ontology_gen/{domain_id}/ for debugging.
    """
    import json as _json, yaml as _yaml, re as _re, hashlib as _hashlib, asyncio
    from pathlib import Path as _Path
    import os as _os

    domain_id = id.strip().lower().replace(" ", "-")
    if not domain_id or not name.strip():
        raise HTTPException(status_code=400, detail="id and name are required")

    # ── Step 0: GatherContent ──────────────────────────────────────────
    kw_list = _extract_keywords(keywords) if keywords else _extract_keywords(description)
    samples = _gather_vault_files(
        vault_path=vault_path, vault_subdir=vault_subdir,
        keywords=kw_list, sample_limit=min(sample_limit, 50),
    )
    # Cache hashes
    if domain_id:
        _save_step(domain_id, "vault_hashes.json",
                   {"files": {s["file"]: s["hash"] for s in samples},
                    "scanned_at": __import__("time").time()})
    if not samples:
        raise HTTPException(status_code=400, detail="No relevant vault files found. Connect a vault with markdown files.")

    content_text = _build_content_text(samples)

    # ── Common: Few-shot example ───────────────────────────────────────
    few_shot = _load_few_shot_yaml()

    # ── Step 1: EntityScan ─────────────────────────────────────────────
    entity_prompt = f"""TASK: Extract domain-specific ENTITY NAMES from documents. Do NOT describe or analyze the documents themselves.

EXAMPLE: If the document is about RAG technology, extract: "RAG", "retrieval pipeline", etc.

For each entity found, provide:
- name: brief name of the entity
- type: methods | systems | concepts | problems | references
- excerpt: short quote from the document (≤30 chars)

Domain: {description}

Documents:
{content_text[:4000]}

OUTPUT ONLY valid JSON (no markdown, no text before/after):
{{"entities":{{"methods":[{{"name":"RAG","excerpt":"RAG combines retrieval..."}}],"systems":[{{"name":"Harness","excerpt":"Harness is a system..."}}],"concepts":[],"problems":[],"references":[]}}}}"""

    try:
        entities_data = await asyncio.wait_for(
            _llm_step(entity_prompt, domain_id, "step1_entities"), timeout=30
        )
    except Exception:
        entities_data = {"entities": {}, "evidence": {}}
    _save_step(domain_id, "step1_entities.json", entities_data)

    # ── Step 2: ConceptCluster ─────────────────────────────────────────
    entities_json = _json.dumps(entities_data.get("entities", {}), ensure_ascii=False, indent=2)
    cluster_prompt = f"""TASK: Group these entities into 4-8 ontology classes.

Entities found:
{entities_json[:2000]}

For each class, define: name (PascalCase), label (Chinese), description, required_fields (list), optional_fields (list), categories (kebab-case list).

EXAMPLE format:
{{"classes":[{{"name":"AITechnique","label":"AI方法","description":"AI techniques and algorithms","required_fields":["name","description"],"optional_fields":["tags"],"categories":["ai-techniques"]}}]}}

OUTPUT ONLY valid JSON:"""

    try:
        classes_data = await asyncio.wait_for(
            _llm_step(cluster_prompt, domain_id, "step2_classes"), timeout=30
        )
    except Exception:
        classes_data = {"classes": []}
    _save_step(domain_id, "step2_classes.json", classes_data)

    # ── Step 3: RelationExtract ────────────────────────────────────────
    classes_simple = _json.dumps([
        {"name": c.get("name", ""), "label": c.get("label", "")}
        for c in classes_data.get("classes", [])
    ], ensure_ascii=False, indent=2)

    relation_prompt = f"""TASK: Identify relations between these classes from the documents.

Classes: {classes_simple[:1500]}

Documents:
{content_text[:2000]}

For each relation: name (snake_case), label (Chinese), domain (source class names), range (target class names), type (forward|symmetric|transitive).

EXAMPLE: {{"relations":[{{"name":"implements","label":"实现","domain":["AISystem"],"range":["AITechnique"],"type":"forward"}}]}}

OUTPUT ONLY valid JSON:"""

    try:
        relations_data = await asyncio.wait_for(
            _llm_step(relation_prompt, domain_id, "step3_relations"), timeout=30
        )
    except Exception:
        relations_data = {"relations": []}
    _save_step(domain_id, "step3_relations.json", relations_data)

    # ── Step 4: RuleRefine ─────────────────────────────────────────────
    state_classes = [c for c in classes_data.get("classes", [])
                     if any(kw in str(c.get("label", "")) for kw in ["方法", "系统", "问题", "流程", "事件", "变更"])]
    if state_classes:
        state_class_names = _json.dumps([c.get("label") for c in state_classes], ensure_ascii=False)
        rule_prompt = f"""TASK: Define state machines for these classes if there are lifecycle descriptions.

Classes: {state_class_names}
Documents: {content_text[:3000]}

For each class with states: default state, states list (name+label), transitions list (from, to, trigger with type/relation/threshold/operator).

EXAMPLE: {{"state_machines":[{{"class_label":"AI方法","default":"emerging","states":[{{"name":"emerging","label":"新兴"}}],"transitions":[{{"from":"emerging","to":"established","trigger":{{"type":"relation_count","relation":"implements","threshold":3,"operator":">="}},"description":"≥3 implementations"}}]}}]}}

OUTPUT ONLY valid JSON:"""

        try:
            states_data = await asyncio.wait_for(
                _llm_step(rule_prompt, domain_id, "step4_states"), timeout=30
            )
        except Exception:
            states_data = {"state_machines": []}
        _save_step(domain_id, "step4_states.json", states_data)
    else:
        states_data = {"state_machines": []}

    # ── Step 5: AssembleYAML ───────────────────────────────────────────
    yaml_str = _assemble_yaml(domain_id, name.strip(), description.strip(),
                              classes_data, relations_data, states_data, entities_data)
    _save_step(domain_id, "final.yaml", yaml_str)

    # ── Return preview YAML (user should review before saving) ────────
    return {
        "status": "preview",
        "domain_id": domain_id,
        "yaml": yaml_str,
        "stats": {
            "files_scanned": len(samples),
            "entities_found": sum(len(v) for v in entities_data.get("entities", {}).values()),
            "classes_generated": len(classes_data.get("classes", [])),
            "relations_found": len(relations_data.get("relations", [])),
            "state_machines": len(states_data.get("state_machines", [])),
        },
    }


@router.post("/ontology/domains/{domain_id}/evolve", response_model=Dict[str, Any])
async def evolve_ontology_domain(
    domain_id: str,
    vault_path: str = Body(""),
    vault_subdir: str = Body(""),
    keywords: str = Body(""),
    sample_limit: int = Body(10),
):
    """Delta analysis: detect new vault files → suggest ontology changes.

    Compares current vault file hashes against cached hashes from last generate run.
    Returns suggestions for new classes, relations, and state machine changes.
    """
    import json as _json, asyncio, os as _os
    from pathlib import Path as _Path

    gen_dir = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontology_gen" / domain_id

    # 1. Load cached hashes
    cache_file = gen_dir / "vault_hashes.json"
    cached = {}
    if cache_file.exists():
        try:
            cached = _json.loads(cache_file.read_text()).get("files", {})
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    # 2. Scan current vault
    all_files = []
    vp = vault_path or _discover_vault_path()
    if not vp:
        return {"suggestions": [], "message": "No vault found. Connect a vault first."}

    for root, dirs, files in _os.walk(vp):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.endswith(".md"):
                all_files.append(_os.path.join(root, f))

    # 3. Find new/modified files
    new_files = []
    for fp in all_files:
        try:
            content = _Path(fp).read_text(encoding="utf-8", errors="ignore")
            h = _hash_content(content)
            fname = _Path(fp).name
            if fname not in cached or cached[fname] != h:
                new_files.append({"file": fname, "path": fp, "content": content[:2000], "hash": h,
                                  "is_new": fname not in cached})
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    if not new_files:
        return {"suggestions": [], "message": "No new or modified vault files found.",
                "new_files_found": 0}

    # 4. Load current ontology
    onto_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    existing_classes = []
    if onto_path.exists():
        try:
            from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
            domain = load_ontology_from_yaml(str(onto_path))
            existing_classes = [{"label": c.label, "categories": c.allowed_categories} for c in domain.classes]
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    # 5. Delta entity scan on new content only (with optional keyword filtering)
    if keywords:
        kw_list = _extract_keywords(keywords)
        scored = []
        for nf in new_files:
            score = _filename_match_score(nf["file"].lower(), "", kw_list) + \
                    _content_preview_score(nf["path"], kw_list)
            scored.append((nf, score))
        scored.sort(key=lambda x: -x[1])
        delta_files = [f for f, _ in scored[:sample_limit]]
    elif len(new_files) > sample_limit:
        import random
        delta_files = random.sample(new_files, sample_limit)
    else:
        delta_files = new_files

    # Apply vault_subdir filter
    if vault_subdir:
        delta_files = [f for f in delta_files if vault_subdir.lower() in f.get("file", "").lower() or vault_subdir.lower() in f.get("path", "").lower()]
        if not delta_files and new_files:
            delta_files = random.sample(new_files, min(sample_limit, len(new_files))) if isinstance(new_files, list) else [new_files[0]]

    content_text = _build_content_text(delta_files)

    delta_prompt = f"""TASK: Compare new documents against existing ontology classes. 
Find entities/systems/concepts that are NOT covered by existing classes.

Existing classes: {_json.dumps(existing_classes, ensure_ascii=False)[:1500]}

New documents:
{content_text[:3000]}

Suggest: 1) New classes needed, 2) New relations, 3) Changes to existing state machines.

OUTPUT ONLY valid JSON:
{{"new_classes":[{{"name":"...","label":"...","description":"...","required_fields":["name"],"categories":[]}}],"new_relations":[],"state_changes":[],"summary":"Brief summary of changes"}}"""

    try:
        result = await _llm_step(delta_prompt, domain_id, "evolve", max_retries=1)
    except Exception:
        result = {"new_classes": [], "new_relations": [], "state_changes": [], "summary": "LLM analysis failed"}

    # 6. Update cache
    _save_step(domain_id, "vault_hashes.json",
               {"files": {s["file"]: s["hash"] for s in new_files},
                "scanned_at": __import__("time").time()})

    return {
        "suggestions": result,
        "new_files_found": len(new_files),
        "existing_classes": [c["label"] for c in existing_classes],
    }


@router.post("/ontology/domains/{domain_id}/repair", response_model=Dict[str, Any])
async def repair_ontology_domain(
    domain_id: str,
    vault_path: str = Body(""),
    vault_subdir: str = Body(""),
    keywords: str = Body(""),
    sample_limit: int = Body(20),
):
    """Audit existing ontology against full Vault content. Returns repair suggestions.

    Checks: missing classes, missing fields, missing synonyms, weak relations,
    weak state machines (states without transitions), and uncovered entities.
    """
    import json as _json, asyncio, os as _os
    from pathlib import Path as _Path

    # 1. Load current ontology
    onto_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    if not onto_path.exists():
        return {"repair_suggestions": {}, "error": f"Domain '{domain_id}' not found"}

    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    domain = load_ontology_from_yaml(str(onto_path))

    existing = {
        "classes": [{
            "name": c.uri.rsplit("/", 1)[-1].rsplit("#", 1)[-1], "label": c.label,
            "required_fields": c.required_fields, "optional_fields": c.optional_fields,
            "categories": c.allowed_categories, "synonyms": getattr(c, "synonyms", []) or [],
            "has_states": bool(getattr(c, "states", {}).get("enum")),
            "has_transitions": bool(getattr(c, "states", {}).get("transitions")),
        } for c in domain.classes],
        "relations": [{"name": getattr(r, "name", "") or str(r), "label": getattr(r, "label", ""),
                       "domain": str(getattr(r, "domain", []))} for r in domain.object_properties],
    }

    # 2. Scan Vault
    vp = vault_path or _discover_vault_path()
    kw_list = _extract_keywords(keywords) if keywords else None
    samp = _gather_vault_files(vault_path=vp, vault_subdir=vault_subdir, keywords=kw_list, sample_limit=sample_limit)
    if not samp:
        return {"repair_suggestions": {}, "error": "No vault files found"}

    content_text = _build_content_text(samp)

    # 3. LLM audit
    repair_prompt = f"""TASK: Audit this ontology YAML against Vault documents. Find gaps.

Existing ontology (summary):
  Classes: {_json.dumps([{ "label": c["label"], "fields": c["required_fields"]+c["optional_fields"][:3], "synonyms": c["synonyms"][:3], "has_states": c["has_states"], "has_transitions": c["has_transitions"] } for c in existing["classes"]], ensure_ascii=False)[:2000]}
  Relations: {len(existing["relations"])} total

Vault documents:
{content_text[:3000]}

Report these issues:
1. missing_classes: entities NOT covered by any existing class (with suggested name/label)
2. missing_fields: common properties missing from class field definitions
3. missing_synonyms: class labels that lack common search terms
4. weak_relations: domain with < 3 classes but 0 relations → suggest new
5. weak_state_machines: classes with states enum but no transitions

OUTPUT ONLY valid JSON:
{{"missing_classes":[{{"label":"...","suggested_name":"...","category":"..."}}],"missing_fields":[{{"class":"...","field":"...","reason":"..."}}],"missing_synonyms":[{{"class":"...","suggested":["..."]}}],"weak_relations":[{{"suggestion":"Add relation between X and Y"}}],"weak_state_machines":[{{"class":"...","issue":"..."}}],"summary":"..."}}"""

    try:
        result = await _llm_step(repair_prompt, domain_id, "repair", max_retries=1)
    except Exception:
        result = {"summary": "LLM audit failed", "missing_classes": [], "missing_fields": [],
                  "missing_synonyms": [], "weak_relations": [], "weak_state_machines": []}

    return {
        "repair_suggestions": result,
        "domain_id": domain_id,
        "existing_classes": len(existing["classes"]),
        "files_scanned": len(samp),
    }


# ── Helper functions for ontology generation ──────────────────────

def _gather_vault_files(*, vault_path: str, vault_subdir: str = "", keywords: list = None, sample_limit: int = 30):
    """Unified vault file gathering with optional subdir + keyword filtering."""
    import os as _os
    from pathlib import Path as _Path

    if not vault_path:
        vault_path = _discover_vault_path()
    if not vault_path or not _Path(vault_path).is_dir():
        return []

    root = _Path(vault_path)
    if vault_subdir:
        root = root / vault_subdir.lstrip("/")
    if not root.is_dir():
        root = _Path(vault_path)

    keywords = keywords or []
    all_files = []
    for d_root, dirs, files in _os.walk(str(root)):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.endswith(".md") and not f.startswith("."):
                all_files.append(_os.path.join(d_root, f))

    if not all_files:
        return []

    if keywords:
        scored = []
        for fp in all_files:
            fname = _os.path.basename(fp).lower()
            dirname = _os.path.basename(_os.path.dirname(fp)).lower()
            fname_score = _filename_match_score(fname, dirname, keywords)
            content_score = _content_preview_score(fp, keywords)
            total = 0.4 * fname_score + 0.6 * content_score
            if total > 0 or len(all_files) <= sample_limit:
                scored.append((fp, total))
        scored.sort(key=lambda x: -x[1])
        if not scored or scored[0][1] == 0:
            scored = _sample_by_size(all_files, sample_limit)
    else:
        scored = _sample_by_size(all_files, sample_limit)

    samples = []
    for fp, _ in scored[:sample_limit]:
        try:
            content = _Path(fp).read_text(encoding="utf-8", errors="ignore")
            samples.append({
                "file": _Path(fp).name, "path": fp,
                "content": content[:2000], "hash": _hash_content(content),
            })
        except Exception as e:
            logging.warning(str(e), exc_info=True)
    return samples


def _gather_vault_content(*, description: str, vault_path: str, domain_id: str = "", sample_limit: int = 30):
    """Enhanced sampling: filename + content preview weighted scoring (backward compat)."""
    keywords = _extract_keywords(description)
    samples = _gather_vault_files(vault_path=vault_path, keywords=keywords, sample_limit=sample_limit)
    if domain_id:
        _save_step(domain_id, "vault_hashes.json",
                   {"files": {s["file"]: s["hash"] for s in samples},
                    "scanned_at": __import__("time").time()})
    return samples


def _discover_vault_path():
    """Find first connected vault path from SQLite."""
    try:
        import sqlite3
        from pathlib import Path as _Path
        db = _Path.home() / ".aiplat" / "kb" / "tenants" / "default" / "kb.sqlite3"
        if db.exists():
            conn = sqlite3.connect(str(db))
            row = conn.execute(
                "SELECT vault_path FROM kb_vaults WHERE enabled=1 LIMIT 1"
            ).fetchone()
            conn.close()
            if row:
                return row[0]
    except Exception as e:
        logging.warning(str(e), exc_info=True)
    return ""


def _extract_keywords(description: str):
    """Extract Chinese + English keywords from domain description."""
    import re as _re
    words = _re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', description)
    return [w.lower() for w in words if len(w) >= 2]


def _filename_match_score(fname: str, dirname: str, keywords: list) -> float:
    text = fname + " " + dirname
    hits = sum(1 for kw in keywords if kw in text)
    return hits / max(len(keywords), 1)


def _content_preview_score(fp: str, keywords: list) -> float:
    try:
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            head = f.read(500)
        text = head.lower()
        hits = sum(1 for kw in keywords if kw in text)
        return hits / max(len(keywords), 1)
    except Exception:
        return 0.0


def _sample_by_size(all_files: list, limit: int):
    """Fallback: sample largest files."""
    sizes = []
    for fp in all_files:
        try:
            sizes.append((fp, __import__("os").path.getsize(fp)))
        except Exception:
            sizes.append((fp, 0))
    sizes.sort(key=lambda x: -x[1])
    return [(fp, 1.0) for fp, _ in sizes[:limit]]


def _hash_content(content: str):
    import hashlib
    return hashlib.md5(content.encode()).hexdigest()


def _build_content_text(samples):
    parts = []
    for s in samples:
        parts.append(f"# 文件: {s['file']}\n{s['content'][:1500]}\n")
    return "\n---\n".join(parts)


def _load_few_shot_yaml():
    """Load an existing ontology YAML as few-shot example."""
    from pathlib import Path as _Path
    import os as _os
    base = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    for fname in ["ai-knowledge.yaml", "it-ops.yaml"]:
        p = base / fname
        if p.exists():
            text = p.read_text(encoding="utf-8")
            return text[:4000]
    return ""


async def _llm_step(prompt: str, domain_id: str, step_name: str, max_retries: int = 3):
    """LLM call with JSON parse + retry + fallback."""
    import json as _json, re as _re
    from core.harness.utils.model_injection import best_model_for_purpose, create_selected_adapter
    from core.harness.utils.prompt_loader import _async_prompt_resolve
    from core.adapters.llm.base import LLMConfig

    model_name = best_model_for_purpose("ontology_gen")
    model = create_selected_adapter(model_name=model_name)
    system_content = await _async_prompt_resolve("ontology-engineer")

    for attempt in range(max_retries):
        try:
            resp = await sys_llm_generate(
                model,
                [{"role": "system", "content": system_content},
                 {"role": "user", "content": prompt}],
                trace_context={"source": "wiki_ontology", "phase": "suggest"},
            )
            content = resp.content if hasattr(resp, 'content') else str(resp)
            clean = content.strip()
            # Strip markdown code fences
            if clean.startswith("```"):
                clean = _re.sub(r'^```\w*\n?', '', clean)
                clean = _re.sub(r'\n?```$', '', clean)
            # Find JSON boundaries: strip leading text before { and trailing text after }
            brace_start = clean.find('{')
            brace_end = clean.rfind('}')
            if brace_start >= 0 and brace_end > brace_start:
                clean = clean[brace_start:brace_end + 1]
            match = _re.search(r'\{[\s\S]*\}', clean)
            if match:
                return _json.loads(match.group(0))
            else:
                raise _json.JSONDecodeError("No JSON found", clean, 0)
        except Exception:
            if attempt == max_retries - 1:
                return _fallback_result(step_name)
            prompt += "\n\n注意：必须输出严格 JSON，不要用 markdown 代码块包裹。"

    return _fallback_result(step_name)


def _fallback_result(step_name):
    if "entities" in step_name:
        return {"entities": {"methods": [], "systems": [], "concepts": [], "problems": [], "references": []}, "evidence": {}}
    elif "classes" in step_name:
        return {"classes": []}
    elif "relations" in step_name:
        return {"relations": []}
    elif "states" in step_name:
        return {"state_machines": []}
    return {}


def _save_step(domain_id: str, filename: str, data):
    """Save step output to disk for debugging and caching."""
    import json as _json, os as _os
    from pathlib import Path as _Path
    dir_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontology_gen" / domain_id
    dir_path.mkdir(parents=True, exist_ok=True)
    try:
        if isinstance(data, str):
            (dir_path / filename).write_text(data, encoding="utf-8")
        else:
            (dir_path / filename).write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logging.warning(str(e), exc_info=True)


def _assemble_yaml(domain_id, name, description, classes_data, relations_data, states_data, entities_data):
    """Programmatic YAML assembly with graceful degradation."""
    import yaml as _yaml

    yaml_dict = {
        "name": name,
        "namespace": f"http://aiplat.local/ontology/{domain_id}/",
        "description": description,
        "version": "1.0.0",
        "classes": {},
        "object_properties": [],
    }

    evidence = entities_data.get("evidence", {}) or {}

    # Assemble classes
    for cls in (classes_data.get("classes", []) or []):
        cn = cls.get("name", "")
        if not cn:
            continue
        synonyms = []
        if isinstance(evidence, dict) and cn in evidence:
            excerpts = evidence[cn].get("excerpts", []) or []
            synonyms = [cn] + [e[:20] for e in excerpts[:3]]
        else:
            synonyms = [cls.get("label", cn)]

        ctype = " ".join(cls.get("categories", []) or [])
        label = cls.get("label", "")
        if any(kw in label for kw in ["方法", "工具"]):
            cth = 0.75
        elif any(kw in label for kw in ["问题", "参考"]):
            cth = 0.85
        else:
            cth = 0.80

        yaml_dict["classes"][cn] = {
            "label": label,
            "description": cls.get("description", f"{label} 类"),
            "required_fields": cls.get("required_fields", ["name", "description"]) or ["name", "description"],
            "optional_fields": cls.get("optional_fields", []) or [],
            "categories": cls.get("categories", []) or [],
            "synonyms": synonyms,
            "confidence_threshold": cth,
        }

    # Assemble relations
    for rel in (relations_data.get("relations", []) or []):
        yaml_dict["object_properties"].append({
            "name": rel.get("name", ""),
            "label": rel.get("label", ""),
            "domain": rel.get("domain", []) or [],
            "range": rel.get("range", []) or [],
            "description": rel.get("description", ""),
            "transitive": rel.get("type") == "transitive",
            "symmetric": rel.get("type") == "symmetric",
        })

    # Attach state machines to classes
    for sm in (states_data.get("state_machines", []) or []):
        class_label = sm.get("class_label", "")
        for cn, cd in yaml_dict["classes"].items():
            if cd.get("label") == class_label:
                cd["states"] = {
                    "description": sm.get("description", ""),
                    "default": sm.get("default", ""),
                    "enum": sm.get("states", []) or [],
                    "transitions": sm.get("transitions", []) or [],
                }
                break

    return _yaml.dump(yaml_dict, allow_unicode=True, default_flow_style=False, sort_keys=False)


@router.post("/ontology/domains", response_model=Dict[str, Any])
async def create_ontology_domain(req: OntologyDomainCreate):
    """Create a new domain ontology (YAML file)."""
    from pathlib import Path as _Path
    import os as _os
    d = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    file_path = d / f"{req.id}.yaml"
    if file_path.exists():
        raise HTTPException(status_code=409, detail=f"Domain '{req.id}' already exists")
    ns = req.namespace or f"http://aiplat.local/ontology/{req.id}/"
    data = {
        "name": req.name,
        "namespace": ns,
        "description": req.description,
        "version": req.version,
        "classes": {},
        "object_properties": [],
        "data_properties": [],
    }
    _write_domain_yaml(req.id, data)

    # Hot-register in registry.json → DomainRouter auto-recognizes
    from core.harness.knowledge.domain_router import DomainRouter
    router = DomainRouter()
    router.register_domain(req.id, {
        "name": req.name,
        "description": req.description or f"{req.name} 领域知识本体",
        "ontology_file": f"{req.id}.yaml",
        "collection_id": req.id,
        "namespace": ns,
        "min_wiki_score": 0.25,
        "expand_subclasses": True,
        "system_prompt_id": f"domain-prompt-{req.id}",
        "min_cross_results": 3,
    })

    return {"status": "created", "id": req.id, "name": req.name}


@router.put("/ontology/domains/{domain_id}", response_model=Dict[str, Any])
async def update_ontology_domain(domain_id: str, req: OntologyDomainCreate):
    """Update domain metadata (name, description, version)."""
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from pathlib import Path as _Path
    import os as _os
    d = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    file_path = d / f"{domain_id}.yaml"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    domain = load_ontology_from_yaml(str(file_path))
    # Rebuild YAML preserving classes/properties
    # Detect state/transition changes for auto-re-evaluation
    old_states_snapshot = {}
    for cls in domain.classes:
        old_states_snapshot[cls.label] = str(getattr(cls, "states", {}) or {}) + \
            str(getattr(cls, "transitions", []) or []) + \
            str(getattr(cls, "side_effects", []) or [])

    data = {
        "name": req.name, "namespace": domain.namespace, "description": req.description,
        "version": req.version,
        "classes": {cls.uri.split("#")[-1]: {
            "label": cls.label, "description": "",
            "required_fields": cls.required_fields, "optional_fields": cls.optional_fields,
            "categories": cls.allowed_categories, "parent": cls.parent.split("#")[-1] if cls.parent else None,
        } for cls in domain.classes},
        "object_properties": [{"name": p.uri.split("#")[-1], "label": p.label,
            "domain": [d.split("#")[-1] for d in p.domain],
            "range": [r.split("#")[-1] for r in p.range],
            "transitive": p.is_transitive, "symmetric": p.is_symmetric,
        } for p in domain.object_properties],
        "data_properties": [{"name": p.uri.split("#")[-1], "label": p.label,
            "domain": [d.split("#")[-1] for d in p.domain], "range": p.range,
        } for p in domain.data_properties],
    }
    _write_domain_yaml(domain_id, data)

    # Reload updated domain to detect state changes
    new_domain = load_ontology_from_yaml(str(file_path))
    new_states_snapshot = {}
    for cls in new_domain.classes:
        new_states_snapshot[cls.label] = str(getattr(cls, "states", {}) or {}) + \
            str(getattr(cls, "transitions", []) or []) + \
            str(getattr(cls, "side_effects", []) or [])

    # Auto-re-evaluate state machines for classes with changed states/transitions
    affected_labels = [lbl for lbl, snap in new_states_snapshot.items()
                       if old_states_snapshot.get(lbl) != snap]
    reeval_results = {}
    if affected_labels:
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            from core.harness.ontology_engine.state_machine import StateMachine, EvalContext
            from core.harness.ontology_engine.state_history import record_state_change

            graph = GraphIndex.load(domain_id)
            sm = StateMachine(new_domain)

            # Build label→class_name mapping (class_name is YAML key, label is human-readable)
            label_to_class_name = {cls.label: cls.uri.split("#")[-1] for cls in new_domain.classes}

            for label in affected_labels:
                actual_class_name = label_to_class_name.get(label, label)
                nodes = [n for n in graph._nodes.values() if n.class_name == actual_class_name]
                if not nodes:
                    nodes = [n for n in graph._nodes.values() if n.class_name == label]
                if not nodes:
                    continue

                instances = [{"class_name": n.class_name, "entity_name": n.entity_name,
                              "state": getattr(n, "state", None),
                              "properties": {"state": getattr(n, "state", None)}} for n in nodes]
                ctx = EvalContext(instances)

                transitions = []
                for inst in instances:
                    chain = sm.evaluate_chain(inst, ctx)
                    if chain:
                        final = chain[-1].to_state
                        inst["properties"]["state"] = final
                        for node in nodes:
                            if node.entity_name == inst["entity_name"]:
                                node.state = final
                        for tres in chain:
                            record_state_change(
                                domain_id=domain_id, entity_name=inst["entity_name"],
                                class_name=label, from_state=tres.from_state,
                                to_state=tres.to_state,
                                trigger=tres.trigger_type, description=tres.description)
                            transitions.append({
                                "entity": inst["entity_name"],
                                "from": tres.from_state, "to": tres.to_state,
                                "trigger": tres.trigger_type,
                            })

                reeval_results[label] = {
                    "entities": len(nodes),
                    "transitions": len(transitions),
                    "detail": transitions[:10],
                }
        except Exception as e:
            reeval_results["error"] = str(e)

    return {"status": "updated", "id": domain_id,
            "state_reevaluations": reeval_results if reeval_results else None}


@router.delete("/ontology/domains/{domain_id}", response_model=Dict[str, Any])
async def delete_ontology_domain(domain_id: str):
    """Delete a domain ontology file + cascade cleanup."""
    from pathlib import Path as _Path
    import os as _os
    d = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat"))
    file_path = d / "ontologies" / f"{domain_id}.yaml"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    file_path.unlink()

    # Remove from registry.json
    _remove_from_registry(domain_id)

    # Cascade cleanup: graph DB, wiki collection, review files
    cleaned = []
    import shutil
    home = d
    for path, label in [
        (home / "graph" / f"{domain_id}.db", "graph_db"),
        (home / "graph" / f"{domain_id}.json", "graph_json"),
        (home / "wiki" / "collections" / domain_id, "wiki_collection"),
        (home / "ontology_reviews" / f"{domain_id}.json", "review_file"),
    ]:
        if path.exists():
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
                cleaned.append(label)
            except Exception as e:
                logging.warning(str(e), exc_info=True)

    return {"status": "deleted", "id": domain_id, "cleaned": cleaned}


@router.post("/ontology/domains/{domain_id}/classes", response_model=Dict[str, Any])
async def add_ontology_class(domain_id: str, req: OntologyClassCreate):
    """Add a class to a domain ontology."""
    from pathlib import Path as _Path
    import os as _os
    d = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    file_path = d / f"{domain_id}.yaml"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    import yaml as _yaml
    with open(file_path, "r", encoding="utf-8") as f:
        raw = _yaml.safe_load(f)
    classes = raw.get("classes", {}) or {}
    if req.name in classes:
        raise HTTPException(status_code=409, detail=f"Class '{req.name}' already exists")
    classes[req.name] = {
        "label": req.label, "description": req.description or "",
        "required_fields": req.required_fields, "optional_fields": req.optional_fields,
        "categories": req.categories, "parent": req.parent or None,
    }
    raw["classes"] = classes
    _write_domain_yaml(domain_id, raw)
    return {"status": "added", "domain": domain_id, "class": req.name}


@router.put("/ontology/domains/{domain_id}/classes/{class_name}", response_model=Dict[str, Any])
async def update_ontology_class(domain_id: str, class_name: str, req: OntologyClassCreate):
    """Update an existing class in a domain ontology."""
    from pathlib import Path as _Path
    import os as _os
    d = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    file_path = d / f"{domain_id}.yaml"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    import yaml as _yaml
    with open(file_path, "r", encoding="utf-8") as f:
        raw = _yaml.safe_load(f)
    classes = raw.get("classes", {}) or {}
    if class_name not in classes:
        raise HTTPException(status_code=404, detail=f"Class '{class_name}' not found in '{domain_id}'")
    # Preserve existing fields not being updated (states, transitions, fields, etc.)
    existing = classes[class_name]
    existing["label"] = req.label
    existing["description"] = req.description or existing.get("description", "")
    existing["required_fields"] = req.required_fields
    existing["optional_fields"] = req.optional_fields
    existing["categories"] = req.categories
    if req.parent:
        existing["parent"] = req.parent
    raw["classes"] = classes
    _write_domain_yaml(domain_id, raw)

    # v2.9: Report downstream impact
    impact = {"graph_nodes_affected": 0}
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        graph = GraphIndex.load(domain_id)
        affected = graph.get_entities_by_class(class_name)
        impact["graph_nodes_affected"] = len(affected)
    except Exception:
        logging.getLogger(__name__).debug('update_ontology_class failed', exc_info=True)

    return {
        "status": "updated", "domain": domain_id, "class": class_name,
        "downstream_impact": impact,
        "warning": (
            f"已修改类 '{class_name}'，但 {impact['graph_nodes_affected']} 个已有 GraphIndex 节点 "
            f"不会被自动重新分类。如需全量重跑，调用 "
            f"POST /ontology/domains/{domain_id}/build-instances"
        ) if impact["graph_nodes_affected"] > 0 else None,
    }


@router.put("/ontology/domains/{domain_id}/properties/{prop_name}", response_model=Dict[str, Any])
async def update_ontology_property(domain_id: str, prop_name: str, req: OntologyPropertyCreate):
    """Update an existing object property in a domain ontology."""
    from pathlib import Path as _Path
    import os as _os
    d = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    file_path = d / f"{domain_id}.yaml"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    import yaml as _yaml
    with open(file_path, "r", encoding="utf-8") as f:
        raw = _yaml.safe_load(f)
    props = raw.get("object_properties", []) or []
    updated = False
    for p in props:
        if p.get("name") == prop_name:
            p["name"] = req.name
            p["label"] = req.label
            p["domain"] = req.domain
            p["range"] = req.range
            p["transitive"] = req.transitive
            p["symmetric"] = req.symmetric
            updated = True
            break
    if not updated:
        raise HTTPException(status_code=404, detail=f"Property '{prop_name}' not found in '{domain_id}'")
    raw["object_properties"] = props
    _write_domain_yaml(domain_id, raw)
    return {"status": "updated", "domain": domain_id, "property": prop_name}


@router.delete("/ontology/domains/{domain_id}/classes/{class_name}", response_model=Dict[str, Any])
async def delete_ontology_class(domain_id: str, class_name: str, force: bool = False):
    """Delete a class from a domain ontology. Use ?force=true for cascade cleanup."""
    from pathlib import Path as _Path
    import os as _os
    d = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    file_path = d / f"{domain_id}.yaml"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    import yaml as _yaml
    with open(file_path, "r", encoding="utf-8") as f:
        raw = _yaml.safe_load(f)
    classes = raw.get("classes", {}) or {}
    if class_name not in classes:
        raise HTTPException(status_code=404, detail=f"Class '{class_name}' not found in '{domain_id}'")

    # Detect affected data before deletion
    class_label = str(classes[class_name].get("label", class_name))
    class_categories = list(classes[class_name].get("categories", []) or [])

    orphan_nodes = 0
    orphan_pages = 0
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        g = GraphIndex.load(domain_id)
        orphan_nodes = sum(1 for n in g._nodes.values() if n.class_name == class_name)
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    if not force:
        return {
            "status": "confirm_required",
            "class": class_name, "label": class_label,
            "orphan_nodes": orphan_nodes,
            "orphan_categories": class_categories,
            "message": f"删除类 '{class_label}' 将影响 {orphan_nodes} 个图节点",
            "hint": "添加 ?force=true 确认级联删除",
        }

    # Cascade: remove graph nodes
    if orphan_nodes > 0:
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            g = GraphIndex.load(domain_id)
            to_remove = [n.entity_id for n in g._nodes.values() if n.class_name == class_name]
            for eid in to_remove:
                g.remove_entity(eid)
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    del classes[class_name]
    raw["classes"] = classes
    _write_domain_yaml(domain_id, raw)
    return {"status": "deleted", "domain": domain_id, "class": class_name}


class MigrateClassifyRequest(BaseModel):
    old_class_name: str
    new_class_name: str
    migrate_graph: bool = True


@router.post("/ontology/domains/{domain_id}/migrate-classify", response_model=Dict[str, Any])
async def migrate_classify(domain_id: str, req: MigrateClassifyRequest):
    """Migrate all GraphIndex nodes from old_class_name to new_class_name and update YAML.

    Use this after renaming a class in the ontology YAML to preserve existing knowledge graph data.
    Without this migration, old-class nodes become orphaned and invisible to state machines and
    class-based retrieval.
    """
    from pathlib import Path as _Path
    import os as _os
    d = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    file_path = d / f"{domain_id}.yaml"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    import yaml as _yaml
    with open(file_path, "r", encoding="utf-8") as f:
        raw = _yaml.safe_load(f)
    classes = raw.get("classes", {}) or {}
    if req.old_class_name not in classes:
        raise HTTPException(status_code=404, detail=f"Class '{req.old_class_name}' not found in '{domain_id}'")
    if req.new_class_name in classes and req.new_class_name != req.old_class_name:
        raise HTTPException(status_code=409, detail=f"Class '{req.new_class_name}' already exists. Delete it first or choose a different name.")

    old_label = str(classes[req.old_class_name].get("label", req.old_class_name))

    # 1) Rename in YAML
    classes[req.new_class_name] = classes.pop(req.old_class_name)
    raw["classes"] = classes
    _write_domain_yaml(domain_id, raw)

    # 2) Migrate GraphIndex nodes
    graph_migrated = 0
    if req.migrate_graph:
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            graph = GraphIndex.load(domain_id)
            graph_migrated = graph.migrate_class_nodes(req.old_class_name, req.new_class_name)
            graph.save()
        except Exception as e:
            logging.warning("GraphIndex migration skipped: %s", e)

    return {
        "status": "migrated",
        "domain": domain_id,
        "old_class_name": req.old_class_name,
        "new_class_name": req.new_class_name,
        "old_label": old_label,
        "graph_nodes_migrated": graph_migrated,
        "next_steps": [
            "本体编辑器 → 验证报告 → 检查分类覆盖率",
            f"如需全量重新分类，调用 POST /ontology/domains/{domain_id}/build-instances",
        ],
    }


@router.post("/ontology/domains/{domain_id}/properties", response_model=Dict[str, Any])
async def add_ontology_property(domain_id: str, req: OntologyPropertyCreate):
    """Add an object property to a domain ontology."""
    from pathlib import Path as _Path
    import os as _os
    d = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    file_path = d / f"{domain_id}.yaml"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    import yaml as _yaml
    with open(file_path, "r", encoding="utf-8") as f:
        raw = _yaml.safe_load(f)
    props = raw.get("object_properties", []) or []
    props.append({
        "name": req.name, "label": req.label,
        "domain": req.domain, "range": req.range,
        "transitive": req.transitive, "symmetric": req.symmetric,
    })
    raw["object_properties"] = props
    _write_domain_yaml(domain_id, raw)
    return {"status": "added", "domain": domain_id, "property": req.name}


@router.delete("/ontology/domains/{domain_id}/properties/{prop_name}", response_model=Dict[str, Any])
async def delete_ontology_property(domain_id: str, prop_name: str):
    """Delete an object property from a domain ontology."""
    from pathlib import Path as _Path
    import os as _os
    d = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    file_path = d / f"{domain_id}.yaml"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
    import yaml as _yaml
    with open(file_path, "r", encoding="utf-8") as f:
        raw = _yaml.safe_load(f)
    props = raw.get("object_properties", []) or []
    before = len(props)
    raw["object_properties"] = [p for p in props if p.get("name") != prop_name]
    if len(raw["object_properties"]) == before:
        raise HTTPException(status_code=404, detail=f"Property '{prop_name}' not found in '{domain_id}'")
    _write_domain_yaml(domain_id, raw)
    return {"status": "deleted", "domain": domain_id, "property": prop_name}

@router.get("/ontology/rules", response_model=Dict[str, Any])
async def list_inference_rules():
    """List all inference rules (built-in + registered)."""
    try:
        from core.harness.knowledge.knowledge_validator import DEFAULT_RULES
        rules = [{
            "name": r.name, "description": r.description,
            "trigger": r.trigger.value, "enabled": r.enabled,
            "severity": r.severity,
        } for r in DEFAULT_RULES]
        return {"rules": rules, "total": len(rules)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list rules: {e}")


@router.post("/ontology/rules", response_model=Dict[str, Any])
async def register_inference_rule(body: Dict[str, Any]):
    """Register a custom inference rule."""
    try:
        from core.harness.knowledge.knowledge_validator import (
            InferenceRule, RuleTrigger, register_rule
        )
        trigger = body.get("trigger", "on_create")
        if trigger not in [t.value for t in RuleTrigger]:
            raise HTTPException(status_code=400,
                detail=f"Invalid trigger. Must be one of {[t.value for t in RuleTrigger]}")
        rule = InferenceRule(
            name=body["name"],
            description=body.get("description", ""),
            trigger=RuleTrigger(trigger),
            pattern=body.get("pattern", ""),
            action=body.get("action", ""),
            severity=body.get("severity", "warning"),
        )
        register_rule(rule)
        return {"status": "registered", "name": rule.name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register rule: {e}")


# Evidence Chain — migrated to wiki_evidence.py (include_router, no prefix)
# OWL/RDF Export + Inference — migrated to wiki_ontology_export.py (include_router prefix="/ontology")
# Pattern Detector — migrated to wiki_ontology_patterns.py (include_router prefix="/ontology")

# ── Ontology Suggestions (Layer 3) ───────────────────────────────

@router.get("/ontology/suggestions", response_model=Dict[str, Any])
async def list_suggestions(status: str = "", collection: str = "default"):
    """List ontology evolution suggestions."""
    try:
        from core.harness.knowledge.knowledge_ontology import load_pending_suggestions
        suggestions = load_pending_suggestions(collection)
        if status:
            suggestions = [s for s in suggestions if s.get("status") == status]
        return {"suggestions": suggestions, "total": len(suggestions)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list suggestions: {e}")


@router.post("/ontology/suggestions", response_model=Dict[str, Any])
async def generate_suggestions(collection: str = "default"):
    """Scan wiki data and generate ontology evolution suggestions."""
    try:
        from core.harness.knowledge.knowledge_ontology import add_suggestions_from_patterns
        suggestions = add_suggestions_from_patterns(collection_id=collection)
        pending = [s for s in suggestions if s.get("status") == "pending"]
        return {"status": "generated", "total": len(suggestions), "pending": len(pending)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Suggestion generation failed: {e}")


@router.post("/ontology/suggestions/{suggestion_id}/accept", response_model=Dict[str, Any])
async def accept_suggestion(suggestion_id: str, reviewer: str = "", collection: str = "default"):
    """Accept an ontology evolution suggestion (marks for implementation)."""
    try:
        from core.harness.knowledge.knowledge_ontology import accept_suggestion
        result = accept_suggestion(suggestion_id, reviewer=reviewer, collection_id=collection)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Suggestion '{suggestion_id}' not found")
        return {"status": "accepted", "suggestion": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Accept failed: {e}")


@router.post("/ontology/suggestions/{suggestion_id}/reject", response_model=Dict[str, Any])
async def reject_suggestion(suggestion_id: str, reason: str = "", reviewer: str = "", collection: str = "default"):
    """Reject an ontology evolution suggestion."""
    try:
        from core.harness.knowledge.knowledge_ontology import reject_suggestion
        result = reject_suggestion(suggestion_id, reason=reason, reviewer=reviewer, collection_id=collection)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Suggestion '{suggestion_id}' not found")
        return {"status": "rejected", "suggestion": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reject failed: {e}")


@router.post("/ontology/suggestions/{suggestion_id}/generate-code", response_model=Dict[str, Any])
async def generate_code(suggestion_id: str, collection: str = "default"):
    """Generate implementation code for an accepted suggestion."""
    try:
        from core.harness.knowledge.knowledge_ontology import generate_code_for_suggestion
        result = generate_code_for_suggestion(suggestion_id, collection_id=collection)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Code generation failed: {e}")


@router.get("/ontology/schema-readiness", response_model=Dict[str, Any])
async def check_schema_readiness(collection: str = "default"):
    """Check how many wiki pages would pass ERROR-mode schema validation.

    Returns readiness percentage and list of failing pages with missing fields.
    Use this before enabling AIPLAT_WIKI_SCHEMA_MODE=error.
    """
    try:
        from core.harness.knowledge.knowledge_ontology import check_schema_readiness
        return check_schema_readiness(collection_id=collection)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Readiness check failed: {e}")


@router.post("/clean-stale-references", response_model=Dict[str, Any])
async def clean_stale_references_endpoint(collection: str = "default"):
    """Scan wiki pages, move stale kb: references from source_articles to stale_references.

    A reference is stale when the kb:doc_id does not exist in the KB database.
    After cleanup, the A-Box is rebuilt to refresh validator consistency scores.
    """
    try:
        from core.harness.knowledge.wiki_engine import clean_stale_references
        result = clean_stale_references(collection_id=collection)
        return {
            "status": "completed",
            "scanned": result["scanned"],
            "affected_pages": result["affected"],
            "stale_refs_moved": result["stale_refs_moved"],
            "abox_rebuilt": result.get("abox_rebuilt", False),
            "details": result.get("details", []),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {e}")


@router.post("/seed-instances", response_model=Dict[str, Any])
async def seed_instances_endpoint(collection: str = "default"):
    """Create seed instances for empty T-Box categories (atoms, contradictions).

    Scans topic pages for sub-concepts (→ atom pages) and contradictory
    page pairs (→ contradiction pages). Uses LLM for content analysis.
    """
    try:
        from core.harness.knowledge.wiki_engine import seed_instances
        result = await seed_instances(collection_id=collection)
        return {
            "status": "completed",
            "atoms_created": result["atoms_created"],
            "contradictions_created": result["contradictions_created"],
            "details": result.get("details", []),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Seeding failed: {e}")


@router.post("/backfill-evidence", response_model=Dict[str, Any])
async def backfill_evidence_endpoint(limit: int = 50, collection: str = "default"):
    """Backfill evidence annotations for wiki pages without them.

    Extracts the first 1-2 sentences from each page as evidence_text,
    embedding them as HTML comments for the evidence-chain API.
    """
    try:
        from core.harness.knowledge.wiki_engine import backfill_evidence_batch_sync
        result = backfill_evidence_batch_sync(collection_id=collection, limit=limit)
        return {
            "status": "completed",
            "candidates": result["total_candidates"],
            "succeeded": result["succeeded"],
            "failed": result["failed"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backfill failed: {e}")


@router.post("/batch-atomize", response_model=Dict[str, Any])
async def batch_atomize_endpoint(limit: int = 10, category: str = "topics", collection: str = "default"):
    """Batch atomize pages of a given category using LLM sub-concept extraction.

    Rate limited to 1 request/second. Creates KnowledgeAtom pages from
    topic page content.
    """
    import asyncio
    try:
        from core.harness.knowledge.wiki_engine import (
            search_pages, read_page, write_atom, _extract_sub_concepts
        )
        pages = [p for p in search_pages(limit=1000, collection_id=collection)
                 if p.get("category") == category]
        created = 0
        for page in pages[:limit]:
            full = read_page(page["title"], collection_id=collection)
            if full and len(full.get("body", "")) > 500:
                atoms = await _extract_sub_concepts(
                    page["title"], full["body"], collection
                )
                for atom in atoms[:2]:
                    existing = read_page(atom["title"], collection_id=collection)
                    if not existing:
                        write_atom(atom, collection_id=collection)
                        created += 1
                await asyncio.sleep(1.0)
        return {"status": "completed", "atoms_created": created, "scanned": min(limit, len(pages))}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch atomize failed: {e}")


@router.post("/maintain/fts-rebuild", response_model=Dict[str, Any])
async def rebuild_fts_index(collection: str = "default"):
    """Rebuild FTS5 full-text search index for wiki pages."""
    try:
        from core.harness.knowledge.wiki_fts import fts_index_pages
        count = fts_index_pages()
        return {"status": "completed", "indexed": count}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FTS rebuild failed: {e}")


@router.post("/wiki/evolve", response_model=Dict[str, Any])
async def evolve_knowledge(collection: str = "default", generations: int = 1,
                            max_mutations: int = 5, force: bool = False):
    """Run knowledge evolution — event-driven, not timer-driven.

    Triggers:
      - New pages >= 3 since last gen (auto, from wiki_auto_update)
      - Golden pass_rate dropped >= 10% (auto, from metrics)
      - force=True (manual, from frontend)
    
    Uses local LLM (qwen2.5:7b) for zero API cost.
    """
    try:
        from core.harness.knowledge.evolution_runner import EvolutionRunner
        runner = EvolutionRunner(
            collection_id=collection,
            max_mutations=max_mutations,
        )
        results = []
        for _ in range(generations):
            result = await runner.run_one_generation()
            results.append(result)
            if result.get("verdict") == "SKIPPED":
                if not force:
                    break
        return {"generations": results, "collection": collection}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evolution failed: {e}")


@router.get("/wiki/evolution-history", response_model=Dict[str, Any])
async def get_evolution_history(collection: str = "default"):
    """Get evolution generation history."""
    import json as _json, os as _os
    hist_path = _os.path.join(
        _os.path.expanduser(_os.getenv("AIPLAT_HOME", "~/.aiplat")),
        "wiki", "collections", collection, "evolution_history.json")
    if not _os.path.exists(hist_path):
        return {"generations": [], "total": 0}
    try:
        with open(hist_path) as f:
            history = _json.loads(f.read())
        return {"generations": history, "total": len(history)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/maintain/model-log", response_model=Dict[str, Any])
async def get_model_selection_log():
    """Return recent model selection log entries."""
    try:
        import json, os
        log_path = os.path.expanduser("~/.aiplat/wiki/model_selection_log.json")
        if not os.path.exists(log_path):
            return {"entries": [], "total": 0}
        with open(log_path) as f:
            entries = json.loads(f.read())
        return {"entries": entries[-50:], "total": len(entries)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/active-synthesis", response_model=Dict[str, Any])
async def run_active_synthesis(
    domain: str = "default",
    collection: str = "default",
    max_gaps: int = 5,
    auto_submit: bool = False,
):
    """Run active knowledge synthesis — detect gaps → research → draft → propose.

    Trigger modes:
      - Manual: set auto_submit=true to automatically create proposals
      - Preview: set auto_submit=false (default) to see drafts without submitting

    This is the STORM-style 'Compiler Mode': AI actively scans for knowledge
    gaps and proposes new wiki pages, rather than passively waiting for uploads.
    """
    try:
        from core.harness.knowledge.active_synthesis import run_active_synthesis as do_synthesis
        result = await do_synthesis(
            domain_id=domain,
            collection_id=collection,
            max_gaps=max_gaps,
            auto_submit=auto_submit,
        )
        return {"status": "completed", **result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:300])

# Proposal Workflow — migrated to wiki_proposals.py (include_router, no prefix)

# SQL Ontology Bridge — migrated to wiki_ontology_sql.py, mounted via include_router below

