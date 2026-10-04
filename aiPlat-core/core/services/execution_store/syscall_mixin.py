"""
SyscallMixin — extracted from ExecutionStore events_mixin.py.

Auto-generated via Mixin split. Contains entity-specific CRUD methods.
"""
from typing import Any, Dict, List, Optional, Tuple
import json, time, sqlite3, logging
import anyio
import uuid
from ._base import _derive_change_summary, _json_dumps, _json_loads, run_store_io


class SyscallMixin:
    """Extracted from ExecutionStore."""
    # ==================== Syscall Events (Audit) ====================

    async def _insert_event_raw(self, event: Dict[str, Any]) -> None:
        """Pure SQL INSERT — no EventBus publish, no side effects. Used by DLQ worker."""
        if isinstance(event, dict):
            _k = str(event.get("kind") or "").strip()
            _n = str(event.get("name") or "").strip()
            if not _k and not _n:
                return
        # Best-effort validation
        try:
            from core.harness.observation.event_schema import SyscallEvent
            SyscallEvent.model_validate(event)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        await self.init()
        db_path = self._config.db_path

        error_code = event.get("error_code")
        if not error_code:
            try:
                err_obj = event.get("error") if isinstance(event.get("error"), dict) else None
                if isinstance(err_obj, dict) and err_obj.get("code"):
                    error_code = err_obj.get("code")
                else:
                    err_str = event.get("error")
                    if isinstance(err_str, str) and err_str.strip():
                        error_code = err_str.strip().upper().replace(" ", "_")[:64]
            except Exception:
                error_code = None

        payload = (
            event.get("id") or str(uuid.uuid4()),
            event.get("trace_id"),
            event.get("span_id"),
            event.get("run_id"),
            event.get("tenant_id"),
            event.get("kind") or "",
            event.get("name") or "",
            event.get("status") or "",
            event.get("start_time"),
            event.get("end_time"),
            event.get("duration_ms"),
            _json_dumps(event.get("args") or {}),
            _json_dumps(event.get("result") or {}),
            event.get("error") if isinstance(event.get("error"), str) else _json_dumps(event.get("error") or None),
            error_code,
            event.get("target_type"),
            event.get("target_id"),
            event.get("user_id"),
            event.get("session_id"),
            event.get("approval_request_id"),
            float(event.get("created_at") or time.time()),
            int(event.get("input_tokens") or 0),
            int(event.get("output_tokens") or 0),
            float(event.get("cost") or 0.0),
            event.get("parent_span_id"),
        )

        def _sync():
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO syscall_events(
                      id, trace_id, span_id, run_id, tenant_id, kind, name, status, start_time, end_time, duration_ms,
                      args_json, result_json, error, error_code, target_type, target_id, user_id, session_id,
                      approval_request_id, created_at, input_tokens, output_tokens, cost, parent_span_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()

        await run_store_io(_sync)

    async def add_syscall_event(self, event: Dict[str, Any]) -> None:
        """Append a syscall audit event (best-effort)."""
        # Reject EventBus SSE ghosts: graph_done / graph_upsert envelopes have no
        # kind/name — persisting them shows as UI「event / unknown」(run-5fc64fbf7c96).
        if isinstance(event, dict):
            _k = str(event.get("kind") or "").strip()
            _n = str(event.get("name") or "").strip()
            if not _k and not _n:
                logging.debug(
                    "add_syscall_event skip empty kind/name keys=%s",
                    list(event.keys())[:10],
                )
                return
        # Guard: never let routing/work events reuse a ReAct container span_id
        # (step:/agent:/skill:) — that overwrites the step card in RunGraph.
        try:
            if isinstance(event, dict):
                sid = str(event.get("span_id") or "")
                name = str(event.get("name") or "")
                kind = str(event.get("kind") or "")
                is_container_sid = sid.startswith(("step:", "agent:", "skill:"))
                is_container_name = (
                    name.startswith("step_")
                    or kind == "step"
                    or name in ("agent_start", "agent_end", "skill_start", "skill_end")
                )
                if is_container_sid and not is_container_name:
                    parent = str(event.get("parent_span_id") or sid)
                    if not event.get("parent_span_id"):
                        event["parent_span_id"] = sid
                    event["span_id"] = f"{kind or 'work'}:{name or 'event'}:{sid}"
                    if str(event.get("parent_span_id") or "") == str(event.get("span_id") or ""):
                        event["parent_span_id"] = parent if parent != event["span_id"] else ""
        except Exception:
            logging.debug("span_id container collision rewrite failed", exc_info=True)
        # Best-effort validation via Pydantic schema
        try:
            from core.harness.observation.event_schema import SyscallEvent
            SyscallEvent.model_validate(event)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        await self.init()
        db_path = self._config.db_path

        # Best-effort normalize error_code for aggregation.
        error_code = event.get("error_code")
        if not error_code:
            try:
                # Prefer structured error object.
                err_obj = event.get("error") if isinstance(event.get("error"), dict) else None
                if isinstance(err_obj, dict) and err_obj.get("code"):
                    error_code = err_obj.get("code")
                else:
                    err_str = event.get("error")
                    if isinstance(err_str, str) and err_str.strip():
                        # Map common cases; fallback to uppercase token.
                        m = err_str.strip().upper().replace(" ", "_")
                        error_code = m[:64]
            except Exception:
                error_code = None

        payload = (
            event.get("id") or str(uuid.uuid4()),
            event.get("trace_id"),
            event.get("span_id"),
            event.get("run_id"),
            event.get("tenant_id"),
            event.get("kind") or "",
            event.get("name") or "",
            event.get("status") or "",
            event.get("start_time"),
            event.get("end_time"),
            event.get("duration_ms"),
            _json_dumps(event.get("args") or {}),
            _json_dumps(event.get("result") or {}),
            event.get("error") if isinstance(event.get("error"), str) else _json_dumps(event.get("error") or None),
            error_code,
            event.get("target_type"),
            event.get("target_id"),
            event.get("user_id"),
            event.get("session_id"),
            event.get("approval_request_id"),
            float(event.get("created_at") or time.time()),
            int(event.get("input_tokens") or 0),
            int(event.get("output_tokens") or 0),
            float(event.get("cost") or 0.0),
            event.get("parent_span_id"),
        )

        def _sync():
            conn = self._connect()
            try:
                # UPSERT: close-before-generate reuses id ``{run}:pre_llm_prep`` with
                # status=ok; INSERT OR IGNORE left the row stuck at running and orphan
                # wrongly fired pre_llm_prep_stalled (run-c8dda3ff18d4).
                conn.execute(
                    """
                    INSERT INTO syscall_events(
                      id, trace_id, span_id, run_id, tenant_id, kind, name, status, start_time, end_time, duration_ms,
                      args_json, result_json, error, error_code, target_type, target_id, user_id, session_id,
                      approval_request_id, created_at, input_tokens, output_tokens, cost, parent_span_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                      status=excluded.status,
                      end_time=COALESCE(excluded.end_time, syscall_events.end_time),
                      duration_ms=COALESCE(excluded.duration_ms, syscall_events.duration_ms),
                      args_json=CASE
                        WHEN excluded.args_json IS NOT NULL AND excluded.args_json != '{}' AND excluded.args_json != 'null'
                        THEN excluded.args_json ELSE syscall_events.args_json END,
                      result_json=CASE
                        WHEN excluded.result_json IS NOT NULL AND excluded.result_json != '{}' AND excluded.result_json != 'null'
                        THEN excluded.result_json ELSE syscall_events.result_json END,
                      error=COALESCE(excluded.error, syscall_events.error),
                      error_code=COALESCE(excluded.error_code, syscall_events.error_code),
                      input_tokens=CASE
                        WHEN excluded.input_tokens > 0 THEN excluded.input_tokens
                        ELSE syscall_events.input_tokens END,
                      output_tokens=CASE
                        WHEN excluded.output_tokens > 0 THEN excluded.output_tokens
                        ELSE syscall_events.output_tokens END,
                      cost=CASE
                        WHEN excluded.cost > 0 THEN excluded.cost
                        ELSE syscall_events.cost END,
                      parent_span_id=COALESCE(excluded.parent_span_id, syscall_events.parent_span_id),
                      trace_id=COALESCE(excluded.trace_id, syscall_events.trace_id),
                      span_id=COALESCE(excluded.span_id, syscall_events.span_id);
                    """,
                    payload,
                )
                conn.commit()
            finally:
                conn.close()

        # Dedicated store pool — never share with LLM asyncio.to_thread zombies
        # (run-1a2dd36236ae: generate=success then no routing; status API hung).
        await run_store_io(_sync)
        # Publish to real-time observation layer (best-effort, non-blocking)
        try:
            from core.harness.observation.event_bus import EventBus
            publish_event = dict(event)
            publish_event.setdefault("input_tokens", int(event.get("input_tokens") or 0))
            publish_event.setdefault("output_tokens", int(event.get("output_tokens") or 0))
            publish_event.setdefault("cost", float(event.get("cost") or 0.0))
            EventBus.publish(str(event.get("run_id") or ""), publish_event)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        # Export to OpenTelemetry (best-effort)
        try:
            from core.harness.observation.otel_bridge import export_syscall_as_span
            export_syscall_as_span(event)
        except Exception as e:
            logging.debug(str(e), exc_info=True)
        # Mirror into RunGraph when this run already has a graph projection
        try:
            import asyncio as _aio_mirror

            from core.harness.observation.run_graph import mirror_syscall_to_graph

            await _aio_mirror.wait_for(mirror_syscall_to_graph(event), timeout=5.0)
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    async def close_running_syscall_events(
        self,
        run_id: str,
        *,
        status: str = "timeout",
        error: Optional[str] = None,
        error_code: Optional[str] = None,
        kind: Optional[str] = None,
        name: Optional[str] = None,
    ) -> int:
        """Flip still-running syscall rows to a terminal status (orphan / cancel).

        Optional ``kind`` / ``name`` filter (e.g. kind=llm, name=generate) so a nested
        LLM finish does not prematurely close the parent skill/agent running row.
        """
        await self.init()
        rid = str(run_id or "").strip()
        if not rid:
            return 0
        end_t = time.time()
        st = str(status or "timeout")
        err = error if isinstance(error, str) else None
        code = error_code if isinstance(error_code, str) else None
        kind_f = str(kind or "").strip().lower() or None
        name_f = str(name or "").strip() or None

        def _sync() -> int:
            conn = self._connect()
            try:
                clauses = ["run_id=?", "lower(status)='running'"]
                params: list = [rid]
                if kind_f:
                    clauses.append("lower(kind)=?")
                    params.append(kind_f)
                if name_f:
                    clauses.append("name=?")
                    params.append(name_f)
                where = " AND ".join(clauses)
                cur = conn.execute(
                    f"""
                    UPDATE syscall_events
                       SET status=?,
                           end_time=?,
                           duration_ms=CASE
                             WHEN start_time IS NOT NULL AND start_time > 0
                             THEN (? - start_time) * 1000.0
                             ELSE COALESCE(duration_ms, 0)
                           END,
                           error=COALESCE(?, error),
                           error_code=COALESCE(?, error_code)
                     WHERE {where}
                    """,
                    (st, end_t, end_t, err, code, *params),
                )
                conn.commit()
                return int(cur.rowcount or 0)
            finally:
                conn.close()

        n = int(await run_store_io(_sync))
        # Syscall UPDATE does not go through add_syscall_event → mirror. Always try to
        # close matching RunGraph cards — even when n==0 (UPSERT already flipped the
        # row to success, so UPDATE matched nothing). Without this, canvas stays on
        # 「推理 · generate」while syscall is success (run-ff1319e103fd).
        if name_f == "pre_llm_prep":
            try:
                if hasattr(self, "list_run_graph_nodes") and hasattr(self, "upsert_run_graph_node"):
                    gstat = (
                        "ok"
                        if st in ("ok", "success", "completed", "done")
                        else ("error" if st in ("error", "failed", "timeout") else "ok")
                    )
                    seal_end = time.time()
                    for node in await self.list_run_graph_nodes(rid):
                        if str(node.get("status") or "").lower() != "running":
                            continue
                        if str(node.get("name") or "") != "pre_llm_prep":
                            continue
                        start = node.get("start_time")
                        dur = None
                        if start is not None:
                            try:
                                dur = (float(seal_end) - float(start)) * 1000.0
                            except Exception:
                                dur = None
                        await self.upsert_run_graph_node(
                            {
                                "run_id": rid,
                                "node_id": node.get("node_id"),
                                "parent_id": node.get("parent_id"),
                                "kind": node.get("kind") or "context",
                                "name": "pre_llm_prep",
                                "label": node.get("label") or "pre_llm_prep",
                                "role": node.get("role") or "work",
                                "status": gstat,
                                "start_time": start or seal_end,
                                "end_time": seal_end,
                                "duration_ms": dur if dur is not None else node.get("duration_ms"),
                                "args": node.get("args") or {},
                                "updated_at": seal_end,
                            }
                        )
            except Exception:
                logging.debug("close_running: graph pre_llm_prep close failed", exc_info=True)
        if kind_f == "llm" and (name_f or "") in ("generate", "generate_stream", ""):
            try:
                if hasattr(self, "list_run_graph_nodes") and hasattr(self, "upsert_run_graph_node"):
                    for node in await self.list_run_graph_nodes(rid):
                        if str(node.get("status") or "").lower() != "running":
                            continue
                        nm = str(node.get("name") or "")
                        if name_f and nm != name_f:
                            continue
                        if not name_f and nm not in ("generate", "generate_stream"):
                            continue
                        start = node.get("start_time")
                        # Prefer syscall end_time when UPSERT already closed the row.
                        seal_end = end_t
                        try:
                            if hasattr(self, "list_syscall_events"):
                                ev = await self.list_syscall_events(run_id=rid, limit=80)
                                items = (ev or {}).get("items") if isinstance(ev, dict) else (ev or [])
                                best_end = -1.0
                                for it in items or []:
                                    if not isinstance(it, dict):
                                        continue
                                    if str(it.get("kind") or "").lower() != "llm":
                                        continue
                                    if str(it.get("name") or "") not in ("generate", "generate_stream"):
                                        continue
                                    if str(it.get("status") or "").lower() not in (
                                        "success", "ok", "completed", "done", "timeout", "failed", "error",
                                    ):
                                        continue
                                    e1 = float(it.get("end_time") or 0.0)
                                    if e1 > best_end:
                                        best_end = e1
                                if best_end > 0:
                                    seal_end = best_end
                        except Exception:
                            pass  # noqa: cleanup-best-effort
                        dur = None
                        if start is not None:
                            try:
                                dur = (float(seal_end) - float(start)) * 1000.0
                            except Exception:
                                dur = None
                        gstat = "ok" if st in ("ok", "success", "completed", "done") else (
                            "error" if st in ("error", "failed", "timeout") else "ok"
                        )
                        await self.upsert_run_graph_node(
                            {
                                "run_id": rid,
                                "node_id": node.get("node_id"),
                                "parent_id": node.get("parent_id"),
                                "kind": node.get("kind") or "llm",
                                "name": nm,
                                "label": node.get("label") or nm,
                                "role": node.get("role") or "work",
                                "status": gstat,
                                "start_time": start or seal_end,
                                "end_time": seal_end,
                                "duration_ms": dur if dur is not None else node.get("duration_ms"),
                                "args": node.get("args") or {},
                                "updated_at": seal_end,
                            }
                        )
            except Exception:
                logging.debug("close_running: graph generate close failed", exc_info=True)
        # Unfiltered seal (Agent row already terminal): leftover canvas cards such as
        # pre_llm_prep / step_N / agent_start stay 「执行中」after auto_done if we only
        # mirror llm:generate (qa_agent run-124d89d5ef3f — step_2 「准备 · LLM 前置」).
        if not kind_f and not name_f:
            try:
                if hasattr(self, "list_run_graph_nodes") and hasattr(self, "upsert_run_graph_node"):
                    gstat = (
                        "ok"
                        if st in ("ok", "success", "completed", "done")
                        else ("error" if st in ("error", "failed", "timeout") else "ok")
                    )
                    for node in await self.list_run_graph_nodes(rid):
                        if str(node.get("status") or "").lower() != "running":
                            continue
                        start = node.get("start_time")
                        dur = None
                        if start is not None:
                            try:
                                dur = (float(end_t) - float(start)) * 1000.0
                            except Exception:
                                dur = None
                        await self.upsert_run_graph_node(
                            {
                                "run_id": rid,
                                "node_id": node.get("node_id"),
                                "parent_id": node.get("parent_id"),
                                "kind": node.get("kind") or "work",
                                "name": node.get("name"),
                                "label": node.get("label") or node.get("name"),
                                "role": node.get("role") or "work",
                                "status": gstat,
                                "start_time": start or end_t,
                                "end_time": end_t,
                                "duration_ms": dur if dur is not None else node.get("duration_ms"),
                                "args": node.get("args") or {},
                                "updated_at": end_t,
                            }
                        )
            except Exception:
                logging.debug("close_running: leftover graph seal failed", exc_info=True)
        return n

    async def add_import_audit(
        self,
        *,
        skill_id: str,
        skill_name: str = "",
        source_type: str = "",
        pattern: str = "",
        adapted: bool = False,
        lint_errors: int = 0,
        lint_warnings: int = 0,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an import audit event for skill compliance tracking."""
        await self.init()
        db_path = self._config.db_path

        def _sync():
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO import_audits(skill_id, skill_name, source_type, pattern, adapted,
                      lint_errors, lint_warnings, details_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(skill_id),
                        str(skill_name),
                        str(source_type),
                        str(pattern),
                        1 if adapted else 0,
                        int(lint_errors),
                        int(lint_warnings),
                        _json_dumps(details or {}),
                        float(time.time()),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        await run_store_io(_sync)

    async def list_syscall_events(
        self,
        limit: int = 100,
        offset: int = 0,
        tenant_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        run_id: Optional[str] = None,
        kind: Optional[str] = None,
        name: Optional[str] = None,
        status: Optional[str] = None,
        error_contains: Optional[str] = None,
        error_code: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        approval_request_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List syscall events with basic filters (best-effort; no FTS)."""
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                clauses = []
                params: list = []
                if tenant_id:
                    clauses.append("tenant_id=?")
                    params.append(str(tenant_id))
                if trace_id:
                    clauses.append("trace_id=?")
                    params.append(trace_id)
                if span_id:
                    clauses.append("span_id=?")
                    params.append(span_id)
                if run_id:
                    clauses.append("run_id=?")
                    params.append(run_id)
                if kind:
                    clauses.append("kind=?")
                    params.append(kind)
                if status:
                    clauses.append("status=?")
                    params.append(status)
                if name:
                    clauses.append("name LIKE ?")
                    params.append(f"%{name}%")
                if error_contains:
                    clauses.append("error LIKE ?")
                    params.append(f"%{error_contains}%")
                if error_code:
                    clauses.append("error_code=?")
                    params.append(error_code)
                if target_type:
                    clauses.append("target_type=?")
                    params.append(target_type)
                if target_id:
                    clauses.append("target_id=?")
                    params.append(target_id)
                if approval_request_id:
                    clauses.append("approval_request_id=?")
                    params.append(approval_request_id)
                where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

                total_row = conn.execute(f"SELECT COUNT(*) AS c FROM syscall_events {where_sql}", tuple(params)).fetchone()
                total = int(total_row["c"] if total_row else 0)
                rows = conn.execute(
                    f"""
                    SELECT * FROM syscall_events
                    {where_sql}
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    tuple(params + [int(limit), int(offset)]),
                ).fetchall()

                items = []
                for r in rows:
                    items.append(
                        {
                            "id": r["id"],
                            "trace_id": r["trace_id"],
                            "span_id": r["span_id"] if "span_id" in r.keys() else None,
                            "parent_span_id": r["parent_span_id"] if "parent_span_id" in r.keys() else None,
                            "run_id": r["run_id"],
                            "kind": r["kind"],
                            "name": r["name"],
                            "status": r["status"],
                            "start_time": r["start_time"],
                            "end_time": r["end_time"],
                            "duration_ms": r["duration_ms"],
                            "args": _json_loads(r["args_json"]) or {},
                            "result": _json_loads(r["result_json"]) or {},
                            "error": r["error"],
                            "error_code": r["error_code"] if "error_code" in r.keys() else None,
                            "target_type": r["target_type"] if "target_type" in r.keys() else None,
                            "target_id": r["target_id"] if "target_id" in r.keys() else None,
                            "user_id": r["user_id"] if "user_id" in r.keys() else None,
                            "session_id": r["session_id"] if "session_id" in r.keys() else None,
                            "tenant_id": r["tenant_id"] if "tenant_id" in r.keys() else None,
                            "approval_request_id": r["approval_request_id"] if "approval_request_id" in r.keys() else None,
                            "input_tokens": r["input_tokens"] if "input_tokens" in r.keys() else 0,
                            "output_tokens": r["output_tokens"] if "output_tokens" in r.keys() else 0,
                            "cost": r["cost"] if "cost" in r.keys() else 0.0,
                            "created_at": r["created_at"],
                        }
                    )
                return {"items": items, "total": total}
            finally:
                conn.close()

        return await run_store_io(_sync)

    # ==================== Change Control (Derived from syscall_events) ====================

    async def list_change_controls(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List change controls (grouped by change_id) from syscall_events.

        Source of truth:
          syscall_events(kind='changeset', target_type='change', target_id=change_id)
        """
        await self.init()
        db_path = self._config.db_path

        def _sync() -> Dict[str, Any]:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            try:
                clauses = ["kind='changeset'", "target_type='change'", "target_id IS NOT NULL", "target_id != ''"]
                params: list = []
                if tenant_id:
                    clauses.append("tenant_id=?")
                    params.append(str(tenant_id))
                where = " AND ".join(clauses)
                clauses_e = ["e.kind='changeset'", "e.target_type='change'", "e.target_id IS NOT NULL", "e.target_id != ''"]
                if tenant_id:
                    clauses_e.append("e.tenant_id=?")
                where_e = " AND ".join(clauses_e)

                total_row = conn.execute(f"SELECT COUNT(DISTINCT target_id) AS c FROM syscall_events WHERE {where};", params).fetchone()
                total = int(total_row["c"] if total_row else 0)

                rows = conn.execute(
                    f"""
                    SELECT e.*
                    FROM syscall_events e
                    JOIN (
                      SELECT target_id, MAX(created_at) AS last_ts
                      FROM syscall_events
                      WHERE {where}
                      GROUP BY target_id
                    ) t
                    ON e.target_id = t.target_id AND e.created_at = t.last_ts
                    WHERE {where_e}
                    ORDER BY e.created_at DESC
                    LIMIT ? OFFSET ?;
                    """,
                    [*params, int(limit), int(offset)],
                ).fetchall()

                return {"items": [dict(r) for r in rows], "total": total}
            finally:
                conn.close()

        raw = await anyio.to_thread.run_sync(_sync)
        out_items = []
        for r in raw.get("items") or []:
            args = _json_loads(r.get("args_json")) or {}
            result = _json_loads(r.get("result_json")) or {}
            change_id = r.get("target_id")
            latest = {**r, "args": args, "result": result, "change_id": change_id}
            out_items.append({**latest, "summary": _derive_change_summary(latest)})
        return {"items": out_items, "total": int(raw.get("total") or 0), "limit": int(limit), "offset": int(offset)}

    async def get_change_control(
        self,
        *,
        change_id: str,
        limit: int = 200,
        offset: int = 0,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a change control detail: latest + events."""
        items = await self.list_syscall_events(
            limit=int(limit),
            offset=int(offset),
            tenant_id=tenant_id,
            kind="changeset",
            target_type="change",
            target_id=str(change_id),
        )
        latest = (items.get("items") or [None])[0] if isinstance(items.get("items"), list) and items.get("items") else None
        summary = _derive_change_summary(latest) if isinstance(latest, dict) else _derive_change_summary(None)
        return {"change_id": str(change_id), "latest": latest, "events": {**items, "limit": int(limit), "offset": int(offset)}, "summary": summary}

