"""
TTSTool — 本地文本转语音工具 (Piper TTS)

零网络、零 API Key、纯 CPU 本地执行。
通过 InfraAudioAdapter.synthesize() 调用 piper CLI,
模型配置从 llm_profile.yaml 读取 (best_model_for_purpose("tts")).

调用链:
  Agent → sys_tool_call("tts_generate") → PolicyGate → TTSTool.execute()
    → InfraAudioAdapter.synthesize() → piper CLI → WAV 文件
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from core.apps.tools.base import BaseTool, ToolMetadata

logger = logging.getLogger(__name__)


class TTSTool(BaseTool):
    def __init__(self):
        super().__init__(ToolMetadata(
            name="tts_generate",
            display_name="文本转语音",
            description="调用本地 Piper TTS 引擎将文本转为 WAV 音频文件。零网络、零 API Key。支持中文女声(huayan)和中文通用(ljspeech)。",
            category="multimodal",
            tags=["tts", "audio", "voice", "speech", "语音"],
        ))
        self.input_schema = {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "要转换为语音的文本内容",
                },
                "voice": {
                    "type": "string",
                    "enum": ["huayan", "ljspeech"],
                    "default": "huayan",
                    "description": "语音角色: huayan(女声,自然), ljspeech(通用)",
                },
            },
            "required": ["text"],
        }

    async def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        text = str(args.get("text", "")).strip()
        if not text:
            return {"success": False, "error": "text 不能为空"}

        voice = str(args.get("voice", "huayan"))

        try:
            from core.harness.infrastructure.infra_audio_adapter import InfraAudioAdapter
            adapter = InfraAudioAdapter()
            path = await adapter.synthesize(text, voice=voice)
            return {
                "success": True,
                "audio_path": path,
                "text_length": len(text),
                "voice": voice,
            }
        except Exception as e:
            logger.warning("TTS generation failed: %s", e)
            return {"success": False, "error": str(e)[:200]}
