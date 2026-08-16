"""
OperationRecorder — 操作录制器 (Agent 闭环执行 — 技能自动化沉淀)

监听 sys_tool_call / sys_skill_call 的事件流，记录用户操作序列，
支持一键生成 SKILL.md。

设计原则:
  - 零开销: 仅在 trace_context["_recording_id"] 存在时记录
  - 脱敏: SkillGenerator 调用 LLM 前自动替换敏感信息

调用者: RecordingPanel 前端 / REST API
"""

from __future__ import annotations

import json as _json
import logging
import time as _time
import uuid as _uuid
from dataclasses import dataclass, field
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RECORDING_STORE = _Path(
    __import__("os").getenv("AIPLAT_HOME",
                            str(_Path("~").expanduser() / ".aiplat"))
) / "recordings"


# ── Data Models ──────────────────────────────────────────────────────────

@dataclass
class OperationStep:
    """单个操作步骤."""
    seq: int
    tool_name: str
    tool_args: Dict[str, Any] = field(default_factory=dict)
    result_type: str = ""              # success | failed | approval_required
    result_summary: str = ""           # 结果摘要 (截断到 200 字符)
    duration_ms: float = 0.0
    recorded_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seq": self.seq,
            "tool": self.tool_name,
            "args_summary": self._summarize_args(),
            "result": self.result_type,
            "result_summary": self.result_summary[:200],
            "duration_ms": self.duration_ms,
        }

    def _summarize_args(self) -> str:
        """脱敏后的参数摘要."""
        if not self.tool_args:
            return "{}"
        safe = {}
        for k, v in list(self.tool_args.items())[:5]:
            if isinstance(v, (str, int, float, bool)):
                safe[k] = v
            elif isinstance(v, (list, dict)):
                safe[k] = f"<{type(v).__name__}(len={len(v)})>"
        return _json.dumps(safe, ensure_ascii=False)[:200]


@dataclass
class Recording:
    recording_id: str
    status: str = "idle"               # idle | recording | stopped
    steps: List[OperationStep] = field(default_factory=list)
    started_at: float = 0.0
    stopped_at: float = 0.0
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recording_id": self.recording_id,
            "status": self.status,
            "step_count": len(self.steps),
            "steps": [s.to_dict() for s in self.steps],
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
        }


# ── OperationRecorder ─────────────────────────────────────────────────────

class OperationRecorder:
    """操作录制器.

    使用方式:
        recorder = OperationRecorder()
        rid = recorder.start("录制月报生成流程")
        # ... 用户执行操作 ...
        recording = recorder.stop()
        recording.save()
    """

    _instance: Optional["OperationRecorder"] = None
    _active: Optional[Recording] = None

    @classmethod
    def get(cls) -> "OperationRecorder":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start(self, description: str = "") -> str:
        """开始录制."""
        rid = f"rec_{_uuid.uuid4().hex[:12]}"
        self._active = Recording(
            recording_id=rid,
            status="recording",
            started_at=_time.time(),
            description=description,
        )
        logger.info("Recording started: %s", rid)
        return rid

    def stop(self) -> Optional[Recording]:
        """停止录制."""
        if not self._active:
            return None
        self._active.status = "stopped"
        self._active.stopped_at = _time.time()
        recording = self._active
        self._active = None
        logger.info("Recording stopped: %s (%d steps)", recording.recording_id, len(recording.steps))
        return recording

    def is_recording(self) -> bool:
        return self._active is not None and self._active.status == "recording"

    def get_recording_id(self) -> str:
        return self._active.recording_id if self._active else ""

    def record_step(
        self,
        tool_name: str,
        tool_args: Optional[Dict[str, Any]],
        result_type: str,
        result_summary: str,
        duration_ms: float = 0.0,
    ) -> None:
        """记录单个操作步骤 (仅在录制中时生效)."""
        if not self._active or self._active.status != "recording":
            return

        step = OperationStep(
            seq=len(self._active.steps) + 1,
            tool_name=tool_name or "unknown",
            tool_args=tool_args or {},
            result_type=result_type,
            result_summary=result_summary[:200],
            duration_ms=duration_ms,
            recorded_at=_time.time(),
        )
        self._active.steps.append(step)

    def get_active(self) -> Optional[Recording]:
        return self._active

    def save(self, recording: Recording) -> str:
        """持久化录制结果到磁盘."""
        import os as _os
        _os.makedirs(str(RECORDING_STORE), exist_ok=True)
        path = str(RECORDING_STORE / f"{recording.recording_id}.json")
        with open(path, "w") as f:
            _json.dump(recording.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info("Recording saved: %s", path)
        return path

    def load(self, recording_id: str) -> Optional[Dict[str, Any]]:
        """从磁盘加载录制结果."""
        path = RECORDING_STORE / f"{recording_id}.json"
        if not path.exists():
            return None
        with open(path) as f:
            return _json.load(f)

    def list_recordings(self, limit: int = 20) -> List[Dict[str, Any]]:
        """列出最近的录制."""
        if not RECORDING_STORE.exists():
            return []
        files = sorted(RECORDING_STORE.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]
        results = []
        for f in files:
            try:
                with open(f) as fh:
                    data = _json.load(fh)
                results.append({
                    "recording_id": data.get("recording_id", f.stem),
                    "step_count": data.get("step_count", 0),
                    "started_at": data.get("started_at", 0),
                    "status": data.get("status", ""),
                })
            except Exception:
                continue
        return results


# Need Path for file operations
import os as _os
from pathlib import Path as _Path
