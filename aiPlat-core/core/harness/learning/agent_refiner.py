"""
AgentRefiner — 三省六部制「早朝复盘」→ AGENTS.md 自动优化建议

每晚扫描 EvolutionEngine 的诊断数据, 检测每个 Agent 的:
  - 封驳率: review_gate rejection 频次 → 建议增加审核清单
  - 阻塞点: 高频失败的工具/技能 → 建议替换或增加反模式
  - 模板化机会: 重复成功的操作序列 → 建议固化为 Skill
  - 职责漂移: Agent 执行了不在 scope 内的工具 → 建议调整权限

产出: agent目录下的 _evolution_suggestions.md (建议性, 不自动修改 AGENTS.md)

集成: EvolutionEngine._do_agent_refinement() (新增 Step 14)
调用者: EvolutionEngine 夜间流水线
"""

from __future__ import annotations

import json as _json
import logging
import os as _os
import time as _time
from dataclasses import dataclass, field
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentDiagnostic:
    agent_id: str
    total_decisions: int = 0
    rejected_count: int = 0            # 封驳次数 (review_gate deny)
    failed_tools: Dict[str, int] = field(default_factory=dict)  # tool→fail_count
    state_violations: int = 0          # state_guard 违规
    repeated_success: List[str] = field(default_factory=list)  # 反复成功的工具序列
    outside_scope_tools: List[str] = field(default_factory=list)  # 超出权限范围

    @property
    def rejection_rate(self) -> float:
        return self.rejected_count / max(self.total_decisions, 1)


class AgentRefiner:
    """AGENTS.md 自动优化建议器."""

    def __init__(self):
        self._db_path = _os.path.expanduser("~/.aiplat/data/aiplat_platform.sqlite3")

    def run(self, *, lookback_days: int = 7) -> Dict[str, Any]:
        """每晚运行: 扫描所有 Agent → 生成优化建议.

        Returns:
            {agent_id: {"suggestions": [...], "written_to": "/path/to/_evolution_suggestions.md"}}
        """
        agents = self._scan_agents()
        if not agents:
            return {"summary": "no agents found"}

        results = {}
        for agent_id in agents:
            diag = self._diagnose(agent_id, lookback_days)
            if not diag.total_decisions:
                continue

            suggestions = self._generate_suggestions(diag)
            if suggestions:
                path = self._write_suggestions(agent_id, suggestions)
                results[agent_id] = {
                    "suggestions": suggestions,
                    "written_to": path,
                    "rejection_rate": f"{diag.rejection_rate:.1%}",
                    "failed_tools": dict(list(diag.failed_tools.items())[:5]),
                }

        # Also generate prompt improvement suggestions from model health data
        prompt_results = self._refine_prompts_from_model_health()
        if prompt_results.get("suggestions"):
            results["_prompt_improvements"] = prompt_results

        logger.info("AgentRefiner: %d agents analyzed, %d refined, %d prompt suggestions",
                      len(agents), len(results), prompt_results.get("count", 0))
        return {"refined": len(results), "agents": results}

    def _scan_agents(self) -> List[str]:
        """扫描所有 Agent 目录."""
        agents = set()
        for root in [
            _os.path.expanduser("~/.aiplat/agents"),
            _os.path.join(_os.path.dirname(__file__), "../../..", "engine/agents"),
        ]:
            try:
                if _os.path.isdir(root):
                    for d in _os.listdir(root):
                        if _os.path.isfile(_os.path.join(root, d, "AGENT.md")):
                            agents.add(d)
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
        return sorted(agents)

    def _diagnose(self, agent_id: str, lookback_days: int) -> AgentDiagnostic:
        """从 lineage_decisions + action_audit 诊断 Agent."""
        diag = AgentDiagnostic(agent_id=agent_id)

        if not _os.path.exists(self._db_path):
            return diag

        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            cutoff = _time.time() - lookback_days * 86400

            # Count decisions by this agent
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM lineage_decisions WHERE agent_id=? AND decided_at>?",
                (agent_id, cutoff)
            ).fetchone()
            diag.total_decisions = row["cnt"] if row else 0

            if not diag.total_decisions:
                conn.close()
                return diag

            # Count rejections (outcome_status=failed or outcome contains 'denied'/'blocked')
            row = conn.execute(
                """SELECT COUNT(*) as cnt FROM lineage_decisions
                   WHERE agent_id=? AND decided_at>?
                     AND (outcome_status='failed' OR outcome_summary LIKE '%denied%' OR outcome_summary LIKE '%blocked%')""",
                (agent_id, cutoff)
            ).fetchone()
            diag.rejected_count = row["cnt"] if row else 0

            # Count failed tools
            rows = conn.execute(
                """SELECT chosen_option, COUNT(*) as cnt FROM lineage_decisions
                   WHERE agent_id=? AND decided_at>?
                     AND outcome_status='failed'
                   GROUP BY chosen_option ORDER BY cnt DESC LIMIT 10""",
                (agent_id, cutoff)
            ).fetchall()
            diag.failed_tools = {r["chosen_option"]: r["cnt"] for r in rows}

            # Count state violations
            row = conn.execute(
                """SELECT COUNT(*) as cnt FROM lineage_decisions
                   WHERE agent_id=? AND decided_at>?
                     AND choice_reasoning LIKE '%state_guard%'""",
                (agent_id, cutoff)
            ).fetchone()
            diag.state_violations = row["cnt"] if row else 0

            # Detect repeated success patterns (3+ consecutive same tool sequence)
            rows = conn.execute(
                """SELECT chosen_option, outcome_status FROM lineage_decisions
                   WHERE agent_id=? AND decided_at>? AND outcome_status='success'
                   ORDER BY decided_at ASC LIMIT 100""",
                (agent_id, cutoff)
            ).fetchall()
            success_tools = [r["chosen_option"] for r in rows]
            for i in range(len(success_tools) - 2):
                seq = success_tools[i:i + 3]
                if len(set(seq)) == 1:  # Same tool 3 times in a row
                    diag.repeated_success.append(seq[0])

            conn.close()
        except Exception as e:
            logger.debug("Agent diagnosis failed for %s: %s", agent_id, e)

        return diag

    def _generate_suggestions(self, diag: AgentDiagnostic) -> List[str]:
        """根据诊断数据生成优化建议."""
        suggestions = []

        # ① 封驳率高 → 建议增加审核清单
        if diag.rejection_rate > 0.2:
            suggestions.append(
                f"**封驳率 {diag.rejection_rate:.0%}**: "
                f"建议在 SOP 中增加「提交前自检清单」——"
                f"确认依赖就绪、状态合法、输出字段完整。"
            )

        # ② 高频失败工具 → 建议替换或增加反模式
        for tool, count in diag.failed_tools.items():
            if count >= 3:
                suggestions.append(
                    f"**工具 `{tool}` 失败 {count} 次**: "
                    f"建议在 SKILL.md 反模式章节增加 `{tool}` 的错误处理路径, "
                    f"或替换为更可靠的替代工具。"
                )

        # ③ 状态违规 → 建议增加状态检查
        if diag.state_violations >= 2:
            suggestions.append(
                f"**状态违规 {diag.state_violations} 次**: "
                f"建议在 PreToolUse 前增加 `OntologyValidator.pre_check()` 调用。"
            )

        # ④ 重复成功 → 建议模板化
        for tool in list(set(diag.repeated_success))[:3]:
            if diag.repeated_success.count(tool) >= 3:
                suggestions.append(
                    f"**操作 `{tool}` 连续成功 3+ 次**: "
                    f"建议使用 OperationRecorder 录制该操作 → SkillGenerator 固化为可复用 Skill。"
                )

        return suggestions

    def _refine_prompts_from_model_health(self) -> Dict[str, Any]:
        """Generate prompt improvement suggestions from ModelHealthStore data.

        Models with high failure rate and sufficient call history are
        analyzed. Suggestions go into refinement_candidates for
        voting-based adoption, same path as agent refinements.
        """
        try:
            from infra.management.model.model_health_store import get_model_health_store
            store = get_model_health_store()
            all_health = store.list_health_scores()
        except Exception as e:
            logger.debug("Model health read failed: %s", e)
            return {"count": 0, "suggestions": 0}

        suggestions = []
        for model_name, health in all_health.items():
            calls = health.get("call_count", 0)
            if calls < 10:  # insufficient data for reliable analysis
                continue

            failure_rate = health.get("failure_count", 0) / calls
            avg_latency = health.get("avg_latency_ms", 1000.0)
            biz_score = health.get("business_score", 0.5)

            # Generate suggestion based on failure patterns
            if failure_rate > 0.3:
                if avg_latency > 5000:
                    msg = (
                        f"Prompt optimization for {model_name}: "
                        f"High failure rate ({failure_rate:.0%}) with extreme latency "
                        f"({avg_latency:.0f}ms). Consider simplifying output format "
                        f"requirements or adding timeout handling instructions."
                    )
                elif biz_score < 0.4:
                    msg = (
                        f"Prompt optimization for {model_name}: "
                        f"High failure rate ({failure_rate:.0%}) and low business pass rate "
                        f"({biz_score:.0%}). Review prompt for output quality — "
                        f"check that expected output schema is clearly specified."
                    )
                else:
                    msg = (
                        f"Prompt optimization for {model_name}: "
                        f"Elevated failure rate ({failure_rate:.0%}) with "
                        f"{calls} total calls. Consider adding retry instructions "
                        f"or explicit error-handling examples to the system prompt."
                    )

                # Submit to refinement_candidates for voting
                _suggest_prompt_improvement(
                    model_name, msg,
                    confidence=min(95.0, 50.0 + failure_rate * 100)
                )
                suggestions.append(model_name)

        return {"count": len(suggestions), "suggestions": suggestions}

    def _write_suggestions(self, agent_id: str, suggestions: List[str]) -> str:
        """将建议写入 agent 目录下的 _evolution_suggestions.md."""
        for root in [
            _os.path.expanduser(f"~/.aiplat/agents/{agent_id}"),
            _os.path.join(_os.path.dirname(__file__), "../../..", "engine/agents", agent_id),
        ]:
            if _os.path.isdir(root):
                path = _os.path.join(root, "_evolution_suggestions.md")
                content = f"# {agent_id} — 早朝复盘建议\n\n"
                content += f"**生成时间**: {_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                content += f"**数据范围**: 最近 7 天\n\n"
                content += "## 优化建议\n\n"
                for i, s in enumerate(suggestions, 1):
                    content += f"{i}. {s}\n\n"
                content += "\n---\n"
                content += "> ⚠️ 此为自动生成的建议，不自动修改 AGENTS.md。审核后手动采纳。\n"
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info("Agent refinement written: %s", path)
                return path
        return ""


async def submit_refinement_suggestion(
    target_model: str, suggestion: str, confidence: float
) -> None:
    """Submit a refinement candidate for voting-based adoption.

    High-confidence suggestions (≥80%) are stored in refinement_candidates
    table. They require ≥3 independent pipeline verifications (vote_count)
    before apply_mature_refinements actually writes to AGENT.md.

    Args:
        target_model: agent_id or skill name
        suggestion: human-readable refinement text
        confidence: 0-100 confidence percentage
    """
    if confidence < 80.0:
        logger.debug("Suggestion confidence %.1f%% < 80%%, skipping.", confidence)
        return

    try:
        import os as _os, sqlite3, time as _time
        from core.utils.paths import get_aiplat_data_dir

        db = _os.path.join(get_aiplat_data_dir(""), "data", "pipeline_runs.db")
        db = _os.path.expanduser(db)
        # Use the main execution DB for refinement_candidates
        main_db = _os.path.join(_os.path.expanduser("~"), ".aiplat", "aiplat_executions.sqlite3")
        if not _os.path.isfile(main_db):
            logger.debug("Main DB not found, skipping refinement submission")
            return

        conn = sqlite3.connect(main_db, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            now = _time.strftime("%Y-%m-%dT%H:%M:%S")
            # Check for existing similar suggestion within 7 days
            existing = conn.execute("""
                SELECT id, vote_count FROM refinement_candidates
                WHERE target_model = ? AND suggestion_text = ?
                  AND status = 'pending'
                  AND last_seen_at > datetime(?, '-7 days')
            """, (target_model, suggestion, now)).fetchone()

            if existing:
                conn.execute(
                    """UPDATE refinement_candidates
                       SET vote_count = vote_count + 1, last_seen_at = ?
                       WHERE id = ?""",
                    (now, existing["id"]),
                )
                logger.info("Suggestion vote %d→%d for %s",
                            existing["vote_count"], existing["vote_count"] + 1, target_model)
            else:
                conn.execute(
                    """INSERT INTO refinement_candidates
                       (target_model, suggestion_text, confidence,
                        first_seen_at, last_seen_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (target_model, suggestion, confidence, now, now),
                )
                logger.info("New refinement candidate for %s (confidence=%.1f%%)",
                            target_model, confidence)
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.debug("submit_refinement_suggestion failed", exc_info=True)


def _suggest_prompt_improvement(
    model_name: str, suggestion: str, confidence: float = 85.0
) -> None:
    """Write a prompt improvement suggestion to refinement_candidates (sync).

    Uses the same voting mechanism as AgentRefiner — suggestions with
    ≥3 votes from independent pipeline runs are auto-applied.
    """
    try:
        import sqlite3, time as _t
        from pathlib import Path

        main_db = _os.path.join(
            _os.path.expanduser("~"), ".aiplat", "aiplat_executions.sqlite3")
        if not _os.path.isfile(main_db):
            return

        # Use a compound target ID: model_name as primary, "prompt" as type
        target = f"{model_name}/prompt"
        now = _t.strftime("%Y-%m-%dT%H:%M:%S")

        conn = sqlite3.connect(main_db, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            existing = conn.execute("""
                SELECT id, vote_count FROM refinement_candidates
                WHERE target_model = ? AND status = 'pending'
                  AND last_seen_at > datetime(?, '-7 days')
            """, (target, now)).fetchone()

            if existing:
                conn.execute(
                    """UPDATE refinement_candidates
                       SET vote_count = vote_count + 1, last_seen_at = ?
                       WHERE id = ?""",
                    (now, existing["id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO refinement_candidates
                       (target_model, suggestion_text, confidence,
                        first_seen_at, last_seen_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (target, suggestion, confidence, now, now),
                )
            conn.commit()
            logger.info("Prompt suggestion for %s (confidence=%.1f%%)",
                        model_name, confidence)
        finally:
            conn.close()
    except Exception:
        logger.debug("_suggest_prompt_improvement failed", exc_info=True)
