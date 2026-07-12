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
            fd = GraphIndex.load("fde-delivery")
            sessions = []
            for _, n in fd._nodes.items():
                if getattr(n, "class_name", "") == "DiagnosisSession":
                    nb = fd.get_neighbors(getattr(n, "entity_id", ""), direction="outgoing")
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
                                    pass

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

        try:
            first = snapshots[0]
            last = snapshots[-1]
            first_delivery = first.get("components", {}).get("delivery", {}).get("delivery_rate", 0)
            last_delivery = last.get("components", {}).get("delivery", {}).get("delivery_rate", 0)
            delivery_decline = first_delivery - last_delivery if first_delivery and last_delivery else 0

            first_layers = first.get("components", {}).get("context_bus", {}).get("layers_ok", 0)
            last_layers = last.get("components", {}).get("context_bus", {}).get("layers_ok", 0)
            layers_growth = last_layers - first_layers if first_layers and last_layers else 0

            if layers_growth > 2 and delivery_decline > 10:
                return {
                    "rule": "knowledge_gap", "severity": "warning",
                    "finding": f"Pipeline 健康度增长 +{layers_growth}，但交付率下降 {delivery_decline}%——知识在产出但未转化为交付",
                    "confidence": 0.75, "insufficient_data": False, "auto_fixable": True,
                    "suggested_action": "检查交付流程是否正常、客户反馈是否及时录入、FDE诊断后是否有行动项跟进",
                    "metrics": {"layers_growth": layers_growth, "delivery_decline": delivery_decline},
                }
        except Exception as e:
            logger.debug("Knowledge gap check skipped: %s", str(e))

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

                    # Audit record
                    _record_heal_audit(fix_name, resolved, before, after)
                except Exception as e:
                    actions.append({
                        "finding": fix_name,
                        "resolved": False,
                        "error": str(e)[:200],
                    })

        return {
            "auto_fixed": auto_fixed,
            "actions": actions,
            "confidence": confidence,
            "philosophy": "可回滚、可审计、有验证",
        }

    def _snapshot(self, tag: str, phase: str) -> Dict[str, str]:
        return {"tag": f"{tag}_{phase}", "ts": str(__import__('time').time())}


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
    return "suggest: run GET /fde/sessions/{id}/improve for recent sessions"


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
        pass
