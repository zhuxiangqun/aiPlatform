"""
VoiceLoopTool — 完整语音循环工具 (STT → Agent → Browser/Tool → TTS)

接线 harness/multimodal/voice_loop.py 的 VoiceLoop 类 (P0-B3)。
与 TTSTool (单程 TTS) 互补: VoiceLoopTool 执行完整语音闭环。
通过 sys_tool_call("voice_loop") → PolicyGate → VoiceLoopTool.execute() 调用。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from core.apps.tools.base import BaseTool, ToolMetadata

logger = logging.getLogger(__name__)


class VoiceLoopTool(BaseTool):
    def __init__(self):
        super().__init__(ToolMetadata(
            name="voice_loop",
            description="执行完整语音循环: 语音转文字(STT) → Agent 推理 → 浏览器操作 → 文字转语音(TTS)。"
                        "输入本地音频文件路径, 返回转录文本、Agent 回复与 TTS 输出。"
                        "零网络、零 API Key (本地 Whisper + Piper)。",
            category="multimodal",
            tags=["voice", "audio", "speech", "stt", "tts", "语音"],
        ))
        self.input_schema = {
            "type": "object",
            "properties": {
                "audio_path": {
                    "type": "string",
                    "description": "本地音频文件路径 (wav/mp3/m4a/ogg/flac)",
                },
            },
            "required": ["audio_path"],
        }

    async def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        audio_path = str(args.get("audio_path", "")).strip()
        if not audio_path:
            return {"success": False, "error": "audio_path 不能为空"}

        try:
            from core.harness.multimodal.voice_loop import VoiceLoop
            result = await VoiceLoop().process_voice_command(audio_path)
            return {"success": True, **result}
        except Exception as e:
            logger.warning("Voice loop failed: %s", e)
            return {"success": False, "error": str(e)[:300]}
