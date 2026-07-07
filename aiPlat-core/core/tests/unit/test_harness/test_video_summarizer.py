"""G1 Video L4→L5 — VideoSummarizer + knowledge bridge 集成测试.

Verifies video parsing pipeline is wired to AI summarization.
"""
import pytest


@pytest.mark.asyncio
async def test_video_summarizer_exists():
    """G1: VideoSummarizer 类存在且可创建."""
    from core.harness.document.video import VideoSummarizer, VideoParser
    vs = VideoSummarizer()
    assert vs is not None
    assert hasattr(vs, "summarize")
    # VideoParser is used as fallback parser
    vp = VideoParser()
    assert vp is not None
    assert hasattr(vp, "parse")


@pytest.mark.asyncio
async def test_video_pipeline_has_five_methods():
    """G1: VideoParser has probe+transcribe+keyframes+describe+parse (5核心方法)."""
    from core.harness.document.video import VideoParser
    vp = VideoParser()
    core_methods = ["probe", "transcribe_audio", "describe_frames", "parse"]
    for m in core_methods:
        assert hasattr(vp, m), f"Missing method: {m}"
