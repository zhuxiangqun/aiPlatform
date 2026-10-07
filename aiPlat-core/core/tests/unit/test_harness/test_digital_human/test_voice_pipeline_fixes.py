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

import pytest

from core.harness.digital_human.voice_pipeline import transcribe


@pytest.fixture(autouse=True)
def _ensure_asyncio_loop():
    """integration import creates EventBus Queue — needs a loop on Py3.9."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    yield


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
    """registry 无顾问时用 materials_chat；注入实况简报；TTS 默认关闭。"""
    from core.harness.digital_human import voice_pipeline

    captured = {}

    class FakeAgent:
        async def execute(self, ctx):
            captured["ctx"] = ctx
            from core.harness.interfaces import AgentResult
            return AgentResult(success=True, output={"answer": "真AI回答"})

    class FakeRegistry:
        def get(self, name):
            if name == "materials_chat":
                return FakeAgent()
            return None

    monkeypatch.setenv("AIPLAT_DIGITAL_HUMAN_TTS", "false")
    monkeypatch.setattr("core.harness.integration.get_agent_registry", lambda: FakeRegistry())
    monkeypatch.setattr(
        "core.harness.digital_human.platform_status_brief.build_platform_status_brief",
        lambda **kw: "=== 平台实况简报 ===\n工作区 Agent (0): (空)",
    )

    answer, audio = asyncio.run(voice_pipeline.generate_answer("你好，介绍一下系统"))
    assert answer == "真AI回答"
    assert audio == b""
    assert "平台实况简报" in captured["ctx"].variables.get("message", "")
    assert captured["ctx"].variables.get("_consultant_agent") == "materials_chat"


def test_generate_answer_prefers_platform_consultant(monkeypatch):
    """优先使用 platform_consultant，且注入实况简报。"""
    from core.harness.digital_human import voice_pipeline

    captured = {}

    class FakeConsultant:
        async def execute(self, ctx):
            captured["ctx"] = ctx
            from core.harness.interfaces import AgentResult
            return AgentResult(success=True, output={"answer": "走应用工厂"})

    class FakeRegistry:
        def get(self, name):
            if name == "platform_consultant":
                return FakeConsultant()
            return None

    monkeypatch.setenv("AIPLAT_DIGITAL_HUMAN_TTS", "false")
    monkeypatch.setattr("core.harness.integration.get_agent_registry", lambda: FakeRegistry())
    monkeypatch.setattr(
        "core.harness.digital_human.platform_status_brief.build_platform_status_brief",
        lambda **kw: "=== 平台实况简报 ===\n工作区 Agent (1): factory_agent",
    )

    answer, audio = asyncio.run(voice_pipeline.generate_answer("设备报修怎么建"))
    assert answer == "走应用工厂"
    assert audio == b""
    msg = captured["ctx"].variables.get("message", "")
    assert captured["ctx"].variables.get("_consultant_agent") == "platform_consultant"
    assert captured["ctx"].variables.get("_skip_claude_md") is True
    assert captured["ctx"].variables.get("_coding_policy_profile") == "off"
    assert "factory_agent" in msg
    assert msg.startswith("设备报修怎么建")
    assert msg.index("设备报修怎么建") < msg.index("平台实况简报")
    assert "---" in msg


def test_rewrite_empty_model_answer():
    from core.harness.digital_human.voice_pipeline import (
        _NO_MODEL_USER_MSG,
        _rewrite_empty_model_answer,
    )
    assert _rewrite_empty_model_answer("No model available") == _NO_MODEL_USER_MSG
    assert _rewrite_empty_model_answer("走应用工厂") == "走应用工厂"


def test_strip_consultant_cot_keeps_final_reply():
    from core.harness.digital_human.voice_pipeline import _strip_consultant_cot

    dumped = """### 步骤1：分析问题约束

用户问画面功能，但没有提供截图。

### 步骤2：可能的解读角度

1. 没发图 2. 当前页

### 步骤4：结论

---

**`/workspace/agents` — Agent 工作区**

这个画面用来管理工作区里的 Agent 资产。
"""
    out = _strip_consultant_cot(dumped)
    assert "步骤1" not in out
    assert "可能的解读" not in out
    assert "/workspace/agents" in out
    assert "Agent 资产" in out
    assert _strip_consultant_cot("这个页面用来新建 Agent。") == "这个页面用来新建 Agent。"


def test_ensure_consultant_llm_resolves_auto(monkeypatch):
    from types import SimpleNamespace
    from core.harness.digital_human import voice_pipeline

    bound = {}

    class DummyAdapter:
        pass

    def fake_ensure(agent, *, model_name, force=False):
        bound["model_name"] = model_name
        agent._model = DummyAdapter()
        return agent._model

    monkeypatch.setattr(
        "core.harness.utils.model_injection.ensure_agent_model", fake_ensure
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection.best_model_for_purpose_with_meta",
        lambda p, messages=None: {
            "model": "qwen2.5:3b",
            "model_purpose": "agent" if p == "auto" else "wrong",
        },
    )

    agent = SimpleNamespace(
        _model=None,
        _config=SimpleNamespace(model="hardcoded:99b", metadata={"system_prompt": "你是小朱"}),
        _conv_config=SimpleNamespace(system_prompt="default"),
    )
    voice_pipeline._ensure_consultant_llm(agent, "怎么在平台上建 Agent")
    assert bound["model_name"] == "qwen2.5:3b"
    assert isinstance(agent._model, DummyAdapter)
    assert agent._conv_config.system_prompt == "你是小朱"


def test_ensure_consultant_llm_rebinds_existing_remote(monkeypatch):
    from types import SimpleNamespace
    from core.harness.digital_human import voice_pipeline

    bound = {}

    class DummyAdapter:
        def __init__(self, name):
            self.model_name = name

    def fake_ensure(agent, *, model_name, force=False):
        bound["model_name"] = model_name
        bound["force"] = force
        agent._model = DummyAdapter(model_name)
        return agent._model

    monkeypatch.setattr("core.harness.utils.model_injection.ensure_agent_model", fake_ensure)
    monkeypatch.setattr(
        "core.harness.utils.model_injection.best_model_for_purpose_with_meta",
        lambda p, messages=None: {"model": "qwen2.5:3b", "model_purpose": "chat"},
    )

    agent = SimpleNamespace(
        _model=DummyAdapter("deepseek-chat"),
        _config=SimpleNamespace(model="auto", metadata={}),
        _conv_config=SimpleNamespace(system_prompt=""),
    )
    voice_pipeline._ensure_consultant_llm(agent, "你好")
    assert bound["model_name"] == "qwen2.5:3b"
    assert bound["force"] is True
    assert agent._model.model_name == "qwen2.5:3b"


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

    class FakeAgent:
        async def execute(self, ctx):
            captured["run_ctx"] = (ctx.variables or {}).get("_run_context", {})
            from core.harness.interfaces import AgentResult
            return AgentResult(success=True, output={"answer": "根据页面数据回答"})

    class FakeRegistry:
        def get(self, name):
            if name == "materials_chat":
                return FakeAgent()
            return None

    monkeypatch.setenv("AIPLAT_DIGITAL_HUMAN_TTS", "false")
    monkeypatch.setattr("core.harness.integration.get_agent_registry", lambda: FakeRegistry())
    monkeypatch.setattr(
        "core.harness.digital_human.platform_status_brief.build_platform_status_brief",
        lambda **kw: "brief",
    )

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

    class FakeAgent:
        async def execute(self, ctx):
            captured["run_ctx"] = (ctx.variables or {}).get("_run_context", {})
            from core.harness.interfaces import AgentResult
            return AgentResult(success=True, output={"answer": "ok"})

    class FakeRegistry:
        def get(self, name):
            if name == "materials_chat":
                return FakeAgent()
            return None

    monkeypatch.setenv("AIPLAT_DIGITAL_HUMAN_TTS", "false")
    monkeypatch.setattr("core.harness.integration.get_agent_registry", lambda: FakeRegistry())
    monkeypatch.setattr(
        "core.harness.digital_human.platform_status_brief.build_platform_status_brief",
        lambda **kw: "brief",
    )

    async def run():
        return await voice_pipeline.generate_answer("你好")

    asyncio.run(run())
    assert "page_data" not in captured["run_ctx"]


def test_consultant_status_frame_uses_infra_auto_select(monkeypatch):
    from core.harness.digital_human import voice_pipeline

    monkeypatch.setattr(
        "core.harness.utils.model_injection.best_model_for_purpose_with_meta",
        lambda p, messages=None: {"model": "picked-by-infra", "model_purpose": "agent"},
    )
    frame = voice_pipeline._consultant_status_frame("怎么在平台上建 Agent")
    assert frame["type"] == "status"
    assert frame["data"] == "thinking"
    assert frame["model"] == "picked-by-infra"
    assert frame["purpose"] == "agent"
    screen = voice_pipeline._consultant_status_frame("这个画面的功能是什么")
    assert screen["model"] == "picked-by-infra"


def test_role_ack_detects_polite_variant():
    from core.harness.digital_human.voice_pipeline import _is_consultant_role_ack

    assert _is_consultant_role_ack(
        "好的，了解了您的角色和要求。我会严格按照您的指示进行回答。请告诉我，您是想做一个应用还是做一个Agent呢？"
    )


def test_generate_answer_does_not_template_audit_or_factory(monkeypatch):
    """Audit / Agent-vs-工厂 questions go through the consultant with injected facts."""
    from core.harness.digital_human import voice_pipeline
    from core.harness.interfaces import AgentResult

    captured = {}

    class FakeConsultant:
        async def execute(self, ctx):
            captured["msg"] = ctx.variables.get("message", "")
            return AgentResult(success=True, output={"answer": "LLM_RAN"})

    class FakeRegistry:
        def get(self, name):
            return FakeConsultant() if name == "platform_consultant" else None

    monkeypatch.setenv("AIPLAT_DIGITAL_HUMAN_TTS", "false")
    monkeypatch.setattr("core.harness.integration.get_agent_registry", lambda: FakeRegistry())
    monkeypatch.setattr(voice_pipeline, "_ensure_consultant_llm", lambda *_a, **_k: "m")
    monkeypatch.setattr(voice_pipeline, "_consultant_model_meta", lambda _t="": {"model": "m", "model_purpose": "reasoning"})

    q = "解读一下这个画面的审核结果并告知我应该怎么做"
    data = "skillId: upload_video；issue0: error/unrealized_side_effect SIDE_EFFECT_UNREALIZED"
    ctx = {"route": "/workspace/skills", "label": "Skill", "purpose": "工作区 Skill"}
    answer, _ = asyncio.run(voice_pipeline.generate_answer(q, page_context=ctx, page_data=data))
    assert answer == "LLM_RAN"
    assert "upload_video" in captured["msg"]
    assert "unrealized_side_effect" in captured["msg"]
    assert q in captured["msg"]

    q2 = "我想做一个分析视频的应用，应该是做一个agent还是通过应用工厂做一个应用？"
    answer2, _ = asyncio.run(voice_pipeline.generate_answer(q2))
    assert answer2 == "LLM_RAN"
    assert "/app/factory" in captured["msg"] or "应用工厂" in captured["msg"]


def test_generate_answer_injects_this_session_dialogue(monkeypatch, tmp_path):
    from core.harness.digital_human import trajectory_collector as traj
    from core.harness.digital_human import voice_pipeline
    from core.harness.interfaces import AgentResult

    traj._TRAJ_DIR = tmp_path
    captured = {}

    class FakeConsultant:
        async def execute(self, ctx):
            captured["msg"] = ctx.variables.get("message", "")
            return AgentResult(success=True, output={"answer": "LLM_RAN"})

    class FakeRegistry:
        def get(self, name):
            return FakeConsultant() if name == "platform_consultant" else None

    monkeypatch.setenv("AIPLAT_DIGITAL_HUMAN_TTS", "false")
    monkeypatch.setattr("core.harness.integration.get_agent_registry", lambda: FakeRegistry())
    monkeypatch.setattr(voice_pipeline, "_ensure_consultant_llm", lambda *_a, **_k: "m")
    sid = "dh_continuity_test"
    traj.collect_turn(sid, "user", "解读一下这个画面的审核结果并告知我应该怎么做")
    traj.collect_turn(sid, "assistant", "upload_video 说会真上传但没绑 Tool")
    asyncio.run(
        voice_pipeline.generate_answer(
            "能不能把解读精简一点解释？",
            session_id=sid,
            page_data="skillId: upload_video；issue0: error/unrealized_side_effect",
        )
    )
    assert "本会话刚才" in captured["msg"]
    assert "解读一下这个画面的审核结果" in captured["msg"]
    assert captured["msg"].index("能不能把解读精简一点解释？") < captured["msg"].index("本会话刚才")


def test_recent_session_turns_reads_jsonl(tmp_path):
    from core.harness.digital_human import trajectory_collector as traj

    traj._TRAJ_DIR = tmp_path
    traj.collect_turn("s1", "user", "第一问审核")
    traj.collect_turn("s1", "assistant", "去绑 Tool")
    turns = traj.recent_session_turns("s1", max_turns=4)
    assert [t["role"] for t in turns] == ["user", "assistant"]
    text = traj.format_session_dialogue(turns)
    assert "本会话刚才" in text
    assert "第一问审核" in text


def test_role_ack_falls_back_to_page_facts(monkeypatch):
    from core.harness.digital_human import voice_pipeline
    from core.harness.interfaces import AgentResult

    class FakeConsultant:
        async def execute(self, ctx):
            return AgentResult(
                success=True,
                output={"answer": "了解了您的角色。请告诉我用户的具体需求。"},
            )

    class FakeRegistry:
        def get(self, name):
            return FakeConsultant() if name == "platform_consultant" else None

    monkeypatch.setenv("AIPLAT_DIGITAL_HUMAN_TTS", "false")
    monkeypatch.setattr("core.harness.integration.get_agent_registry", lambda: FakeRegistry())
    monkeypatch.setattr(voice_pipeline, "_ensure_consultant_llm", lambda *_a, **_k: "m")
    data = "skillId: upload_video；issue0: error/unrealized_side_effect SIDE_EFFECT_UNREALIZED"
    answer, _ = asyncio.run(
        voice_pipeline.generate_answer(
            "根据这个画面的审核结果，我应该怎么做？",
            page_data=data,
        )
    )
    assert "upload_video" in answer
    assert "了解了您的角色" not in answer
    assert "SIDE_EFFECT_UNREALIZED" not in answer
    assert "registe" not in answer


def test_unasked_factory_dump_falls_back_to_compact_audit(monkeypatch):
    from core.harness.digital_human import voice_pipeline
    from core.harness.interfaces import AgentResult

    dump = """好的，我会根据您提供的信息和平台实况简报中的信息来回答您的问题。

### 关于“解读一下这个画面的审核结果”

#### 做应用 vs 做 Agent
- **应用**：应用工厂
- **Agent**：对话角色
"""

    class FakeConsultant:
        async def execute(self, ctx):
            return AgentResult(success=True, output={"answer": dump})

    class FakeRegistry:
        def get(self, name):
            return FakeConsultant() if name == "platform_consultant" else None

    monkeypatch.setenv("AIPLAT_DIGITAL_HUMAN_TTS", "false")
    monkeypatch.setattr("core.harness.integration.get_agent_registry", lambda: FakeRegistry())
    monkeypatch.setattr(voice_pipeline, "_ensure_consultant_llm", lambda *_a, **_k: "m")
    data = "skillId: upload_video；auditSummary: 1错误 2警告；issue0: error/unrealized_side_effect 真上传：去安装 Tool"
    answer, _ = asyncio.run(
        voice_pipeline.generate_answer(
            "能不能把解读精简一点解释？",
            page_data=data,
        )
    )
    assert "upload_video" in answer
    assert "做应用 vs 做 Agent" not in answer
    assert "prompt" in answer or "改成只出文案" in answer


def test_general_question_keeps_inventory_and_llm_answer(monkeypatch):
    from core.harness.digital_human import voice_pipeline
    from core.harness.interfaces import AgentResult

    captured = {}

    class FakeConsultant:
        async def execute(self, ctx):
            captured["msg"] = ctx.variables.get("message", "")
            return AgentResult(
                success=True,
                output={
                    "answer": "【通用说明，非 aiPlat 既有】对象存储是把文件放到云上用 URL 访问。",
                },
            )

    class FakeRegistry:
        def get(self, name):
            return FakeConsultant() if name == "platform_consultant" else None

    calls = {}

    def fake_brief(**kw):
        calls["include_inventory"] = kw.get("include_inventory")
        return "=== 平台实况简报 ===\n工作区 Agent (1): factory_agent"

    monkeypatch.setenv("AIPLAT_DIGITAL_HUMAN_TTS", "false")
    monkeypatch.setattr("core.harness.integration.get_agent_registry", lambda: FakeRegistry())
    monkeypatch.setattr(voice_pipeline, "_ensure_consultant_llm", lambda *_a, **_k: "m")
    monkeypatch.setattr(
        "core.harness.digital_human.platform_status_brief.build_platform_status_brief",
        fake_brief,
    )
    data = "skillId: upload_video；issue0: error/unrealized_side_effect"
    answer, _ = asyncio.run(
        voice_pipeline.generate_answer("对象存储是什么？", page_data=data)
    )
    assert calls.get("include_inventory") is True
    assert "通用说明，非 aiPlat 既有" in answer
    assert "对象存储" in answer
    assert "改成只出文案" not in answer
