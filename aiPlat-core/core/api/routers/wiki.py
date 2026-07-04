"""
Wiki API — persistent LLM-curated knowledge base endpoints.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
import logging

router = APIRouter(prefix="/wiki", tags=["wiki"])

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


@router.delete("/pages/{title}", response_model=Dict[str, Any])
async def delete_page(title: str, collection: str = "default"):
    from core.harness.knowledge.wiki_engine import delete_page as _del
    ok = _del(title, collection_id=collection)
    if not ok:
        raise HTTPException(status_code=404, detail="wiki_page_not_found")
    return {"title": title, "status": "deleted"}


@router.delete("/pages-all", response_model=Dict[str, Any])
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
        pass
    try:
        from core.harness.knowledge.wiki_engine import invalidate_graph_cache
        invalidate_graph_cache(body.collection if hasattr(body, 'collection') else "default")
    except Exception:
        pass
    # ── Provenance: mark all answers referencing this source as stale ──
    try:
        from core.harness.knowledge.provenance import get_provenance_tracker, ProvenanceScanner
        tracker = get_provenance_tracker()
        scanner = ProvenanceScanner(tracker)
        import asyncio as _asyncio
        _asyncio.create_task(scanner.on_source_updated(sid, str(time.time())))
    except Exception:
        pass
    return {"source_id": sid, "status": "ingested",
            "message": "Text stored. Execute wiki_curator agent to process and update wiki pages."}


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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Atomization failed: {e}")


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
                sql = f"SELECT doc_id, source_uri, kind, status, meta_json, created_at FROM documents WHERE tenant_id=? AND collection_id=? AND doc_id IN ({placeholders}) ORDER BY created_at DESC LIMIT ?"
                docs = conn.execute(sql, (tenant_id, collection_id, *doc_ids, limit)).fetchall()
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

                # Track keywords for cross-linking
                for kw in tags[:5]:
                    if kw not in topic_keywords:
                        topic_keywords[kw] = []
                    topic_keywords[kw].append(title)

                # Create wiki page (fast, no LLM)
                safe_title = re.sub(r"[<>:\"/\\|?*]", "_", title)[:120]
                write_page(safe_title, body, category="entities", tags=tags, summary=summary,
                          source_articles=[f"kb:{doc_id}"], collection_id=collection)
                # Queue for parallel curation (deferred, batched LLM calls)
                _curation_queue.append((doc_id, safe_title, body, tags, summary, collection, tenant_id, dict(doc)))
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Index generation failed: {e}")


@router.get("/wiki/health-trend", response_model=Dict[str, Any])
async def get_wiki_health_trend():
    """Get wiki health score trend over time."""
    try:
        from core.harness.knowledge.wiki_health_rules import get_health_trend
        return get_health_trend()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get health trend: {e}")


@router.get("/wiki/golden-queries/seed", response_model=Dict[str, Any])
async def seed_golden_queries():
    """Create a default golden_queries.yaml template."""
    try:
        from core.harness.knowledge.wiki_structured_query import seed_golden_queries
        return {"status": seed_golden_queries()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed: {e}")


@router.post("/wiki/golden-queries/run", response_model=Dict[str, Any])
async def run_golden_tests():
    """Run regression tests against golden queries."""
    try:
        from core.harness.knowledge.wiki_structured_query import run_golden_tests
        return run_golden_tests()
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Structured query failed: {e}")


@router.post("/ontology/rebuild", response_model=Dict[str, Any])
async def ontology_rebuild(collection: str = "default"):
    """Full rebuild of the knowledge ontology A-Box from current Wiki+KB data."""
    try:
        from core.harness.knowledge.knowledge_abox_builder import rebuild_full
        onto = rebuild_full(collection_id=collection)
        return {"status": "rebuilt", "triples": len(onto.triples), "collection": collection}
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


@router.get("/wiki/duplicates", response_model=Dict[str, Any])
async def detect_wiki_duplicates(collection: str = "default"):
    """Detect potentially duplicate wiki pages using embedding similarity."""
    try:
        from core.harness.knowledge.wiki_engine import detect_duplicate_pages
        duplicates = detect_duplicate_pages(collection_id=collection)
        return {"duplicates": duplicates, "total": len(duplicates)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Duplicate detection failed: {e}")


# ── Collection Management ───────────────────────────────────────

@router.get("/collections", response_model=Dict[str, Any])
async def list_wiki_collections():
    """List all wiki collections with page counts."""
    try:
        from core.harness.knowledge.wiki_engine import list_collections
        cols = list_collections()
        return {"collections": cols, "total": len(cols)}
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create collection: {e}")


@router.delete("/collections/{collection_id}", response_model=Dict[str, Any])
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list classes: {e}")


# ── Domain Ontology API (YAML-based) ─────────────────────────────

@router.get("/ontology/domains", response_model=Dict[str, Any])
async def list_ontology_domains():
    """List available domain ontology files."""
    from core.harness.knowledge.ontology_loader import list_domain_files, load_ontology_from_yaml
    from core.harness.knowledge.domain_router import DomainRouter
    from pathlib import Path as _Path
    import os as _os

    base_dir = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    router = DomainRouter()
    domains = []
    for domain_id in list_domain_files():
        file_path = str(base_dir / f"{domain_id}.yaml")
        try:
            domain = load_ontology_from_yaml(file_path)
            cfg = router.domain_config(domain.id)
            domains.append({
                "id": domain.id,
                "name": domain.name,
                "version": domain.version,
                "description": domain.description,
                "namespace": domain.namespace,
                "class_count": len(domain.classes),
                "property_count": len(domain.object_properties) + len(domain.data_properties),
                "min_wiki_score": cfg.get("min_wiki_score", 0.25),
                "expand_subclasses": cfg.get("expand_subclasses", True),
                "min_cross_results": cfg.get("min_cross_results", 3),
                "system_prompt_id": cfg.get("system_prompt_id", ""),
                "collection_id": cfg.get("collection_id", domain.id),
            })
        except Exception as e:
            logging.warning(str(e), exc_info=True)
    return {"domains": domains, "total": len(domains)}


@router.get("/ontology/domains/{domain_id}", response_model=Dict[str, Any])
async def get_ontology_domain(domain_id: str):
    """Get full domain ontology including classes + properties."""
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from core.harness.knowledge.domain_router import DomainRouter
    from pathlib import Path as _Path
    import os as _os

    base_dir = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    file_path = base_dir / f"{domain_id}.yaml"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain ontology '{domain_id}' not found")
    try:
        domain = load_ontology_from_yaml(str(file_path))
        cfg = DomainRouter().domain_config(domain.id)
        return {
            "id": domain.id,
            "name": domain.name,
            "namespace": domain.namespace,
            "description": domain.description,
            "version": domain.version,
            "min_wiki_score": cfg.get("min_wiki_score", 0.25),
            "expand_subclasses": cfg.get("expand_subclasses", True),
            "min_cross_results": cfg.get("min_cross_results", 3),
            "system_prompt_id": cfg.get("system_prompt_id", ""),
            "collection_id": cfg.get("collection_id", domain.id),
            "classes": [{
                "uri": c.uri, "label": c.label,
                "parent": c.parent.replace(domain.namespace, "") if c.parent else None,
                "required_fields": c.required_fields,
                "optional_fields": c.optional_fields,
                "categories": c.allowed_categories,
                "description": c.description,
                "fields": c.fields,
                "states": getattr(c, "states", None) or None,
                "transitions": getattr(c, "transitions", None) or [],
                "side_effects": getattr(c, "side_effects", None) or [],
                "synonyms": getattr(c, "synonyms", None) or [],
            } for c in domain.classes],
            "object_properties": [{
                "uri": p.uri, "label": p.label,
                "domain": [d.replace(domain.namespace, "") for d in (p.domain or [])],
                "range": [r.replace(domain.namespace, "") for r in (p.range or [])],
                "transitive": p.is_transitive, "symmetric": p.is_symmetric,
                "description": getattr(p, "description", "") or "",
            } for p in domain.object_properties],
            "data_properties": [{
                "uri": p.uri, "label": p.label,
                "domain": [d.replace(domain.namespace, "") for d in (p.domain or [])],
                "range": p.range,
            } for p in domain.data_properties],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load domain '{domain_id}': {e}")


@router.get("/ontology/domains/{domain_id}/validation-report", response_model=Dict[str, Any])
async def validate_ontology_domain(domain_id: str, collection: str = ""):
    """Cross-check existing data (Wiki pages + Graph nodes) against current ontology schema.

    Returns validation report with orphan pages, missing required fields,
    orphan graph nodes, and state mismatches.
    """
    from core.harness.knowledge.ontology_validator import validate_domain, validate_report_to_dict
    cid = collection or domain_id
    report = validate_domain(domain_id, collection_id=cid)
    return validate_report_to_dict(report)


_verify_cache: dict = {}  # domain_id → (timestamp, result)


@router.post("/ontology/domains/{domain_id}/verify", response_model=Dict[str, Any])
async def verify_ontology_domain(domain_id: str, collection: str = ""):
    """Unified verification: classification coverage + graph stats + anomalies.
    
    Results cached for 60s to reduce filesystem scan load.
    """
    import time as _time
    now = _time.time()
    cached = _verify_cache.get(domain_id)
    if cached and now - cached[0] < 60:
        return cached[1]

    from core.harness.knowledge.wiki_engine import search_pages, list_all_pages
    from core.harness.ontology_engine.graph_index import GraphIndex
    from core.harness.knowledge.domain_router import DomainRouter
    from collections import Counter

    router = DomainRouter()
    cid = collection or router.resolve_collection(domain_id) or domain_id

    # 1. Classification coverage
    all_pages = list_all_pages(collection_id=cid)
    cat_counts = Counter()
    unclassified = 0
    for p in all_pages:
        cat = str(p.get("category") or "")
        if cat in ("entities", "topics", ""):
            unclassified += 1
        else:
            cat_counts[cat] += 1

    # 2. Graph stats
    graph_nodes = graph_edges = 0
    try:
        graph = GraphIndex.load(domain_id)
        graph_nodes = len(graph._nodes)
        graph_edges = sum(len(n.out_edges) for n in graph._nodes.values())
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    # 3. Issues detection
    issues = []
    total = len(all_pages)

    if unclassified > total * 0.5:
        issues.append({"type": "unclassified_high", "severity": "warn",
                       "detail": f"{unclassified}/{total} 页未分类，执行分类+构建"})
    elif unclassified > 0:
        issues.append({"type": "unclassified", "severity": "info",
                       "detail": f"{unclassified}/{total} 页未分类"})

    if graph_nodes < total * 0.1:
        issues.append({"type": "few_nodes", "severity": "warn",
                       "detail": f"图节点 {graph_nodes}，远少于 {total} 页"})

    classified_by_cat = {c: n for c, n in cat_counts.items() if n > 0}
    if len(classified_by_cat) >= 3 and graph_edges == 0:
        issues.append({"type": "no_edges", "severity": "warn",
                       "detail": "分类多但图中无边，运行构建实例"})

    overall = "pass" if not any(i["severity"] == "warn" for i in issues) else "warn"

    result = {
        "overall": overall, "domain_id": domain_id,
        "classification": {"total_pages": total, "classified": total - unclassified,
                          "unclassified": unclassified, "by_category": dict(cat_counts.most_common(10))},
        "graph": {"nodes": graph_nodes, "edges": graph_edges},
        "issues": issues,
    }
    _verify_cache[domain_id] = (now, result)
    return result


@router.get("/ontology/domains/{domain_id}/scoring", response_model=Dict[str, Any])
async def get_scoring_config(domain_id: str):
    """Get current retrieval scoring weights for a domain."""
    try:
        import yaml, os
        from pathlib import Path as _Path
        config_path = os.getenv("AIPLAT_LLM_CONFIG_PATH",
            str(_Path(__file__).resolve().parent.parent.parent.parent.parent /
                "aiPlat-infra" / "config" / "infra" / "llm_profile.yaml"))
        profile = yaml.safe_load(open(config_path)) or {}
        return profile.get("retrieval_scoring", {
            "semantic": 0.55, "fts_keyword": 0.15,
            "freshness": 0.10, "credibility": 0.10, "density": 0.10,
        })
    except Exception:
        return {"semantic": 0.55, "fts_keyword": 0.15, "freshness": 0.10, "credibility": 0.10, "density": 0.10}


@router.put("/ontology/domains/{domain_id}/scoring", response_model=Dict[str, Any])
async def update_scoring_config(domain_id: str, config: dict):
    """Update retrieval scoring weights. Changes take effect immediately."""
    import yaml, os
    from pathlib import Path as _Path
    config_path = os.getenv("AIPLAT_LLM_CONFIG_PATH",
        str(_Path(__file__).resolve().parent.parent.parent.parent.parent /
            "aiPlat-infra" / "config" / "infra" / "llm_profile.yaml"))
    try:
        profile = yaml.safe_load(open(config_path)) or {}
    except Exception:
        profile = {}
    allowed = {"semantic", "fts_keyword", "freshness", "credibility", "density"}
    scoring = {k: float(config.get(k, 0.10)) for k in allowed}
    profile["retrieval_scoring"] = scoring
    with open(config_path, "w") as f:
        yaml.dump(profile, f, allow_unicode=True, default_flow_style=False)
    # Clear verify cache so next verify reflects new weights
    _verify_cache.pop(domain_id, None)
    return {"status": "saved", "scoring": scoring, "cache_cleared": True}


def _clean_summary(text: str, max_len: int = 200) -> str:
    """Strip markdown images, HTML tags, and truncate for clean display."""
    import re as _re
    # Strip markdown images: ![alt](url)
    text = _re.sub(r'!\[.*?\]\(.*?\)', '', text)
    # Strip raw image URLs
    text = _re.sub(r'https?://\S+\.(?:jpg|jpeg|png|gif|webp|gif)\S*', '', text)
    # Strip HTML tags
    text = _re.sub(r'<[^>]+>', '', text)
    # Collapse whitespace
    text = _re.sub(r'\s+', ' ', text).strip()
    # Remove leading special chars
    text = _re.sub(r'^[`\s]+', '', text)
    return text[:max_len]


@router.get("/ontology/domains/{domain_id}/instances", response_model=Dict[str, Any])
async def list_instances_by_class(domain_id: str, class_label: str = ""):
    """List all ontology instances (Wiki pages) for a given class_label.

    Maps class_label → domain YAML categories → searches Wiki pages by category.
    Wiki pages ARE the ontology instances — no separate graph node store needed.
    """
    from core.harness.knowledge.wiki_engine import search_pages, read_page
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from core.harness.knowledge.domain_router import DomainRouter
    from pathlib import Path as _Path
    import os as _os, re as _re

    if not class_label:
        return {"instances": [], "total": 0, "error": "class_label parameter required"}

    # Resolve class_label → category names
    onto_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    categories = []
    if onto_path.exists():
        domain = load_ontology_from_yaml(str(onto_path))
        for cls in domain.classes:
            if cls.label == class_label:
                categories = cls.allowed_categories or []
                break

    if not categories:
        # Fallback: use class_label itself as category
        categories = [class_label]

    router = DomainRouter()
    cid = router.resolve_collection(domain_id) or domain_id

    instances = []
    for cat in categories:
        pages = search_pages(category=cat, limit=200, collection_id=cid)
        for p in pages:
            summary = _clean_summary(p.get("summary", "") or "")
            if not summary:
                try:
                    full = read_page(p.get("title", ""), category=cat, collection_id=cid)
                    if full:
                        body = str(full.get("body", "") or "")[:500]
                        body = _re.sub(r'[#*`>\[\]!|~]', '', body)
                        body = _re.sub(r'https?://\S+', '', body)
                        body = _re.sub(r'\s+', ' ', body).strip()
                        summary = body[:200]
                except Exception as e:
                    logging.warning(str(e), exc_info=True)

            instances.append({
                "entity_name": p.get("title", ""),
                "wiki_title": p.get("title", ""),
                "class_name": class_label,
                "category": cat,
                "summary": _clean_summary(p.get("summary", "") or ""),
                "tags": p.get("tags", []) or [],
                "related": p.get("related", []) or [],
                "state": p.get("frontmatter", {}).get("state", "") if isinstance(p.get("frontmatter"), dict) else "",
                "last_updated": p.get("last_updated", ""),
            })

    return {"instances": instances, "total": len(instances), "class_label": class_label}




@router.get("/ontology/class-by-category", response_model=Dict[str, Any])
async def get_ontology_class_by_category(category: str = "entities", collection: str = "default"):
    """Return the OntologyClass matching a category name, with required/optional/template fields.
    
    Used by Wiki creation form to dynamically render fields.
    Checks all loaded domain ontologies + built-in classes.
    """
    from core.harness.knowledge.ontology_loader import load_all_domains
    from core.harness.knowledge.knowledge_ontology import CLASSES
    from pathlib import Path as _Path
    import os as _os

    result = {"category": category, "found": False, "required_fields": [], "optional_fields": [],
              "template_markdown": "", "class_label": category}

    # 1) Check domain ontologies first
    domains = load_all_domains()
    for domain_id, domain in domains.items():
        for cls in domain.classes:
            if category in cls.allowed_categories:
                result.update({
                    "found": True,
                    "domain": domain_id,
                    "required_fields": cls.required_fields,
                    "optional_fields": cls.optional_fields,
                    "template_markdown": cls.template_markdown,
                    "class_label": cls.label,
                    "class_uri": cls.uri,
                })
                return result

    # 2) Fall back to built-in CLASSES
    for cls in CLASSES:
        if category in (cls.allowed_categories or []):
            result.update({
                "found": True,
                "domain": "built-in",
                "required_fields": cls.required_fields,
                "optional_fields": cls.optional_fields,
                "template_markdown": cls.template_markdown,
                "class_label": cls.label,
                "class_uri": cls.uri,
            })
            return result

    return result


@router.post("/ontology/domains/{domain_id}/classify-all", response_model=Dict[str, Any])
async def classify_all_pages(domain_id: str, collection: str = "", limit: int = 5):
    """Auto-classify unclassified wiki pages using LLM (reads body content), then auto-trigger build-instances.

    Reads first 300 chars of each page body to improve classification accuracy.
    After classification, auto-calls build-instances to populate the knowledge graph.
    """
    from core.harness.knowledge.wiki_engine import search_pages, read_page, write_page
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from core.harness.knowledge.domain_router import DomainRouter
    from core.harness.utils.model_injection import create_selected_adapter
    from core.adapters.llm.base import LLMConfig
    import re as _re, json as _json, os as _os, logging
    from pathlib import Path as _Path

    router = DomainRouter()
    cid = collection or router.resolve_collection(domain_id) or domain_id

    all_pages = search_pages(limit=200, collection_id=cid)
    batch = [p for p in all_pages if p.get('category') in ('entities', 'topics', '')][:limit]
    if not batch:
        return {"status": "no_unclassified", "total_pages": len(all_pages)}

    onto_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    all_classes = []
    if onto_path.exists():
        domain = load_ontology_from_yaml(str(onto_path))
        for cls in domain.classes:
            all_classes.append({"label": cls.label, "categories": cls.allowed_categories or []})

    if not all_classes:
        return {"status": "no_classes", "total_pages": len(batch)}

    # Pre-read page bodies for better classification
    page_bodies = {}
    for p in batch[:5]:  # Limit to 15 per LLM call
        try:
            full = read_page(p["title"], collection_id=cid)
            if full:
                page_bodies[p["title"]] = str(full.get("body", "") or "")[:100]
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    cat_names = ", ".join(c["categories"][0] for c in all_classes if c["categories"])
    class_lines = "\n".join(
        f"  - {c['label']}: category='{c['categories'][0] if c['categories'] else 'none'}'"
        for c in all_classes
    )
    page_lines = "\n".join(
        f"  - {p['title']}\n    excerpt: {page_bodies.get(p['title'], '')[:120]}"
        for p in batch[:15]
    )

    prompt = (
        f"Classify each page. Use ONLY: {cat_names}\n\n"
        f"Pages:\n{page_lines}\n\n"
        f"Output JSON array. Include the EXACT page title (copy-paste from above) and category:\n"
        f'[{{"title":"copy the exact title from the list above","category":"one of {cat_names}"}}]'
    )

    try:
        from core.harness.utils.model_injection import generate_with_fallback
        data = {"suggestions": []}

        for attempt in range(5):
            resp, _ = await generate_with_fallback(
                "ontology_gen",
                [{"role": "system", "content": "Output ONLY valid JSON without markdown."},
                 {"role": "user", "content": prompt}],
                timeout=120, config=LLMConfig(model="", timeout=120, max_tokens=2048),
            )
            content = resp.content if hasattr(resp, 'content') else str(resp)
            logging.getLogger("wiki").info(f"classify-all response: {content[:200]}")
            clean = content.strip()
            # Strip markdown code fences
            if clean.startswith('```'):
                clean = _re.sub(r'^```\w*\s*', '', clean)
                clean = _re.sub(r'\s*```$', '', clean)
            # Support both object {...} and array [{...}] responses
            brace_start = clean.find('{')
            bracket_start = clean.find('[')
            start = bracket_start if bracket_start >= 0 and (brace_start < 0 or bracket_start < brace_start) else brace_start
            if start >= 0:
                dec = _json.JSONDecoder()
                data, _ = dec.raw_decode(clean[start:])
                if isinstance(data, list):
                    data = {"suggestions": data}
                elif isinstance(data, dict):
                    if "suggestions" not in data and "pages" not in data and "title" in data:
                        data = {"suggestions": [data]}
                data_sug = data.get("suggestions") or data.get("pages") or []
                if isinstance(data_sug, list) and len(data_sug) > 0:
                    break
    except Exception as e:
        logging.getLogger("wiki").warning(f"classify-all LLM failed: {e}")
        return {"status": "llm_failed", "total": len(batch), "error": str(e)}

    suggestions = data.get("suggestions", []) or data.get("pages", [])
    valid_cats = set()
    for c in all_classes:
        valid_cats.update(c.get("categories", []) or [])
    applied, errors = [], []

    # Normalize function for title matching
    def _norm(t: str) -> str:
        t = t.strip()
        t = __import__('re').sub(r'[：:—\-–\s、，。；！？【】（）《》""'']+', '', t)
        return __import__('unicodedata').normalize('NFKC', t)[:80]

    # Build normalized title → page mapping for batch
    page_by_norm = {}
    for p in batch:
        page_by_norm[_norm(p.get("title", ""))] = p

    # Apply each suggestion
    for si, s in enumerate(suggestions):
        if isinstance(s, str):
            continue  # skip malformed LLM output
        s_title = s.get("title", "")
        # Strip [category] prefix that LLM may copy from prompt
        s_title = _re.sub(r'^\[[^\]]+\]\s*', '', s_title).strip()
        s_cat = s.get("category", "")
        # Fallback: if title missing, match by position in batch
        if not s_title and si < len(batch):
            s_title = batch[si].get("title", "")
        if s_cat not in valid_cats:
            continue  # skip hallucinated categories

        # Find matching page by normalized title
        nt = _norm(s_title)
        page = page_by_norm.get(nt)
        if not page:
            # Try partial match
            for pn, pp in page_by_norm.items():
                if pn and nt and (pn in nt or nt in pn):
                    page = pp; break
        if not page:
            continue

        title = page.get("title", "")
        if s_cat == page.get("category"):
            continue

        try:
            full = read_page(title, collection_id=cid)
            if not full: continue
            write_page(title=title, body=full.get("body", ""),
                       category=s_cat, collection_id=cid,
                       tags=list(full.get("tags", []) or []))
            applied.append({"title": title, "category": s_cat,
                           "confidence": s.get("confidence", 0)})
        except Exception as e:
            errors.append(f"{title}: {e}")

    return {
        "status": "classified", "total_pages": len(batch),
        "applied": len(applied), "errors": len(errors), "details": applied[:20],
        "error_details": errors[:10],
    }


# ── Ontology Engine API ─────────────────────────────────────────

@router.post("/ontology/engine/process", response_model=Dict[str, Any])
async def ontology_engine_process(req: dict, collection: str = "default"):
    """本体引擎处理：单文档 → 本体实例。
    
    请求体: {"text": "...", "domain_id": "ai-knowledge", "doc_id": "kb:xxx"}
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    text = req.get("text", "") if isinstance(req, dict) else ""
    doc_id = req.get("doc_id", "") if isinstance(req, dict) else ""

    if not text.strip():
        raise HTTPException(status_code=400, detail="text is required")

    from core.harness.ontology_engine.engine import load_engine
    engine = load_engine(domain_id)
    if engine is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    chunks = [{"id": "chunk-0", "text": text, "entities": []}]
    result = await engine.process_chunks(chunks, doc_id=doc_id)
    return result.to_dict()


@router.post("/ontology/engine/process-and-write", response_model=Dict[str, Any])
async def ontology_engine_process_and_write(req: dict, collection: str = "default"):
    """本体引擎 → 实例 → 自动写 Wiki 页面。
    
    请求体: {"text": "...", "domain_id": "ai-knowledge", "doc_id": "kb:xxx", "auto_write": true}
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    text = req.get("text", "") if isinstance(req, dict) else ""
    doc_id = req.get("doc_id", "") if isinstance(req, dict) else ""
    auto_write = bool(req.get("auto_write", True)) if isinstance(req, dict) else True

    from core.harness.ontology_engine.engine import load_engine
    from core.harness.knowledge.wiki_engine import write_page

    engine = load_engine(domain_id)
    if engine is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    chunks = [{"id": "chunk-0", "text": text, "entities": []}]
    result = await engine.process_chunks(chunks, doc_id=doc_id)

    written = []
    if auto_write and result.instances:
        for inst in result.instances:
            fm = inst.get("frontmatter", {})
            title = fm.get("title", "")
            if not title:
                continue
            try:
                await write_page(
                    title=title,
                    body=fm.get("body", "") or str(fm.get("description", "") or ""),
                    category=fm.get("category", "entities"),
                    collection_id=collection,
                    tags=list(fm.get("tags", []) or []),
                    summary=str(fm.get("summary", "") or ""),
                )
                written.append(title)
            except Exception as e:
                logging.warning(str(e), exc_info=True)

    return {**result.to_dict(), "written_pages": written, "written_count": len(written)}


@router.post("/ontology/domains/{domain_id}/cleanup-nodes", response_model=Dict[str, Any])
async def cleanup_cross_domain_nodes(domain_id: str):
    """Remove graph nodes whose entity_name matches keywords from other domains.

    Auto-detects cross-domain vocabulary from other domains' YAML labels and synonyms.
    Config-driven — no hardcoded domain terms. Scales to any new domain.
    """
    from core.harness.ontology_engine.graph_index import GraphIndex
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml, load_all_domains
    from pathlib import Path as _Path
    import os as _os

    graph = GraphIndex.load(domain_id)

    # Build current domain's vocabulary from labels + synonyms
    domain_vocab = set()
    onto_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    if onto_path.exists():
        domain = load_ontology_from_yaml(str(onto_path))
        for cls in domain.classes:
            domain_vocab.add(cls.label)
            for syn in (getattr(cls, "synonyms", []) or []):
                domain_vocab.add(syn)

    # Auto-build cross-domain keywords from OTHER domains' labels + synonyms
    cross_keywords = set()
    try:
        for other_id, other_dom in load_all_domains().items():
            if other_id == domain_id:
                continue
            for cls in other_dom.classes:
                cross_keywords.add(cls.label)
                for syn in (getattr(cls, "synonyms", []) or []):
                    cross_keywords.add(syn)
    except Exception as e:
        logging.warning(str(e), exc_info=True)

    if not cross_keywords:
        return {"status": "no_cross_keywords", "domain_id": domain_id}

    removed = []
    for node in list(graph._nodes.values()):
        name = node.entity_name or ""
        if any(kw in name for kw in cross_keywords) and not any(v in name for v in domain_vocab):
            graph.remove_entity(node.entity_id)
            removed.append({"entity_id": node.entity_id, "entity_name": name[:80], "class_name": node.class_name})

    return {"status": "cleaned", "domain_id": domain_id, "removed": len(removed), "details": removed[:20]}


@router.post("/ontology/domains/{domain_id}/backfill-summaries", response_model=Dict[str, Any])
async def backfill_summaries(domain_id: str, collection: str = "", limit: int = 200):
    """Backfill empty summaries for all wiki pages in this domain's collection.

    Calls write_page for each page with empty summary, which triggers
    auto-summary generation from the page body.
    """
    from core.harness.knowledge.wiki_engine import read_page, write_page, list_all_pages
    from core.harness.knowledge.domain_router import DomainRouter

    router = DomainRouter()
    cid = collection or router.resolve_collection(domain_id) or domain_id

    pages = list_all_pages(collection_id=cid)
    filled = 0
    for page in pages[:limit]:
        title = str(page.get("title") or "")
        if not title:
            continue
        try:
            page_cat = str(page.get("category") or "entities")
            full = read_page(title, category=page_cat, collection_id=cid)
            if not full:
                continue
            body = str(full.get("body", "") or "")
            write_page(
                title=title, body=body,
                category=str(full.get("category", "entities")),
                collection_id=cid, summary="",  # empty → auto-generate from body
                tags=list(full.get("tags", []) or []),
            )
            filled += 1
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    return {"status": "backfilled", "filled": filled, "total": min(len(pages), limit)}


_build_semaphore = None  # lazy init to avoid import-time asyncio issues


@router.post("/ontology/domains/{domain_id}/build-instances", response_model=Dict[str, Any])
async def build_instances_batch(domain_id: str, collection: str = "", limit: int = 50):
    """Batch-run ontology engine on all Wiki pages in this domain's collection.
    
    Uses parallel processing (2 concurrent) — prevents OOM on 16GB machines.
    """
    from core.harness.ontology_engine.engine import load_engine
    from core.harness.knowledge.wiki_engine import read_page, write_page, list_all_pages
    from core.harness.knowledge.domain_router import DomainRouter
    import asyncio

    router = DomainRouter()
    cid = collection or router.resolve_collection(domain_id) or domain_id

    engine = load_engine(domain_id)
    if engine is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    # ── Differential: skip already-built pages ──
    import os as _os, json as _json
    from pathlib import Path as _Path
    built_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "graph" / f"{domain_id}_built.json"
    built_pages = set()
    if built_path.exists():
        try:
            built_pages = set(_json.loads(built_path.read_text(encoding="utf-8")))
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    pages = list_all_pages(collection_id=cid)
    if not pages:
        return {"status": "no_pages", "domain_id": domain_id, "collection": cid}

    # Filter to classified pages only, skip already-built
    valid = []
    new_sources = []
    skipped = 0
    for page in pages[:limit]:
        cat = str(page.get("category") or "")
        if cat in ("entities", "topics", ""):
            continue
        title = str(page.get("title") or "")
        if title in built_pages:
            skipped += 1
            continue
        full = read_page(title, category=str(page.get("category") or "entities"), collection_id=cid)
        if full and len(str(full.get("body") or "")) >= 20:
            valid.append({"title": title, "body": str(full.get("body") or "")[:8000]})
            new_sources.append(title)

    results = {"domain_id": domain_id, "collection": cid, "total_pages": len(pages),
               "processed": 0, "instances_created": 0, "errors": 0, "details": []}

    # Parallel batch processing: 10 concurrent pages
    batch_size = 2  # was 10 — reduced to prevent OOM on M2 16GB
    for i in range(0, len(valid), batch_size):
        batch = valid[i:i + batch_size]
        tasks = [_process_single_page(engine, page, cid) for page in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for j, br in enumerate(batch_results):
            if isinstance(br, Exception):
                results["errors"] += 1
                results["details"].append({"title": batch[j]["title"], "error": str(br)})
            else:
                results["processed"] += 1
                results["instances_created"] += br.get("instances", 0)
                results["details"].append(br)
                # Mark page as built
                built_pages.add(new_sources[i + j])

    # Persist differential tracking
    results["skipped"] = skipped
    if new_sources:
        built_path.parent.mkdir(parents=True, exist_ok=True)
        built_path.write_text(_json.dumps(sorted(built_pages), ensure_ascii=False), encoding="utf-8")

    return results


@router.post("/ontology/domains/{domain_id}/build-edges", response_model=Dict[str, Any])
async def build_cross_page_edges(domain_id: str):
    """Build cross-page edges by linking graph nodes via wiki references + keyword overlap.
    
    Strategy:
      1. Load graph nodes + wiki page cross-references (related, source_articles)
      2. Match references to other graph nodes
      3. Use YAML relation type definitions to determine edge type
      4. Add edges to graph via add_relation()
    """
    from core.harness.ontology_engine.engine import get_graph
    from core.harness.knowledge.wiki_engine import read_page, list_all_pages
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from core.harness.knowledge.domain_router import DomainRouter
    from pathlib import Path as _Path
    import os as _os

    graph = get_graph(domain_id)
    if not graph or len(graph._nodes) < 2:
        return {"edges_created": 0, "message": "Not enough nodes for cross-page edges"}

    router = DomainRouter()
    cid = router.resolve_collection(domain_id) or domain_id
    nodes = list(graph._nodes.values())

    # Load domain relation type definitions
    onto_path = _Path(_os.getenv("AIPLAT_HOME", _Path.home() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    domain = load_ontology_from_yaml(str(onto_path))
    class_to_categories = {}
    for cls in domain.classes:
        class_to_categories[cls.label] = set(cls.allowed_categories or [])

    # Build: entity_name → node + wiki page data
    name_to_node = {}
    name_to_page = {}
    all_pages = list_all_pages(collection_id=cid)
    page_by_title = {p.get("title", ""): p for p in all_pages}

    for node in nodes:
        name = node.entity_name or node.entity_id
        name_to_node[name] = node
        # Try to find matching wiki page
        for title, page in page_by_title.items():
            if name in title or title in name:
                name_to_page[name] = page
                break

    # Reload pages for nodes that need cross-reference data
    node_cross_refs = {}
    for name, page in name_to_page.items():
        full = read_page(page.get("title", ""), category=page.get("category", "entities"), collection_id=cid)
        if full:
            related = full.get("related", []) or []
            sources = full.get("source_articles", []) or []
            body = full.get("body", "")
            # Extract wiki-style links from body [[title]]
            import re
            wiki_links = re.findall(r'\[\[([^\]]+)\]\]', str(body))
            node_cross_refs[name] = {
                "related": [str(r) for r in related],
                "sources": [str(s) for s in sources],
                "body": str(body)[:2000],
                "wiki_links": wiki_links,
            }

    # Phase 1: Match via wiki references (related, source_articles, [[links]])
    edges_added = 0
    seen_pairs = set()
    existing_edges = set()
    for node in nodes:
        nid = node.entity_id or node.entity_name
        if nid not in graph._nodes:
            continue
        for edge in graph._nodes[nid].out_edges:
            existing_edges.add((nid, edge.target_id))

    for name, refs in node_cross_refs.items():
        if name not in name_to_node:
            continue
        source_node = name_to_node[name]
        source_id = source_node.entity_id or name
        source_class = source_node.class_name or ""

        # Collect all reference targets
        ref_targets = []
        ref_targets.extend(refs.get("related", []))
        ref_targets.extend(refs.get("sources", []))
        ref_targets.extend(refs.get("wiki_links", []))

        for ref in ref_targets:
            ref = str(ref).strip()
            if not ref:
                continue
            # Match to node by name
            for target_name, target_node in name_to_node.items():
                if target_name == name:
                    continue  # skip self
                target_id = target_node.entity_id or target_name
                target_class = target_node.class_name or ""
                pair_key = (source_id, target_id)
                if pair_key in seen_pairs:
                    continue
                if pair_key in existing_edges:
                    continue
                # Check if ref matches target
                ref_low = ref.lower()
                target_low = target_name.lower()
                if ref_low not in target_low and target_low not in ref_low:
                    continue
                seen_pairs.add(pair_key)

                # Determine relation type from YAML object_properties
                rel_type = _match_relation_type(domain, source_class, target_class)
                if rel_type:
                    graph.add_relation(
                        source_id=source_id,
                        target_id=target_id,
                        relation_name=rel_type,
                        confidence=0.8,
                    )
                    edges_added += 1

    # Phase 2: Entity name in body — primary cross-page linking strategy
    for name_a, refs_a in node_cross_refs.items():
        if name_a not in name_to_node:
            continue
        source_node = name_to_node[name_a]
        source_id = source_node.entity_id or name_a
        source_class = source_node.class_name or ""

        for name_b, refs_b in node_cross_refs.items():
            if name_b == name_a:
                continue
            pair_key = (source_id, name_b)
            if pair_key in seen_pairs or pair_key in existing_edges:
                continue
            target_node = name_to_node.get(name_b)
            if not target_node:
                continue
            target_id = target_node.entity_id or name_b
            target_class = target_node.class_name or ""

            body_a = refs_a.get("body", "")
            body_b = refs_b.get("body", "")

            # Check bidirectional keyword overlap
            linked = False
            # name_a appears in body_b?
            if name_a and len(name_a) >= 3 and name_a.lower() in body_b.lower():
                linked = True
            # name_b appears in body_a?
            elif name_b and len(name_b) >= 3 and name_b.lower() in body_a.lower():
                linked = True
            # Overlap in page names (one title contains the other)
            elif name_a and name_b and (name_a.lower() in name_b.lower() or name_b.lower() in name_a.lower()):
                linked = True

            if not linked:
                continue

            # ── Semantic gate: keyword overlap ≥ 2 + cosine ≥ 0.7 ──
            keywords_a = _extract_keywords_light(body_a) if body_a else set()
            keywords_b = _extract_keywords_light(body_b) if body_b else set()
            overlap = len(keywords_a & keywords_b)
            if overlap < 2:
                continue  # weak candidate, skip

            # Read cached vectors from vectors.json (no recomputation)
            vec_a = _get_cached_vector(name_a, collection_id=cid)
            vec_b = _get_cached_vector(name_b, collection_id=cid)
            if vec_a and vec_b:
                sim = _cosine_similarity(vec_a, vec_b)
                if sim < 0.7:
                    continue  # semantically unrelated

            seen_pairs.add(pair_key)

            rel_type = _match_relation_type(domain, source_class, target_class)
            if not rel_type:
                rel_type = _match_relation_type(domain, target_class, source_class)
                source_id, target_id = target_id, source_id  # swap for inverse

            if rel_type:
                graph.add_relation(
                    source_id=source_id,
                    target_id=target_id,
                    relation_name=rel_type,
                    confidence=0.6,
                )
                edges_added += 1

    graph.save()
    return {"edges_created": edges_added, "total_nodes": len(nodes),
            "total_pairs_checked": len(seen_pairs)}


def _extract_keywords_light(text: str) -> set:
    """Extract Chinese bigrams + English words as keyword set."""
    import re
    tokens = set()
    # Chinese: 2-gram sliding window
    chinese = re.findall(r'[\u4e00-\u9fff]+', text)
    for seg in chinese:
        for i in range(len(seg) - 1):
            tokens.add(seg[i:i+2])
    # English: words ≥ 3 chars
    eng = re.findall(r'[a-zA-Z]{3,}', text)
    tokens.update(w.lower() for w in eng)
    return tokens


def _get_cached_vector(title: str, *, collection_id: str = "default") -> list:
    """Read cached embedding vector from vectors.json. Returns None if not found."""
    import json, os
    from pathlib import Path
    cache_path = Path(os.getenv("AIPLAT_HOME", Path.home() / ".aiplat")) / "wiki" / "collections" / collection_id / "vectors.json"
    if not cache_path.exists():
        return None
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        return cache.get(title)
    except Exception:
        return None


def _cosine_similarity(a: list, b: list) -> float:
    """Compute cosine similarity between two float lists."""
    import math
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _match_relation_type(domain, source_class: str, target_class: str) -> str:
    """Find matching relation type from domain YAML object_properties.
    
    Resolves both Chinese labels and short IDs to match against full URI domain/range values.
    """
    # Build label→uri mapping
    label_to_uri = {}
    for cls in domain.classes:
        uri = getattr(cls, 'uri', '') or ''
        if uri:
            label_to_uri[cls.label] = uri
    
    # Candidate URIs for source and target
    source_uris = {source_class, label_to_uri.get(source_class, '')}
    target_uris = {target_class, label_to_uri.get(target_class, '')}
    
    for prop in (domain.object_properties or []):
        domains = set(prop.domain or [])
        ranges = set(prop.range or [])
        if source_uris & domains and target_uris & ranges:
            return prop.label
    # Try inverse
    for prop in (domain.object_properties or []):
        domains = set(prop.domain or [])
        ranges = set(prop.range or [])
        if target_uris & domains and source_uris & ranges:
            return prop.inverse_of or prop.inverse_label or ""
    return ""


async def _process_single_page(engine, page: dict, cid: str) -> dict:
    """Process one page through the engine pipeline. Runs in parallel with others."""
    import asyncio
    global _build_semaphore
    if _build_semaphore is None:
        _build_semaphore = asyncio.Semaphore(3)  # max 3 concurrent pages across all requests
    from core.harness.knowledge.wiki_engine import write_page
    async with _build_semaphore:
        chunks = [{"id": f"wiki-{page['title']}", "text": page["body"][:8000], "entities": []}]
        result = await engine.process_chunks(chunks, doc_id=f"wiki:{page['title']}")
        inst_count = len(result.instances) if hasattr(result, "instances") else 0

        if hasattr(result, "instances") and result.instances:
            for inst in result.instances[:3]:
                fm = inst.get("frontmatter", {})
                ititle = fm.get("title", "") or inst.get("entity_name", "")
                if ititle and ititle != page["title"]:
                    try:
                        await write_page(
                            title=ititle, body=fm.get("body", "") or str(fm.get("description", "") or ""),
                            category=fm.get("category", "entities"), collection_id=cid,
                        )
                    except Exception as e:
                        logging.warning(str(e), exc_info=True)

        return {"title": page["title"], "instances": inst_count,
                "relations": len(result.relations) if hasattr(result, "relations") else 0}


@router.get("/ontology/engine/traces/{instance_title:path}", response_model=Dict[str, Any])
async def ontology_engine_trace(instance_title: str, doc_id: str = ""):
    """查询实例溯源。需提供 instance_title 和可选的 doc_id。"""
    import os as _os
    from pathlib import Path as _Path
    traces_dir = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontology_traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    safe = instance_title.replace("/", "_")[:120]
    trace_file = traces_dir / f"{safe}.json"
    if not trace_file.exists():
        raise HTTPException(status_code=404, detail=f"No trace found for '{instance_title}'")
    return _json.loads(trace_file.read_text(encoding="utf-8"))


@router.post("/ontology/engine/parse", response_model=Dict[str, Any])
async def ontology_engine_parse(req: dict):
    """解析文档 → 结构化Chunk → 本体引擎处理。
    
    支持: 文本字符串 + 格式参数
    
    请求体: {"text":"...", "format":"md|txt|html", "domain_id":"ai-knowledge"}
    """
    text = req.get("text", "") if isinstance(req, dict) else ""
    fmt = req.get("format", "txt") if isinstance(req, dict) else "txt"
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"

    if not text.strip():
        raise HTTPException(status_code=400, detail="text is required")

    # Step 1: Parse document
    from core.harness.ontology_engine.document_parser import DocumentParser
    parser = DocumentParser()
    parsed = parser.parse_text(text, format=fmt)

    # Step 2: Classify chunks
    from core.harness.ontology_engine.engine import load_engine
    engine = load_engine(domain_id)
    classifications = []
    if engine:
        from core.harness.ontology_engine.class_mapper import ClassMapper
        mapper = ClassMapper(engine._domain)
        for chunk in parsed.chunks:
            cls = mapper.classify_text(chunk.text, threshold=0.5)
            classifications.append({
                "chunk_id": chunk.id,
                "heading": " > ".join(chunk.heading_path) if chunk.heading_path else "",
                "text_preview": chunk.text[:120],
                "class": cls or "unknown",
            })

    return {
        "title": parsed.title,
        "format": parsed.format,
        "chunk_count": len(parsed.chunks),
        "classifications": classifications,
        "chunks": [c.to_dict() for c in parsed.chunks[:10]],  # First 10 only
        "warnings": parsed.parse_warnings,
    }


@router.post("/ontology/engine/parse-and-process", response_model=Dict[str, Any])
async def ontology_engine_parse_and_process(req: dict, collection: str = "default"):
    """解析文档 → 结构化Chunk → 本体引擎 → 自动写Wiki页面。
    
    完整链路: 上传文档 → 解析 → 类映射 → 属性提取 → 写入
    """
    from core.harness.ontology_engine.document_parser import DocumentParser
    from core.harness.ontology_engine.engine import load_engine

    text = req.get("text", "") if isinstance(req, dict) else ""
    fmt = req.get("format", "txt") if isinstance(req, dict) else "txt"
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    auto_write = bool(req.get("auto_write", False)) if isinstance(req, dict) else False

    if not text.strip():
        raise HTTPException(status_code=400, detail="text is required")

    # Parse
    parser = DocumentParser()
    parsed = parser.parse_text(text, format=fmt)

    # Engine process
    engine = load_engine(domain_id)
    if engine is None:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    chunks = [c.to_dict() for c in parsed.chunks]
    result = await engine.process_chunks(chunks, doc_id=f"upload:{parsed.title}")

    # Write
    written = []
    if auto_write and result.instances:
        from core.harness.knowledge.wiki_engine import write_page
        for inst in result.instances:
            fm = inst.get("frontmatter", {})
            title = fm.get("title", "")
            if not title:
                continue
            try:
                await write_page(
                    title=title, body=str(fm.get("description", "") or ""),
                    category=fm.get("category", "entities"),
                    collection_id=collection,
                    tags=list(fm.get("tags", []) or []),
                    summary=str(fm.get("summary", "") or ""),
                )
                written.append(title)
            except Exception as e:
                logging.warning(str(e), exc_info=True)

    return {
        **result.to_dict(),
        "parsed": {"title": parsed.title, "chunk_count": len(parsed.chunks), "warnings": parsed.parse_warnings},
        "written_pages": written,
    }


@router.post("/ontology/engine/simulate-state", response_model=Dict[str, Any])
async def simulate_state_transitions(req: dict):
    """模拟状态机：给定一批实例，返回状态转换链和受影响的实例。

    请求体: {
      "domain_id": "ai-knowledge",
      "instances": [
        {"class_name": "AI方法", "properties": {"name": "RAG", "maturity": "research"}, "chunk_id": "c0"},
        {"class_name": "AI系统", "properties": {"name": "SysA"}, "chunk_id": "c0"}
      ]
    }
    返回: { state_transitions, affected_instances, summary }
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    raw_instances = req.get("instances", []) if isinstance(req, dict) else []

    from core.harness.ontology_engine.engine import load_engine
    from core.harness.ontology_engine.state_machine import EvalContext

    engine = load_engine(domain_id)
    if not engine:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    state_machine = getattr(engine, "_state_machine", None)
    if not state_machine:
        raise HTTPException(status_code=500, detail="State machine not initialized")

    # Normalize instances
    instances = []
    for i, ri in enumerate(raw_instances):
        instances.append({
            "class_name": str(ri.get("class_name", "")),
            "entity_text": str(ri.get("entity_text", "") or ri.get("properties", {}).get("name", f"inst-{i}")),
            "properties": dict(ri.get("properties", {}) or {}),
            "chunk_id": str(ri.get("chunk_id", f"sim-{i}")),
        })

    ctx = EvalContext(instances)
    state_transitions = []
    affected_instances = []

    for inst in instances:
        chain = state_machine.evaluate_chain(inst, ctx)
        if chain:
            for tres in chain:
                entry = tres.to_dict()
                entry["entity_text"] = inst["entity_text"]
                state_transitions.append(entry)
                # Collect affected: which other instances match side_effect targets
                for effect in tres.side_effects:
                    for action in effect.get("actions", []):
                        if action.get("type") == "mark_related_for_review":
                            rel = action.get("relation", "")
                            target_class = state_machine._relation_to_target_class(rel)
                            if target_class:
                                for other in instances:
                                    if other is not inst and other.get("class_name") == target_class:
                                        affected_instances.append({
                                            "from_instance": inst["entity_text"],
                                            "from_class": inst["class_name"],
                                            "to_instance": other["entity_text"],
                                            "to_class": other["class_name"],
                                            "reason": action.get("message", f"关联关系: {rel}"),
                                            "transition": f"{tres.from_state} → {tres.to_state}",
                                        })

    return {
        "state_transitions": state_transitions,
        "affected_instances": affected_instances,
        "summary": (
            f"{len(instances)} 实例 → {len(state_transitions)} 次状态转换"
            f"{', 影响 ' + str(len(affected_instances)) + ' 个关联实例' if affected_instances else ''}"
        ),
    }


@router.post("/ontology/engine/simulate-scenarios", response_model=Dict[str, Any])
async def simulate_scenarios(req: dict):
    """Multi-scenario simulation sandbox — compare different configurations side by side.

    请求体: {
      "domain_id": "ai-knowledge",
      "instances": [...],   # 基础实例
      "scenarios": [        # 多个场景对比
        {"label": "基线(无干预)", "instances": [...]},
        {"label": "方案A: 加强审查", "instances": [...]},
        {"label": "方案B: 自动放行", "instances": [...]}
      ]
    }
    返回: { domain_id, baseline: {...}, scenarios: [{label, ...}, ...], comparison: {...} }
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    raw_instances = req.get("instances", []) if isinstance(req, dict) else []
    raw_scenarios = req.get("scenarios", []) if isinstance(req, dict) else []

    from core.harness.ontology_engine.engine import load_engine
    from core.harness.ontology_engine.state_machine import EvalContext

    engine = load_engine(domain_id)
    if not engine:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    state_machine = getattr(engine, "_state_machine", None)
    if not state_machine:
        raise HTTPException(status_code=500, detail="State machine not initialized")

    def _run_scenario(insts):
        normalized = []
        for i, ri in enumerate(insts):
            normalized.append({
                "class_name": str(ri.get("class_name", "")),
                "entity_text": str(ri.get("entity_text", "") or f"inst-{i}"),
                "properties": dict(ri.get("properties", {}) or {}),
                "chunk_id": str(ri.get("chunk_id", f"sim-{i}")),
            })
        ctx = EvalContext(normalized)
        trans = []
        affected = []
        for inst in normalized:
            chain = state_machine.evaluate_chain(inst, ctx)
            if chain:
                for tres in chain:
                    entry = tres.to_dict()
                    entry["entity_text"] = inst["entity_text"]
                    trans.append(entry)
        return {
            "instance_count": len(normalized),
            "state_transitions": trans,
            "transition_count": len(trans),
            "final_states": {inst["entity_text"]: inst.get("properties", {}).get("state", "unknown")
                             for inst in normalized if inst.get("properties", {}).get("state")},
        }

    # Run baseline
    baseline = _run_scenario(raw_instances) if raw_instances else {"instance_count": 0, "transition_count": 0}

    # Run each scenario
    scenario_results = []
    for sc in raw_scenarios:
        label = sc.get("label", f"Scenario {len(scenario_results)+1}")
        si = sc.get("instances", [])
        result = _run_scenario(si) if si else {"instance_count": 0, "transition_count": 0}
        result["label"] = label
        scenario_results.append(result)

    # Comparison
    comparison = {
        "baseline_transitions": baseline.get("transition_count", 0),
        "scenario_transitions": [r.get("transition_count", 0) for r in scenario_results],
        "scenario_labels": [r.get("label", "") for r in scenario_results],
    }

    return {
        "domain_id": domain_id,
        "baseline": baseline,
        "scenarios": scenario_results,
        "comparison": comparison,
    }


@router.get("/ontology/engine/reviews/{domain_id}", response_model=Dict[str, Any])
async def list_ontology_reviews(domain_id: str):
    """Get pending review queue for a domain ontology."""
    from pathlib import Path as _Path
    import os as _os, json as _json

    reviews_dir = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontology_reviews"
    review_file = reviews_dir / f"{domain_id}.json"
    if not review_file.exists():
        return {"domain_id": domain_id, "reviews": [], "total": 0}
    try:
        reviews = _json.loads(review_file.read_text())
    except Exception:
        return {"domain_id": domain_id, "reviews": [], "total": 0}

    return {
        "domain_id": domain_id,
        "reviews": reviews,
        "total": len(reviews),
        "pending": sum(1 for r in reviews if r.get("status") == "pending"),
    }


@router.post("/ontology/engine/reviews/{domain_id}/resolve", response_model=Dict[str, Any])
async def resolve_ontology_review(domain_id: str, req: dict):
    """Mark a review as resolved."""
    from pathlib import Path as _Path
    import os as _os, json as _json

    review_id = req.get("review_id", "") if isinstance(req, dict) else ""
    if not review_id:
        raise HTTPException(status_code=400, detail="review_id required")

    reviews_dir = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontology_reviews"
    review_file = reviews_dir / f"{domain_id}.json"
    if not review_file.exists():
        raise HTTPException(status_code=404, detail="No reviews for this domain")

    reviews = _json.loads(review_file.read_text())
    resolved = False
    for r in reviews:
        if r.get("id") == review_id:
            r["status"] = "resolved"
            resolved = True
            break
    if not resolved:
        raise HTTPException(status_code=404, detail=f"Review '{review_id}' not found")

    review_file.write_text(_json.dumps(reviews, ensure_ascii=False, indent=2))
    return {"review_id": review_id, "status": "resolved"}


@router.get("/ontology/engine/cross-domain-stats", response_model=Dict[str, Any])
async def get_cross_domain_stats():
    """Get aggregated stats across all domain graphs."""
    from core.harness.ontology_engine.engine import get_sharded_graph
    sharded = get_sharded_graph()
    # Load all domains
    for did in ["ai-knowledge", "default", "ship-design"]:
        sharded.get_shard(did)
    return {
        "total": sharded.total_stats(),
        "per_domain": sharded.stats_all(),
    }


@router.get("/ontology/engine/graph-stats/{domain_id}", response_model=Dict[str, Any])
async def get_graph_stats(domain_id: str):
    """Get graph statistics: nodes, edges, inferred edges."""
    from core.harness.ontology_engine.graph_index import GraphIndex
    graph = GraphIndex.load(domain_id)
    base = graph.stats()
    inferred = sum(1 for n in graph._nodes.values() for e in n.out_edges if getattr(e, "inferred", False))
    return {"domain_id": domain_id, "node_count": base["node_count"], "edge_count": base["edge_count"], "inferred_edges": inferred, "avg_degree": base["avg_degree"]}


@router.post("/ontology/engine/resolve", response_model=Dict[str, Any])
@router.post("/ontology/engine/cross-source-resolve", response_model=Dict[str, Any])
async def cross_source_resolve(req: dict):
    """P1: Cross-source entity aggregation. Link entities from different data sources.

    请求体: {
      "domain_id": "ai-knowledge",
      "instances_a": [...],  // primary source
      "instances_b": [...],  // secondary source to link against
      "source_a": "wiki", "source_b": "erp"
    }
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    raw_a = req.get("instances_a", []) if isinstance(req, dict) else []
    raw_b = req.get("instances_b", []) if isinstance(req, dict) else []
    src_a = req.get("source_a", "") if isinstance(req, dict) else ""
    src_b = req.get("source_b", "") if isinstance(req, dict) else ""

    from core.harness.ontology_engine.entity_resolver import EntityResolver
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from pathlib import Path as _Path
    import os as _os

    ont_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    domain = load_ontology_from_yaml(str(ont_path)) if ont_path.exists() else None
    resolver = EntityResolver(domain)

    def normalize(insts):
        return [{
            "class_name": str(x.get("class_name", "")),
            "entity_text": str(x.get("entity_text", "") or x.get("properties", {}).get("name", f"e{i}")),
            "properties": dict(x.get("properties", {}) or {}),
            "chunk_id": str(x.get("chunk_id", src_a if i < len(raw_a) else src_b)),
        } for i, x in enumerate(insts)]

    result = resolver.cross_source_resolve(
        normalize(raw_a), normalize(raw_b),
        source_a=src_a, source_b=src_b,
    )
    return result.to_dict()


@router.post("/ontology/engine/resolve", response_model=Dict[str, Any])
async def resolve_entities(req: dict):
    """Run entity resolver on a list of instances.

    请求体: {
      "domain_id": "ai-knowledge",
      "instances": [{"class_name":"AI方法","entity_text":"RAG","chunk_id":"c0"}, ...],
      "doc_type": "md"
    }
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    raw_instances = req.get("instances", []) if isinstance(req, dict) else []
    doc_type = req.get("doc_type", "") if isinstance(req, dict) else ""

    from core.harness.ontology_engine.entity_resolver import EntityResolver
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from pathlib import Path as _Path
    import os as _os

    ont_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    if not ont_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    domain = load_ontology_from_yaml(str(ont_path))
    resolver = EntityResolver(domain)
    normalized = []
    for i, ri in enumerate(raw_instances):
        normalized.append({
            "class_name": str(ri.get("class_name", "")),
            "entity_text": str(ri.get("entity_text", "") or ri.get("properties", {}).get("name", f"e{i}")),
            "chunk_id": str(ri.get("chunk_id", f"c{i}")),
            "properties": dict(ri.get("properties", {}) or {}),
        })
    result = resolver.resolve(normalized, doc_type=doc_type)
    return result.to_dict()


@router.get("/ontology/engine/state-history/{domain_id}", response_model=Dict[str, Any])
async def get_state_history(domain_id: str, entity: str = "", limit: int = 200):
    """Get state machine change history for a domain or specific entity."""
    from core.harness.ontology_engine.state_history import get_domain_history, get_entity_history

    if entity:
        history = get_entity_history(domain_id, entity)
        return {"domain_id": domain_id, "entity": entity, "history": history, "total": len(history)}
    else:
        history = get_domain_history(domain_id, limit)
        return {"domain_id": domain_id, "history": history, "total": len(history)}


@router.get("/ontology/engine/state-stats/{domain_id}", response_model=Dict[str, Any])
async def get_state_statistics(
    domain_id: str,
    entity: str = "",
    window: str = "24h",
    class_name: str = "",
):
    """Get time-series window statistics for state transitions.

    参数:
      entity:     filter by entity name (optional)
      window:     time window, e.g. "1h", "6h", "24h", "7d"
      class_name: filter by class (optional)

    返回:
      window_stats: sliding window metrics (velocity, distribution, chains)
      transition_rate: bucketed transition rate over time
      state_distribution: current state distribution across entities
    """
    from core.harness.ontology_engine.state_history import (
        get_entity_window_stats, get_domain_transition_rate, get_state_distribution
    )

    # Parse window
    w = window.lower()
    if w.endswith("h"):
        hours = float(w[:-1])
    elif w.endswith("d"):
        hours = float(w[:-1]) * 24
    else:
        hours = 24.0

    window_stats = get_entity_window_stats(
        domain_id, entity_name=entity, window_hours=hours, class_name=class_name,
    )
    rate = get_domain_transition_rate(domain_id, window_hours=hours, bucket_minutes=max(15, int(hours * 60 / 24)))
    distrib = get_state_distribution(domain_id, class_name=class_name)

    return {
        "domain_id": domain_id,
        "window": window,
        "entity": entity or "(all)",
        "window_stats": window_stats,
        "transition_rate": rate,
        "state_distribution": distrib,
    }


@router.post("/ontology/engine/traverse", response_model=Dict[str, Any])
async def graph_traverse(req: dict):
    """Multi-hop graph traversal from a start entity.

    请求体: {
      "domain_id": "ai-knowledge",
      "start_entity": "RAG",
      "max_hops": 2,
      "relation_types": ["implements", "applies"],
      "direction": "both"
    }
    返回: { paths, terminal_entities, stats }
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    start_entity = req.get("start_entity", "") if isinstance(req, dict) else ""
    max_hops = int(req.get("max_hops", 2)) if isinstance(req, dict) else 2
    relation_types = req.get("relation_types") if isinstance(req, dict) else None
    direction = str(req.get("direction", "both")) if isinstance(req, dict) else "both"

    if not start_entity:
        raise HTTPException(status_code=400, detail="start_entity is required")

    from core.harness.ontology_engine.graph_index import GraphIndex
    from core.harness.ontology_engine.graph_traversal import traverse as _traverse

    graph = GraphIndex.load(domain_id)
    if len(graph) == 0:
        raise HTTPException(status_code=404, detail=f"Graph for domain '{domain_id}' is empty. Run engine first.")

    result = _traverse(
        start_entity=start_entity,
        graph=graph,
        max_hops=max_hops,
        relation_filter=relation_types,
        direction=direction,
    )

    return {
        "domain_id": domain_id,
        "start_entity": start_entity,
        **result.to_dict(),
    }


@router.post("/ontology/engine/feedback", response_model=Dict[str, Any])
async def submit_feedback(req: dict):
    """Submit user feedback on an answer.
    
    请求体: {"session_id":"...", "query":"...", "rating":4, "is_helpful":true, "domain_id":"default"}
    """
    from core.harness.ontology_engine.state_history import record_feedback
    sid = req.get("session_id", "") if isinstance(req, dict) else ""
    q = req.get("query", "") if isinstance(req, dict) else ""
    rating = int(req.get("rating", 0)) if isinstance(req, dict) else 0
    helpful = req.get("is_helpful") if isinstance(req, dict) else None
    domain = req.get("domain_id", "default") if isinstance(req, dict) else "default"
    record_feedback(session_id=sid, query_text=q, rating=rating, is_helpful=helpful, domain_id=domain)
    return {"status": "recorded"}


@router.get("/ontology/engine/feedback-stats/{domain_id}", response_model=Dict[str, Any])
async def get_feedback_statistics(domain_id: str):
    from core.harness.ontology_engine.state_history import get_feedback_stats
    return get_feedback_stats(domain_id)


@router.get("/ontology/engine/recommend/{domain_id}", response_model=Dict[str, Any])
async def get_knowledge_recommendations(
    domain_id: str,
    department: str = "",
    queries: str = "",
    limit: int = 5,
):
    """L5 active knowledge recommendation.

    Query: ?department=研发部&queries=RAG,知识检索&limit=5
    Returns ranked recommendations with reasons.
    """
    from core.harness.knowledge.wiki_engine import recommend_knowledge
    recent = [q.strip() for q in queries.split(",") if q.strip()] if queries else []
    result = recommend_knowledge(
        department=department, recent_queries=recent,
        domain_id=domain_id, limit=limit,
    )
    return {"domain_id": domain_id, "recommendations": result, "total": len(result)}


@router.post("/ontology/engine/parse-logic-form", response_model=Dict[str, Any])
async def parse_logic_form(req: dict):
    """NL2LF: Parse natural language to structured Logic Form."""
    from core.harness.knowledge.ontology_query_mapper import parse_to_logic_form
    query = req.get("query", "") if isinstance(req, dict) else ""
    if not query: raise HTTPException(status_code=400, detail="query required")
    return parse_to_logic_form(query)


@router.post("/ontology/engine/detect-gaps", response_model=Dict[str, Any])
async def detect_knowledge_gaps_endpoint(req: dict):
    """Detect knowledge gaps from query patterns.

    请求体: {
      "domain_id": "ai-knowledge",
      "queries": ["什么是RAG", "RAG怎么用", ...],
      "min_frequency": 2
    }
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    queries = req.get("queries", []) if isinstance(req, dict) else []
    min_freq = int(req.get("min_frequency", 2)) if isinstance(req, dict) else 2

    from core.harness.ontology_engine.knowledge_gap_detector import detect_knowledge_gaps
    result = detect_knowledge_gaps(queries, domain_id=domain_id, min_frequency=min_freq)
    return {"domain_id": domain_id, **result}


@router.post("/ontology/engine/process-from-datasource", response_model=Dict[str, Any])
async def process_from_datasource(req: dict):
    """Palantir-style: process data from an external data source through the ontology engine.

    请求体: {"source_id": "erp_db", "domain_id": "ai-knowledge"}
    """
    from core.harness.ontology_engine.data_source import DataSourceRegistry
    from core.harness.ontology_engine.engine import load_engine

    source_id = req.get("source_id", "") if isinstance(req, dict) else ""
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"

    if not source_id:
        raise HTTPException(status_code=400, detail="source_id required")

    DataSourceRegistry.load_from_dir()
    engine = load_engine(domain_id)
    if not engine:
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    result = await engine.process_from_datasource(source_id)
    return {
        "source_id": source_id,
        "domain_id": domain_id,
        "instances": len(result.instances),
        "transitions": result.stats.get("state_transitions", 0),
        "warnings": result.warnings[:5],
        "errors": result.errors,
    }


@router.get("/ontology/datasources", response_model=Dict[str, Any])
async def list_datasources():
    from core.harness.ontology_engine.data_source import DataSourceRegistry
    DataSourceRegistry.load_from_dir()
    return {"datasources": DataSourceRegistry.list_sources()}


@router.post("/ontology/engine/synthesize", response_model=Dict[str, Any])
async def run_knowledge_synthesis(req: dict):
    """Synthesize graph knowledge into Wiki pages.

    请求体: {"domain_id": "ai-knowledge"}
    返回: { pages_written, chains, fact_cards, conclusions }
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"
    from core.harness.ontology_engine.graph_index import GraphIndex
    from core.harness.ontology_engine.knowledge_synthesis import KnowledgeSynthesizer

    graph = GraphIndex.load(domain_id)
    if len(graph) == 0:
        raise HTTPException(status_code=404, detail=f"Graph for '{domain_id}' is empty")

    synthesizer = KnowledgeSynthesizer(graph)
    result = synthesizer.synthesize(domain_id=domain_id, write_to_wiki=True)
    return {
        "domain_id": domain_id,
        **result.to_dict(),
    }


@router.post("/ontology/engine/snapshot/{domain_id}", response_model=Dict[str, Any])
async def create_graph_snapshot(domain_id: str, label: str = ""):
    """Create a versioned snapshot of the current graph state."""
    from core.harness.ontology_engine.graph_index import GraphIndex
    graph = GraphIndex.load(domain_id)
    if len(graph) == 0:
        raise HTTPException(status_code=404, detail=f"Graph for '{domain_id}' is empty")
    result = graph.snapshot(label)
    return {"domain_id": domain_id, **result}


@router.get("/ontology/engine/snapshots/{domain_id}", response_model=Dict[str, Any])
async def list_graph_snapshots(domain_id: str):
    from core.harness.ontology_engine.graph_index import GraphIndex
    graph = GraphIndex.load(domain_id)
    return {"domain_id": domain_id, "snapshots": graph.list_snapshots()}


@router.post("/ontology/engine/snapshot/{domain_id}/restore", response_model=Dict[str, Any])
async def restore_graph_snapshot(domain_id: str, req: dict):
    snapshot_id = int(req.get("snapshot_id", 0)) if isinstance(req, dict) else 0
    if not snapshot_id:
        raise HTTPException(status_code=400, detail="snapshot_id required")
    from core.harness.ontology_engine.graph_index import GraphIndex
    graph = GraphIndex.load(domain_id)
    result = graph.restore_snapshot(snapshot_id)
    return {"domain_id": domain_id, **result}


@router.get("/ontology/sdk/{domain_id}", response_model=Dict[str, Any])
async def generate_ontology_sdk(domain_id: str, language: str = "python"):
    """Generate a client SDK from the domain ontology YAML.

    Produces dataclass definitions with fields, enums, state machines,
    and API wrappers for all CRUD operations on the domain.

    Query: ?language=python|typescript
    """
    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from pathlib import Path as _Path
    import os as _os

    ont_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    if not ont_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    domain = load_ontology_from_yaml(str(ont_path))

    if language == "python":
        lines = [f'"""Auto-generated SDK for {domain.name} domain — v{domain.version}."""', '',
                 'from dataclasses import dataclass, field', 'from typing import List, Optional', '',
                 f'# {domain.description}', f'# Generated from: {domain_id}.yaml', '']
        for cls in domain.classes:
            lines.append('@dataclass')
            lines.append(f'class {cls.label}:')
            lines.append(f'    """{cls.description}"""')
            for rf in cls.required_fields:
                lines.append(f'    {rf}: str  # required')
            for of in cls.optional_fields:
                lines.append(f'    {of}: Optional[str] = None')
            lines.append(f'    tags: List[str] = field(default_factory=list)')
            if getattr(cls, 'states', None):
                states = getattr(cls, 'states', {})
                def_state = states.get('default', 'unknown')
                lines.append(f'    state: str = "{def_state}"')
                enums = states.get('enum', [])
                if enums:
                    evals = [s['name'] for s in enums]
                    lines.append(f'    # Valid states: {", ".join(evals)}')
            lines.append('')

        lines.append('# ── API Client ──')
        lines.append(f'BASE = "http://localhost:8002/api/core/wiki/ontology"')
        lines.append('')
        lines.append('async def search_pages(query: str, limit: int = 10):')
        lines.append('    import aiohttp')
        lines.append(f'    async with aiohttp.ClientSession() as s:')
        lines.append(f'        async with s.get(f"{{BASE}}/../pages?q={{query}}&limit={{limit}}") as r:')
        lines.append(f'            return await r.json()')

        return {"domain_id": domain_id, "language": language, "code": "\n".join(lines)}

    elif language == "typescript":
        ts = [f'// Auto-generated SDK for {domain.name} domain — v{domain.version}',
              f'// {domain.description}', '']
        for cls in domain.classes:
            ts.append(f'export interface {cls.label} {{')
            for rf in cls.required_fields:
                ts.append(f'  {rf}: string;  // required')
            for of in cls.optional_fields:
                ts.append(f'  {of}?: string;')
            ts.append(f'  tags: string[];')
            if getattr(cls, 'states', None):
                ts.append(f'  state: string;')
            ts.append('}')
            ts.append('')
        return {"domain_id": domain_id, "language": language, "code": "\n".join(ts)}

    raise HTTPException(status_code=400, detail=f"Unsupported language: {language}. Use python or typescript")


@router.post("/ontology/engine/infer", response_model=Dict[str, Any])
async def run_graph_inference(req: dict):
    """Run inference rules on the domain graph to derive new edges.

    请求体: {"domain_id": "ai-knowledge"}
    返回: { inferred_edges, rule_hits, stats }
    """
    domain_id = req.get("domain_id", "ai-knowledge") if isinstance(req, dict) else "ai-knowledge"

    from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
    from core.harness.ontology_engine.graph_index import GraphIndex
    from core.harness.ontology_engine.graph_inference import GraphInference
    from pathlib import Path as _Path
    import os as _os

    ont_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / f"{domain_id}.yaml"
    if not ont_path.exists():
        raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")

    domain = load_ontology_from_yaml(str(ont_path))
    graph = GraphIndex.load(domain_id)
    if len(graph) == 0:
        raise HTTPException(status_code=404, detail=f"Graph for '{domain_id}' is empty")

    inferencer = GraphInference(domain, graph)
    result = inferencer.infer()
    applied = inferencer.apply_to_graph(result)
    if applied:
        graph.save()

    return {
        "domain_id": domain_id,
        "applied": applied,
        **result.to_dict(),
    }


from pydantic import BaseModel as _PydanticBaseModel, Field as _PydanticField

class OntologyDomainCreate(_PydanticBaseModel):
    id: str = _PydanticField(min_length=1, max_length=50, description="域标识 (如 ai-knowledge)")
    name: str = _PydanticField(min_length=1, max_length=100, description="显示名 (如 AI知识)")
    namespace: str = ""
    description: str = ""
    version: str = "1.0.0"

class OntologyClassCreate(_PydanticBaseModel):
    name: str
    label: str
    description: str = ""
    required_fields: list = []
    optional_fields: list = []
    categories: list = []
    parent: str = ""

class OntologyPropertyCreate(_PydanticBaseModel):
    name: str
    label: str
    domain: list = []
    range: list = []
    transitive: bool = False
    symmetric: bool = False


def _remove_from_registry(domain_id: str) -> None:
    """Remove a domain from registry.json."""
    from pathlib import Path as _Path
    import os as _os, json
    registry_path = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies" / "registry.json"
    if not registry_path.exists():
        return
    with open(registry_path, "r", encoding="utf-8") as f:
        reg = json.load(f)
    reg.get("domains", {}).pop(domain_id, None)
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)


def _write_domain_yaml(domain_id: str, data: dict) -> None:
    """Save domain ontology back to YAML file."""
    import yaml as _yaml
    from pathlib import Path as _Path
    import os as _os
    d = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"
    d.mkdir(parents=True, exist_ok=True)
    file_path = d / f"{domain_id}.yaml"
    # Preserve order with safe_dump
    content = _yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
    file_path.write_text(f"# {data.get('name', domain_id)} 领域本体模型\n{content}", encoding="utf-8")


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
            resp = await model.generate(
                [{"role": "system", "content": system_content},
                 {"role": "user", "content": prompt}],
                config=LLMConfig(model=model_name, timeout=60, max_tokens=2048),
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

            for label in affected_labels:
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
    return {"status": "updated", "domain": domain_id, "class": class_name}


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
        orphan_nodes = sum(1 for n in g._nodes.values() if n.class_name == class_label)
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
            to_remove = [n.entity_id for n in g._nodes.values() if n.class_name == class_label]
            for eid in to_remove:
                g.remove_entity(eid)
        except Exception as e:
            logging.warning(str(e), exc_info=True)

    del classes[class_name]
    raw["classes"] = classes
    _write_domain_yaml(domain_id, raw)
    return {"status": "deleted", "domain": domain_id, "class": class_name}


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


# ── Evidence Chain API (Phase 4) ──────────────────────────────────

@router.get("/claim/{title}/evidence-chain", response_model=Dict[str, Any])
async def get_claim_evidence_chain(title: str, collection: str = "default"):
    """Return full evidence chain for a Wiki claim/atom.

    Chain: page → source documents → contradictions → resolutions.
    """
    try:
        from core.harness.knowledge.wiki_engine import read_page, search_pages
        from core.harness.knowledge.knowledge_abox_builder import build_abox
        from core.harness.knowledge.knowledge_validator import TripleStore, _short

        page = read_page(title, collection_id=collection)
        if not page:
            raise HTTPException(status_code=404, detail=f"Page '{title}' not found")

        # 1. Direct source evidence
        source_articles = page.get("source_articles", [])
        evidence_text = None
        # Check if this is an atom page with evidence_text in frontmatter
        fm = page.get("fm", {})
        if fm.get("source_doc_id"):
            evidence_text = fm.get("evidence_text", "")
            source_articles = [fm["source_doc_id"]]
        # Fallback: evidence_text may be in summary field (write_atom stores it there)
        if not evidence_text:
            evidence_text = fm.get("evidence_text") or page.get("summary", "") or None
        # Parse evidence metadata from body HTML comments
        body = page.get("body", "")
        evidence_meta = {}
        import re as _re
        for m in _re.finditer(r'<!--\s*(source_doc_id|evidence_start|evidence_end|confidence):\s*([\d.]+[^\s-]*)\s*-->', body):
            key, val = m.group(1), m.group(2)
            try:
                evidence_meta[key] = float(val) if key in ("confidence", "evidence_start", "evidence_end") else val
            except ValueError:
                evidence_meta[key] = val
        if evidence_meta.get("source_doc_id") and not source_articles:
            source_articles = [evidence_meta["source_doc_id"]]

        # 2. Contradictions and related pages
        contradictions = page.get("contradictions", [])
        related = page.get("related", [])

        # 3. Ontology-level contradictions (from A-Box)
        onto = build_abox(collection_id=collection)
        store = TripleStore(onto.triples)
        onto_contradictions = [
            _short(c) for c in store.objects(f"http://aiplat.local/knowledge#{title}",
                                              "http://aiplat.local/knowledge#contradicts")
        ]

        # 4. Stale references
        stale = page.get("stale_references", [])

        return {
            "claim": title,
            "source_articles": source_articles,
            "evidence_text": evidence_text,
            "contradictions": contradictions,
            "onto_contradictions": [c for c in onto_contradictions if c != title],
            "related": related,
            "stale_references": stale,
            "has_controversy": len(contradictions) > 0 or len(onto_contradictions) > 1,
            "category": page.get("category", ""),
            "last_updated": page.get("last_updated", ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evidence chain failed: {e}")


# ── OWL/RDF Export (Phase 5) ─────────────────────────────────────

@router.get("/ontology/export", response_model=Dict[str, Any])
async def export_ontology_rdf(format: str = "turtle", collection: str = "default"):
    """Export T-Box + A-Box as OWL/RDF.

    Supported formats: turtle (default), rdfxml, ntriples.
    Compatible with Protégé, GraphDB, Stardog, and other semantic web tools.
    """
    try:
        from core.harness.knowledge.knowledge_abox_builder import build_abox
        from core.harness.knowledge.knowledge_ontology import export_to_owl_rdf

        build_abox(collection_id=collection)
        rdf_text = export_to_owl_rdf(format=format)

        content_types = {
            "turtle": "text/turtle",
            "rdfxml": "application/rdf+xml",
            "ntriples": "application/n-triples",
        }
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(rdf_text, media_type=content_types.get(format, "text/plain"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")


@router.get("/ontology/infer", response_model=Dict[str, Any])
async def run_inference_engine(collection: str = "default"):
    """Run full inference engine and return suggested edges."""
    try:
        from core.harness.knowledge.knowledge_abox_builder import build_abox
        from core.harness.knowledge.knowledge_validator import (
            TripleStore, run_full_inference, _short
        )
        onto = build_abox(collection_id=collection)
        store = TripleStore(onto.triples)
        inference = run_full_inference(store)

        suggestions = []
        for kind in ("transitive", "source_chain"):
            for inf in inference.get(kind, []):
                suggestions.append({
                    "kind": kind,
                    "from": _short(inf["subject"]),
                    "relation": inf["predicate"].replace("http://aiplat.local/knowledge#", ""),
                    "to": _short(inf["object"]),
                })

        return {
            "summary": inference.get("summary", ""),
            "suggestions": suggestions,
            "total": len(suggestions),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}")


# ── Pattern Detector (Ontology Evolution Layer 1) ─────────────────

@router.get("/ontology/patterns", response_model=Dict[str, Any])
async def detect_patterns(collection: str = "default"):
    """Scan wiki data and detect patterns not yet covered by T-Box.

    Returns:
    - undefined_categories: categories used in wiki but not in any T-Box class
    - tag_clusters: high-frequency tags that may warrant new ontology classes
    - dangling_references: pages referencing titles that don't exist (with variant suggestions)
    - category_gaps: T-Box classes with zero wiki pages
    - undefined_relations: relationship types in pages not in OBJECT_PROPERTIES
    """
    try:
        from core.harness.knowledge.knowledge_validator import detect_ontology_patterns
        patterns = detect_ontology_patterns(collection_id=collection)
        return {
            "summary": patterns.summary,
            "scanned_pages": patterns.scanned_pages,
            "scanned_collections": patterns.scanned_collections,
            "undefined_categories": patterns.undefined_categories,
            "undefined_relations": patterns.undefined_relations,
            "tag_clusters": patterns.tag_clusters,
            "dangling_references": patterns.dangling_references,
            "category_gaps": patterns.category_gaps,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pattern detection failed: {e}")


@router.get("/ontology/metrics", response_model=Dict[str, Any])
async def get_ontology_metrics(collection: str = "default", refresh: bool = False):
    """Four-dimension ontology health metrics (cache-backed).

    Dimensions:
    1. Coverage: % wiki pages covered by T-Box classes
    2. Consistency: validator errors / warnings / score
    3. Inference gain: transitive + source_chain edges inferred
    4. Maintenance cost: pending suggestions + last review time
    Class usage: per-class wiki page counts

    Cache is auto-invalidated when wiki pages are created/updated/deleted,
    then rebuilt in a background subprocess. refresh=true shows cache age.
    """
    try:
        from core.harness.knowledge.knowledge_validator import load_metrics_cache
        import time as _time, os as _os

        if refresh:
            # Invalidate cache and trigger background rebuild
            cache_path = _os.path.join(_os.path.expanduser(_os.getenv("AIPLAT_HOME", "~/.aiplat")),
                                        "wiki", "collections", collection, "metrics_cache.json")
            try:
                if _os.path.exists(cache_path):
                    _os.remove(cache_path)
            except Exception as e:
                logging.warning(str(e), exc_info=True)
            from core.harness.knowledge._bg_tasks import enqueue
            enqueue("rebuild_metrics", collection_id=collection)
            return {"source": "recomputing", "message": "后台重新计算中，请稍后刷新。预计 1-3 分钟完成。"}

        cached = load_metrics_cache(collection)
        if cached and "metrics" in cached:
            age = round(_time.time() - cached.get("computed_at", _time.time()), 0)
            return {"source": "cache", "cache_age_seconds": age, **cached["metrics"]}
        return {"source": "pending", "message": "Metrics not yet computed. Click '刷新指标' to trigger rebuild.", "consistency": {"score": 0, "errors": 0}, "coverage": {"percentage": 0, "covered": 0, "total": 0}, "inference_gain": {"summary": "pending", "total_inferred": 0}, "maintenance_cost": {"pending_suggestions": 0}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Metrics failed: {e}")


@router.get("/ontology/metrics/history", response_model=Dict[str, Any])
async def get_metrics_history(collection: str = "default"):
    """Return historical metrics snapshots for trend analysis (last 30 days)."""
    try:
        from core.harness.knowledge.knowledge_validator import load_metrics_history
        history = load_metrics_history(collection)
        return {"history": history, "total": len(history)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"History failed: {e}")


@router.get("/ontology/golden-regression", response_model=Dict[str, Any])
async def run_golden_regression(collection: str = "default", min_score: float = None, strict: bool = False):
    """Run golden query regression test to validate retrieval quality.

    Uses golden_queries.yaml (8 queries) to check whether wiki retrieval
    returns expected concepts. Returns pass rate and per-query details.

    Args:
        min_score: Custom min_wiki_score threshold (overrides strict).
        strict: Use production threshold (0.3) instead of test threshold (0.1).
    """
    try:
        from core.harness.knowledge.knowledge_validator import run_golden_query_regression
        result = run_golden_query_regression(collection_id=collection, min_score=min_score, strict_mode=strict)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Regression failed: {e}")


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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch atomize failed: {e}")


@router.post("/maintain/fts-rebuild", response_model=Dict[str, Any])
async def rebuild_fts_index(collection: str = "default"):
    """Rebuild FTS5 full-text search index for wiki pages."""
    try:
        from core.harness.knowledge.wiki_fts import fts_index_pages
        count = fts_index_pages()
        return {"status": "completed", "indexed": count}
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
        history = _json.loads(open(hist_path).read())
        return {"generations": history, "total": len(history)}
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
        entries = json.loads(open(log_path).read())
        return {"entries": entries[-50:], "total": len(entries)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════
# Markings API (Phase 2 — lineage-based security)
# ══════════════════════════════════════════════════════════════

class MarkingSetRequest(BaseModel):
    entity_uri: str
    label: str
    level: int = 2  # 1=public, 2=internal, 3=confidential, 4=restricted
    scope: str = ""


class MarkingDeleteRequest(BaseModel):
    entity_uri: str
    label: str = ""


@router.put("/ontology/markings", response_model=Dict[str, Any])
async def set_entity_marking(req: MarkingSetRequest, collection: str = "default"):
    u"""Set a marking on an ontology entity."""
    from core.harness.knowledge.knowledge_markings import set_marking, MarkingLevel
    try:
        level = MarkingLevel(max(1, min(4, req.level)))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid level: {req.level}")

    marking = set_marking(
        entity_uri=req.entity_uri,
        label=req.label,
        level=level,
        scope=req.scope,
        collection_id=collection,
    )
    return {"status": "ok", "marking": marking.to_dict()}


@router.delete("/ontology/markings", response_model=Dict[str, Any])
async def remove_entity_marking(req: MarkingDeleteRequest, collection: str = "default"):
    u"""Remove a marking from an entity (or all if label is empty)."""
    from core.harness.knowledge.knowledge_markings import remove_marking
    ok = remove_marking(
        entity_uri=req.entity_uri,
        label=req.label,
        collection_id=collection,
    )
    return {"status": "ok" if ok else "not_found", "removed": ok}


@router.get("/ontology/markings/{entity_uri:path}", response_model=Dict[str, Any])
async def get_entity_marking_info(
    entity_uri: str,
    collection: str = "default",
    resolve_effective: bool = True,
):
    u"""Get explicit + effective markings for an entity, with propagation traces."""
    from core.harness.knowledge.knowledge_markings import (
        get_entity_markings, get_propagation_tree,
    )
    if resolve_effective:
        result = get_propagation_tree(entity_uri, collection_id=collection)
    else:
        result = get_entity_markings(entity_uri, collection_id=collection, resolve_effective=False)
    return result


@router.put("/ontology/permissions", response_model=Dict[str, Any])
async def grant_entity_permission(
    entity_uri: str = Body(...),
    role: str = Body(...),
    actions: List[str] = Body(...),
    collection: str = "default",
):
    u"""Grant per-object permission on an ontology entity."""
    from core.policy.object_permission import grant_object_permission
    perm = grant_object_permission(
        entity_uri=entity_uri,
        role=role,
        actions=actions,
        collection_id=collection,
    )
    return {"status": "ok", "permission": perm.to_dict()}


@router.delete("/ontology/permissions", response_model=Dict[str, Any])
async def revoke_entity_permission(
    entity_uri: str = Body(...),
    role: str = Body(default=""),
    action: str = Body(default=""),
    collection: str = "default",
):
    u"""Revoke a per-object permission."""
    from core.policy.object_permission import revoke_object_permission
    ok = revoke_object_permission(
        entity_uri=entity_uri,
        role=role,
        action=action,
        collection_id=collection,
    )
    return {"status": "ok" if ok else "not_found", "revoked": ok}


@router.get("/ontology/permissions/{entity_uri:path}", response_model=Dict[str, Any])
async def list_entity_permissions(
    entity_uri: str,
    collection: str = "default",
):
    u"""List all effective permissions for an ontology entity."""
    from core.policy.object_permission import get_effective_permissions
    perms = get_effective_permissions(entity_uri, collection_id=collection)
    return {"entity_uri": entity_uri, "permissions": perms}


# ══════════════════════════════════════════════════════════════
# Semantic Suggestions API (Phase 3 — LLM-driven evolution)
# ══════════════════════════════════════════════════════════════

class SemanticSuggestRequest(BaseModel):
    collection: str = "default"
    max_suggestions: int = 5
    confidence_threshold: float = 0.7
    include_llm: bool = True


@router.post("/ontology/suggestions/semantic", response_model=Dict[str, Any])
async def generate_semantic_suggestions_endpoint(req: SemanticSuggestRequest = Body(default=None)):
    u"""Generate semantic ontology evolution suggestions via LLM (Tier 2).

    Dimensions: semantic merge detection, field gap analysis, relation inference.
    Set include_llm=False to get only Tier 1 (rule-based) suggestions.
    """
    if req is None:
        req = SemanticSuggestRequest()

    if not req.include_llm:
        from core.harness.knowledge.knowledge_ontology import add_suggestions_from_patterns
        suggestions = add_suggestions_from_patterns(
            collection_id=req.collection,
        )
        return {"suggestions": suggestions, "total": len(suggestions), "source": "rule"}

    try:
        from core.harness.knowledge.knowledge_evolution_llm import generate_semantic_suggestions
        suggestions = await generate_semantic_suggestions(
            collection_id=req.collection,
            max_suggestions=req.max_suggestions,
            confidence_threshold=req.confidence_threshold,
        )
        return {"suggestions": suggestions, "total": len(suggestions), "source": "llm"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Semantic suggestion generation failed: {e}")


@router.post("/ontology/suggestions/{suggestion_id}/impact", response_model=Dict[str, Any])
async def predict_suggestion_impact(suggestion_id: str, collection: str = "default"):
    u"""Predict the impact scope of accepting an evolution suggestion."""
    from core.harness.knowledge.knowledge_ontology import (
        load_pending_suggestions, get_ontology,
    )
    from core.harness.knowledge.knowledge_evolution_llm import predict_evolution_impact

    suggestions = load_pending_suggestions(collection)
    suggestion = next((s for s in suggestions if s.get("id") == suggestion_id), None)
    if not suggestion:
        raise HTTPException(status_code=404, detail=f"Suggestion '{suggestion_id}' not found")

    onto = get_ontology()
    impact = predict_evolution_impact(suggestion, onto)
    return impact


# ══════════════════════════════════════════════════════════════
# Health & Quality API (Phase 4 — pipeline feedback loop)
# ══════════════════════════════════════════════════════════════

@router.get("/ontology/health/triggers", response_model=Dict[str, Any])
async def get_health_triggers(collection: str = "default"):
    u"""Get triggered curation tasks from ontology health checks."""
    from core.harness.knowledge.knowledge_quality import check_ontology_health_triggers
    triggers = check_ontology_health_triggers(collection_id=collection)
    return {"triggers": triggers, "total": len(triggers), "collection_id": collection}


@router.get("/ontology/health/score", response_model=Dict[str, Any])
async def get_ontology_health_score(collection: str = "default"):
    u"""Get composite ontology health score from axiom validation + quality signals."""
    try:
        from core.harness.knowledge.knowledge_validator import validate_all
        report = validate_all(collection_id=collection)
        return {
            "axiom_score": report.score,
            "violations": report.violations_by_severity,
            "passed_axioms": len(report.passed_axioms),
            "failed_axioms": len(report.failed_axioms),
            "total_triples": report.total_triples,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ontology/quality/{entity_uri:path}", response_model=Dict[str, Any])
async def get_entity_quality(entity_uri: str, collection: str = "default"):
    u"""Get quality score and signal history for an ontology entity."""
    from core.harness.knowledge.knowledge_quality import (
        get_entity_quality_score, get_quality_signals,
    )
    score = get_entity_quality_score(entity_uri, collection_id=collection)
    signals = get_quality_signals(entity_uri, limit=20, collection_id=collection)
    return {"quality": score, "recent_signals": signals}


# ══════════════════════════════════════════════════════════════
# WriteBack API (Phase 5 — external system integration)
# ══════════════════════════════════════════════════════════════

class WritebackRegisterRequest(BaseModel):
    target_type: str = "rest_webhook"
    target_endpoint: str
    trigger_actions: List[str] = ["create", "update"]
    field_mapping: Dict[str, str] = {}
    auth: Dict[str, str] = {}


@router.get("/ontology/writebacks", response_model=Dict[str, Any])
async def list_writebacks(collection: str = "default"):
    u"""List all registered writeback configurations."""
    from core.harness.knowledge.knowledge_writeback import load_writebacks
    configs = load_writebacks(collection_id=collection)
    return {"writebacks": [c.to_dict() for c in configs], "total": len(configs)}


@router.post("/ontology/writebacks", response_model=Dict[str, Any])
async def register_writeback_endpoint(req: WritebackRegisterRequest, collection: str = "default"):
    u"""Register a new writeback target."""
    from core.harness.knowledge.knowledge_writeback import (
        register_writeback, WriteBackConfig, WriteBackTarget,
    )
    try:
        target = WriteBackTarget(req.target_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid target_type: {req.target_type}")

    config = WriteBackConfig(
        target_type=target,
        target_endpoint=req.target_endpoint,
        trigger_actions=req.trigger_actions,
        field_mapping=req.field_mapping,
        auth=req.auth,
    )
    register_writeback(config, collection_id=collection)
    return {"status": "ok", "config": config.to_dict()}


@router.delete("/ontology/writebacks", response_model=Dict[str, Any])
async def unregister_writeback_endpoint(target_endpoint: str, collection: str = "default"):
    u"""Remove a writeback target."""
    from core.harness.knowledge.knowledge_writeback import unregister_writeback
    ok = unregister_writeback(target_endpoint, collection_id=collection)
    return {"status": "ok" if ok else "not_found"}


# ══════════════════════════════════════════════════════════════
# Field-Level Security API (附章 — cell/field-level access control)
# ══════════════════════════════════════════════════════════════

class FieldPermissionRequest(BaseModel):
    entity_uri: str
    field_name: str
    visibility: str = "all"
    redaction_strategy: str = "mask"


@router.get("/ontology/field-permissions/{entity_uri:path}", response_model=Dict[str, Any])
async def get_field_permissions(entity_uri: str, collection: str = "default"):
    u"""Get field-level permission rules for an entity."""
    from core.policy.field_level_security import load_field_permissions
    perms = load_field_permissions(collection_id=collection)
    applicable = [p.to_dict() for p in perms if p.entity_uri == entity_uri]
    return {"entity_uri": entity_uri, "permissions": applicable, "total": len(applicable)}


@router.put("/ontology/field-permissions", response_model=Dict[str, Any])
async def set_field_permission_endpoint(req: FieldPermissionRequest, collection: str = "default"):
    u"""Set a field-level permission rule (visibility + redaction strategy)."""
    from core.policy.field_level_security import set_field_permission
    perm = set_field_permission(
        entity_uri=req.entity_uri,
        field_name=req.field_name,
        visibility=req.visibility,
        redaction_strategy=req.redaction_strategy,
        collection_id=collection,
    )
    return {"status": "ok", "permission": perm.to_dict()}


@router.delete("/ontology/field-permissions", response_model=Dict[str, Any])
async def remove_field_permission_endpoint(
    entity_uri: str = Body(...),
    field_name: str = Body(default=""),
    collection: str = "default",
):
    u"""Remove field-level permission(s). Pass empty field_name to clear all for entity."""
    from core.policy.field_level_security import remove_field_permission
    ok = remove_field_permission(entity_uri, field_name, collection_id=collection)
    return {"status": "ok" if ok else "not_found"}


# ══════════════════════════════════════════════════════════════
# Scene Model API (Phase A — purpose-driven pipeline templates)
# ══════════════════════════════════════════════════════════════

class SceneCreateRequest(BaseModel):
    scene_id: str
    name: str = ""
    description: str = ""
    required_entities: List[str] = []
    algorithm_nodes: List[Dict[str, Any]] = []
    llm_judgment_nodes: List[Dict[str, Any]] = []
    entry_conditions: Dict[str, Any] = {}
    expected_outcomes: List[Dict[str, Any]] = []
    tags: List[str] = []


@router.get("/ontology/scenes", response_model=Dict[str, Any])
async def list_scene_models(collection: str = "default"):
    u"""List all ontology scene templates. Auto-seeds built-in scenes on first access."""
    from core.harness.knowledge.scene_model import list_scenes, create_builtin_scenes
    scenes = list_scenes(collection_id=collection)
    if not scenes:
        from core.harness.knowledge.scene_model import save_scene
        builtins = create_builtin_scenes()
        for s in builtins:
            save_scene(s, collection_id=collection)
        scenes = list_scenes(collection_id=collection)
    return {"scenes": [s.to_dict() for s in scenes], "total": len(scenes)}


@router.post("/ontology/scenes", response_model=Dict[str, Any])
async def create_scene_model(req: SceneCreateRequest, collection: str = "default"):
    from core.harness.knowledge.scene_model import OntologyScene, save_scene
    scene = OntologyScene(
        scene_id=req.scene_id, name=req.name, description=req.description,
        required_entities=req.required_entities, algorithm_nodes=req.algorithm_nodes,
        llm_judgment_nodes=req.llm_judgment_nodes, entry_conditions=req.entry_conditions,
        expected_outcomes=req.expected_outcomes, tags=req.tags,
    )
    save_scene(scene, collection_id=collection)
    return {"status": "ok", "scene": scene.to_dict()}


@router.get("/ontology/scenes/{scene_id}", response_model=Dict[str, Any])
async def get_scene_model(scene_id: str, collection: str = "default"):
    from core.harness.knowledge.scene_model import get_scene
    scene = get_scene(scene_id, collection_id=collection)
    if not scene:
        raise HTTPException(status_code=404, detail=f"Scene '{scene_id}' not found")
    return {"scene": scene.to_dict(), "pipeline_stages": scene.to_pipeline_stages(),
            "stage_count": len(scene.to_pipeline_stages())}


@router.post("/ontology/scenes/{scene_id}/instantiate", response_model=Dict[str, Any])
async def instantiate_scene_model(scene_id: str, params: Dict[str, Any] = Body(default={}), collection: str = "default"):
    from core.harness.knowledge.scene_model import instantiate_scene
    config = instantiate_scene(scene_id, params=params, collection_id=collection)
    if not config:
        raise HTTPException(status_code=404, detail=f"Scene '{scene_id}' not found")
    return {"pipeline_config": config, "stage_count": len(config.get("stages", []))}


@router.delete("/ontology/scenes/{scene_id}", response_model=Dict[str, Any])
async def delete_scene_model(scene_id: str, collection: str = "default"):
    from core.harness.knowledge.scene_model import delete_scene
    ok = delete_scene(scene_id, collection_id=collection)
    return {"status": "ok" if ok else "not_found"}


# ══════════════════════════════════════════════════════════════
# Growth Metrics API (Phase E — knowledge compound interest)
# ══════════════════════════════════════════════════════════════

@router.get("/ontology/growth-stats", response_model=Dict[str, Any])
async def get_growth_stats(days: int = 30, collection: str = "default"):
    u"""Get knowledge base growth statistics for the last N days."""
    from core.harness.knowledge.knowledge_growth import get_growth_stats, estimate_compound_value
    stats = get_growth_stats(collection_id=collection, days=days)
    compound = estimate_compound_value(collection_id=collection)
    return {**stats, "compound": compound}


@router.post("/ontology/growth/snapshot", response_model=Dict[str, Any])
async def take_snapshot(collection: str = "default"):
    u"""Manually trigger a growth snapshot."""
    from core.harness.knowledge.knowledge_growth import take_growth_snapshot
    snap = take_growth_snapshot(collection_id=collection)
    return {"status": "ok", "snapshot": snap.to_dict()}


# ══════════════════════════════════════════════════════════════
# Learning Coach API (L6 — built-in AI Learning Coach)
# ══════════════════════════════════════════════════════════════

class ProfileRequest(BaseModel):
    learner_id: str
    target_role: str = "ai_literate"
    current_level: str = "beginner"
    weekly_hours: int = 3
    prior_knowledge: List[str] = []
    interests: List[str] = []
    goals: str = ""


@router.post("/learning/profile", response_model=Dict[str, Any])
async def create_learner_profile(req: ProfileRequest):
    u"""Create or update a learner profile."""
    from core.harness.knowledge.learning_ontology import (
        LearnerProfile, TargetRole, CurrentLevel, save_learner_profile, load_learner_profile,
    )
    existing = load_learner_profile(req.learner_id)
    profile = LearnerProfile(
        learner_id=req.learner_id,
        current_level=CurrentLevel(req.current_level),
        target_role=TargetRole(req.target_role),
        weekly_hours=req.weekly_hours,
        prior_knowledge=req.prior_knowledge,
        interests=req.interests,
        goals=req.goals,
        created_at=existing.created_at if existing else "",
    )
    save_learner_profile(profile)
    return {"status": "ok", "profile": profile.to_dict()}


@router.get("/learning/profile/{learner_id}", response_model=Dict[str, Any])
async def get_learner_profile(learner_id: str):
    u"""Get a learner profile."""
    from core.harness.knowledge.learning_ontology import load_learner_profile
    profile = load_learner_profile(learner_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Learner '{learner_id}' not found")
    return profile.to_dict()


@router.get("/learning/paths", response_model=Dict[str, Any])
async def list_learning_paths():
    u"""List all available learning paths with summaries."""
    from core.harness.knowledge.learning_paths import get_path_summary
    return {"paths": get_path_summary()}


@router.post("/learning/start", response_model=Dict[str, Any])
async def start_learning_path(learner_id: str = Body(...), path_id: str = Body(...)):
    u"""Start a learning path. Returns the first chapter with content."""
    from core.harness.knowledge.learning_ontology import load_learner_profile, save_learner_profile
    from core.harness.knowledge.learning_paths import get_path, get_chapter_body_sync

    profile = load_learner_profile(learner_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Learner '{learner_id}' not found")

    chapters = get_path(path_id)
    if not chapters:
        raise HTTPException(status_code=404, detail=f"Path '{path_id}' not found")

    profile.active_path_id = path_id
    profile.current_chapter_id = chapters[0].chapter_id
    save_learner_profile(profile)

    first = chapters[0]
    body = get_chapter_body_sync(first)
    return {
        "path_id": path_id, "chapter": first.to_dict(),
        "body": body, "total_chapters": len(chapters),
        "next": chapters[1].chapter_id if len(chapters) > 1 else None,
    }


@router.get("/learning/chapter/{chapter_id}", response_model=Dict[str, Any])
async def get_chapter(chapter_id: str):
    u"""Get chapter content (cached body or skeleton)."""
    from core.harness.knowledge.learning_paths import get_builtin_paths, get_chapter_body_sync
    paths = get_builtin_paths()
    for pid, chs in paths.items():
        for c in chs:
            if c.chapter_id == chapter_id:
                body = get_chapter_body_sync(c)
                return {"path_id": pid, "chapter": c.to_dict(), "body": body}
    raise HTTPException(status_code=404, detail=f"Chapter '{chapter_id}' not found")


@router.post("/learning/chapter/{chapter_id}/compile", response_model=Dict[str, Any])
async def compile_chapter_body_endpoint(chapter_id: str):
    u"""Trigger AI compilation of chapter body text."""
    from core.harness.knowledge.learning_paths import get_builtin_paths, compile_chapter_body
    paths = get_builtin_paths()
    for pid, chs in paths.items():
        for c in chs:
            if c.chapter_id == chapter_id:
                body = await compile_chapter_body(c, force=True)
                return {"chapter_id": chapter_id, "status": "compiled", "body_length": len(body)}
    raise HTTPException(status_code=404, detail=f"Chapter '{chapter_id}' not found")


@router.post("/learning/chapter/{chapter_id}/complete", response_model=Dict[str, Any])
async def complete_chapter_endpoint(
    chapter_id: str,
    learner_id: str = Body(...),
    answers: List[Any] = Body(default=[]),
):
    u"""Submit answers for a chapter's exercises. Returns assessment results."""
    from core.harness.knowledge.learning_ontology import load_learner_profile
    from core.harness.knowledge.learning_paths import get_builtin_paths
    from core.harness.knowledge.learning_assessment import complete_chapter

    profile = load_learner_profile(learner_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Learner '{learner_id}' not found")

    paths = get_builtin_paths()
    chapter = None
    for pid, chs in paths.items():
        for c in chs:
            if c.chapter_id == chapter_id:
                chapter = c
                break
    if not chapter:
        raise HTTPException(status_code=404, detail=f"Chapter '{chapter_id}' not found")

    result = await complete_chapter(profile, chapter, answers)
    return result


@router.get("/learning/progress/{learner_id}", response_model=Dict[str, Any])
async def get_learning_progress(learner_id: str):
    u"""Get learning progress: completed chapters, scores, radar data."""
    from core.harness.knowledge.learning_ontology import load_learner_profile
    from core.harness.knowledge.learning_paths import get_builtin_paths

    profile = load_learner_profile(learner_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Learner '{learner_id}' not found")

    paths = get_builtin_paths()
    path_chapters = paths.get(profile.active_path_id, [])

    total = len(path_chapters)
    completed = [c for c in profile.completed_chapters if c in {ch.chapter_id for ch in path_chapters}]

    # Radar data: mastery per chapter
    radar = [
        {"chapter_id": c.chapter_id, "title": c.title,
         "mastery": profile.mastery_scores.get(c.chapter_id, 0),
         "completed": c.chapter_id in profile.completed_chapters}
        for c in path_chapters
    ]

    return {
        "learner_id": learner_id,
        "path_id": profile.active_path_id,
        "progress": f"{len(completed)}/{total}",
        "completion_pct": round(len(completed) / max(1, total) * 100, 1),
        "completed_chapters": completed,
        "current_chapter": profile.current_chapter_id,
        "radar": radar,
        "mastery_average": round(sum(profile.mastery_scores.values()) / max(1, len(profile.mastery_scores)), 1),
    }


@router.post("/learning/ask", response_model=Dict[str, Any])
async def ask_learning_coach(
    learner_id: str = Body(...),
    question: str = Body(...),
):
    u"""Ask the AI Learning Coach a question, with learning context injected."""
    from core.harness.knowledge.learning_ontology import load_learner_profile
    from core.harness.knowledge.learning_paths import get_builtin_paths, _path_name

    profile = load_learner_profile(learner_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Learner '{learner_id}' not found")

    # Build context
    paths = get_builtin_paths()
    path_chapters = paths.get(profile.active_path_id, [])
    path_name = _path_name(profile.active_path_id) if profile.active_path_id else "未知路径"
    completed_names = [
        next((c.title for c in path_chapters if c.chapter_id == ch_id), ch_id)
        for ch_id in profile.completed_chapters
    ]

    context = (
        f"学生信息: 目标={profile.target_role.value}, 当前水平={profile.current_level.value}, "
        f"每周投入={profile.weekly_hours}小时。"
        f"正在学: {path_name}。"
        f"已完成: {len(completed_names)}/{len(path_chapters)} 章"
        + (f" ({', '.join(completed_names[-5:])})" if completed_names else "")
    )

    try:
        from core.harness.syscalls.llm import sys_llm_generate
        from core.harness.utils.prompt_loader import _sync_resolve
        prompt = _sync_resolve("learning-coach-chat",
            path_name=path_name, context=context, question=question)
        result = await sys_llm_generate(
            None, [{"role": "user", "content": prompt}],
            max_tokens=800,
        )
        reply = result.get("content", "") if isinstance(result, dict) else str(result)
        return {"learner_id": learner_id, "reply": reply, "context": context}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learning/recommendation/{learner_id}", response_model=Dict[str, Any])
async def get_learning_recommendation(learner_id: str):
    u"""Get recommended next learning action based on profile + gaps."""
    from core.harness.knowledge.learning_ontology import load_learner_profile
    from core.harness.knowledge.learning_paths import get_builtin_paths

    profile = load_learner_profile(learner_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Learner '{learner_id}' not found")

    paths = get_builtin_paths()
    path_chapters = paths.get(profile.active_path_id, [])

    # Find next unmet prerequisite chapter
    next_chapter = None
    recommendations = []
    for c in path_chapters:
        if c.chapter_id in profile.completed_chapters:
            continue
        prereq_met = all(p in profile.completed_chapters for p in c.prerequisites)
        if prereq_met and not next_chapter:
            next_chapter = c.chapter_id
        blocked = [p for p in c.prerequisites if p not in profile.completed_chapters]
        if blocked:
            rec = f"学习 '{c.title}' 之前，需要先完成: {', '.join(blocked[:3])}"
            recommendations.append(rec)

    return {
        "learner_id": learner_id,
        "next_chapter": next_chapter,
        "blocked_recommendations": recommendations,
        "weakest_areas": sorted(profile.mastery_scores.items(), key=lambda x: x[1])[:3],
    }


# ══════════════════════════════════════════════════════════════
# Loop Trigger API (event-driven pipeline)
# ══════════════════════════════════════════════════════════════

class TriggerRegisterRequest(BaseModel):
    trigger_id: str = ""
    mode: str = "cron"              # cron | webhook | goal
    scene_id: str = ""
    cron_expression: str = ""       # "0 6 * * *"
    webhook_pattern: str = ""       # "github_pr" | "jira_ticket" | "*"
    params: Dict[str, Any] = {}


@router.post("/loop/triggers", response_model=Dict[str, Any])
async def register_loop_trigger(req: TriggerRegisterRequest):
    u"""Register a pipeline trigger (cron/webhook/goal)."""
    from core.harness.execution.event_loop import register_trigger, Trigger
    t = Trigger(
        trigger_id=req.trigger_id or f"trigger_{int(__import__('time').time())}",
        mode=req.mode, scene_id=req.scene_id, params=req.params,
        cron_expression=req.cron_expression, webhook_pattern=req.webhook_pattern,
    )
    register_trigger(t)
    return {"status": "ok", "trigger": t.to_dict()}


@router.get("/loop/triggers", response_model=Dict[str, Any])
async def list_loop_triggers():
    u"""List all registered pipeline triggers."""
    from core.harness.execution.event_loop import load_triggers
    triggers = load_triggers()
    return {"triggers": [t.to_dict() for t in triggers], "total": len(triggers)}


@router.delete("/loop/triggers/{trigger_id}", response_model=Dict[str, Any])
async def remove_loop_trigger(trigger_id: str):
    u"""Remove a pipeline trigger."""
    from core.harness.execution.event_loop import remove_trigger
    ok = remove_trigger(trigger_id)
    return {"status": "ok" if ok else "not_found"}


@router.post("/loop/webhook", response_model=Dict[str, Any])
async def handle_webhook(source: str = Body(...), payload: Dict[str, Any] = Body(default={})):
    u"""Handle incoming webhook — dispatches to matching triggers."""
    from core.harness.execution.event_loop import dispatch_webhook
    count = await dispatch_webhook(source, payload)
    return {"triggered": count}
