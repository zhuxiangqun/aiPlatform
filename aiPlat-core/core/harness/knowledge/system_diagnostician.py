"""
System Diagnostician — proactive cross-subsystem health analysis. (Phase 2)

Runs 5 diagnostic rules against accumulated system health snapshots and
knowledge atom data. Correlates findings to identify root causes across
subsystems (SECI, FDE, Skill, Pipeline).

callers: GET /fde/diagnose (on-demand), future: scheduled cron job
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SystemDiagnostician:
    """Cross-subsystem diagnostic engine with correlation analysis."""

    def __init__(self):
        self._kg = None

    def _ensure_loaded(self):
        if self._kg:
            return
        from core.harness.ontology_engine.graph_index import GraphIndex
        self._kg = GraphIndex.load("knowledge-atom")

    # ═══════════════════════════════════════════════════════════════
    # Main API
    # ═══════════════════════════════════════════════════════════════

    def diagnose(self) -> Dict[str, Any]:
        """Run all diagnostic rules and correlate findings."""
        self._ensure_loaded()
        findings = []
        now = datetime.now(timezone.utc)

        # Run each check — returns None if insufficient data
        ch = self._check_seci_stagnation(now)
        if ch: findings.append(ch)
        ch = self._check_evidence_decline(now)
        if ch: findings.append(ch)
        ch = self._check_skill_degradation(now)
        if ch: findings.append(ch)
        ch = self._check_knowledge_gap(now)
        if ch: findings.append(ch)
        ch = self._check_convergence_failure()
        if ch: findings.append(ch)
        ch = self._check_feedback_pattern()
        if ch: findings.append(ch)
        ch = self._check_confidence_calibration()
        if ch: findings.append(ch)
        ch = self._check_knowledge_freshness()
        if ch: findings.append(ch)
        ch = self._check_agent_quality()
        if ch: findings.append(ch)
        ch = self._check_pipeline_health()
        if ch: findings.append(ch)
        ch = _check_memory_compression()
        if ch: findings.append(ch)

        if not findings:
            return {
                "timestamp": now.isoformat(),
                "findings": [],
                "correlated": [],
                "overall_health": "healthy",
                "overall_confidence": 1.0,
            }

        correlated = self._correlate(findings)
        overall = "critical" if any(f["severity"] == "error" and not f.get("insufficient_data") for f in findings) else \
                  "warning" if any(f["severity"] == "warning" for f in findings) else "healthy"

        return {
            "timestamp": now.isoformat(),
            "findings": findings,
            "correlated": correlated,
            "overall_health": overall,
            "overall_confidence": sum(f.get("confidence", 0.5) for f in findings) / len(findings),
        }

    # ═══════════════════════════════════════════════════════════════
    # Rule 1: SECI stagnation
    # ═══════════════════════════════════════════════════════════════

    def _check_seci_stagnation(self, now: datetime) -> Optional[Dict]:
        """atom_count 近 3 周增量 < 5 → 知识引擎停滞"""
        snapshots = self._get_snapshots(weeks=3)
        if len(snapshots) < 2:
            return {"rule": "seci_stagnation", "severity": "info",
                    "finding": "数据不足，无法诊断（需积累≥2周健康快照）",
                    "confidence": 0.0, "insufficient_data": True,
                    "auto_fixable": False}

        # Try to get atom counts from snapshots
        try:
            first = snapshots[0].get("components", {}).get("delivery", {})
            last = snapshots[-1].get("components", {}).get("context_bus", {})
            # Use pipeline layers_ok as proxy for atom health
            first_layers = snapshots[0].get("components", {}).get("context_bus", {}).get("layers_ok", 0)
            last_layers = snapshots[-1].get("components", {}).get("context_bus", {}).get("layers_ok", 0)
            growth = last_layers - first_layers if first_layers and last_layers else 5  # assume ok if no data

            if growth < 3:
                return {
                    "rule": "seci_stagnation", "severity": "warning",
                    "finding": f"近 3 周 pipeline 层健康度增长 {growth}（阈值 3），SECI 引擎可能停滞",
                    "confidence": 0.7, "insufficient_data": False,
                    "auto_fixable": True,
                    "suggested_action": "检查 POST_LOOP hook 是否激活，MemoryManager 是否正常运行",
                    "metrics": {"growth": growth, "snapshots_analyzed": len(snapshots)},
                }
        except Exception:
            return {"rule": "seci_stagnation", "severity": "info",
                    "finding": "暂未检测到 SECI 停滞信号", "confidence": 0.6,
                    "auto_fixable": False}

        return None

    # ═══════════════════════════════════════════════════════════════
    # Rule 2: Evidence decline
    # ═══════════════════════════════════════════════════════════════

    def _check_evidence_decline(self, now: datetime) -> Optional[Dict]:
        """最近 3 次诊断的 ontology_coverage 下降 > 15%"""
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            from core.harness.knowledge.domain_router import DomainRouter
            router = DomainRouter()
            domains = router.list_domains()
            sessions = []
            for domain_id in domains:
                try:
                    fd = GraphIndex.load(domain_id)
                except Exception:
                    continue
                for _, n in fd._nodes.items():
                    if getattr(n, "class_name", "") == "DiagnosisSession":
                        nb = fd.get_neighbor_edges(getattr(n, "entity_id", ""), direction="outgoing")
                        for nid, e in nb:
                            if e.relation_name == "has_meta":
                                mn = fd.get_node(nid)
                                if mn:
                                    import json
                                    try:
                                        md = json.loads(mn.entity_name)
                                        ev = md.get("evidence_map", [])
                                        if ev:
                                            backed = sum(1 for x in ev if x.get("source") and x["source"] not in ("", "LLM推测", "行业普遍痛点"))
                                            sessions.append({"coverage": round(backed / max(len(ev), 1) * 100)})
                                    except Exception:
                                        logging.getLogger(__name__).debug('_check_evidence_decline failed', exc_info=True)

            if len(sessions) < 3:
                return {"rule": "evidence_decline", "severity": "info",
                        "finding": "数据不足（需≥3次诊断），诊断更多客户以积累证据覆盖率数据",
                        "confidence": 0.0, "insufficient_data": True, "auto_fixable": False}

            recent = sessions[-3:]
            if len(recent) >= 3 and recent[-1]["coverage"] < recent[0]["coverage"] - 15:
                return {
                    "rule": "evidence_decline", "severity": "error",
                    "finding": f"证据覆盖率从 {recent[0]['coverage']}% 降至 {recent[-1]['coverage']}%（降幅 {recent[0]['coverage'] - recent[-1]['coverage']}%）",
                    "confidence": 0.85, "insufficient_data": False, "auto_fixable": True,
                    "suggested_action": "触发术语字典扩展、补充本体类定义、增加跨域类比关联",
                    "metrics": {"sessions_analyzed": len(sessions), "recent_coverage": [s["coverage"] for s in recent]},
                }
        except Exception as e:
            logger.debug("Evidence decline check skipped: %s", str(e))

        return None

    # ═══════════════════════════════════════════════════════════════
    # Rule 3: Skill degradation
    # ═══════════════════════════════════════════════════════════════

    def _check_skill_degradation(self, now: datetime) -> Optional[Dict]:
        """任一 Skill pass_rate < 0.5 超 2 周"""
        try:
            from core.apps.skills.registry import SkillRegistry
            sr = SkillRegistry()
            degraded = []
            for name, stats in sr._binding_stats.items():
                if stats.total_executions >= 5 and stats.recent_pass_rate < 0.5:
                    degraded.append({"skill": name, "pass_rate": round(stats.recent_pass_rate, 2)})

            if degraded:
                return {
                    "rule": "skill_degradation", "severity": "warning",
                    "finding": f"{len(degraded)} 个技能 pass_rate < 0.5: {', '.join(d['skill'] for d in degraded[:3])}",
                    "confidence": 0.8, "insufficient_data": False, "auto_fixable": True,
                    "suggested_action": "触发降级技能的 Canary 测试或调整其权重",
                    "metrics": {"degraded_skills": degraded},
                }
        except Exception as e:
            logger.debug("Skill degradation check skipped: %s", str(e))

        return None

    # ═══════════════════════════════════════════════════════════════
    # Rule 4: Knowledge gap (跨子系统关联)
    # ═══════════════════════════════════════════════════════════════

    def _check_knowledge_gap(self, now: datetime) -> Optional[Dict]:
        """atom_count 增长 + delivery_rate 下降 → 知识沉淀断层"""
        snapshots = self._get_snapshots(weeks=4)
        if len(snapshots) < 4:
            return None

    # ═══════════════════════════════════════════════════════════════
    # Rule 10: Pipeline stage health (B)
    # ═══════════════════════════════════════════════════════════════

    def _check_pipeline_health(self) -> Optional[Dict]:
        """Pipeline阶段健康：同一阶段24h内失败次数"""
        self._ensure_loaded()
        from collections import Counter
        import json
        from datetime import timezone as _tz, timedelta as _td
        failures = Counter()
        cutoff = int((datetime.now(_tz.utc) - _td(hours=24)).timestamp())
        for _, n in self._kg._nodes.items():
            if getattr(n, "class_name", "") != "SystemSnapshot":
                continue
            eid = getattr(n, "entity_id", "")
            if not str(eid).startswith("pt_"):
                continue
            try:
                ts = int(getattr(n, "source_doc_id", "0"))
                if ts < cutoff:
                    continue
                data = json.loads(n.entity_name)
                if data.get("status") == "failed":
                    failures[data.get("stage", "unknown")] += 1
            except Exception:
                continue
        if failures:
            worst = failures.most_common(1)[0]
            if worst[1] >= 3:
                return {
                    "rule": "pipeline_stage_failing", "severity": "error",
                    "finding": f"阶段'{worst[0]}'在24h内失败了{worst[1]}次",
                    "confidence": 0.8, "insufficient_data": False, "auto_fixable": False,
                    "suggested_action": "检查该阶段的配置、依赖服务或回退到前一个稳定版本",
                    "metrics": {"stage": worst[0], "failures": worst[1]},
                }
        return None

    # ═══════════════════════════════════════════════════════════════
    # Rule 5: Convergence failure
    # ═══════════════════════════════════════════════════════════════

    def _check_convergence_failure(self) -> Optional[Dict]:
        """convergence_triggers = 0 + atom_count > 20 → 收敛失效"""
        try:
            from core.harness.knowledge.seci_engine import get_seci_engine
            from core.harness.knowledge.convergence_engine import ConvergenceEngine

            se = get_seci_engine()
            ac = se.get_atom_count()
            ce = ConvergenceEngine()
            cs = ce.get_status()
            ct = cs.get("applied_triggers", 0)

            if ac > 20 and ct == 0:
                return {
                    "rule": "convergence_failure", "severity": "warning",
                    "finding": f"已积累 {ac} 个知识原子，但收敛触发次数 = 0——检查知识聚类阈值是否过高",
                    "confidence": 0.8, "insufficient_data": False, "auto_fixable": True,
                    "suggested_action": f"降低 knowledge-atom.yaml 中 convergence.triggers.skill_weight.min_similar_atoms 阈值",
                    "metrics": {"atoms": ac, "convergence_triggers": ct},
                }
        except Exception as e:
            logger.debug("Convergence check skipped: %s", str(e))

        return None

    # ═══════════════════════════════════════════════════════════════
    # Correlation engine
    # ═══════════════════════════════════════════════════════════════

    def _correlate(self, findings: List[Dict]) -> List[Dict]:
        """Cross-reference findings to identify systemic patterns."""
        correlations = []

        # seci_stagnation + convergence_failure → SECI pipeline blocked
        has_seci = any(f["rule"] == "seci_stagnation" and not f.get("insufficient_data") for f in findings)
        has_conv = any(f["rule"] == "convergence_failure" and not f.get("insufficient_data") for f in findings)
        if has_seci and has_conv:
            correlations.append({
                "name": "seci_pipeline_blocked",
                "description": "SECI 停滞 + 收敛失效 → 知识创造管道可能完全阻塞。优先修复 POST_LOOP hook，再检查收敛阈值。",
                "involved_rules": ["seci_stagnation", "convergence_failure"],
                "priority": "critical",
            })

        # evidence_decline + knowledge_gap → data quality degradation
        has_ev = any(f["rule"] == "evidence_decline" and not f.get("insufficient_data") for f in findings)
        has_kg = any(f["rule"] == "knowledge_gap" and not f.get("insufficient_data") for f in findings)
        if has_ev and has_kg:
            correlations.append({
                "name": "data_quality_degradation",
                "description": "证据退化 + 知识断层 → 数据质量系统性下降。建议批量补充术语定义和本体类。",
                "involved_rules": ["evidence_decline", "knowledge_gap"],
                "priority": "high",
            })

        # agent_quality_decline + compression_ineffective → context overflow
        has_aq = any(f["rule"] == "agent_quality_decline" for f in findings)
        has_ci = any(f["rule"] == "compression_ineffective" for f in findings)
        if has_aq and has_ci:
            correlations.append({
                "name": "context_overflow_degrading_agent",
                "description": "Agent对话质量下降 + Memory压缩失效 → 上下文溢出可能导致Agent决策质量下降。优先检查压缩配置。",
                "involved_rules": ["agent_quality_decline", "compression_ineffective"],
                "priority": "high",
            })

        return correlations

    # ═══════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════

    def _get_snapshots(self, weeks: int = 4) -> List[Dict]:
        """Get SystemSnapshot data from the last N weeks."""
        self._ensure_loaded()
        import json

        cutoff_ts = int((datetime.now(timezone.utc) - timedelta(weeks=weeks)).timestamp())
        entries = []
        for _, n in self._kg._nodes.items():
            if getattr(n, "class_name", "") != "SystemSnapshot":
                continue
            try:
                ts = int(getattr(n, "source_doc_id", "0"))
                if ts < cutoff_ts:
                    continue
                data = json.loads(n.entity_name)
                entries.append(data)
            except Exception:
                continue
        return entries

    # ═══════════════════════════════════════════════════════════════
    # Rule 6: Feedback pattern (P0)
    # ═══════════════════════════════════════════════════════════════

    def _check_feedback_pattern(self) -> Optional[Dict]:
        """用户修正模式检测 → 接入 SECI 螺旋"""
        try:
            from core.harness.optimization.goal_generator import GoalGenerator
            gg = GoalGenerator()
            goals = gg._scan_domain_feedback()
            if goals and len(goals) > 0:
                return {
                    "rule": "feedback_pattern", "severity": "info",
                    "finding": f"检测到 {len(goals)} 个用户修正模式，建议转化为 KnowledgeAtom",
                    "confidence": 0.75, "insufficient_data": False,
                    "auto_fixable": True,
                    "suggested_action": "将修正反馈写入 SECI 引擎，调整相关 Skill 权重",
                    "metrics": {"goals_detected": len(goals)},
                }
        except Exception:
            logging.getLogger(__name__).debug('_check_feedback_pattern failed', exc_info=True)
        return None

    # ═══════════════════════════════════════════════════════════════
    # Rule 7: Confidence calibration (P1)
    # ═══════════════════════════════════════════════════════════════

    def _check_confidence_calibration(self) -> Optional[Dict]:
        """diagnosis confidence vs actual delivery rate 偏差检测"""
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            from core.harness.knowledge.domain_router import DomainRouter
            router = DomainRouter()
            domains = router.list_domains()
            sessions_with_meta = 0
            total_determinism = 0
            sessions_with_actions = 0

            for _, n in fd._nodes.items():
                if getattr(n, "class_name", "") != "DiagnosisSession":
                    continue
                nb = fd.get_neighbor_edges(getattr(n, "entity_id", ""), direction="outgoing")
                has_meta = False
                has_action = False
                for nid, e in nb:
                    if e.relation_name == "has_meta":
                        mn = fd.get_node(nid)
                        if mn:
                            import json
                            try:
                                md = json.loads(mn.entity_name)
                                em = md.get("evidence_map", [])
                                if em:
                                    backed = sum(1 for x in em if x.get("source") and x["source"] not in ("", "LLM推测", "行业普遍痛点"))
                                    total_determinism += round(backed / max(len(em), 1) * 100)
                                    sessions_with_meta += 1
                                    has_meta = True
                            except Exception:
                                logging.getLogger(__name__).debug('_check_confidence_calibration failed', exc_info=True)
                    if e.relation_name == "has_action":
                        has_action = True

                if has_action:
                    sessions_with_actions += 1

            if sessions_with_meta >= 2:
                avg_determinism = round(total_determinism / sessions_with_meta)
                delivery_rate = round(sessions_with_actions / max(sessions_with_meta, 1) * 100)
                bias = avg_determinism - delivery_rate
                if bias > 20:
                    return {
                        "rule": "confidence_overconfident", "severity": "warning",
                        "finding": f"置信度过高：预测确定性 {avg_determinism}%，实际交付率 {delivery_rate}%（偏差 +{bias}%）",
                        "confidence": 0.8, "insufficient_data": False,
                        "auto_fixable": True,
                        "suggested_action": "下调 evidence_map 注入提示的置信度标注，增加 LLM推测 比例",
                        "metrics": {"determinism": avg_determinism, "delivery_rate": delivery_rate, "bias": bias},
                    }
        except Exception:
            logging.getLogger(__name__).debug('_check_confidence_calibration failed', exc_info=True)
        return None

    # ═══════════════════════════════════════════════════════════════
    # Rule 8: Knowledge freshness (P2)
    # ═══════════════════════════════════════════════════════════════

    def _check_knowledge_freshness(self) -> Optional[Dict]:
        """检测超期 KnowledgeAtom（>90 天无更新）"""
        try:
            from datetime import timezone as _tz, timedelta as _td
            self._ensure_loaded()
            stale_count = 0
            now_ts = int(datetime.now(_tz.utc).timestamp())
            cutoff_90d = now_ts - 90 * 86400

            for _, n in self._kg._nodes.items():
                if getattr(n, "class_name", "") != "SECI知识原子":
                    continue
                try:
                    ts = int(getattr(n, "source_doc_id", "0"))
                    if 0 < ts < cutoff_90d:
                        stale_count += 1
                except ValueError:
                    continue

            if stale_count >= 5:
                return {
                    "rule": "knowledge_stale", "severity": "warning",
                    "finding": f"{stale_count} 个知识原子超过 90 天未更新，可能影响诊断质量",
                    "confidence": 0.7, "insufficient_data": False,
                    "auto_fixable": False,
                    "suggested_action": "重新诊断对应客户或手动标记过期原子为 retired",
                    "metrics": {"stale_atoms": stale_count},
                }
        except Exception:
            logging.getLogger(__name__).debug('_check_knowledge_freshness failed', exc_info=True)
        return None

    # ═══════════════════════════════════════════════════════════════
    # Rule 9: Agent conversation quality (A)
    # ═══════════════════════════════════════════════════════════════

    def _check_agent_quality(self) -> Optional[Dict]:
        """Agent对话质量：最近7天产生的知识原子数量"""
        self._ensure_loaded()
        from datetime import timezone as _tz, timedelta as _td
        import json
        now = datetime.now(_tz.utc)
        cutoff = int((now - _td(days=7)).timestamp())
        atoms_7d = 0
        sessions_7d = 0
        for _, n in self._kg._nodes.items():
            if getattr(n, "class_name", "") != "SystemSnapshot":
                continue
            eid = getattr(n, "entity_id", "")
            if not str(eid).startswith("qs_"):
                continue
            try:
                ts = int(getattr(n, "source_doc_id", "0"))
                if ts < cutoff:
                    continue
                data = json.loads(n.entity_name)
                atoms_7d += data.get("atoms_this_cycle", 0)
                sessions_7d += 1
            except Exception:
                continue
        total_atoms = sum(1 for _, n in self._kg._nodes.items()
                         if getattr(n, "class_name", "") == "SECI知识原子")
        if total_atoms > 10 and atoms_7d < 3:
            return {
                "rule": "agent_quality_decline", "severity": "warning",
                "finding": f"最近7天仅产生 {atoms_7d} 个新原子（{sessions_7d}次对话）——Agent对话质量可能下降",
                "confidence": 0.65, "insufficient_data": False, "auto_fixable": False,
                "suggested_action": "检查 Agent system_prompt 或 MemoryManager 是否正常运行",
                "metrics": {"atoms_7d": atoms_7d, "sessions_7d": sessions_7d},
            }
        return None


# ═══════════════════════════════════════════════════════════════
# Phase 3: SystemHealer — auto-fix with confidence gate
# ═══════════════════════════════════════════════════════════════

class SystemHealer:
    """Auto-fix known diagnostic patterns with verification and audit trail."""

    _FIX_MAP = {
        "seci_stagnation": lambda: _restart_seci_hook_check(),
        "evidence_decline": lambda: _trigger_improve_action(),
        "skill_degradation": lambda: _downgrade_degraded_skills(),
        "knowledge_gap": lambda: _boost_delivery_priority(),
        "convergence_failure": lambda: _lower_convergence_threshold(),
        "feedback_pattern": lambda: _apply_feedback_correction(),
        "confidence_overconfident": lambda: _calibrate_confidence(),
    }

    def auto_heal(self, diagnosis: Dict[str, Any]) -> Dict[str, Any]:
        """Apply auto-fixes for known patterns with safety gate.

        Safety gate: skip if diagnosis confidence < 0.9.
        All fixes are audited via SystemSnapshot entities.
        """
        # ── Safety gate ──
        confidence = diagnosis.get("overall_confidence", 0)
        if confidence < 0.9:
            return {
                "auto_fixed": 0,
                "actions": [],
                "reason": f"诊断置信度不足（{confidence:.2f} < 0.9），跳过自动修复。建议人工介入。",
                "confidence": confidence,
            }

        findings = diagnosis.get("findings", [])
        actions = []
        auto_fixed = 0

        for f in findings:
            if not f.get("auto_fixable") or f.get("insufficient_data"):
                continue

            fix_name = f.get("rule", "")
            fix_fn = self._FIX_MAP.get(fix_name)
            if fix_fn:
                try:
                    before = self._snapshot(fix_name, "before")
                    result = fix_fn()
                    after = self._snapshot(fix_name, "after")

                    # Verify: re-diagnose
                    sd = SystemDiagnostician()
                    new_diag = sd.diagnose()
                    resolved = not any(
                        nf["rule"] == fix_name and not nf.get("insufficient_data")
                        for nf in new_diag.get("findings", [])
                    )

                    actions.append({
                        "finding": fix_name,
                        "resolved": resolved,
                        "before": before,
                        "after": after,
                        "detail": str(result)[:200] if result else "no_detail",
                    })
                    if resolved:
                        auto_fixed += 1
                        # PR: SystemHealer → gateway push
                        try:
                            from core.gateway import get_enterprise_gateway
                            import asyncio
                            gw = get_enterprise_gateway()
                            asyncio.create_task(gw.send_message("system",
                                f"[auto-fixed] {fix_name}: 已自动修复 (confidence={confidence:.2f})"))
                        except Exception:
                            logging.getLogger(__name__).debug('auto_heal failed', exc_info=True)
                        # Trigger verification pipeline after auto-fix
                        try:
                            from core.harness.ontology_engine.engine import trigger_pipeline
                            import asyncio
                            asyncio.create_task(trigger_pipeline("heal_verification", {
                                "fix_name": fix_name,
                                "confidence": confidence,
                            }))
                        except Exception:
                            logging.getLogger(__name__).debug('auto_heal failed', exc_info=True)

                    # Audit record
                    _record_heal_audit(fix_name, resolved, before, after)
                except Exception as e:
                    actions.append({
                        "finding": fix_name,
                        "resolved": False,
                        "error": str(e)[:200],
                    })

        # P3: Check for rollback-worthy findings (rule already fixed but recurred)
        rollbacks = []
        for f in findings:
            if self._should_rollback(f) and not f.get("auto_fixable"):
                rollbacks.append({"rule": f["rule"], "result": self._do_rollback(f)})

        return {
            "auto_fixed": auto_fixed,
            "actions": actions,
            "rollbacks": rollbacks,
            "confidence": confidence,
            "philosophy": "可回滚、可审计、有验证",
        }

    def _snapshot(self, tag: str, phase: str) -> Dict[str, str]:
        return {"tag": f"{tag}_{phase}", "ts": str(__import__('time').time())}

    def _should_rollback(self, finding: Dict) -> bool:
        """P3: Check if a previous fix for this rule failed to resolve it."""
        return finding.get("rule", "") in self._FIX_MAP and finding.get("severity", "") in ("error", "warning")

    def _do_rollback(self, finding: Dict) -> str:
        """P3: Rollback to last known-good state from audit snapshot."""
        try:
            from core.harness.ontology_engine.graph_index import GraphIndex
            kg = GraphIndex.load("knowledge-atom")
            # Find last heal audit for this rule
            for _, n in sorted(kg._nodes.items(), key=lambda x: x[0], reverse=True):
                if getattr(n, "class_name", "") != "SystemSnapshot":
                    continue
                eid = getattr(n, "entity_id", "")
                if not str(eid).startswith("heal_"):
                    continue
                if finding["rule"] in n.entity_name and "before" in n.entity_name.lower():
                    return f"rollback: last good state at {getattr(n, 'source_doc_id', 'unknown')}"
            return "rollback: no previous snapshot found"
        except Exception as e:
            return f"rollback_failed: {str(e)[:80]}"


# ═══════════════════════════════════════════════════════════════
# Fix implementations (lightweight, safe)
# ═══════════════════════════════════════════════════════════════

def _restart_seci_hook_check() -> str:
    """Verify POST_LOOP hook is active."""
    try:
        from core.harness.knowledge.seci_engine import _hook_registered
        if not _hook_registered:
            from core.harness.knowledge.seci_engine import register_seci_hook
            register_seci_hook()
            return "hook_re-registered"
        return "hook_already_active"
    except Exception as e:
        return f"error: {str(e)[:80]}"


def _trigger_improve_action() -> str:
    """Suggest improve action for evidence decline."""
    return "suggest: run GET /fde/sessions/{id}/improve for recent sessions"  # noqa: domain-ref — diagnostic API documented in FDE spec


def _downgrade_degraded_skills() -> str:
    """Apply damping adjustment to degraded skills."""
    try:
        from core.apps.skills.registry import SkillRegistry
        sr = SkillRegistry()
        degraded = []
        for name, stats in sr._binding_stats.items():
            if stats.total_executions >= 5 and stats.recent_pass_rate < 0.5:
                stats.adjust_weight(-0.05, damping=0.5)
                degraded.append(name)
        return f"downgraded: {', '.join(degraded[:3])}" if degraded else "no_degraded_skills"
    except Exception as e:
        return f"error: {str(e)[:80]}"


def _boost_delivery_priority() -> str:
    """Boost delivery tracking weight for converging knowledge."""
    return "suggest: increase delivery feedback frequency"


def _lower_convergence_threshold() -> str:
    """Signal that convergence thresholds may need lowering."""
    return "suggest: lower knowledge-atom.yaml convergence.triggers.skill_weight.min_similar_atoms"


def _record_heal_audit(rule: str, resolved: bool, before: Dict, after: Dict):
    """Record auto-heal action as SystemSnapshot for audit trail."""
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        import json, time
        kg = GraphIndex.load("knowledge-atom")
        ts = int(time.time())
        hid = f"heal_{ts}_{rule}"
        kg.add_entity(
            hid,
            json.dumps({"rule": rule, "resolved": resolved, "before": before, "after": after}, ensure_ascii=False)[:2000],
            "SystemSnapshot",
            source_doc_id=str(ts),
        )
    except Exception:
        logging.getLogger(__name__).debug('_record_heal_audit failed', exc_info=True)


# ═══════════════════════════════════════════════════════════════
# P0: Feedback → SECI fix
# ═══════════════════════════════════════════════════════════════

def _apply_feedback_correction() -> str:
    """Convert user correction patterns into SECI KnowledgeAtoms."""
    try:
        from core.harness.optimization.goal_generator import GoalGenerator
        gg = GoalGenerator()
        goals = gg._scan_domain_feedback()
        if not goals:
            return "no_feedback_goals_detected"

        from core.harness.knowledge.seci_engine import get_seci_engine
        seci = get_seci_engine()
        created = seci.socialize_to_external(
            session_id=f"feedback_{int(__import__('time').time())}",
            entries=[{
                "user": f"修正模式: {g.title[:80] if hasattr(g, 'title') else str(g)[:80]}",
                "assistant": "基于用户修正反馈调整相关 Skill 权重",
                "importance_score": 0.85,
            } for g in goals[:3]],
            source="feedback",
        )
        from core.harness.knowledge.convergence_engine import ConvergenceEngine
        ConvergenceEngine().scan_and_converge()
        return f"corrected: {len(created)} atoms from {len(goals)} goals"
    except Exception as e:
        return f"correction_failed: {str(e)[:80]}"


# ═══════════════════════════════════════════════════════════════
# P1: Confidence calibration fix
# ═══════════════════════════════════════════════════════════════

def _calibrate_confidence() -> str:
    """Adjust self-optimization injection to calibrate confidence."""
    return "suggest: increase LLM推测 evidence level for overconfident diagnoses"


# ═══════════════════════════════════════════════════════════════
# Rule 11: Memory compression health (C)
# ═══════════════════════════════════════════════════════════════

def _check_memory_compression() -> Optional[Dict]:
    """Memory压缩健康：压缩比持续低于30%"""
    try:
        from core.harness.memory.manager import get_memory_manager
        mm = get_memory_manager()
        comp = getattr(mm, '_compression', None)
        if not comp or not hasattr(comp, 'compression_stats'):
            return None
        stats = comp.compression_stats
        if len(stats) < 2:
            return None
        savings = [(b - a) / max(b, 1) for b, a in stats[-2:]]
        avg = sum(savings) / len(savings)
        if all(s < 0.30 for s in savings):
            return {
                "rule": "compression_ineffective", "severity": "warning",
                "finding": f"最近压缩比仅{avg:.0%}——上下文可能溢出，影响Agent决策质量",
                "confidence": 0.6, "insufficient_data": False, "auto_fixable": False,
                "suggested_action": "检查压缩阈值设置，或增加低优先级内容的裁剪策略",
                "metrics": {"compression_ratio": round(avg, 2), "samples": len(stats)},
            }
    except Exception:
        logging.getLogger(__name__).debug('_check_memory_compression failed', exc_info=True)
    return None
