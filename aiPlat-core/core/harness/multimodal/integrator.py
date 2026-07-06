"""MultimodalIntegrator — bridges audio/browser/video into Agent decision loop.
G-axis L2→L3 enabler.

Transforms standalone multimodal modules into Agent-aware context providers.
"""
import os, sys, json, asyncio
from typing import Optional


class MultimodalIntegrator:
    """Bridges standalone multimodal modules into Agent context.

    Three input channels:
    - Audio: STT transcription → text injected into Agent prompt
    - Browser: screenshot/action results → structured observation
    - Video: keyframe extraction + transcript → summary context

    The integrator does NOT duplicate existing modules. It wraps them
    and provides a unified interface for Agent context injection.
    """

    def __init__(self):
        self._audio_adapter = None
        self._browser_engine = None
        self._video_parser = None
        self._initialized = False

    async def _initialize(self):
        if self._initialized:
            return
        try:
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
            core_path = os.path.join(repo_root, 'aiPlat-core')
            if core_path not in sys.path:
                sys.path.insert(0, core_path)

            # Lazy-load adapters to avoid import overhead when not used
            from core.harness.utils.model_injection import create_infra_audio_adapter
            self._audio_adapter = create_infra_audio_adapter()
            self._initialized = True
        except Exception as e:
            print(f"  [!] MultimodalIntegrator init partial: {e}", file=sys.stderr)
            self._initialized = True

    async def transcribe_audio(self, audio_path: str) -> dict:
        """Transcribe audio to text for Agent context."""
        await self._initialize()
        if not self._audio_adapter:
            return {"success": False, "text": "", "error": "Audio adapter not available"}

        try:
            text = await self._audio_adapter.transcribe(audio_path)
            return {"success": True, "text": text, "source": "audio_stt"}
        except Exception as e:
            return {"success": False, "text": "", "error": str(e)[:500], "source": "audio_stt"}

    async def capture_browser(self, command: str, **kwargs) -> dict:
        """Execute browser action and return structured observation."""
        try:
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
            core_path = os.path.join(repo_root, 'aiPlat-core')
            if core_path not in sys.path:
                sys.path.insert(0, core_path)

            from core.apps.testing.browser_test_engine import BrowserTestEngine
            if self._browser_engine is None:
                self._browser_engine = BrowserTestEngine()

            action_map = {
                "navigate": self._browser_engine.navigate,
                "click": self._browser_engine.click,
                "screenshot": self._browser_engine.screenshot,
                "get_text": self._browser_engine.get_text,
                "fill": self._browser_engine.fill,
            }

            action = action_map.get(command)
            if not action:
                return {"success": False, "error": f"Unknown browser command: {command}", "source": "browser"}

            result = await action(**kwargs)
            return {"success": True, "result": str(result)[:2000], "command": command, "source": "browser"}
        except ImportError:
            return {"success": False, "error": "BrowserTestEngine not available", "source": "browser"}
        except Exception as e:
            return {"success": False, "error": str(e)[:500], "command": command, "source": "browser"}

    async def parse_video_context(self, video_path: str) -> dict:
        """Extract keyframes + transcript summary from video."""
        try:
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
            core_path = os.path.join(repo_root, 'aiPlat-core')
            if core_path not in sys.path:
                sys.path.insert(0, core_path)

            from core.apps.document_intelligence.video_parser import VideoParser
            if self._video_parser is None:
                self._video_parser = VideoParser()

            result = await self._video_parser.parse(video_path)
            return {
                "success": True,
                "transcript": str(getattr(result, "transcript", ""))[:5000],
                "keyframes": len(getattr(result, "keyframes", [])),
                "duration": getattr(result, "duration", 0),
                "source": "video_parser",
            }
        except ImportError:
            return {"success": False, "error": "VideoParser not available. Install: pip install faster-whisper", "source": "video_parser"}
        except Exception as e:
            return {"success": False, "error": str(e)[:500], "source": "video_parser"}

    def build_multimodal_context(self, inputs: list[dict]) -> str:
        """Aggregate multimodal inputs into a structured context block for Agent.

        Args:
            inputs: list of dicts from transcribe_audio / capture_browser / parse_video_context

        Returns:
            Formatted context string for injection into Agent system/user prompt.
        """
        if not inputs:
            return ""

        blocks = []
        for inp in inputs:
            source = inp.get("source", "unknown")
            if source == "audio_stt":
                blocks.append(f"[语音转录]\n{inp.get('text', '')}")
            elif source == "browser":
                blocks.append(f"[浏览器操作: {inp.get('command', '')}]\n{inp.get('result', '')}")
            elif source == "video_parser":
                blocks.append(f"[视频解析: {inp.get('keyframes', 0)}帧, {inp.get('duration', 0)}s]\n{inp.get('transcript', '')}")

        return "\n\n".join(blocks)

    async def process_multimodal_input(self, file_path: str, file_type: str) -> dict:
        """Auto-detect and process multimodal input by file extension."""
        ext = os.path.splitext(file_path)[1].lower() if "." in file_path else ""

        audio_exts = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}
        video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
        image_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

        if ext in audio_exts or file_type == "audio":
            return await self.transcribe_audio(file_path)
        elif ext in video_exts or file_type == "video":
            return await self.parse_video_context(file_path)
        elif ext in image_exts or file_type == "image":
            return {"success": True, "result": f"Image file: {file_path}", "source": "image", "note": "Use vision model for analysis"}
        else:
            return {"success": False, "error": f"Unsupported type: {ext}", "source": "unknown"}


# Singleton
_integrator: Optional[MultimodalIntegrator] = None


async def get_multimodal_integrator() -> MultimodalIntegrator:
    global _integrator
    if _integrator is None:
        _integrator = MultimodalIntegrator()
    return _integrator
