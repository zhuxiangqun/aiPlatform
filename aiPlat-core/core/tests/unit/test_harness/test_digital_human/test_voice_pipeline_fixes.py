"""P0-1/P0-2 数字人管线修复测试 — registry 单例解析 + ASR segment 拼接 + profile 应用。

背景（分析报告 2026-08-21）：
  - P0-1: voice_pipeline 用 integration.get_agent_registry（DI 解析 TypeError → 空实例）
          → materials_chat 永远取不到 → 回答退化为 echo。修复: 改用 discovery 单例 + 直接创建兜底。
  - P0-2: transcribe 对 List[Dict] 结果用 str() → 输出垃圾文本。修复: 按 segment 拼接。
  - P1-1: digital_human profile 未应用。修复: generate_answer 入口 set_profile_override。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from core.harness.digital_human.voice_pipeline import transcribe


# ═══════════════════════════════════════════════════════════
# P0-2: ASR 转写 segment 拼接
# ═══════════════════════════════════════════════════════════

class FakeWhisperList:
    """模拟 InfraAudioAdapter.transcribe 返回 List[Dict]（真实返回类型）。"""

    def __init__(self, segments):
        self._segments = segments

    def transcribe(self, path):
        return self._segments


def test_transcribe_joins_segments(monkeypatch):
    """List[Dict] segment → 按顺序拼接文本，而非 str(list) 垃圾。"""
    fake = FakeWhisperList([
        {"start_ms": 0, "end_ms": 1200, "text": "你好小朱"},
        {"start_ms": 1200, "end_ms": 2000, "text": "帮我查一下合同"},
    ])

    async def fake_get_whisper():
        return fake

    monkeypatch.setattr("core.harness.digital_human.voice_pipeline._get_whisper", fake_get_whisper)
    text = asyncio.run(transcribe(b"fake-audio-bytes"))
    assert text == "你好小朱帮我查一下合同"
    assert not text.startswith("[{")  # 不再是 list repr


def test_transcribe_dict_fallback(monkeypatch):
    """旧式 dict 返回（{text: ...}）仍兼容。"""
    class FakeWhisperDict:
        def transcribe(self, path):
            return {"text": "旧式结果", "language": "zh"}

    async def fake_get_whisper():
        return FakeWhisperDict()

    monkeypatch.setattr("core.harness.digital_human.voice_pipeline._get_whisper", fake_get_whisper)
    assert asyncio.run(transcribe(b"x")) == "旧式结果"


def test_transcribe_empty_segments(monkeypatch):
    async def fake_get_whisper():
        return FakeWhisperList([])

    monkeypatch.setattr("core.harness.digital_human.voice_pipeline._get_whisper", fake_get_whisper)
    assert asyncio.run(transcribe(b"x")) == ""


# ═══════════════════════════════════════════════════════════
# P0-1: registry 解析走 discovery 单例
# ═══════════════════════════════════════════════════════════

def test_generate_answer_uses_discovery_registry(monkeypatch):
    """generate_answer 必须从 discovery 单例取 agent，而非 integration DI（P0-1）。"""
    import inspect
    from core.harness.digital_human import voice_pipeline
    src = inspect.getsource(voice_pipeline)
    # 不应再 import integration 的 get_agent_registry
    assert "from core.harness.integration import get_agent_registry" not in src
    assert "from core.apps.agents import get_agent_registry as _get_discovery_registry" in src


def test_generate_answer_direct_creation_fallback(monkeypatch):
    """单例为空时兜底直接创建 MaterialsChatAgent，不再退化 echo。"""
    from core.harness.digital_human import voice_pipeline

    captured = {}

    class FakeRegistry:
        def get(self, name):
            return None

    class FakeAgent:
        async def execute(self, ctx):
            captured["ctx"] = ctx
            from core.harness.interfaces import AgentResult
            return AgentResult(success=True, output={"answer": "真AI回答"})

    async def fake_tts(text, **kw):
        return b"TTSAUDIO"

    monkeypatch.setattr("core.apps.agents.get_agent_registry", lambda: FakeRegistry())
    monkeypatch.setattr("core.harness.syscalls.tts.sys_tts_generate", fake_tts)

    import core.apps.agents.materials_chat as mc_mod

    class FakeMCAgent(FakeAgent):
        def __init__(self, config):
            self._config = config

    monkeypatch.setattr(mc_mod, "MaterialsChatAgent", FakeMCAgent)

    async def run():
        return await voice_pipeline.generate_answer("你好，介绍一下系统")

    answer, audio = asyncio.run(run())
    assert answer == "真AI回答"
    assert audio == b"TTSAUDIO"


def test_generate_answer_echo_fallback_only_when_no_agent(monkeypatch):
    """确认 echo fallback 仍存在作为最后防线（双保险，非主路径）。"""
    from core.harness.digital_human import voice_pipeline
    src = open(voice_pipeline.__file__).read()
    assert '收到:' in src  # fallback 保留
