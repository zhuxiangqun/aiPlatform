"""VoiceLoop — STT→Agent→Browser→TTS 语音半闭环引擎。
import logging
G-axis L3→L4 enabler.

完整链路: 语音输入 → STT转录 → Agent推理决策 → 浏览器/工具操作 → TTS语音反馈
"""
import asyncio, json, os, sys, tempfile
from typing import Optional


class VoiceLoop:
    """Voice-driven Agent interaction loop.

    Chain: audio_in → STT → Agent → Browser/Tool → TTS → audio_out
    """

    def __init__(self):
        self._audio = None
        self._browser = None
        self._init_ok = False

    async def _ensure_modules(self):
        if self._init_ok:
            return
        try:
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
            core_path = os.path.join(repo_root, 'aiPlat-core')
            if core_path not in sys.path:
                sys.path.insert(0, core_path)

            from core.harness.utils.model_injection import create_infra_audio_adapter
            self._audio = create_infra_audio_adapter()
            self._init_ok = True
        except Exception as e:
            print(f"  [!] VoiceLoop init failed: {e}", file=sys.stderr)
            self._init_ok = True

    async def stt(self, audio_path: str) -> dict:
        """Speech-to-text: audio file → transcribed text."""
        await self._ensure_modules()
        if not self._audio:
            return {"success": False, "text": "", "error": "Audio adapter unavailable"}

        try:
            text = await self._audio.transcribe(audio_path)
            return {"success": True, "text": text, "source": "stt"}
        except Exception as e:
            return {"success": False, "text": "", "error": str(e)[:300]}

    async def tts(self, text: str, output_path: str = "") -> dict:
        """Text-to-speech: text → audio file."""
        await self._ensure_modules()
        if not self._audio:
            return {"success": False, "path": "", "error": "Audio adapter unavailable"}

        try:
            if not output_path:
                output_path = os.path.join(tempfile.gettempdir(), f"tts_{hash(text)}.wav")
            await self._audio.synthesize(text, output_path)
            return {"success": True, "path": output_path, "source": "tts"}
        except Exception as e:
            return {"success": False, "path": "", "error": str(e)[:300]}

    async def process_voice_command(self, audio_path: str, llm_callback=None) -> dict:
        """Full voice loop: STT → Agent → Browser/Tool → TTS.

        Args:
            audio_path: Input audio file path
            llm_callback: async fn(text) → response_dict. If None, uses sys_llm_generate.

        Returns:
            dict with transcription, agent_response, browser_result, tts_output_path
        """
        result = {"transcription": "", "agent_response": "", "actions": [], "tts_path": ""}

        # Step 1: STT
        stt_r = await self.stt(audio_path)
        if not stt_r["success"]:
            return {**result, "error": f"STT failed: {stt_r.get('error')}"}
        result["transcription"] = stt_r["text"]

        # Step 2: Agent reasoning via LLM
        if llm_callback:
            agent_r = await llm_callback(stt_r["text"])
        else:
            agent_r = await self._default_llm_reason(stt_r["text"])
        result["agent_response"] = str(agent_r.get("content", agent_r.get("reply", "")))

        # Step 3: Execute browser actions if agent requested
        actions = agent_r.get("actions", []) if isinstance(agent_r, dict) else []
        for action in actions:
            try:
                from core.harness.multimodal import get_multimodal_integrator
                integrator = await get_multimodal_integrator()
                br = await integrator.capture_browser(**action)
                result["actions"].append(br)
            except Exception:
                logging.getLogger(__name__).debug('process_voice_command failed', exc_info=True)

        # Step 4: TTS feedback
        tts_text = result["agent_response"] or "Action completed."
        tts_r = await self.tts(tts_text[:500])
        result["tts_path"] = tts_r.get("path", "")

        return result

    async def _default_llm_reason(self, text: str) -> dict:
        """Default LLM reasoning when no callback provided."""
        try:
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
            core_path = os.path.join(repo_root, 'aiPlat-core')
            if core_path not in sys.path:
                sys.path.insert(0, core_path)
            from core.harness.utils.model_injection import best_model_for_purpose, create_selected_adapter
            from core.harness.syscalls.llm import sys_llm_generate

            model = best_model_for_purpose("chat")
            adapter = create_selected_adapter(model_name=model)
            response = await sys_llm_generate(
                adapter,
                prompt=[{"role": "user", "content": f"User said: {text}. Respond concisely with your answer and any actions to take. Format as JSON with 'content' and 'actions' fields."}],
                model_name=model,
                temperature=0.7,
                max_tokens=1024,
            )
            try:
                return json.loads(response.content)
            except json.JSONDecodeError:
                return {"content": response.content, "actions": []}
        except Exception as e:
            return {"content": f"Voice command received: {text}", "actions": []}


_voice_loop: Optional[VoiceLoop] = None


async def get_voice_loop() -> VoiceLoop:
    global _voice_loop
    if _voice_loop is None:
        _voice_loop = VoiceLoop()
    return _voice_loop
