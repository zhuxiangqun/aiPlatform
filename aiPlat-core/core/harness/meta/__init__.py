"""
Meta-Agent — 元认知自改进 (Phase 4.4, 远期探索)

观察 AutoLearner 审批历史，自动生成改进 AutoLearner 策略的建议。
只读建议，不修改任何代码。所有策略变更必须人工审批。

触发: 每天自动分析一次 (或通过 API 手动触发)
环境变量: AIPLAT_META_AGENT_ENABLED=false (默认关闭, 远期探索)
"""

from __future__ import annotations
import logging

import asyncio, os, time, logging, json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from collections import Counter

_log = logging.getLogger("aiplat.meta_agent")


@dataclass
class MetaSuggestion:
    """元策略建议"""
    type: str = ""              # rejection_pattern / user_quality / stagnation / coverage_gap
    title: str = ""
    body: str = ""
    suggested_action: str = ""
    confidence: float = 0.0     # [0, 1]
    category: str = "auto_learner"  # 建议目标组件
    severity: str = "info"      # info / warning / critical


class MetaAgent:
    """元认知 Agent — 观察 AutoLearner，生成改进建议。

    Usage:
        meta = MetaAgent()
        suggestions = await meta.analyze(days=7)
        for s in suggestions:
            print(f"[{s.severity}] {s.title}: {s.suggested_action}")
    """

    def __init__(self):
        self._enabled = os.getenv("AIPLAT_META_AGENT_ENABLED", "false").lower() in ("1", "true", "yes")
        self._suggestions: List[MetaSuggestion] = []
        self._last_run: float = 0

    async def analyze(self, days: int = 7) -> List[MetaSuggestion]:
        """分析 AutoLearner 审批历史，生成改进建议"""
        if not self._enabled:
            return []

        self._suggestions = []
        self._last_run = time.time()

        # 1. Fetch approval history
        approvals = await self._fetch_approval_history(days)
        rejections = await self._fetch_rejection_history(days)

        all_records = approvals + rejections
        if not all_records:
            _log.info("MetaAgent: no data to analyze")
            return []

        # 2. Pattern detection
        await self._detect_rejection_patterns(rejections, approvals)
        await self._detect_user_quality(all_records)
        await self._detect_stagnation(approvals, days)
        await self._detect_coverage_gaps(approvals, days)

        # 3. Publish to event bus
        for s in self._suggestions:
            await self._publish(s)

        return self._suggestions

    # ── Detectors ────────────────────────────────────────────────────────

    async def _detect_rejection_patterns(self, rejections: list, approvals: list):
        """检测高频拒绝原因"""
        if len(rejections) < 5:
            return

        reasons = []
        for r in rejections:
            reason = (r.get("rejection_reason") or r.get("reason") or "").strip()
            if reason and len(reason) > 3:
                # Normalize: extract key phrase
                for kw in ["删除", "delete", "写入", "write", "权限", "permission", "格式", "format",
                           "缺少", "missing", "安全", "security", "文件", "file"]:
                    if kw in reason.lower():
                        reasons.append(kw)
                        break
                else:
                    reasons.append(reason[:30])

        if not reasons:
            return

        patterns = Counter(reasons).most_common(5)
        total = len(rejections)

        for pattern, count in patterns:
            ratio = count / total
            if ratio >= 0.3:  # 30% 以上
                self._suggestions.append(MetaSuggestion(
                    type="rejection_pattern",
                    title=f"高频拒绝原因: {pattern}",
                    body=f"过去 7 天 {count}/{total} 个 Draft 因与 '{pattern}' 相关的原因被拒绝 (占比 {ratio:.0%})。",
                    suggested_action=f"建议在 AutoLearner 中增加预检规则: 如 Draft 涉及 '{pattern}', 置信度 < 0.9 直接打回，无需提交人工审核。",
                    confidence=min(0.9, ratio),
                    severity="warning",
                ))

    async def _detect_user_quality(self, records: list):
        """检测用户维度的质量差异"""
        users = {}
        for r in records:
            uid = r.get("created_by") or r.get("agent_id") or "unknown"
            if uid not in users:
                users[uid] = {"approved": 0, "rejected": 0, "total": 0}
            users[uid]["total"] += 1
            if r.get("status") in ("approved", "accepted"):
                users[uid]["approved"] += 1
            else:
                users[uid]["rejected"] += 1

        for uid, stats in users.items():
            if stats["total"] >= 5:
                rate = stats["approved"] / stats["total"]
                if rate < 0.3:
                    self._suggestions.append(MetaSuggestion(
                        type="user_quality",
                        title=f"低质量贡献者: {uid}",
                        body=f"{uid} 提交了 {stats['total']} 个 Draft, 仅 {stats['approved']} 个通过 (通过率 {rate:.0%})。",
                        suggested_action=f"建议检查 {uid} 的 Agent 配置或 Skill 质量。可以考虑暂停其自学习权限直至质量提升。",
                        confidence=0.7,
                        severity="warning",
                    ))
                elif rate > 0.8 and stats["total"] >= 10:
                    self._suggestions.append(MetaSuggestion(
                        type="user_quality",
                        title=f"高质量贡献者: {uid}",
                        body=f"{uid} 提交了 {stats['total']} 个 Draft, {stats['approved']} 个通过 (通过率 {rate:.0%})。",
                        suggested_action=f"建议提升 {uid} 的自学习权限（如跳过部分人工审核）。",
                        confidence=0.7,
                        severity="info",
                    ))

    async def _detect_stagnation(self, approvals: list, days: int):
        """检测停滞"""
        recent = [a for a in approvals if a.get("created_at", 0) > time.time() - days * 86400]
        if not recent and days >= 7:
            self._suggestions.append(MetaSuggestion(
                type="stagnation",
                title="AutoLearner 可能停滞",
                body=f"过去 {days} 天没有产生任何新的审批通过的 Skill Draft。",
                suggested_action="检查 AutoLearner 是否正常运行，或降低触发阈值 (当前 pass_rate ≥ 80%)。",
                confidence=0.9,
                severity="critical",
            ))

    async def _detect_coverage_gaps(self, approvals: list, days: int):
        """检测能力覆盖缺口"""
        categories = Counter(
            a.get("category", "") or a.get("skill_category", "") or "unknown"
            for a in approvals if a.get("status") in ("approved", "accepted")
        )
        # Report top and missing categories
        if len(categories) == 1:
            cat = list(categories.keys())[0]
            self._suggestions.append(MetaSuggestion(
                type="coverage_gap",
                title=f"技能生成集中在 {cat}",
                body=f"过去 {days} 天生成的所有 Draft 都属于 '{cat}' 类别。",
                suggested_action=f"这可能意味着 AutoLearner 偏向特定领域。考虑在不同类型的任务上运行 Agent 以丰富多样性。",
                confidence=0.6,
                severity="info",
            ))

    # ── Internal ────────────────────────────────────────────────────────

    async def _fetch_approval_history(self, days: int) -> List[Dict[str, Any]]:
        """获取审批通过的历史"""
        try:
            import os as _os
            draft_dir = _os.path.expanduser("~/.aiplat/skill_drafts")
            results = []
            if _os.path.isdir(draft_dir):
                cutoff = time.time() - days * 86400
                for f in _os.listdir(draft_dir):
                    if f.endswith(".yaml"):
                        fpath = _os.path.join(draft_dir, f)
                        mtime = _os.path.getmtime(fpath)
                        if mtime > cutoff:
                            results.append({
                                "name": f.replace(".yaml", ""),
                                "created_at": mtime,
                                "status": "approved",
                            })
            return results
        except Exception:
            return []

    async def _fetch_rejection_history(self, days: int) -> List[Dict[str, Any]]:
        """获取被拒绝的历史"""
        try:
            from core.harness.learning import get_auto_learner
            learner = get_auto_learner()
            drafts = learner.list_drafts(status="rejected")
            cutoff = time.time() - days * 86400
            return [d for d in drafts if d.get("created_at", "") > time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(cutoff))]
        except Exception:
            return []

    async def _publish(self, suggestion: MetaSuggestion):
        """发布建议到事件总线"""
        try:
            from core.harness.observation.event_bus import EventBus
            EventBus.publish("meta_suggestion", {
                "type": suggestion.type,
                "title": suggestion.title,
                "body": suggestion.body,
                "action": suggestion.suggested_action,
                "confidence": suggestion.confidence,
                "severity": suggestion.severity,
                "category": suggestion.category,
            })
        except Exception as e:
            logging.debug(str(e), exc_info=True)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "suggestions_count": len(self._suggestions),
            "last_run": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._last_run)) if self._last_run else "never",
        }


# ── Global singleton ─────────────────────────────────────────────────────────

_meta_agent: Optional[MetaAgent] = None

def get_meta_agent() -> MetaAgent:
    global _meta_agent
    if _meta_agent is None:
        _meta_agent = MetaAgent()
    return _meta_agent
