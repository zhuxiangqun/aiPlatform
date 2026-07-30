"""
LineageStore — 决策血缘持久化层 (Phase 41 Decision Lineage)

在 agent 每次做出工具选择 / 参数决策 / 降级触发时记录:
  - 谁 (agent_id, role)
  - 何时 (decided_at)
  - 基于什么上下文版本 (ontology_version, kb_collection_version, context_snapshot_id)
  - 选了哪个选项 (chosen_option)
  - 为什么 (choice_reasoning)
  - 结果如何 (outcome_status, outcome_summary)

表: lineage_decisions (schema v53)
调用者: decision_capture.py → sys_tool_call / sys_skill_call
查询者: LineageViewer 前端 → GET /api/platform/apps/fde/lineage/{run_id}
"""

from __future__ import annotations

import json as _json
import logging
import sqlite3 as _sqlite3
import time as _time
import uuid as _uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Data Model
# ══════════════════════════════════════════════════════════════

class DecisionRecord:
    """单条决策记录."""

    __slots__ = (
        "decision_id", "run_id", "trace_id",
        "agent_id", "actor_role",
        "decided_at",
        "context_snapshot_id", "ontology_version", "kb_collection_version",
        "decision_type",
        "options_considered", "chosen_option", "choice_reasoning",
        "outcome_status", "outcome_summary", "cascaded_decisions",
        "policy_version", "constraint_checks",
        "source_call",
    )

    def __init__(
        self,
        *,
        run_id: str,
        decision_type: str,
        chosen_option: str,
        trace_id: str = "",
        agent_id: str = "",
        actor_role: str = "",
        context_snapshot_id: str = "",
        ontology_version: str = "",
        kb_collection_version: str = "",
        options_considered: Optional[List[Dict]] = None,
        choice_reasoning: str = "",
        outcome_status: str = "pending",
        outcome_summary: str = "",
        cascaded_decisions: Optional[List[str]] = None,
        policy_version: str = "",
        constraint_checks: Optional[Dict] = None,
        source_call: str = "",
    ):
        self.decision_id = f"dec_{_uuid.uuid4().hex[:12]}"
        self.run_id = run_id
        self.trace_id = trace_id
        self.agent_id = agent_id
        self.actor_role = actor_role
        self.decided_at = _time.time()
        self.context_snapshot_id = context_snapshot_id
        self.ontology_version = ontology_version
        self.kb_collection_version = kb_collection_version
        self.decision_type = decision_type
        self.options_considered = _json.dumps(options_considered or [], ensure_ascii=False)
        self.chosen_option = chosen_option
        self.choice_reasoning = choice_reasoning
        self.outcome_status = outcome_status
        self.outcome_summary = outcome_summary
        self.cascaded_decisions = _json.dumps(cascaded_decisions or [], ensure_ascii=False)
        self.policy_version = policy_version
        self.constraint_checks = _json.dumps(constraint_checks or {}, ensure_ascii=False)
        self.source_call = source_call

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "agent_id": self.agent_id,
            "actor_role": self.actor_role,
            "decided_at": self.decided_at,
            "context_snapshot_id": self.context_snapshot_id,
            "ontology_version": self.ontology_version,
            "kb_collection_version": self.kb_collection_version,
            "decision_type": self.decision_type,
            "options_considered": self.options_considered,
            "chosen_option": self.chosen_option,
            "choice_reasoning": self.choice_reasoning,
            "outcome_status": self.outcome_status,
            "outcome_summary": self.outcome_summary,
            "cascaded_decisions": self.cascaded_decisions,
            "policy_version": self.policy_version,
            "constraint_checks": self.constraint_checks,
            "source_call": self.source_call,
            "created_at": self.decided_at,
        }


# ══════════════════════════════════════════════════════════════
# LineageStore
# ══════════════════════════════════════════════════════════════

class LineageStore:
    """决策血缘 SQLite 持久化层.

    使用方式:
        store = LineageStore.get()
        store.insert(DecisionRecord(run_id="r1", decision_type="tool_selection", chosen_option="kb_query"))
    """

    _instance: Optional["LineageStore"] = None

    def __init__(self, db_path: str = ""):
        if not db_path:
            import os as _os
            db_path = _os.path.expanduser("~/.aiplat/data/aiplat_platform.sqlite3")
        self._db_path = db_path

    @classmethod
    def get(cls) -> "LineageStore":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_conn(self) -> _sqlite3.Connection:
        conn = _sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = _sqlite3.Row
        return conn

    def insert(self, record: DecisionRecord) -> str:
        """插入一条决策记录. 返回 decision_id."""
        sql = """
            INSERT INTO lineage_decisions (
                decision_id, run_id, trace_id,
                agent_id, actor_role,
                decided_at,
                context_snapshot_id, ontology_version, kb_collection_version,
                decision_type,
                options_considered, chosen_option, choice_reasoning,
                outcome_status, outcome_summary, cascaded_decisions,
                policy_version, constraint_checks,
                source_call, created_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """
        try:
            conn = self._get_conn()
            conn.execute(sql, (
                record.decision_id,
                record.run_id,
                record.trace_id or "",
                record.agent_id or "",
                record.actor_role or "",
                record.decided_at,
                record.context_snapshot_id or "",
                record.ontology_version or "",
                record.kb_collection_version or "",
                record.decision_type,
                record.options_considered or "[]",
                record.chosen_option,
                record.choice_reasoning or "",
                record.outcome_status,
                record.outcome_summary or "",
                record.cascaded_decisions or "[]",
                record.policy_version or "",
                record.constraint_checks or "{}",
                record.source_call or "",
                record.decided_at,
            ))
            conn.commit()
            conn.close()
            return record.decision_id
        except Exception as e:
            logger.warning("Failed to insert decision lineage: %s", e)
            return ""

    def update_outcome(self, decision_id: str, outcome_status: str, outcome_summary: str = "") -> None:
        """更新决策结果状态."""
        try:
            conn = self._get_conn()
            conn.execute(
                "UPDATE lineage_decisions SET outcome_status=?, outcome_summary=? WHERE decision_id=?",
                (outcome_status, outcome_summary, decision_id),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Failed to update decision outcome: %s", e)

    def get_by_run(self, run_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取某个 run 的所有决策记录."""
        try:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT * FROM lineage_decisions WHERE run_id=? ORDER BY decided_at DESC LIMIT ?",
                (run_id, limit),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("Failed to query lineage for run %s: %s", run_id, e)
            return []

    def get_decision_graph(self, run_id: str) -> Dict[str, Any]:
        """构建决策图谱 (nodes + edges for frontend visualization).

        Returns:
            {"nodes": [...], "edges": [...], "summary": {...}}
        """
        decisions = self.get_by_run(run_id)
        if not decisions:
            return {"nodes": [], "edges": [], "summary": {}}

        nodes = []
        edges = []
        decision_ids = set()

        for d in decisions:
            did = d.get("decision_id", "")
            if not did:
                continue
            decision_ids.add(did)

            # Parse JSON fields
            try:
                options = _json.loads(d.get("options_considered", "[]"))
            except Exception:
                options = []
            try:
                cascaded = _json.loads(d.get("cascaded_decisions", "[]"))
            except Exception:
                cascaded = []
            try:
                constraints = _json.loads(d.get("constraint_checks", "{}"))
            except Exception:
                constraints = {}

            nodes.append({
                "id": did,
                "type": "decision",
                "label": d.get("chosen_option", "")[:60],
                "decision_type": d.get("decision_type", ""),
                "agent_id": d.get("agent_id", ""),
                "outcome": d.get("outcome_status", ""),
                "reasoning": (d.get("choice_reasoning", "") or "")[:200],
                "decided_at": d.get("decided_at", 0),
                "context_version": d.get("ontology_version", "") or d.get("kb_collection_version", ""),
            })

            # Add option nodes
            for i, opt in enumerate(options):
                opt_id = f"{did}_opt_{i}"
                nodes.append({
                    "id": opt_id,
                    "type": "option",
                    "label": str(opt.get("tool", opt.get("action", "")))[:60],
                    "score": opt.get("score", 0),
                    "was_chosen": opt.get("tool", "") == d.get("chosen_option", ""),
                })
                edges.append({
                    "source": did,
                    "target": opt_id,
                    "type": "considered",
                })

            # Cascaded edges
            for cid in cascaded:
                if cid in decision_ids:
                    edges.append({
                        "source": did,
                        "target": cid,
                        "type": "cascaded_to",
                    })

        # Chain edges (sequential decisions by time)
        sorted_decisions = sorted(decisions, key=lambda d: d.get("decided_at", 0))
        for i in range(len(sorted_decisions) - 1):
            a_id = sorted_decisions[i].get("decision_id", "")
            b_id = sorted_decisions[i + 1].get("decision_id", "")
            if a_id and b_id:
                edges.append({
                    "source": a_id,
                    "target": b_id,
                    "type": "next",
                })

        # Summary
        total = len(decisions)
        types = {}
        for d in decisions:
            t = d.get("decision_type", "unknown")
            types[t] = types.get(t, 0) + 1
        success_count = sum(1 for d in decisions if d.get("outcome_status") == "success")

        return {
            "nodes": nodes,
            "edges": edges,
            "summary": {
                "total_decisions": total,
                "decision_types": types,
                "success_rate": round(success_count / max(total, 1) * 100, 1),
                "run_id": run_id,
            },
        }

    def list_recent_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """列出最近有决策记录的 run."""
        try:
            conn = self._get_conn()
            rows = conn.execute("""
                SELECT run_id,
                       COUNT(*) as decision_count,
                       MAX(decided_at) as last_decision_at,
                       SUM(CASE WHEN outcome_status='success' THEN 1 ELSE 0 END) as success_count
                FROM lineage_decisions
                GROUP BY run_id
                ORDER BY last_decision_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("Failed to list recent lineage runs: %s", e)
            return []
