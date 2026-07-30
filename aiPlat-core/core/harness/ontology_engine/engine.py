"""

Ontology Engine — 编排本体实例生成全流程。



Usage:

  engine = OntologyEngine(domain)

  result = await engine.process_chunks(chunks, domain_id="ai-knowledge")

  # result.instances → list of {class_name, properties}

  # result.warnings → list of validation issues

"""



from __future__ import annotations

import logging

import os

import uuid



import json as _json

import time as _time

from pathlib import Path as _Path

from typing import Any, Dict, List, Optional



from core.harness.knowledge.ontology_loader import OntologyDomain, load_ontology_from_yaml

from core.harness.ontology_engine.class_mapper import ClassMapper

from core.harness.ontology_engine.property_extractor import PropertyExtractor

from core.harness.ontology_engine.state_machine import StateMachine, EvalContext, StateTransitionResult, compute_indicators

from core.harness.ontology_engine.state_history import record_transition

from core.harness.ontology_engine.graph_index import GraphIndex

from core.harness.ontology_engine.entity_resolver import EntityResolver


# ═══════════════════════════════════════════════════════════
# Action Registry bridge — zero-downtime migration from
# hardcoded side_effects to ActionRegistry
# ═══════════════════════════════════════════════════════════

_LEGACY_ACTION_MAP: Dict[str, str] = {
    "call_webhook": "builtin_webhook_executor",
    "add_tag": "builtin_add_tag",
    "mark_related_for_review": "builtin_mark_review",
    "inject_case_study": "builtin_case_study",
}


def _resolve_action_ref(effect_entry: Dict[str, Any]) -> Optional[str]:
    """Map old side_effects[].actions[].type to new ActionRegistry action_id.

    1. If 'action_ref' key exists → use directly
    2. If 'type' key is a legacy type → map to builtin bridge action
    3. Otherwise → fall back to hardcoded dispatch
    """
    if "action_ref" in effect_entry:
        return str(effect_entry["action_ref"])
    legacy_type = effect_entry.get("type", "")
    return _LEGACY_ACTION_MAP.get(legacy_type)





_EXTRACTION_SEMAPHORE = __import__('asyncio').Semaphore(5)  # Limit concurrent LLM extraction calls





class ProcessResult:

    """Structured result from ontology engine processing."""



    def __init__(self):

        self.instances: List[Dict[str, Any]] = []

        self.source_traces: List[Dict[str, Any]] = []

        self.relations: List[Dict[str, Any]] = []

        self.state_transitions: List[Dict[str, Any]] = []

        self.affected_instances: List[Dict[str, Any]] = []

        self.merge_map: Dict[str, str] = {}

        self.instance_cases: List[Dict[str, Any]] = []

        self.webhooks_fired: List[Dict[str, Any]] = []

        self.warnings: List[str] = []

        self.errors: List[str] = []

        self.stats: Dict[str, Any] = {"total_chunks": 0, "mapped_entities": 0, "extracted_instances": 0, "valid_instances": 0, "state_transitions": 0}



    def to_dict(self) -> dict:

        return {

            "instances": self.instances,

            "source_traces": self.source_traces,

            "relations": self.relations,

            "state_transitions": self.state_transitions,

            "affected_instances": self.affected_instances,

            "merge_map": self.merge_map,

            "warnings": self.warnings,

            "errors": self.errors,

            "stats": self.stats,

        }





def _clean_entity_title(title: str) -> str:

    """Strip markdown formatting and list markers from entity titles."""

    import re as _re

    cleaned = title.strip()

    cleaned = _re.sub(r'^#+\s*', '', cleaned)

    cleaned = _re.sub(r'^[-*]\s+', '', cleaned)

    cleaned = _re.sub(r'^\d+\.\s+', '', cleaned)

    cleaned = _re.sub(r'^\*\*(.*?)\*\*', r'\1', cleaned)

    cleaned = cleaned.strip()

    if not cleaned or len(cleaned) < 3:

        cleaned = title.strip()[:60]

    return cleaned[:120]





class OntologyEngine:

    """Main orchestrator for ontology instance generation."""



    def __init__(self, domain: OntologyDomain):

        self._domain = domain

        self._mapper = ClassMapper(domain)

        self._extractor = PropertyExtractor(domain)

        self._state_machine = StateMachine(domain)



    # ── Public API ──────────────────────────────────────────────────



    async def process_chunks(

        self,

        chunks: List[Dict[str, Any]],

        *,

        doc_id: str = "",

        model_name: str = "",

        class_threshold: float = 0.5,

    ) -> ProcessResult:

        """Process preprocessed chunks through the ontology engine.



        Args:

            chunks: [{"id": "c1", "text": "...", "entities": [...]}, ...]

            doc_id: source document ID for traceability

            model_name: optional model override

            class_threshold: min confidence for class mapping



        Returns:

            ProcessResult with instances, traces, warnings

        """

        result = ProcessResult()

        result.stats["total_chunks"] = len(chunks)

        seen_titles = set()



        # ── Phase 1: Classify all chunks (parallel-safe, no LLM) ──

        extraction_tasks = []  # (mapping, chunk, table_context)

        for chunk in chunks:

            chunk_id = str(chunk.get("id", ""))

            chunk_text = str(chunk.get("text", "") or "")

            entities = list(chunk.get("entities", []) or [])

            if not chunk_text:

                continue



            # Step 1: ClassMapping

            if entities:

                mappings = self._mapper.map_entities(entities, chunk_text, threshold=class_threshold)

            else:

                cls_name = self._mapper.classify_text(chunk_text, threshold=class_threshold)

                mappings = [{"entity_text": chunk_text[:80], "class_name": cls_name, "confidence": 0.7}] if cls_name else []

            result.stats["mapped_entities"] += len(mappings)



            # Prepare table context

            table_context = ""

            chunk_metadata = chunk.get("metadata", {}) or {}

            tables = chunk_metadata.get("tables", [])

            if tables:

                tc_parts = []

                for t in tables:

                    if isinstance(t, dict):

                        h = t.get("headers", [])

                        r = t.get("rows", [])

                        if h:

                            tc_parts.append(" | ".join(h))

                            tc_parts.append(" | ".join("---" for _ in h))

                        for row in r:

                            tc_parts.append(" | ".join(str(c) for c in row))

                if tc_parts:

                    table_context = "\n".join(tc_parts)



            for mapping in mappings:

                extraction_tasks.append((mapping, chunk, table_context))



        # ── Phase 2: Parallel Property Extraction (LLM) ──

        async def _extract_one(mapping, chunk, tc):

            class_name = str(mapping.get("class_name", ""))

            entity_text = str(mapping.get("entity_text", "") or "")

            confidence = float(mapping.get("confidence", 0))

            chunk_text = str(chunk.get("text", "") or "")

            async with _EXTRACTION_SEMAPHORE:

                try:

                    properties = await self._extractor.extract(

                        class_name=class_name,

                        text=chunk_text,

                        model_name=model_name,

                        table_context=tc,

                    )

                    return (class_name, entity_text, confidence, chunk, properties)

                except Exception:

                    return (class_name, entity_text, confidence, chunk, {})

        

        if extraction_tasks:

            extraction_results = await __import__('asyncio').gather(

                *[_extract_one(m, c, tc) for m, c, tc in extraction_tasks],

                return_exceptions=True

            )

        else:

            extraction_results = []



        # ── Phase 3: Validate + Build instances ──

        for er in extraction_results:

            if isinstance(er, Exception):

                continue

            class_name, entity_text, confidence, chunk, properties = er

            chunk_text = str(chunk.get("text", "") or "")

            chunk_id = str(chunk.get("id", ""))

            if not properties:

                result.warnings.append(f"No properties extracted for '{entity_text}' ({class_name})")

                continue

            result.stats["extracted_instances"] += 1



            # Step 3: Validation

            is_valid, missing, warnings = self._validate(class_name, properties)

            if not is_valid and missing:

                result.warnings.append(

                    f"Instance '{entity_text}' ({class_name}): missing fields {missing}"

                )

                if not properties:

                    continue

            result.warnings.extend(warnings)

            if is_valid:

                result.stats["valid_instances"] += 1



            # Deduplicate by title/name — clean markdown artifacts from entity names

            raw_title = properties.get("title") or properties.get("name") or entity_text

            title = _clean_entity_title(raw_title)

            if title in seen_titles:

                continue

            seen_titles.add(title)



            instance_title = title



            # ── Dynamic field fallback: auto-fill missing required + optional fields ──

            # Driven by domain YAML — zero hardcoded field names

            required = self._get_required_fields(class_name)

            optional = self._get_optional_fields(class_name)

            for field_name in required + optional:

                if properties.get(field_name) not in (None, ""):

                    continue  # already filled by LLM

                filled = self._fallback_value(field_name, class_name, instance_title, chunk_text)

                if filled is not None:

                    properties[field_name] = filled



            instance = {

                "class_name": class_name,

                "entity_text": entity_text,

                "properties": properties,

                "confidence": confidence,

                "chunk_id": chunk_id,

                "category": self._class_to_category(class_name),

                "frontmatter": {

                    **properties,

                    "title": instance_title,

                    "category": self._class_to_category(class_name),

                    "tags": [class_name.lower()],

                    "summary": str(properties.get("description", "") or "")[:200],

                },

            }

            result.instances.append(instance)



            # Step 4: Source trace

            trace = {

                "instance_title": title,

                "class_name": class_name,

                "chunk_id": chunk_id,

                "doc_id": doc_id,

                "confidence": confidence,

                "timestamp": _time.time(),

            }

            result.source_traces.append(trace)

            # Persist trace

            _persist_trace(trace)



        # ── Step 3.2: Entity Resolution (dedup & merge) ────────────

        if result.instances and len(result.instances) > 1:

            try:

                resolver = EntityResolver(self._domain)

                heading_ctx = {}

                for t in result.source_traces:

                    name = t.get("instance_title", "")

                    chunk_id = t.get("chunk_id", "")

                    if name and chunk_id:

                        heading_ctx[name] = chunk_id

                resolved = resolver.resolve(

                    result.instances,

                    doc_type=doc_id,

                    heading_context=heading_ctx,

                )

                if resolved.stats.get("merged", 0) > 0:

                    result.instances = resolved.merged

                    result.merge_map = resolved.merge_map

            except Exception as e:

                logging.debug(str(e), exc_info=True)



        # ── Step 3.4: Compute Function Indicators ─────────────────

        if result.instances:

            ctx = EvalContext(result.instances)

            compute_indicators(result.instances, ctx)



        # ── Step 3.5: State Machine Evaluation ────────────────────

        if result.instances:

            for inst in result.instances:

                chain = self._state_machine.evaluate_chain(inst, ctx)

                if chain:

                    final_state = chain[-1].to_state

                    inst["properties"]["state"] = final_state

                    inst["frontmatter"]["state"] = final_state

                    # Record each step in history

                    history = inst.get("properties", {}).get("state_history", []) or []

                    for tres in chain:

                        history.append({

                            "from": tres.from_state,

                            "to": tres.to_state,

                            "timestamp": _time.time(),

                            "trigger": tres.trigger_type,

                        })

                    inst["properties"]["state_history"] = history

                    result.stats["state_transitions"] += len(chain)

                    result.state_transitions.extend(t.to_dict() for t in chain)

                    # Persist each transition

                    for tres in chain:

                        record_transition(

                            domain_id=self._domain.id,

                            entity_name=inst.get("entity_text", ""),

                            class_name=inst.get("class_name", ""),

                            from_state=tres.from_state,

                            to_state=tres.to_state,

                            trigger_type=tres.trigger_type,

                            transition_desc=tres.transition_desc,

                            doc_id=doc_id,

                        )

                    # Apply side effects from each transition

                    for tres in chain:

                        for effect in tres.side_effects:

                            for action in effect.get("actions", []):

                                action_type = str(action.get("type", ""))

                                # ── v2.7: Action Contract validation ──

                                try:

                                    from core.harness.infrastructure.action_contract import get_action_registry

                                    reg = get_action_registry()

                                    validation = reg.validate_params(action_type, action)

                                    if not validation.get("valid"):

                                        _action_log = logging.getLogger("ontology_engine")

                                        _action_log.warning(

                                            "Action '%s' params invalid: %s — skipping",

                                            action_type, validation.get("errors", []),

                                        )

                                        continue

                                except Exception:

                                    logging.getLogger(__name__).debug('code failed', exc_info=True)
                                # ── v3: ActionRegistry bridge ──
                                resolved_id = _resolve_action_ref(action)
                                if resolved_id:
                                    try:
                                        from core.harness.ontology_engine.action_registry import get_action_registry as _get_reg
                                        _v3_reg = _get_reg()
                                        entity_id = inst.get("entity_id") or inst.get("id", "")
                                        if entity_id and _v3_reg.get(resolved_id):
                                            import asyncio as _asyncio
                                            _loop = _asyncio.get_event_loop()
                                            if _loop.is_running():
                                                _loop.create_task(_v3_reg.execute(
                                                    resolved_id, entity_id, action,
                                                    actor="state_machine", role="system"))
                                            else:
                                                _asyncio.run(_v3_reg.execute(
                                                    resolved_id, entity_id, action,
                                                    actor="state_machine", role="system"))
                                            continue
                                    except Exception:
                                        logging.getLogger(__name__).debug(
                                            'ActionRegistry bridge failed for %s', resolved_id, exc_info=True)

                                if action_type == "add_tag":

                                    tag = str(action.get("tag", ""))

                                    if tag:

                                        fm = inst.setdefault("frontmatter", {})

                                        tags = fm.setdefault("tags", [])

                                        if isinstance(tags, list) and tag not in tags:

                                            tags.append(tag)

                                elif action_type == "call_webhook":

                                    url = str(action.get("url", ""))

                                    if url:

                                        payload = {

                                            "event": "state_transition",

                                            "domain_id": self._domain.id,

                                            "entity": inst.get("entity_text", ""),

                                            "class": inst.get("class_name", ""),

                                            "from_state": tres.from_state,

                                            "to_state": tres.to_state,

                                            "trigger": tres.trigger_type,

                                            "timestamp": _time.time(),

                                        }

                                        result.webhooks_fired.append({

                                            "url": url, "payload": payload,

                                        })

                                        self._fire_webhook(url, payload)

                                elif action_type == "mark_related_for_review":

                                    rel = action.get("relation", "")

                                    target_class = self._state_machine._relation_to_target_class(rel)

                                    if target_class:

                                        for other in result.instances:

                                            if other is not inst and other.get("class_name") == target_class:

                                                result.affected_instances.append({

                                                    "from_instance": inst.get("entity_text", ""),

                                                    "from_class": inst.get("class_name", ""),

                                                    "to_instance": other.get("entity_text", ""),

                                                    "to_class": other.get("class_name", ""),

                                                    "reason": action.get("message", f"关联关系: {rel}"),

                                                    "transition": f"{tres.from_state} → {tres.to_state}",

                                                })

                                elif action_type == "inject_case_study":

                                    template = str(action.get("template", ""))

                                    rel_name = str(action.get("relation_name", "case_study_of"))

                                    rel_label = str(action.get("relation_label", "案例"))

                                    if template:

                                        rendered = template

                                        for key in ("entity_name", "class_name", "from_state", "to_state"):

                                            rendered = rendered.replace(

                                                "{{" + key + "}}",

                                                str(inst.get(key, "") or ""),

                                            )

                                        for prop_key, prop_val in inst.get("properties", {}).items():

                                            rendered = rendered.replace(

                                                "{{properties." + str(prop_key) + "}}",

                                                str(prop_val),

                                            )

                                        result.instance_cases.append({

                                            "from_instance": inst.get("entity_text", ""),

                                            "case_name": rendered[:120],

                                            "relation_name": rel_name,

                                            "relation_label": rel_label,

                                        })

                                elif action_type == "trigger_pipeline":

                                    pipeline_id = str(action.get("pipeline_id", ""))

                                    if pipeline_id:

                                        params = action.get("params", {})

                                        rendered_params = {}

                                        template_ctx = {

                                            "entity_id": inst.get("entity_id", ""),

                                            "entity_name": inst.get("entity_text", ""),

                                            "class_name": inst.get("class_name", ""),

                                            "from_state": tres.from_state,

                                            "to_state": tres.to_state,

                                            "domain_id": self._domain.id,

                                        }

                                        for k, v in params.items():

                                            val = str(v)

                                            for tkey, tval in template_ctx.items():

                                                val = val.replace("{{" + tkey + "}}", str(tval))

                                            rendered_params[k] = val

                                        try:

                                            from core.harness.execution.pipeline_engine import PipelineEngine

                                            engine = PipelineEngine()

                                            await engine.run(pipeline_id, rendered_params)

                                        except Exception as e:

                                            logging.getLogger("ontology_engine").warning(

                                                "trigger_pipeline '%s' failed: %s", pipeline_id, e)



            # ── v2.6: Process Orchestrator — check step completion after state transition ──

            try:

                from core.harness.knowledge.process_orchestrator import check_step_completion

                for inst in result.instances:

                    new_state = inst.get("properties", {}).get("state", "")

                    if new_state:

                        triggered = check_step_completion(

                            self._domain.id,

                            inst.get("class_name", ""),

                            inst.get("entity_text", ""),

                            new_state,

                        )

                        for step in triggered:

                            logging.getLogger("ontology_engine").info(

                                "Process step triggered: %s → %s (auto_create=%s)",

                                step.get("step_label", ""),

                                step.get("next_step", ""),

                                step.get("auto_create", False),

                            )

            except Exception:

                logging.getLogger(__name__).debug('code failed', exc_info=True)


        # ── Step 3.6: Persist review queue ──────────────────────

        if result.affected_instances:

            _persist_reviews(self._domain.id, result.affected_instances)



        # ── Step 5: Relation detection (co-occurrence in chunks) ──

        if result.instances and len(result.instances) >= 2:

            try:

                from core.harness.ontology_engine.relation_mapper import RelationMapper

                rm = RelationMapper(self._domain)

                # Attach chunk_id to instances for co-occurrence detection

                for i, inst in enumerate(result.instances):

                    inst["chunk_id"] = f"chunk-{i % len(chunks)}" if chunks else "default"

                result.relations = rm.detect_co_occurrence(result.instances, chunks)

            except Exception as e:

                logging.debug(str(e), exc_info=True)



        # ── Step 6: Build Graph Index ─────────────────────────────

        if result.instances:

            try:

                graph = GraphIndex.load(self._domain.id)

                # Register all instances as graph nodes

                for inst in result.instances:

                    title = inst.get("properties", {}).get("name") or inst.get("entity_text", "")

                    if title:

                        graph.add_entity(

                            entity_id=title,

                            entity_name=title,

                            class_name=inst.get("class_name", ""),

                            source_doc_id=doc_id,

                        )

                # Add detected relations to graph (if any)

                if result.relations:

                    graph.add_relations_batch(result.relations, domain=self._domain)

                graph.save()

                result.stats["graph_nodes"] = len(graph)

                result.stats["graph_edges"] = graph.stats()["edge_count"]



                # ── Step 6.0: Table rows → HyperEdge mapping ──────

                # Each table row becomes a hyperedge connecting all cell values

                for chunk in (chunks or []):

                    tables = (chunk.get("metadata", {}) or {}).get("tables", [])

                    for t in tables:

                        if isinstance(t, dict):

                            rows = t.get("rows", [])

                            for ri, row in enumerate(rows):

                                cell_entities = [str(c)[:40] for c in row if str(c).strip()]

                                if len(cell_entities) >= 2:

                                    for ce in cell_entities:

                                        if ce not in graph:

                                            graph.add_entity(ce, ce, "table_cell")

                                    graph.add_hyperedge(

                                        event_id=f"{chunk.get('id','c')}-t{ri}",

                                        entity_ids=cell_entities,

                                        context_description=f"Table row {ri}: {' | '.join(cell_entities[:5])}",

                                        source_chunk_id=str(chunk.get("id", "")),

                                    )

                graph.save()



                # ── Step 6.1: Run graph inference ─────────────────

                if getattr(self._domain, "inference_rules", None):

                    try:

                        from core.harness.ontology_engine.graph_inference import GraphInference

                        inferencer = GraphInference(self._domain, graph)

                        inf_result = inferencer.infer()

                        added = inferencer.apply_to_graph(inf_result)

                        if added:

                            graph.save()

                            result.stats["inferred_edges"] = added

                    except Exception as e:

                        logging.debug(str(e), exc_info=True)



                # ── Step 6.2: Inject case study nodes ──────────────

                if result.instance_cases:

                    try:

                        for case in result.instance_cases:

                            case_name = case.get("case_name", "")

                            from_name = case.get("from_instance", "")

                            if case_name and from_name:

                                graph.add_entity(case_name, case_name[:60], "case_study")

                                graph.add_relation(

                                    from_name, case_name,

                                    case.get("relation_name", "case_study_of"),

                                    relation_label=case.get("relation_label", "案例"),

                                )

                        graph.save()

                        result.stats["case_nodes"] = len(result.instance_cases)

                    except Exception as e:

                        logging.debug(str(e), exc_info=True)



                # ── Step 6.3: Knowledge Synthesis ────────────────

                try:

                    from core.harness.ontology_engine.knowledge_synthesis import KnowledgeSynthesizer

                    synthesizer = KnowledgeSynthesizer(graph)

                    synth_result = synthesizer.synthesize(

                        domain_id=self._domain.id, write_to_wiki=True

                    )

                    result.stats["synthesized_pages"] = synth_result.pages_written

                except Exception as e:

                    logging.debug(str(e), exc_info=True)

            except Exception as e:

                logging.debug(str(e), exc_info=True)



        return result



    async def process_text(

        self,

        text: str,

        *,

        doc_id: str = "",

        model_name: str = "",

    ) -> ProcessResult:

        """Process raw text (single chunk) through the engine."""

        chunks = [{"id": "chunk-0", "text": text, "entities": []}]

        return await self.process_chunks(chunks, doc_id=doc_id, model_name=model_name)



    # ── Action Helpers ──────────────────────────────────────────────





    async def process_from_datasource(

        self,

        source_id: str,

        *,

        doc_id: str = "",

        model_name: str = "",

    ) -> ProcessResult:

        """Palantir-style: process data from an external data source.



        Loads data via DataSourceRegistry, maps raw records to ontology instances

        via YAML field_mapping, then feeds through the standard engine pipeline.

        """

        from core.harness.ontology_engine.data_source import DataSourceRegistry



        ds = DataSourceRegistry.get_source(source_id)

        if not ds:

            result = ProcessResult()

            result.errors.append(f"Data source '{source_id}' not found or connection failed")

            return result



        raw_data = ds.fetch_all()

        if not raw_data:

            result = ProcessResult()

            result.warnings.append(f"No data fetched from source '{source_id}'")

            return result



        # Map raw records to chunks

        config = DataSourceRegistry._configs.get(source_id)

        chunks = []

        for record in raw_data:

            mapped = DataSourceRegistry.map_to_ontology(record, source_id)

            chunks.append({

                "id": f"ds-{source_id}-{len(chunks)}",

                "text": _json.dumps(record, ensure_ascii=False)[:3000],

                "entities": [],

                "metadata": {

                    "source_id": source_id,

                    "source_type": getattr(ds.config, "source_type", ""),

                    "mapped_class": mapped.get("class_name", ""),

                    "mapped_properties": mapped.get("properties", {}),

                },

            })



        return await self.process_chunks(chunks, doc_id=doc_id or f"ds:{source_id}", model_name=model_name)





    def _fire_webhook(self, url: str, payload: dict):

        """Fire a webhook asynchronously (best-effort, non-blocking)."""

        import asyncio as _asyncio

        try:

            loop = _asyncio.get_event_loop()

            if loop.is_running():

                loop.create_task(self._post_webhook(url, payload))

            else:

                _asyncio.run(self._post_webhook(url, payload))

        except Exception as e:

            logging.debug(str(e), exc_info=True)



    async def _post_webhook(self, url: str, payload: dict):

        """Post JSON payload to a webhook URL."""

        import aiohttp

        try:

            async with aiohttp.ClientSession() as session:

                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:

                    pass  # Fire-and-forget

        except Exception as e:

            logging.debug(str(e), exc_info=True)



    # ── Helpers ─────────────────────────────────────────────────────



    def _validate(self, class_name: str, properties: Dict[str, Any]) -> tuple:

        """Validate extracted properties against class definition."""

        cls = None

        for c in self._domain.classes:

            if c.label == class_name:

                cls = c

                break

        if cls is None:

            return True, [], []



        missing = []

        for rf in cls.required_fields:

            val = properties.get(rf)

            if val is None or (isinstance(val, str) and not val.strip()) or (isinstance(val, list) and not val):

                missing.append(rf)



        warnings = []

        # Enum check

        for f in (cls.fields or []):

            fname = f.get("name", "")

            fvalues = f.get("values", [])

            if fvalues and fname in properties:

                val = properties[fname]

                if isinstance(val, str) and val not in fvalues:

                    # Try case-insensitive match

                    if val.lower() not in [v.lower() for v in fvalues]:

                        warnings.append(f"Field '{fname}' value '{val}' not in enum {fvalues}")



        return len(missing) == 0, missing, warnings



    def _class_to_category(self, class_name: str) -> str:

        """Map class label to wiki category."""

        for cls in self._domain.classes:

            if cls.label == class_name:

                cats = cls.allowed_categories

                return cats[0] if cats else "entities"

        return "entities"



    def _get_required_fields(self, class_name: str) -> list:

        """Get required field names for a class."""

        for cls in self._domain.classes:

            if cls.label == class_name:

                return list(cls.required_fields or [])

        return []



    def _get_optional_fields(self, class_name: str) -> list:

        """Get optional field names for a class."""

        for cls in self._domain.classes:

            if cls.label == class_name:

                return list(cls.optional_fields or [])

        return []



    def _fallback_value(self, field_name: str, class_name: str,

                        instance_title: str, chunk_text: str) -> Any:

        """Derive a sensible fallback value for a missing field.

        

        Uses field name patterns + context — zero hardcoded domain-specific names.

        Returns None if no reasonable fallback exists.

        """

        fn = field_name.lower()

        # ── Text from instance title ──

        if fn in ("name", "title", "project_number", "discipline_code", "equipment_id",

                  "system_code", "zone_code", "drawing_number", "document_number",

                  "change_id", "comment_id", "report_id"):

            return instance_title[:200]

        # ── Text from chunk body ──

        if fn in ("description", "body", "content", "definition", "key_insights",

                  "reason", "impact", "symptoms", "solution", "steps",

                  "pre_checks", "rollback_steps", "rollback_plan", "risk_assessment",

                  "resolution_steps", "prevention", "industry_context",

                  "current_solutions", "integration_doc"):

            clean = chunk_text.strip()[:800]

            return clean if clean else instance_title[:300]

        # ── Enum/text defaults ──

        if fn in ("maturity", "status", "state", "lifecycle_state"):

            return "draft"

        if fn in ("version",):

            return "1.0"

        if fn in ("severity", "frequency", "impact_scope", "risk_level"):

            return "medium"

        if fn in ("change_type", "type", "category",

                  "discipline", "responsible_discipline"):

            return class_name  # derive from mapped class

        if fn in ("environment",):

            return "production"

        if fn in ("dwt",):

            return "0"

        if fn in ("delivery_date", "scheduled_time", "executed_time",

                  "trigger_time", "resolve_time", "resolution_date"):

            return ""  # timestamp requires real data, leave empty

        if fn in ("owner", "lead_engineer", "requester", "approved_by",

                  "resolved_by", "responsible_team", "owner_team", "supplier"):

            return ""  # person/team names not inferrable

        if fn in ("tags",):

            return [class_name.lower()]

        # ── Numeric/project-specific — leave to LLM ──

        if fn in ("alternatives", "paper_ref", "dependencies", "components",

                  "metrics", "examples", "papers", "source_url", "authors",

                  "year", "publisher", "model", "parameters", "location",

                  "template", "value", "file_path", "ip", "os", "endpoint",

                  "related_systems", "affected_drawings", "affected_equipment",

                  "affected_services", "depends_on", "references",

                  "triggers", "permissions", "effects", "difficulty_level",

                  "diagram_ref", "release_date", "yard", "class_society",

                  "deck", "frame_range", "scale", "revision",

                  "related_equipment", "related_sop_id", "response",

                  "change_history", "state_history", "confidence",

                  "source_articles", "evidence", "relationships",

                  "contradictions", "stale_references", "images",

                  "marking", "field_level_permission", "lifecycle_state",

                  "quality_score", "source_doc_id", "evidence_start",

                  "evidence_end", "evidence_text", "supports_atom_index",

                  "contradicts_atom_index", "_generated_by", "last_updated",

                  "_body", "_category", "_path"):

            return None  # not inferrable without LLM or real data

        # ── Unknown fields: try to extract from chunk text ──

        return None





def load_engine(domain_id: str = "ai-knowledge") -> Optional[OntologyEngine]:

    """Factory: load engine for a domain_id."""

    import os as _os

    d = _Path(_os.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontologies"

    file_path = d / f"{domain_id}.yaml"

    if not file_path.exists():

        return None

    domain = load_ontology_from_yaml(str(file_path))

    return OntologyEngine(domain)





# ── Graph singleton ──────────────────────────────────────────────────



_graph_cache: dict = {}

_graph_cache_order: list = []  # LRU tracking



_MAX_GRAPH_CACHE = 5  # keep at most 5 domain graphs in memory



def get_graph(domain_id: str = "ai-knowledge") -> GraphIndex:

    """Get or load the graph for a domain. Thread-safe via dict cache."""

    global _graph_cache_order

    if domain_id not in _graph_cache:

        _graph_cache[domain_id] = GraphIndex.load(domain_id)

    else:

        _graph_cache_order.remove(domain_id)

    _graph_cache_order.append(domain_id)

    # Evict oldest if exceeding cap

    while len(_graph_cache_order) > _MAX_GRAPH_CACHE:

        old = _graph_cache_order.pop(0)

        if old in _graph_cache:

            del _graph_cache[old]

    return _graph_cache[domain_id]





# ── Sharded Graph singleton ─────────────────────────────────────────



_sharded_graph: Optional[Any] = None



def get_sharded_graph() -> Any:

    """Get or create the cross-domain sharded graph aggregator."""

    global _sharded_graph

    if _sharded_graph is None:

        from core.harness.ontology_engine.sharded_graph import ShardedGraphIndex

        _sharded_graph = ShardedGraphIndex()

    return _sharded_graph





def _persist_trace(trace: Dict[str, Any]) -> None:

    """Persist source trace to disk."""

    import os as _os2

    traces_dir = _Path(_os2.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontology_traces"

    traces_dir.mkdir(parents=True, exist_ok=True)

    safe = str(trace.get("instance_title", "unknown")).replace("/", "_")[:120]

    trace_file = traces_dir / f"{safe}.json"

    trace_file.write_text(_json.dumps(trace, ensure_ascii=False, indent=2))





def _persist_reviews(domain_id: str, affected: List[Dict[str, Any]]) -> None:

    """Persist review queue for entities needing human review.

    

    Phase 7: optionally trigger ApprovalWorkflow for high-risk entities (best-effort).

    """

    # Phase 7: best-effort approval workflow trigger

    if affected and os.getenv("AIPLAT_ONTOLOGY_APPROVAL_ENABLED", "").lower() in ("true", "1", "yes"):

        try:

            import asyncio

            from core.harness.ontology_engine.approval import get_approval_workflow

            wf = get_approval_workflow()

            loop = asyncio.get_event_loop()

            if loop.is_running():

                for entity in affected[:5]:

                    loop.create_task(wf.submit(

                        entity.get("instance_id", str(uuid.uuid4())),

                        entity.get("target_state", "PUBLISHED"),

                        assignee="admin",

                    ))

            else:

                asyncio.run(wf.submit(

                    affected[0].get("instance_id", str(uuid.uuid4())),

                    affected[0].get("target_state", "PUBLISHED"),

                    assignee="admin",

                ))

        except Exception:

            logging.getLogger(__name__).debug('_persist_reviews failed', exc_info=True)
    """Persist affected_instances to review queue for this domain."""

    import os as _os3

    reviews_dir = _Path(_os3.getenv("AIPLAT_HOME", _Path("~").expanduser() / ".aiplat")) / "ontology_reviews"

    reviews_dir.mkdir(parents=True, exist_ok=True)

    review_file = reviews_dir / f"{domain_id}.json"



    existing = []

    if review_file.exists():

        try:

            existing = _json.loads(review_file.read_text())

        except Exception:

            existing = []



    now = _time.time()

    for aff in affected:

        entry = {

            "id": f"{aff.get('from_instance','')}_{aff.get('to_instance','')}",

            "from_instance": aff.get("from_instance", ""),

            "from_class": aff.get("from_class", ""),

            "to_instance": aff.get("to_instance", ""),

            "to_class": aff.get("to_class", ""),

            "reason": aff.get("reason", ""),

            "transition": aff.get("transition", ""),

            "timestamp": now,

            "status": "pending",

        }

        if not any(e.get("id") == entry["id"] for e in existing):

            existing.append(entry)



    review_file.write_text(_json.dumps(existing, ensure_ascii=False, indent=2))





# ── Global: fire-and-forget pipeline trigger ────────────────────



async def trigger_pipeline(pipeline_id: str, params: dict | None = None) -> None:

    """Fire-and-forget pipeline execution. Used by side_effects and event handlers."""

    try:

        from core.harness.execution.pipeline_engine import PipelineEngine

        engine = PipelineEngine()

        await engine.run(pipeline_id, params or {})

    except Exception as e:

        import logging as _log

        _log.getLogger("trigger_pipeline").debug(

            "Pipeline '%s' skipped: %s", pipeline_id, e)

