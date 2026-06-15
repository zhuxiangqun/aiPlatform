"""
Wiki API — persistent LLM-curated knowledge base endpoints.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

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


@router.get("/pages")
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


@router.get("/pages/{title}")
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
        except Exception:
            pass

    return page


@router.delete("/pages/{title}")
async def delete_page(title: str, collection: str = "default"):
    from core.harness.knowledge.wiki_engine import delete_page as _del
    ok = _del(title, collection_id=collection)
    if not ok:
        raise HTTPException(status_code=404, detail="wiki_page_not_found")
    return {"title": title, "status": "deleted"}


@router.delete("/pages-all")
async def delete_all_pages(collection: str = "default"):
    from core.harness.knowledge.wiki_engine import delete_all_pages
    result = delete_all_pages(collection_id=collection)
    return {"deleted": result["deleted"], "message": f"已清空 {result['deleted']} 个 Wiki 页面"}


@router.get("/unprocessed-docs")
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
    
    # Find KB docs not in wiki
    conn = _sq.connect(kb_db)
    conn.row_factory = _sq.Row
    docs = conn.execute(
        "SELECT doc_id, source_uri, kind, status FROM documents WHERE tenant_id=? AND status='ready'",
        (tenant_id,)
    ).fetchall()
    
    unprocessed = []
    for d in docs:
        if d["doc_id"] not in wiki_doc_ids:
            unprocessed.append({
                "doc_id": d["doc_id"],
                "source_uri": d["source_uri"],
                "kind": d["kind"],
                "status": d["status"],
            })
    conn.close()
    return {"items": unprocessed, "total": len(unprocessed)}


@router.get("/skill-deps")
async def get_skill_deps():
    u"""Return Agent→Skill→Syscall dependency graph."""
    from core.harness.knowledge.skill_deps import build_skill_deps
    return build_skill_deps()


@router.get("/skill-impact/{skill_id}")
async def get_skill_impact(skill_id: str):
    u"""Return agents and skills affected by a given skill."""
    from core.harness.knowledge.skill_deps import skill_impact
    result = skill_impact(skill_id)
    if not result.get("exists"):
        raise HTTPException(status_code=404, detail="skill not found")
    return result


@router.post("/skills/install-from-directory")
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
        raise HTTPException(
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
                    except Exception:
                        pass

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


@router.post("/pipeline/ship")
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


@router.post("/pipeline/self-harness")
async def run_self_harness_cycle():
    u"""Run the Self-Harness optimization cycle."""
    try:
        from core.harness.execution.failure_clusterer import load_clusters
        from core.harness.execution.pipeline_engine import PipelineEngine
        from core.harness.kernel.runtime import get_kernel_runtime

        runtime = get_kernel_runtime()
        store = getattr(runtime, "execution_store", None) if runtime else None
        run_states = []
        if store is not None:
            try:
                events = await store.list_completed_runs(limit=50)
                run_states = [e.get("pipeline_state", {}) for e in events if e.get("pipeline_state")]
            except Exception:
                pass

        if not run_states:
            return {"accepted": [], "rejected": [], "message": "No completed runs found for analysis"}

        result = await PipelineEngine._run_self_harness_cycle(run_states)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Self-Harness failed: {e}")


class SandboxRequest(BaseModel):
    seed_params: Dict[str, Any] = {}
    scenario_count: int = 10


@router.post("/pipeline/sandbox")
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



@router.get("/pipeline/diagnose/{run_id}")
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
        except Exception:
            pass

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


@router.get("/proposals")
async def get_proposals(status: str = "", collection: str = "default"):
    u"""List pending wiki knowledge proposals (merge/update/supplement/contradict)."""
    from core.harness.knowledge.wiki_engine import load_proposals
    proposals = load_proposals(collection_id=collection)
    if status:
        proposals = [p for p in proposals if p.get("status") == status]
    return {"items": proposals, "total": len(proposals)}


@router.put("/proposals/{proposal_id}")
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


@router.post("/pages")
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
    except Exception:
        pass
    return {"title": body.title, "path": path, "status": "created", "auto_links": auto_links}


@router.get("/traverse/{title}")
async def traverse_links(title: str, depth: int = 2, collection: str = "default"):
    from core.harness.knowledge.wiki_engine import traverse_links
    pages = traverse_links(title, depth=depth, collection_id=collection)
    return {"root": title, "depth": depth, "pages": len(pages), "items": pages}


@router.get("/lint")
async def lint_wiki(collection: str = "default"):
    from core.harness.knowledge.wiki_engine import wiki_health_report
    return wiki_health_report()


@router.get("/graph")
async def wiki_graph(
    category: str = "",
    keyword: str = "",
    source: str = "",
    max_nodes: int = 300,
 collection: str = "default"):
    from core.harness.knowledge.wiki_engine import build_graph
    return build_graph(category=category, keyword=keyword, source=source, max_nodes=max_nodes, collection_id=collection)


@router.post("/ingest")
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
    return {"source_id": sid, "status": "ingested",
            "message": "Text stored. Execute wiki_curator agent to process and update wiki pages."}


@router.post("/atomize-document")
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


@router.post("/convert-from-kb")
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
                except Exception: pass
                # Try to parse a human-readable title from the URI
                from core.harness.knowledge.wiki_engine import parse_title_from_uri
                readable = parse_title_from_uri(source_uri)
                if readable and len(readable) >= 3:
                    title = readable

                # Skip if already converted
                try:
                    meta = _json.loads(doc["meta_json"] or "{}")
                    wiki_pages = meta.get("wiki_pages", [])
                    if wiki_pages:
                        skipped += 1
                        continue
                except Exception: pass

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

                # Create wiki page
                safe_title = re.sub(r"[<>:\"/\\|?*]", "_", title)[:120]
                write_page(safe_title, body, category="entities", tags=tags, summary=summary,
                          source_articles=[f"kb:{doc_id}"], collection_id=collection)
                docs_converted += 1

                # LLM curation: enhance with proper summary, entity extraction, auto-linking
                try:
                    from core.harness.knowledge.wiki_engine import llm_curate_page, list_all_pages as _lap
                    existing = _lap()
                    existing_titles = [p["title"] for p in existing] if existing else []
                    curated = await llm_curate_page(safe_title, body, existing_titles=existing_titles, source_doc_id=doc_id)
                    # Re-write with LLM-enhanced metadata
                    old_title = safe_title
                    write_page(curated["title"], body,
                        category=curated.get("category", "entities"),
                        tags=curated.get("tags", tags),
                        related=curated.get("related", []),
                        summary=curated.get("summary", summary),
                        source_articles=[f"kb:{doc_id}"], collection_id=collection)
                    # If LLM changed the title, delete the mechanically-created page
                    if curated["title"] != old_title:
                        from core.harness.knowledge.wiki_engine import delete_page as _delp
                        try: _delp(old_title)
                        except Exception: pass
                    # Always delete the mechanical page if it still exists
                    from core.harness.knowledge.wiki_engine import delete_page as _delp2
                    try: _delp2(old_title)
                    except Exception: pass
                    # Create knowledge atom pages with evidence tracking
                    for atom in curated.get("knowledge_atoms", [])[:8]:
                        if not atom.get("title") or not atom.get("body"):
                            continue
                        atom_title = re.sub(r"[<>:\"/\\|?*]", "_", str(atom["title"])[:80])
                        if atom_title and atom_title != curated["title"]:
                            from core.harness.knowledge.wiki_engine import write_atom
                            write_atom({
                                "title": atom_title,
                                "body": str(atom.get("body", ""))[:20000],
                                "source_doc_id": f"kb:{doc_id}",
                                "evidence_text": atom.get("evidence_text", ""),
                                "confidence": float(atom.get("confidence", 0.5)),
                                "tags": list(atom.get("tags", []))[:5],
                                "contradicts_atom_index": atom.get("contradicts_atom_index"),
                                "supports_atom_index": atom.get("supports_atom_index"),
                            }, collection_id=collection)
                            entities_created += 1
                    # After creating knowledge atoms, update main page's related
                    # to include them (prevent orphan pages)
                    if entities_created > 0 and curated.get("title"):
                        main_page = read_page(curated["title"], collection_id=collection)
                        if main_page:
                            atom_titles = []
                            for atom in curated.get("knowledge_atoms", [])[:8]:
                                a_title = re.sub(r"[<>:\"/\\|?*]", "_", str(atom.get("title", ""))[:80])
                                if a_title and a_title != curated["title"]:
                                    atom_titles.append(a_title)
                            if atom_titles:
                                existing_related = set(main_page.get("related", []) or [])
                                existing_related.update(atom_titles)
                                write_page(curated["title"], main_page.get("body", "", collection_id=collection),
                                    category=main_page.get("category", "entities"),
                                    tags=main_page.get("tags", []),
                                    related=list(existing_related)[:10],
                                    summary=main_page.get("summary", ""))
                    # Mark contradictions
                    for con in curated.get("contradictions", [])[:3]:
                        from core.harness.knowledge.wiki_engine import read_page as _rpx
                        old_page = _rpx(con.get("b", ""))
                        if old_page:
                            old_contradictions = set(old_page.get("contradictions", []))
                            old_contradictions.add(safe_title)
                            write_page(con.get("b", "", collection_id=collection), old_page.get("body", ""),
                                category=old_page.get("category", "entities"),
                                tags=old_page.get("tags", []), related=old_page.get("related", []),
                                contradictions=list(old_contradictions)[:10])
                except Exception:
                    pass  # LLM curation best-effort

                # Write back to KB document: record linked wiki page
                final_title = curated["title"] if curated.get("title") and curated["title"] != old_title else safe_title
                try:
                    meta = _json.loads(doc["meta_json"] or "{}")
                    wiki_pages = meta.get("wiki_pages", [])
                    # Remove old mechanical title if it differs from final
                    if final_title != safe_title and safe_title in wiki_pages:
                        wiki_pages.remove(safe_title)
                    if final_title not in wiki_pages:
                        wiki_pages.append(final_title)
                        meta["wiki_pages"] = wiki_pages
                        meta_json_str = _json.dumps(meta, ensure_ascii=False)
                        conn.execute("UPDATE documents SET meta_json=?, wiki_status='wikified' WHERE doc_id=? AND tenant_id=?",
                                    (meta_json_str, doc_id, tenant_id))
                        conn.commit()
                except Exception as e:
                    writeback_errors += 1
                    logger.warning(f"convert-from-kb: failed to write wiki_pages for doc {doc_id}: {e}")

            # Cross-link pages that share keywords (validate against actual existing pages)
            valid_titles = set()
            try:
                from core.harness.knowledge.wiki_engine import search_pages
                valid_titles = set(p["title"] for p in (search_pages(limit=1000, collection_id=collection) or []))
            except Exception:
                pass
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
                    except Exception: pass

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
                    except Exception: pass
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


@router.post("/curate")
async def curate_wiki(collection: str = "default"):
    u"""LLM 深度策展：遍历所有 Wiki 页面，用 LLM 重写标题/分类/标签/摘要/关联。

    返回: {processed, links_added, titles_updated, errors[]}
    如果 LLM 不可用，降级到嵌入自动关联。
    """
    from core.harness.knowledge.wiki_engine import search_pages, llm_curate_page, update_page, auto_link_page
    pages = search_pages(limit=500, collection_id=collection)
    report = {"processed": 0, "links_added": 0, "titles_updated": 0, "errors": []}
    all_titles = [p["title"] for p in pages]

    # Track saved proposals to detect conflicts (same pair, different action)
    saved_pairs: Dict[frozenset, str] = {}

    for p in pages:
        try:
            existing_titles = [t for t in all_titles if t != p["title"]]
            result = await llm_curate_page(p["title"], p.get("body", ""),
                                           existing_titles=existing_titles)
            if result.get("error") or result.get("fallback"):
                # LLM failed → try embedding auto-link as fallback
                report["errors"].append({
                    "page": p["title"],
                    "error": result.get("error", "LLM unavailable"),
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
                        related=result.get("related", []))  # replace, not merge (LLM curates against current titles)
            report["processed"] += 1
            report["links_added"] += len(result.get("related", []))
            if result.get("title") != p["title"]:
                report["titles_updated"] += 1
            # Generate proposals for merge / update / supplement
            import time as _t
            for mc in result.get("merge_candidates", [])[:3]:
                if mc.get("target") and mc["target"] in existing_titles:
                    from core.harness.knowledge.wiki_engine import save_proposal
                    pair = frozenset([p["title"], mc["target"]])
                    if pair in saved_pairs and saved_pairs[pair] != "merge":
                        report["errors"].append({
                            "page": p["title"],
                            "error": f"conflicting proposal: merge→{mc['target']} vs existing {saved_pairs[pair]}",
                        })
                        continue
                    save_proposal({
                        "action": "merge",
                        "from_title": p["title"],
                        "to_title": mc["target"],
                        "reason": str(mc.get("reason", "content overlap")),
                        "source_doc": "",
                        "status": "pending",
                        "created_at": str(int(_t.time())),
                    }, collection_id=collection)
                    saved_pairs[pair] = "merge"
            for con in result.get("contradictions", [])[:3]:
                b_title = con.get("b", "") if isinstance(con, dict) else con
                if b_title and b_title in existing_titles:
                    from core.harness.knowledge.wiki_engine import save_proposal
                    pair = frozenset([p["title"], b_title])
                    if pair in saved_pairs and saved_pairs[pair] != "contradict":
                        report["errors"].append({
                            "page": p["title"],
                            "error": f"conflicting proposal: contradict↔{b_title} vs existing {saved_pairs[pair]}",
                        })
                        continue
                    save_proposal({
                        "action": "contradict",
                        "from_title": p["title"],
                        "to_title": b_title,
                        "reason": str(con.get("detail", "conflicting claims") if isinstance(con, dict) else "conflicting claims"),
                        "source_doc": "",
                        "status": "pending",
                        "created_at": str(int(_t.time())),
                    }, collection_id=collection)
                    saved_pairs[pair] = "contradict"
        except Exception as e:
            report["errors"].append({"page": p["title"], "error": str(e)[:300]})

    return report


@router.post("/wiki/index-md")
async def regenerate_wiki_index(collection: str = "default"):
    """Generate a human-readable wiki index page (index.md) from index.json."""
    try:
        from core.harness.knowledge.wiki_engine import generate_index_md
        content = generate_index_md(collection_id=collection)
        lines = content.count("\n") + 1 if content else 0
        return {"status": "ok", "lines": lines, "content": content[:500]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Index generation failed: {e}")


@router.get("/wiki/health-trend")
async def get_wiki_health_trend():
    """Get wiki health score trend over time."""
    try:
        from core.harness.knowledge.wiki_health_rules import get_health_trend
        return get_health_trend()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get health trend: {e}")


@router.get("/wiki/golden-queries/seed")
async def seed_golden_queries():
    """Create a default golden_queries.yaml template."""
    try:
        from core.harness.knowledge.wiki_structured_query import seed_golden_queries
        return {"status": seed_golden_queries()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed: {e}")


@router.post("/wiki/golden-queries/run")
async def run_golden_tests():
    """Run regression tests against golden queries."""
    try:
        from core.harness.knowledge.wiki_structured_query import run_golden_tests
        return run_golden_tests()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Golden test failed: {e}")


@router.get("/wiki/query-structured")
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


@router.get("/wiki/golden-queries/seed")
async def seed_golden_queries():
    """Create a default golden_queries.yaml template."""
    try:
        from core.harness.knowledge.wiki_structured_query import seed_golden_queries
        return {"status": seed_golden_queries()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed: {e}")


@router.post("/ontology/rebuild")
async def ontology_rebuild(collection: str = "default"):
    """Full rebuild of the knowledge ontology A-Box from current Wiki+KB data."""
    try:
        from core.harness.knowledge.knowledge_abox_builder import rebuild_full
        onto = rebuild_full(collection_id=collection)
        return {"status": "rebuilt", "triples": len(onto.triples), "collection": collection}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rebuild failed: {e}")


@router.get("/ontology/validate")
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


@router.get("/ontology/network/{title:path}")
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


@router.get("/ontology/source-impact")
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


@router.get("/wiki/changelog")
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


@router.post("/wiki/rollback/{title}")
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


@router.get("/wiki/duplicates")
async def detect_wiki_duplicates(collection: str = "default"):
    """Detect potentially duplicate wiki pages using embedding similarity."""
    try:
        from core.harness.knowledge.wiki_engine import detect_duplicate_pages
        duplicates = detect_duplicate_pages(collection_id=collection)
        return {"duplicates": duplicates, "total": len(duplicates)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Duplicate detection failed: {e}")


# ── Collection Management ───────────────────────────────────────

@router.get("/collections")
async def list_wiki_collections():
    """List all wiki collections with page counts."""
    try:
        from core.harness.knowledge.wiki_engine import list_collections
        cols = list_collections()
        return {"collections": cols, "total": len(cols)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list collections: {e}")


@router.post("/collections")
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


@router.delete("/collections/{collection_id}")
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

@router.get("/schema")
async def get_wiki_schema(collection: str = "default"):
    """Return T-Box class schemas, with per-collection extensions applied."""
    try:
        from core.harness.knowledge.knowledge_ontology import (
            get_classes_with_templates, get_extended_class,
            load_collection_extension, OBJECT_PROPERTIES, AI
        )
        extension = load_collection_extension(collection)
        schemas = []
        for cls in get_classes_with_templates():
            # Apply collection extension if applicable
            cat = cls.allowed_categories[0] if cls.allowed_categories else ""
            display_cls = get_extended_class(cat, collection) or cls
            props = []
            for op in OBJECT_PROPERTIES:
                if display_cls.uri in op.domain:
                    props.append({
                        "type": "relation",
                        "label": op.label,
                        "uri": op.uri,
                        "range": [r.replace(AI, "") for r in op.range],
                        "cardinality": {
                            "min": op.min_cardinality or 0,
                            "max": op.max_cardinality,
                        },
                        "is_transitive": op.is_transitive,
                        "is_symmetric": op.is_symmetric,
                    })
            schemas.append({
                "class_uri": display_cls.uri,
                "label": display_cls.label,
                "categories": display_cls.allowed_categories,
                "required_fields": display_cls.required_fields,
                "optional_fields": display_cls.optional_fields,
                "template_markdown": display_cls.template_markdown,
                "relations": props,
            })
        return {
            "schemas": schemas, "total": len(schemas),
            "collection": collection,
            "has_extension": extension is not None,
            "extension_label": extension.get("label", "") if extension else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load schemas: {e}")


@router.get("/ontology/classes")
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


# ── Inference Rules API ─────────────────────────────────────────

@router.get("/ontology/rules")
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


@router.post("/ontology/rules")
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

@router.get("/claim/{title}/evidence-chain")
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

@router.get("/ontology/export")
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


@router.get("/ontology/infer")
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

@router.get("/ontology/patterns")
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


@router.get("/ontology/metrics")
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
            except Exception:
                pass
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


@router.get("/ontology/metrics/history")
async def get_metrics_history(collection: str = "default"):
    """Return historical metrics snapshots for trend analysis (last 30 days)."""
    try:
        from core.harness.knowledge.knowledge_validator import load_metrics_history
        history = load_metrics_history(collection)
        return {"history": history, "total": len(history)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"History failed: {e}")


@router.get("/ontology/golden-regression")
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

@router.get("/ontology/suggestions")
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


@router.post("/ontology/suggestions")
async def generate_suggestions(collection: str = "default"):
    """Scan wiki data and generate ontology evolution suggestions."""
    try:
        from core.harness.knowledge.knowledge_ontology import add_suggestions_from_patterns
        suggestions = add_suggestions_from_patterns(collection_id=collection)
        pending = [s for s in suggestions if s.get("status") == "pending"]
        return {"status": "generated", "total": len(suggestions), "pending": len(pending)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Suggestion generation failed: {e}")


@router.post("/ontology/suggestions/{suggestion_id}/accept")
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


@router.post("/ontology/suggestions/{suggestion_id}/reject")
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


@router.post("/ontology/suggestions/{suggestion_id}/generate-code")
async def generate_code(suggestion_id: str, collection: str = "default"):
    """Generate implementation code for an accepted suggestion."""
    try:
        from core.harness.knowledge.knowledge_ontology import generate_code_for_suggestion
        result = generate_code_for_suggestion(suggestion_id, collection_id=collection)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Code generation failed: {e}")


@router.get("/ontology/schema-readiness")
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


@router.post("/clean-stale-references")
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


@router.post("/seed-instances")
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


@router.post("/backfill-evidence")
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


@router.post("/batch-atomize")
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


@router.post("/maintain/fts-rebuild")
async def rebuild_fts_index(collection: str = "default"):
    """Rebuild FTS5 full-text search index for wiki pages."""
    try:
        from core.harness.knowledge.wiki_fts import fts_index_pages
        count = fts_index_pages()
        return {"status": "completed", "indexed": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FTS rebuild failed: {e}")


@router.post("/wiki/evolve")
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


@router.get("/wiki/evolution-history")
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


@router.get("/maintain/model-log")
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


@router.put("/ontology/markings")
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


@router.delete("/ontology/markings")
async def remove_entity_marking(req: MarkingDeleteRequest, collection: str = "default"):
    u"""Remove a marking from an entity (or all if label is empty)."""
    from core.harness.knowledge.knowledge_markings import remove_marking
    ok = remove_marking(
        entity_uri=req.entity_uri,
        label=req.label,
        collection_id=collection,
    )
    return {"status": "ok" if ok else "not_found", "removed": ok}


@router.get("/ontology/markings/{entity_uri:path}")
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


@router.put("/ontology/permissions")
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


@router.delete("/ontology/permissions")
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


@router.get("/ontology/permissions/{entity_uri:path}")
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


@router.post("/ontology/suggestions/semantic")
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


@router.post("/ontology/suggestions/{suggestion_id}/impact")
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

@router.get("/ontology/health/triggers")
async def get_health_triggers(collection: str = "default"):
    u"""Get triggered curation tasks from ontology health checks."""
    from core.harness.knowledge.knowledge_quality import check_ontology_health_triggers
    triggers = check_ontology_health_triggers(collection_id=collection)
    return {"triggers": triggers, "total": len(triggers), "collection_id": collection}


@router.get("/ontology/health/score")
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


@router.get("/ontology/quality/{entity_uri:path}")
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


@router.get("/ontology/writebacks")
async def list_writebacks(collection: str = "default"):
    u"""List all registered writeback configurations."""
    from core.harness.knowledge.knowledge_writeback import load_writebacks
    configs = load_writebacks(collection_id=collection)
    return {"writebacks": [c.to_dict() for c in configs], "total": len(configs)}


@router.post("/ontology/writebacks")
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


@router.delete("/ontology/writebacks")
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


@router.get("/ontology/field-permissions/{entity_uri:path}")
async def get_field_permissions(entity_uri: str, collection: str = "default"):
    u"""Get field-level permission rules for an entity."""
    from core.policy.field_level_security import load_field_permissions
    perms = load_field_permissions(collection_id=collection)
    applicable = [p.to_dict() for p in perms if p.entity_uri == entity_uri]
    return {"entity_uri": entity_uri, "permissions": applicable, "total": len(applicable)}


@router.put("/ontology/field-permissions")
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


@router.delete("/ontology/field-permissions")
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


@router.get("/ontology/scenes")
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


@router.post("/ontology/scenes")
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


@router.get("/ontology/scenes/{scene_id}")
async def get_scene_model(scene_id: str, collection: str = "default"):
    from core.harness.knowledge.scene_model import get_scene
    scene = get_scene(scene_id, collection_id=collection)
    if not scene:
        raise HTTPException(status_code=404, detail=f"Scene '{scene_id}' not found")
    return {"scene": scene.to_dict(), "pipeline_stages": scene.to_pipeline_stages(),
            "stage_count": len(scene.to_pipeline_stages())}


@router.post("/ontology/scenes/{scene_id}/instantiate")
async def instantiate_scene_model(scene_id: str, params: Dict[str, Any] = Body(default={}), collection: str = "default"):
    from core.harness.knowledge.scene_model import instantiate_scene
    config = instantiate_scene(scene_id, params=params, collection_id=collection)
    if not config:
        raise HTTPException(status_code=404, detail=f"Scene '{scene_id}' not found")
    return {"pipeline_config": config, "stage_count": len(config.get("stages", []))}


@router.delete("/ontology/scenes/{scene_id}")
async def delete_scene_model(scene_id: str, collection: str = "default"):
    from core.harness.knowledge.scene_model import delete_scene
    ok = delete_scene(scene_id, collection_id=collection)
    return {"status": "ok" if ok else "not_found"}


# ══════════════════════════════════════════════════════════════
# Growth Metrics API (Phase E — knowledge compound interest)
# ══════════════════════════════════════════════════════════════

@router.get("/ontology/growth-stats")
async def get_growth_stats(days: int = 30, collection: str = "default"):
    u"""Get knowledge base growth statistics for the last N days."""
    from core.harness.knowledge.knowledge_growth import get_growth_stats, estimate_compound_value
    stats = get_growth_stats(collection_id=collection, days=days)
    compound = estimate_compound_value(collection_id=collection)
    return {**stats, "compound": compound}


@router.post("/ontology/growth/snapshot")
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


@router.post("/learning/profile")
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


@router.get("/learning/profile/{learner_id}")
async def get_learner_profile(learner_id: str):
    u"""Get a learner profile."""
    from core.harness.knowledge.learning_ontology import load_learner_profile
    profile = load_learner_profile(learner_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Learner '{learner_id}' not found")
    return profile.to_dict()


@router.get("/learning/paths")
async def list_learning_paths():
    u"""List all available learning paths with summaries."""
    from core.harness.knowledge.learning_paths import get_path_summary
    return {"paths": get_path_summary()}


@router.post("/learning/start")
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


@router.get("/learning/chapter/{chapter_id}")
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


@router.post("/learning/chapter/{chapter_id}/compile")
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


@router.post("/learning/chapter/{chapter_id}/complete")
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


@router.get("/learning/progress/{learner_id}")
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


@router.post("/learning/ask")
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
        prompt = (
            f"你是 AI 学习教练，你的学生正在学习 '{path_name}' 路径。\n\n"
            f"{context}\n\n"
            f"学生的提问: {question}\n\n"
            f"请用中文回答。回答要有针对性（结合学生的学习进度），"
            f"给出具体的、可操作的建议。如果学生问的是路径中某个章节的内容，"
            f"用通俗的语言解释核心概念，附带一个具体例子。\n"
            f"如果学生卡住了，鼓励他们继续，并给出一个最小的下一步行动。"
        )
        result = await sys_llm_generate(
            None, [{"role": "user", "content": prompt}],
            max_tokens=800,
        )
        reply = result.get("content", "") if isinstance(result, dict) else str(result)
        return {"learner_id": learner_id, "reply": reply, "context": context}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learning/recommendation/{learner_id}")
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
