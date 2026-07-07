"""T0.14 VoiceLoop 集成验证 — STT→TTS pipeline 行为层测试.

Verifies the VoiceLoop full pipeline infrastructure is importable and
the core classes are wired (modules may be absent in CI — graceful skips).
"""
import pytest


@pytest.mark.asyncio
async def test_voice_loop_module_imports():
    """T0.14: VoiceLoop class + get_voice_loop() 存在."""
    from core.harness.multimodal.voice_loop import VoiceLoop, get_voice_loop
    assert VoiceLoop is not None
    vl = await get_voice_loop()
    assert vl is not None
    assert hasattr(vl, "stt"), "STT method missing"
    assert hasattr(vl, "tts"), "TTS method missing"
    assert hasattr(vl, "process_voice_command"), "full voice pipeline missing"


@pytest.mark.asyncio
async def test_voice_loop_stt_module():
    """T0.14: InfraAudioAdapter 可导入 (STT 后端)."""
    try:
        from core.harness.infrastructure.infra_audio_adapter import InfraAudioAdapter
        assert InfraAudioAdapter is not None
    except ImportError:
        pytest.skip("InfraAudioAdapter not available in this environment")


@pytest.mark.asyncio
async def test_voice_loop_configurable():
    """T0.14: VoiceLoop 可创建 + 方法存在."""
    from core.harness.multimodal.voice_loop import VoiceLoop
    vl = VoiceLoop()
    assert vl is not None
    assert hasattr(vl, "stt") and hasattr(vl, "tts") and hasattr(vl, "process_voice_command")
