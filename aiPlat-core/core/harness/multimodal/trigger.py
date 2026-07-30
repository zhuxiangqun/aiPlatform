import logging
"""MultiModalTrigger — multi-modal inputs as Goal loop trigger sources.
G-axis L4→L5 enabler: full closed-loop multi-modal Agent activation.

Auto-detects audio/video/browser events and injects them as Goal triggers,
enabling autonomous multi-modal interaction without human intervention.
"""
import asyncio, json, os, sys, hashlib, time
from datetime import datetime, timezone
from typing import Optional, Callable


class MultiModalTrigger:
    """Multi-modal event → Goal loop trigger bridge.

    Watches for new multi-modal inputs and automatically:
    1. Detects the input type (audio/video/image/browser)
    2. Transcribes/parses as needed
    3. Creates a Goal in the Agent's Goal loop
    4. Injects multi-modal context into the Agent's working memory
    """

    def __init__(self, watch_paths: list[str] | None = None):
        self.watch_paths = watch_paths or self._default_paths()
        self._checksums: dict[str, str] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._triggers: list[dict] = []
        self._callbacks: list[Callable] = []

    def _default_paths(self) -> list[str]:
        home = os.path.expanduser("~")
        return [
            os.path.join(home, ".aiplat", "incoming"),
            os.path.join(home, "Downloads", "aiplat_voice"),
        ]

    def on_trigger(self, callback: Callable[[dict], None]):
        """Register callback: callback(trigger_event) → None.
        trigger_event: {type, path, content, timestamp}"""
        self._callbacks.append(callback)

    def _detect_type(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        audio = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}
        video = {".mp4", ".mov", ".avi", ".mkv"}
        image = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
        if ext in audio:
            return "audio"
        elif ext in video:
            return "video"
        elif ext in image:
            return "image"
        return "unknown"

    async def _process_new_file(self, filepath: str) -> dict:
        """Process a newly detected multi-modal file."""
        ftype = self._detect_type(filepath)
        result = {"type": ftype, "path": filepath, "content": "", "timestamp": datetime.now(timezone.utc).isoformat()}

        try:
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
            core_path = os.path.join(repo_root, 'aiPlat-core')
            if core_path not in sys.path:
                sys.path.insert(0, core_path)

            if ftype == "audio":
                from core.harness.multimodal.voice_loop import get_voice_loop
                loop = await get_voice_loop()
                stt_r = await loop.stt(filepath)
                result["content"] = stt_r.get("text", "")
            elif ftype == "video":
                from core.harness.multimodal import get_multimodal_integrator
                mi = await get_multimodal_integrator()
                vr = await mi.parse_video_context(filepath)
                result["content"] = vr.get("transcript", "")
                result["keyframes"] = vr.get("keyframes", 0)
            elif ftype == "image":
                result["content"] = f"Image input detected: {filepath}"
        except Exception as e:
            result["error"] = str(e)[:200]

        return result

    async def _watch_loop(self):
        """Main watch loop — zero tokens, pure filesystem monitoring."""
        while self._running:
            try:
                for watch_path in self.watch_paths:
                    if not os.path.exists(watch_path):
                        continue
                    for fname in os.listdir(watch_path):
                        fpath = os.path.join(watch_path, fname)
                        if not os.path.isfile(fpath):
                            continue
                        try:
                            with open(fpath, "rb") as f:
                                cs = hashlib.md5(f.read()).hexdigest()
                        except (OSError, PermissionError):
                            continue

                        if cs != self._checksums.get(fpath, ""):
                            self._checksums[fpath] = cs
                            ftype = self._detect_type(fpath)
                            if ftype != "unknown":
                                trigger = await self._process_new_file(fpath)
                                self._triggers.append(trigger)
                                for cb in self._callbacks:
                                    try:
                                        result = cb(trigger)
                                        if asyncio.iscoroutine(result):
                                            await result
                                    except Exception:
                                        logging.getLogger(__name__).debug('_watch_loop failed', exc_info=True)
            except Exception:
                logging.getLogger(__name__).debug('_watch_loop failed', exc_info=True)
            await asyncio.sleep(10)

    async def start(self):
        """Start the multi-modal trigger watch loop."""
        for p in self.watch_paths:
            os.makedirs(p, exist_ok=True)
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        print(f"  [MultiModalTrigger] Watching {len(self.watch_paths)} paths for audio/video/image inputs")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    def get_recent_triggers(self, limit: int = 10) -> list[dict]:
        return self._triggers[-limit:]

    @property
    def trigger_count(self) -> int:
        return len(self._triggers)


class GoalLoopBridge:
    """Bridges MultiModalTrigger events into Agent Goal loop."""

    def __init__(self, trigger: MultiModalTrigger):
        self.trigger = trigger
        self._goal_executor = None
        self._processed: set = set()

    async def handle_multimodal_trigger(self, event: dict):
        """Handle a multi-modal trigger event: create Goal + inject context."""
        event_key = f"{event.get('path','')}:{event.get('timestamp','')}"
        if event_key in self._processed:
            return
        self._processed.add(event_key)

        ftype = event.get("type", "unknown")
        content = event.get("content", "")[:2000]

        try:
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
            core_path = os.path.join(repo_root, 'aiPlat-core')
            if core_path not in sys.path:
                sys.path.insert(0, core_path)

            from core.harness.optimization.goal_generator import GoalGenerator
            from core.harness.optimization.goal_executor import GoalExecutor

            if self._goal_executor is None:
                self._goal_executor = GoalExecutor()

            # Generate a Goal from the multi-modal input
            goal = GoalGenerator().generate(
                context=f"Multi-modal {ftype} input detected",
                content=content,
                priority="normal" if ftype in ("video", "image") else "elevated",
            )
            await self._goal_executor._execute_goal(goal)
        except Exception:
            logging.getLogger(__name__).debug('handle_multimodal_trigger failed', exc_info=True)


_trigger: Optional[MultiModalTrigger] = None
_bridge: Optional[GoalLoopBridge] = None


async def get_multimodal_trigger() -> MultiModalTrigger:
    global _trigger
    if _trigger is None:
        _trigger = MultiModalTrigger()
    return _trigger


async def get_goal_loop_bridge() -> GoalLoopBridge:
    global _trigger, _bridge
    if _trigger is None:
        _trigger = MultiModalTrigger()
    if _bridge is None:
        _bridge = GoalLoopBridge(_trigger)
    return _bridge
