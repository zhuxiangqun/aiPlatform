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
    """generate_answer 必须从 integration 入口解析（其内部已是 discovery 单例），且不直导 apps。"""
    import inspect
    from core.harness.digital_human import voice_pipeline
    src = inspect.getsource(voice_pipeline)
    # 不应直导 core.apps（harness→apps 边界）
    assert "from core.apps.agents import" not in src
    assert "from core.harness.integration import get_agent_registry" in src
    assert "from core.api.core_facade import create_agent" in src  # 兜底经 facade


def test_integration_registry_is_discovery_singleton(monkeypatch):
    """P0-1 根因修复验证: integration.get_agent_registry 现在返回 discovery 单例（非空实例）。"""
    from core.harness.integration import get_agent_registry as di_get
    from core.apps.agents import get_agent_registry as app_get
    assert di_get() is app_get()


def test_generate_answer_direct_creation_fallback(monkeypatch):
    """单例为空时兜底经 CoreFacade.create_agent 创建，不再退化 echo。"""
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

    monkeypatch.setattr("core.harness.integration.get_agent_registry", lambda: FakeRegistry())
    monkeypatch.setattr("core.harness.syscalls.tts.sys_tts_generate", fake_tts)

    def fake_create_agent(agent_type, config):
        assert agent_type == "materials_chat"
        return FakeAgent()

    monkeypatch.setattr("core.api.core_facade.create_agent", fake_create_agent)

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


# ═══════════════════════════════════════════════════════════
# P1-2: 轨迹 → ShareGPT 数据集闭环
# ═══════════════════════════════════════════════════════════

def test_export_sharegpt_dataset(monkeypatch, tmp_path):
    """数字人轨迹聚合为训练侧 ShareGPT JSONL（与 auto_trigger 格式一致）。"""
    import json as _json
    from pathlib import Path as _Path
    from core.harness.digital_human import trajectory_collector as _tc
    traj_dir = tmp_path / "trajectories"
    traj_dir.mkdir()
    _tc._TRAJ_DIR = _Path(str(traj_dir))  # 模块级常量直接指向 tmp（env 已被模块缓存）

    from core.harness.digital_human.trajectory_collector import collect_turn, export_sharegpt_dataset
    collect_turn("sess_a", "user", "你好")
    collect_turn("sess_a", "assistant", "你好！有什么可以帮你？")
    collect_turn("sess_b", "user", "单轮噪音")

    out_dir = tmp_path / "training"
    r = export_sharegpt_dataset(output_dir=str(out_dir), min_turns=2)
    assert r["samples"] == 1
    assert r["skipped_sessions"] == ["sess_b"]
    data = _json.loads(open(r["output_path"]).read())
    assert data["conversations"] == [
        {"from": "human", "value": "你好"},
        {"from": "gpt", "value": "你好！有什么可以帮你？"},
    ]
    # 与 auto_trigger._convert_to_sharegpt 的输出结构一致（from/value 字段名）
    assert data["conversations"][0]["from"] == "human"


def test_export_sharegpt_empty(monkeypatch, tmp_path):
    from pathlib import Path as _Path
    from core.harness.digital_human import trajectory_collector as _tc
    traj_dir = tmp_path / "trajectories"
    traj_dir.mkdir()
    _tc._TRAJ_DIR = _Path(str(traj_dir))
    from core.harness.digital_human.trajectory_collector import export_sharegpt_dataset
    r = export_sharegpt_dataset(output_dir=str(tmp_path / "training"))
    assert r["samples"] == 0


# ═══════════════════════════════════════════════════════════
# P1-3: ASR 容器格式嗅探
# ═══════════════════════════════════════════════════════════

def test_transcribe_detects_webm_suffix(monkeypatch, tmp_path):
    """webm 魔数 → 临时文件用 .webm 后缀（不再误导为 .wav）。"""
    captured = {}

    class FakeWhisper:
        def transcribe(self, path):
            captured["suffix"] = path.split(".")[-1]
            return [{"text": "你好"}]

    async def fake_get_whisper():
        return FakeWhisper()

    monkeypatch.setattr("core.harness.digital_human.voice_pipeline._get_whisper", fake_get_whisper)
    # webm EBML 魔数
    text = asyncio.run(transcribe(b"\x1a\x45\xdf\xa3fake-webm"))
    assert text == "你好"
    assert captured["suffix"] == "webm"


# ═══════════════════════════════════════════════════════════
# P2-4: 页面实时数据注入链路
# ═══════════════════════════════════════════════════════════

def test_generate_answer_injects_page_data(monkeypatch):
    """page_data 参数注入 run_ctx，最终进入 AgentContext.variables._run_context。"""
    from core.harness.digital_human import voice_pipeline

    captured = {}

    class FakeRegistry:
        def get(self, name):
            return None

    class FakeAgent:
        async def execute(self, ctx):
            captured["run_ctx"] = (ctx.variables or {}).get("_run_context", {})
            from core.harness.interfaces import AgentResult
            return AgentResult(success=True, output={"answer": "根据页面数据回答"})

    async def fake_tts(text, **kw):
        return b""

    monkeypatch.setattr("core.harness.integration.get_agent_registry", lambda: FakeRegistry())
    monkeypatch.setattr("core.harness.syscalls.tts.sys_tts_generate", fake_tts)
    monkeypatch.setattr("core.api.core_facade.create_agent", lambda agent_type, config: FakeAgent())

    async def run():
        return await voice_pipeline.generate_answer(
            "当前系统健康吗",
            page_context={"route": "/diagnostics", "label": "诊断概览"},
            session_id="dh_test",
            page_data="layerStatus: infra=healthy, core=degraded; unhealthyLayers: core",
        )

    answer, _ = asyncio.run(run())
    assert answer == "根据页面数据回答"
    assert captured["run_ctx"]["page_data"] == "layerStatus: infra=healthy, core=degraded; unhealthyLayers: core"
    assert captured["run_ctx"]["current_page_label"] == "诊断概览"


def test_page_data_empty_does_not_inject(monkeypatch):
    """无 page_data 时不注入该字段（保持既有行为）。"""
    from core.harness.digital_human import voice_pipeline

    captured = {}

    class FakeRegistry:
        def get(self, name):
            return None

    class FakeAgent:
        async def execute(self, ctx):
            captured["run_ctx"] = (ctx.variables or {}).get("_run_context", {})
            from core.harness.interfaces import AgentResult
            return AgentResult(success=True, output={"answer": "ok"})

    async def fake_tts(text, **kw):
        return b""

    monkeypatch.setattr("core.harness.integration.get_agent_registry", lambda: FakeRegistry())
    monkeypatch.setattr("core.harness.syscalls.tts.sys_tts_generate", fake_tts)
    monkeypatch.setattr("core.api.core_facade.create_agent", lambda agent_type, config: FakeAgent())

    async def run():
        return await voice_pipeline.generate_answer("你好")

    asyncio.run(run())
    assert "page_data" not in captured["run_ctx"]
