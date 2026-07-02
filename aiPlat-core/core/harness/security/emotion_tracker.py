"""
Emotion Tracker — cross-session emotional state tracking and dependency detection.

Tracks emotional arcs across sessions via SemanticMemory (tag="emotion_profile").
Detects over-dependency patterns (excessive usage frequency, emotional dependence).

Usage:
    from core.harness.security.emotion_tracker import EmotionTracker, get_emotion_tracker

    tracker = get_emotion_tracker()
    await tracker.track(session_id="s1", messages=[...], tenant_id="t1")
    state = await tracker.get_state(session_id="s1", tenant_id="t1")
"""

from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger("aiplat.emotion_tracker")


class EmotionalTone(str, Enum):
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    ANXIOUS = "anxious"
    SAD = "sad"
    ANGRY = "angry"
    HOPEFUL = "hopeful"
    FEARFUL = "fearful"
    MIXED = "mixed"


@dataclass
class EmotionSnapshot:
    session_id: str
    timestamp: float
    dominant_tone: EmotionalTone = EmotionalTone.NEUTRAL
    intensity: float = 0.5
    keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "dominant_tone": self.dominant_tone.value,
            "intensity": round(self.intensity, 2),
            "keywords": self.keywords,
        }


@dataclass
class EmotionState:
    tenant_id: str
    session_id: str
    current_tone: EmotionalTone = EmotionalTone.NEUTRAL
    history: List[EmotionSnapshot] = field(default_factory=list)
    trend: str = "stable"                         # improving | stable | declining
    dependency_risk: str = "low"                   # low | medium | high
    sessions_24h: int = 0
    avg_session_length_min: float = 0.0

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "current_tone": self.current_tone.value,
            "trend": self.trend,
            "dependency_risk": self.dependency_risk,
            "sessions_24h": self.sessions_24h,
            "avg_session_length_min": round(self.avg_session_length_min, 1),
            "history": [h.to_dict() for h in self.history[-10:]],
        }


TONAL_KEYWORDS: Dict[EmotionalTone, List[str]] = {
    EmotionalTone.POSITIVE: ["happy", "great", "wonderful", "love", "thank", "hope", "good", "nice",
                              "开心", "太好", "感谢", "喜欢", "幸福", "希望", "不错", "谢谢"],
    EmotionalTone.ANXIOUS: ["worried", "anxious", "nervous", "stress", "panic", "overwhelmed",
                            "担心", "焦虑", "紧张", "压力", "烦躁", "受不了", "崩溃"],
    EmotionalTone.SAD: ["sad", "lonely", "alone", "cry", "depressed", "miss", "empty", "hurt",
                        "难过", "孤独", "寂寞", "哭", "抑郁", "想念", "空虚", "受伤"],
    EmotionalTone.ANGRY: ["angry", "furious", "hate", "unfair", "stupid", "ridiculous",
                          "生气", "愤怒", "恨", "不公平", "烦人", "讨厌"],
    EmotionalTone.FEARFUL: ["scared", "afraid", "terrified", "fear", "danger", "threat",
                            "害怕", "恐惧", "恐怖", "危险", "威胁", "不敢"],
    EmotionalTone.HOPEFUL: ["hope", "better", "future", "dream", "believe", "forward",
                            "希望", "更好", "未来", "梦想", "相信", "期待"],
}


class EmotionTracker:
    """Cross-session emotional state tracker."""

    def __init__(self, dependency_window_days: int = 7, dependency_threshold_sessions: int = 30):
        self._window_days = dependency_window_days
        self._threshold_sessions = dependency_threshold_sessions
        self._cache: Dict[str, EmotionState] = {}

    def _cache_key(self, tenant_id: str, session_id: str) -> str:
        return f"{tenant_id}:{session_id}"

    async def _ensure_table(self) -> None:
        try:
            from core.services.execution_store import get_execution_store
            store = get_execution_store()
            def _create():
                conn = store._connect()
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS emotion_snapshots (
                        id TEXT PRIMARY KEY,
                        tenant_id TEXT NOT NULL DEFAULT 'default',
                        session_id TEXT NOT NULL,
                        dominant_tone TEXT NOT NULL DEFAULT 'neutral',
                        intensity REAL NOT NULL DEFAULT 0.5,
                        keywords_json TEXT NOT NULL DEFAULT '[]',
                        timestamp REAL NOT NULL,
                        created_at TEXT NOT NULL DEFAULT (datetime('now'))
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_emotion_session ON emotion_snapshots(tenant_id, session_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_emotion_timestamp ON emotion_snapshots(timestamp);")
                conn.commit()
                conn.close()
            await store._run_in_executor(_create)
        except Exception as e:
            _log.debug("Emotion persistence unavailable: %s", e)

    async def _persist_snapshot(self, snapshot: EmotionSnapshot, tenant_id: str) -> None:
        import json as _json, uuid as _uuid
        try:
            from core.services.execution_store import get_execution_store
            store = get_execution_store()
            await self._ensure_table()
            sid = str(_uuid.uuid4())
            await store._execute(
                "INSERT OR REPLACE INTO emotion_snapshots(id,tenant_id,session_id,dominant_tone,intensity,keywords_json,timestamp) VALUES(?,?,?,?,?,?,?);",
                (sid, tenant_id, snapshot.session_id, snapshot.dominant_tone.value,
                 snapshot.intensity, _json.dumps(snapshot.keywords), snapshot.timestamp),
            )
        except Exception as e:
            _log.debug("Emotion persist skipped: %s", e)

    async def _load_from_store(self, session_id: str, tenant_id: str = "default") -> Optional[EmotionState]:
        import json as _json
        try:
            from core.services.execution_store import get_execution_store
            store = get_execution_store()
            rows = await store._execute(
                "SELECT * FROM emotion_snapshots WHERE tenant_id=? AND session_id=? ORDER BY timestamp DESC",
                (tenant_id, session_id),
            )
            if not rows:
                return None
            state = EmotionState(tenant_id=tenant_id, session_id=session_id)
            for row in rows:
                state.history.append(EmotionSnapshot(
                    session_id=row[2],
                    timestamp=row[4],
                    dominant_tone=EmotionalTone(row[3]),
                    intensity=row[5],
                    keywords=_json.loads(row[6]) if row[6] else [],
                ))
            if state.history:
                state.current_tone = state.history[0].dominant_tone
                state.trend = self._compute_trend(state.history)
                state.dependency_risk = self._compute_dependency_risk(state, 0.0)
            self._cache[self._cache_key(tenant_id, session_id)] = state
            return state
        except Exception as e:
            _log.debug("Emotion load skipped: %s", e)
            return None

    async def track(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        tenant_id: str = "default",
        session_duration_s: float = 0.0,
    ):
        if not messages:
            return

        text = " ".join(
            str(m.get("content", "")) or ""
            for m in messages
            if isinstance(m.get("content"), str)
        )
        if not text.strip():
            return

        tone, intensity, kw = self._extract_tone(text)
        snapshot = EmotionSnapshot(
            session_id=session_id,
            timestamp=time.time(),
            dominant_tone=tone,
            intensity=intensity,
            keywords=kw,
        )

        key = self._cache_key(tenant_id, session_id)
        state = self._cache.get(key)
        if state is None:
            state = EmotionState(tenant_id=tenant_id, session_id=session_id)
        state.history.append(snapshot)
        state.current_tone = tone
        state.trend = self._compute_trend(state.history)
        state.dependency_risk = self._compute_dependency_risk(state, session_duration_s)
        self._cache[key] = state

        _log.debug("Emotion tracked: session=%s, tone=%s, intensity=%.2f", session_id, tone.value, intensity)

        # Persist snapshot asynchronously so it survives restarts
        import asyncio as _asyncio
        _asyncio.ensure_future(self._persist_snapshot(snapshot, tenant_id))

    def _extract_tone(self, text: str) -> Tuple[EmotionalTone, float, List[str]]:
        lowered = text.lower()
        scores: Dict[EmotionalTone, int] = {}
        all_kw: List[str] = []

        for tone, keywords in TONAL_KEYWORDS.items():
            count = 0
            for kw in keywords:
                if kw.lower() in lowered:
                    count += 1
                    all_kw.append(kw)
            scores[tone] = count

        if not all_kw:
            return EmotionalTone.NEUTRAL, 0.3, []

        best_tone = max(scores, key=scores.get)
        max_count = scores[best_tone]
        intensity = min(1.0, max_count / 5.0)
        return best_tone, intensity, all_kw[:8]

    def _compute_trend(self, history: List[EmotionSnapshot]) -> str:
        if len(history) < 2:
            return "stable"
        recent = history[-3:]
        earlier = history[max(0, len(history) - 6):len(history) - 3] if len(history) >= 3 else []
        if not earlier:
            return "stable"
        recent_neg = sum(1 for s in recent if s.dominant_tone in (EmotionalTone.SAD, EmotionalTone.ANXIOUS, EmotionalTone.ANGRY))
        earlier_neg = sum(1 for s in earlier if s.dominant_tone in (EmotionalTone.SAD, EmotionalTone.ANXIOUS, EmotionalTone.ANGRY))
        if recent_neg > earlier_neg:
            return "declining"
        if recent_neg < earlier_neg:
            return "improving"
        return "stable"

    def _compute_dependency_risk(self, state: EmotionState, session_duration_s: float) -> str:
        now = time.time()
        window_start = now - self._window_days * 86400
        recent = [h for h in state.history if h.timestamp >= window_start]
        state.sessions_24h = sum(1 for h in recent if h.timestamp >= now - 86400)

        # Dependency indicators
        negative_tones = sum(1 for h in recent if h.dominant_tone in (EmotionalTone.SAD, EmotionalTone.ANXIOUS, EmotionalTone.ANGRY, EmotionalTone.FEARFUL))
        session_count = len(recent)

        risk_score = 0
        if state.sessions_24h > self._threshold_sessions:
            risk_score += 2
        if session_count > 50:
            risk_score += 1
        if negative_tones > session_count * 0.4:
            risk_score += 2
        if session_duration_s > 3600:
            risk_score += 1

        if risk_score >= 4:
            return "high"
        if risk_score >= 2:
            return "medium"
        return "low"

    async def get_state(self, session_id: str, tenant_id: str = "default") -> Optional[EmotionState]:
        key = self._cache_key(tenant_id, session_id)
        if key in self._cache:
            return self._cache[key]
        return await self._load_from_store(session_id, tenant_id)

    def get_flagged_sessions(self, tenant_id: str = "default") -> List[EmotionState]:
        flagged = []
        prefix = f"{tenant_id}:"
        for key, state in self._cache.items():
            if key.startswith(prefix) and (state.dependency_risk in ("medium", "high") or
                                            state.trend == "declining"):
                flagged.append(state)
        flagged.sort(key=lambda s: len(s.history), reverse=True)
        return flagged


_emotion_tracker: Optional[EmotionTracker] = None


def get_emotion_tracker() -> EmotionTracker:
    global _emotion_tracker
    if _emotion_tracker is None:
        _emotion_tracker = EmotionTracker()
    return _emotion_tracker
