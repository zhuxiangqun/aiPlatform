"""Active Synthesis — STORM-style proactive knowledge generation.



Closes Gap 1: upgrades wiki_evolve from "passively respond to new information"

to "actively discover knowledge gaps → research → draft wiki pages → submit proposals."



Pipeline:

  1. detect_gaps() → KnowledgeGap objects (from knowledge_gap_detector)

  2. generate_research_questions(entity, gap) → List[str]

  3. retrieve_source_documents(entity, domain_id) → str (concatenated raw docs)

  4. synthesize_wiki_page(entity, research_qs, source_docs) → dict (draft page)

  5. submit_proposal(draft_page, collection_id) → bool



Trigger modes:

  - On-demand: POST /wiki/active-synthesis (manual trigger)

  - Event-driven: after gap detection finds new gaps (via wiki_engine hook)

  - Configuration: AIPLAT_ACTIVE_SYNTHESIS_AUTO=false (default, requires manual trigger)

"""



from __future__ import annotations



import json

import logging

import time

from typing import Any, Dict, List, Optional



logger = logging.getLogger("aiplat.active_synthesis")





# ═══════════════════════════════════════════════════════════════

# Step 1: Gap detection (delegates to knowledge_gap_detector)

# ═══════════════════════════════════════════════════════════════



async def detect_synthesis_gaps(

    *,

    domain_id: str = "default",

    min_frequency: int = 2,

    max_gaps: int = 10,

    queries: Optional[List[str]] = None,

) -> List[Dict[str, Any]]:

    """Detect knowledge gaps suitable for active synthesis.



    Priortizes 'no_instance' gaps (entity known but no wiki page exists).

    Falls back to 'no_entity' gaps if sample is too small.

    """

    try:

        from core.harness.ontology_engine.knowledge_gap_detector import detect_knowledge_gaps



        # If no queries provided, use recent KB search logs

        if not queries:

            queries = _get_recent_queries(domain_id)



        result = detect_knowledge_gaps(

            queries,

            domain_id=domain_id,

            min_frequency=min_frequency,

            max_gaps=max_gaps,

        )

        gaps = result.get("gaps", [])



        # Prioritize no_instance gaps (most actionable)

        actionable = [g for g in gaps if g.get("gap_type") == "no_instance"]

        if len(actionable) < 3:

            actionable += [g for g in gaps if g.get("gap_type") == "no_entity"]

        return actionable[:max_gaps]

    except Exception as e:

        logger.debug("Gap detection failed: %s", e)

        return []





def _get_recent_queries(domain_id: str = "default") -> List[str]:

    """Read recent queries from kb_retrieval logs or search history."""

    # Use conversation history as query source

    try:

        import os

        import sqlite3

        db_path = os.path.expanduser(os.getenv("AIPLAT_EXECUTION_DB_PATH", "~/.aiplat/aiplat_executions.sqlite3"))

        conn = sqlite3.connect(db_path)

        conn.row_factory = sqlite3.Row

        rows = conn.execute(

            "SELECT payload FROM execution_events WHERE event_type='knowledge_retrieve' ORDER BY created_at DESC LIMIT 200"

        ).fetchall()

        conn.close()

        queries = []

        for r in rows:

            try:

                payload = json.loads(r["payload"] or "{}")

                q = payload.get("query", "")

                if q and len(q) > 3:

                    queries.append(q)

            except Exception:

                logging.getLogger(__name__).debug('_get_recent_queries failed', exc_info=True)
        return queries if queries else ["default_query"]

    except Exception:

        return ["default_query"]





# ═══════════════════════════════════════════════════════════════

# Step 2: Generate research questions

# ═══════════════════════════════════════════════════════════════



_RESEARCH_QUESTIONS_PROMPT = """你是一个主题研究助手。给定一个知识缺口（某个概念在知识库中反复出现但没有对应的 Wiki 页面），请生成 3-5 个研究问题，以帮助收集信息来创建该概念的 Wiki 页面。



知识缺口：

- 概念：{entity}

- 缺口类型：{gap_type}

- 建议：{suggestion}



请生成具体、有深度的研究问题。每个问题一行，以数字开头。只列出问题，不要其他文字。"""





async def generate_research_questions(entity: str, gap: Dict[str, Any]) -> List[str]:

    """Generate focused research questions for a knowledge gap."""

    try:

        from core.harness.syscalls.llm import sys_llm_generate

        from core.harness.utils.model_injection import best_model_for_purpose



        prompt = _RESEARCH_QUESTIONS_PROMPT.format(

            entity=entity,

            gap_type=gap.get("gap_type", "unknown"),

            suggestion=gap.get("suggestion", "需要补充相关知识"),

        )

        resp = await sys_llm_generate(

            None,

            [{"role": "user", "content": prompt}],

            model_name=best_model_for_purpose("doc_llm"),

            temperature=0.3,

            max_tokens=300,

        )

        text = getattr(resp, "content", "") or str(resp)

        # Parse numbered questions

        import re

        questions = re.findall(r"\d+\.\s*(.+)", text)

        if not questions:

            questions = [line.strip() for line in text.split("\n") if len(line.strip()) > 10]

        return questions[:5]

    except Exception as e:

        logger.debug("Research questions generation failed: %s", e)

        return [f"{entity} 的定义和核心特征是什么？"]





# ═══════════════════════════════════════════════════════════════

# Step 3: Retrieve source documents

# ═══════════════════════════════════════════════════════════════



def retrieve_source_documents(

    entity_name: str,

    *,

    domain_id: str = "default",

    top_k: int = 8,

) -> str:

    """Retrieve relevant raw documents from kb_elements for synthesis."""

    try:

        from core.harness.syscalls.retrieval import sys_knowledge_retrieve

        import asyncio



        async def _fetch():

            results = await sys_knowledge_retrieve(

                query=entity_name,

                wiki_first=False,

                top_k=top_k,

            )

            if results:

                return "\n\n---\n\n".join(

                    str(r.get("content", str(r)))[:2000] for r in results

                )

            return ""



        # Fallback: try reading from wiki pages with matching names

        docs = asyncio.get_event_loop().run_until_complete(_fetch()) if asyncio.get_event_loop().is_running() else ""

        if not docs:

            try:

                from core.harness.knowledge.wiki_engine import search_pages

                pages = search_pages(query=entity_name, limit=5, collection_id=domain_id)

                if pages:

                    docs = "\n\n---\n\n".join(

                        str(p.get("body", ""))[:1500] for p in pages

                    )

            except Exception:

                logging.getLogger(__name__).debug('_fetch failed', exc_info=True)
        return docs

    except Exception as e:

        logger.debug("Source document retrieval failed: %s", e)

        return ""





# ═══════════════════════════════════════════════════════════════

# Step 4: Synthesize wiki page

# ═══════════════════════════════════════════════════════════════



_SYNTHESIS_PROMPT = """你是一个知识库编辑。请根据以下研究问题和原始资料，为新概念创建一个 Wiki 页面。



## 新概念

{entity}



## 研究问题

{questions}



## 原始资料

{documents}



请以 JSON 格式输出 Wiki 页面草稿（只返回 JSON，不要其他文字）:

{{

  "title": "页面标题",

  "category": "entities",

  "summary": "一句话摘要",

  "body": "完整的 Markdown 格式页面内容。包含以下结构：

## 定义

[概念的定义和核心特征]



## 关键要点

- 要点1

- 要点2

- 要点3



## 相关概念

- [[相关概念1]]

- [[相关概念2]]



## 数据来源

[注明信息来自哪些原始文档]",

  "tags": ["标签1", "标签2"],

  "confidence": 0.0-1.0

}}



要求:

- body 使用 Markdown 格式，至少 200 字

- 如果原始资料不足，在 confidence 中标注低置信度

- tags 至少包含 2 个相关标签"""





async def synthesize_wiki_page(

    entity: str,

    research_questions: List[str],

    source_docs: str,

) -> Optional[Dict[str, Any]]:

    """Synthesize a draft wiki page from research and source documents."""

    if not source_docs:

        logger.info("No source documents for '%s', skipping synthesis", entity)

        return None



    try:

        from core.harness.syscalls.llm import sys_llm_generate

        from core.harness.utils.model_injection import best_model_for_purpose



        prompt = _SYNTHESIS_PROMPT.format(

            entity=entity,

            questions="\n".join(f"- {q}" for q in research_questions),

            documents=source_docs[:6000],  # limit to avoid OOM

        )

        resp = await sys_llm_generate(

            None,

            [{"role": "user", "content": prompt}],

            model_name=best_model_for_purpose("doc_llm"),

            temperature=0.2,

            max_tokens=2000,

        )

        text = getattr(resp, "content", "") or str(resp)



        # Parse JSON

        try:

            draft = json.loads(text)

        except (json.JSONDecodeError, TypeError):

            import re

            m = re.search(r"\{[\s\S]*\"title\"[\s\S]*\}", text)

            if m:

                try:

                    draft = json.loads(m.group(0))

                except (json.JSONDecodeError, TypeError):

                    return None

            else:

                return None



        if not draft.get("title") or not draft.get("body"):

            return None



        # Set defaults

        draft.setdefault("category", "entities")

        draft.setdefault("tags", [])

        draft.setdefault("confidence", 0.5)

        draft["source"] = "active_synthesis"

        draft["research_questions"] = research_questions

        draft["synthesized_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

        return draft

    except Exception as e:

        logger.debug("Synthesis failed for '%s': %s", entity, e)

        return None





# ═══════════════════════════════════════════════════════════════

# Step 5: Submit as proposal

# ═══════════════════════════════════════════════════════════════



def submit_as_proposal(

    draft: Dict[str, Any],

    *,

    collection_id: str = "default",

) -> bool:

    """Submit a synthesized draft as a knowledge proposal for human review."""

    try:

        from core.harness.knowledge.wiki_engine import save_proposal



        proposal = {

            "id": f"active_synth_{int(time.time() * 1000):x}",

            "title": draft.get("title", ""),

            "body": draft.get("body", ""),

            "category": draft.get("category", "entities"),

            "tags": draft.get("tags", []),

            "summary": draft.get("summary", ""),

            "confidence": draft.get("confidence", 0.5),

            "source": "active_synthesis",

            "status": "draft",

            "research_questions": draft.get("research_questions", []),

        }

        save_proposal(proposal, collection_id=collection_id)

        logger.info("Proposal submitted for '%s' (confidence=%.2f)", draft.get("title", ""), draft.get("confidence", 0.5))

        return True

    except Exception as e:

        logger.warning("Proposal submission failed for '%s': %s", draft.get("title", ""), e)

        return False





# ═══════════════════════════════════════════════════════════════

# Main pipeline

# ═══════════════════════════════════════════════════════════════



async def run_active_synthesis(

    *,

    domain_id: str = "default",

    collection_id: str = "default",

    max_gaps: int = 5,

    auto_submit: bool = False,

    min_confidence: float = 0.3,

) -> Dict[str, Any]:

    """Run the full active synthesis pipeline.



    Args:

        domain_id: Ontology domain to target.

        collection_id: Wiki collection for proposals.

        max_gaps: Maximum gaps to process.

        auto_submit: If True, automatically submit proposals. If False, return drafts only.

        min_confidence: Minimum synthesis confidence to auto-submit.



    Returns:

        Dict with gaps_found, drafts_generated, proposals_submitted, results.

    """

    result = {

        "gaps_found": 0,

        "drafts_generated": 0,

        "proposals_submitted": 0,

        "results": [],

    }



    # Step 1: Detect gaps

    gaps = await detect_synthesis_gaps(domain_id=domain_id, max_gaps=max_gaps)

    result["gaps_found"] = len(gaps)



    # Step 2-5: Process each gap

    for gap in gaps:

        entity = gap.get("query", "")

        if not entity:

            continue



        gap_result = {

            "entity": entity,

            "gap_type": gap.get("gap_type", ""),

            "draft_generated": False,

            "proposal_submitted": False,

        }



        try:

            # Step 2: Research questions

            questions = await generate_research_questions(entity, gap)

            gap_result["research_questions"] = questions



            # Step 3: Retrieve documents

            docs = retrieve_source_documents(entity, domain_id=domain_id)

            if not docs:

                gap_result["status"] = "no_documents"

                result["results"].append(gap_result)

                continue



            # Step 4: Synthesize

            draft = await synthesize_wiki_page(entity, questions, docs)

            if not draft:

                gap_result["status"] = "synthesis_failed"

                result["results"].append(gap_result)

                continue



            gap_result["draft"] = {

                "title": draft.get("title"),

                "summary": draft.get("summary"),

                "confidence": draft.get("confidence"),

            }

            gap_result["draft_generated"] = True

            result["drafts_generated"] += 1



            # Step 5: Submit

            confidence = draft.get("confidence", 0)

            if (auto_submit and confidence >= min_confidence) or not auto_submit:

                if submit_as_proposal(draft, collection_id=collection_id):

                    gap_result["proposal_submitted"] = True

                    result["proposals_submitted"] += 1

                    gap_result["status"] = "submitted"

                else:

                    gap_result["status"] = "submit_failed"

            else:

                gap_result["status"] = "low_confidence"



        except Exception as e:

            gap_result["status"] = "error"

            gap_result["error"] = str(e)[:200]

            logger.debug("Active synthesis failed for '%s': %s", entity, e)



        result["results"].append(gap_result)



    return result





# ═══════════════════════════════════════════════════════════════

# Trigger: background run (non-blocking)

# ═══════════════════════════════════════════════════════════════



def trigger_active_synthesis(

    *,

    domain_id: str = "default",

    max_gaps: int = 5,

    auto_submit: bool = False,

) -> None:

    """Trigger active synthesis in background (non-blocking).



    Gated by AIPLAT_ACTIVE_SYNTHESIS_ENABLED (default: false).

    """

    enabled = __import__("os").getenv("AIPLAT_ACTIVE_SYNTHESIS_ENABLED", "false").lower() in ("true", "1", "yes")

    if not enabled:

        return

    import asyncio

    try:

        asyncio.create_task(

            run_active_synthesis(

                domain_id=domain_id,

                max_gaps=max_gaps,

                auto_submit=auto_submit,

            )

        )

    except Exception as e:

        logger.debug("Trigger active synthesis failed: %s", e)

