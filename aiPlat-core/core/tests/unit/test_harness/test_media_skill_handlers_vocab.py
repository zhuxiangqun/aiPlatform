"""Regression: VideoSense / media handler PRD vocabulary for true_test asserts."""
from __future__ import annotations

import json

import pytest

from core.harness.media_skill_handlers import (
    handle_frame_analyzer,
    handle_report_json_export,
    handle_speech_analyzer,
    handle_subtitle_extractor,
    handle_video_downloader,
)


def _blob(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False)


def test_fr001_url_create_returns_queued_and_source_type():
    r = handle_video_downloader(
        {
            "app_name": "videosense",
            "source_type": "url",
            "url": "https://www.youtube.com/watch?v=demo123",
            "task_id": "t-url-001",
        }
    )
    assert r.get("status") == "queued"
    assert r.get("source_type") == "url"
    assert "task_id" in r and r["task_id"]


def test_fr001_upload_create_returns_queued_not_pending():
    r = handle_video_downloader(
        {
            "app_name": "videosense",
            "source_type": "upload",
            "file_name": "sample.mp4",
            "file_size": 10_485_760,
            "task_id": "t-up-001",
        }
    )
    assert r.get("status") == "queued"
    assert r.get("source_type") == "upload"


def test_fr002_unreachable_returns_download_failed_error_code():
    r = handle_video_downloader(
        {
            "app_name": "videosense",
            "source_type": "url",
            "url": "https://www.youtube.com/watch?v=unreachable",
            "task_id": "t-dl-fail-001",
        }
    )
    assert r.get("status") == "failed"
    assert r.get("error_code") == "DOWNLOAD_FAILED"


def test_fr002_download_includes_progress():
    r = handle_video_downloader(
        {
            "app_name": "videosense",
            "source_type": "url",
            "url": "https://www.bilibili.com/video/BV1demo",
            "task_id": "t-dl-001",
        }
    )
    blob = _blob(r)
    assert "status" in blob
    assert "progress" in blob
    assert r.get("source_type") == "url"


def test_long_video_segments_have_start_ms():
    r = handle_video_downloader(
        {
            "app_name": "videosense",
            "source_type": "upload",
            "file_name": "long_video.mp4",
            "file_size": 2_147_483_648,
            "duration_ms": 3_600_000,
            "task_id": "t-long-001",
        }
    )
    blob = _blob(r)
    assert "segments" in blob
    assert "start_ms" in blob
    assert int(r.get("segment_count") or 0) >= 2


def test_speech_no_audio_skipped_reason():
    r = handle_speech_analyzer(
        {
            "app_name": "videosense",
            "task_id": "t-noaudio-001",
            "media_path": "/tmp/videosense/t-noaudio-001.mp4",
            "mode": "transcribe",
        }
    )
    assert r.get("skipped_reason") == "NO_AUDIO_TRACK"
    assert "NO_AUDIO_TRACK" in _blob(r)


def test_subtitle_no_track_skipped_reason():
    r = handle_subtitle_extractor(
        {
            "app_name": "videosense",
            "task_id": "t-nosub-001",
            "media_path": "/tmp/videosense/t-nosub-001.mp4",
        }
    )
    assert r.get("skipped_reason") == "NO_SOFT_SUBTITLE_TRACK"
    assert "NO_SOFT_SUBTITLE_TRACK" in _blob(r)


def test_report_partial_exposes_skipped_reason_and_ms_timeline():
    r = handle_report_json_export(
        {
            "app_name": "videosense",
            "task_id": "t-report-partial-001",
            "export_format": "markdown",
        }
    )
    blob = _blob(r)
    assert "skipped_reason" in blob
    assert "transcription" in blob
    assert "vision" in blob
    assert "start_ms" in blob
    assert "end_ms" in blob


def test_frame_analyzer_exposes_object_and_start_ms():
    r = handle_frame_analyzer(
        {
            "app_name": "videosense",
            "task_id": "t-vis-001",
            "media_path": "/tmp/videosense/t-vis-001.mp4",
        }
    )
    blob = _blob(r)
    assert "scene" in blob
    assert "object" in blob
    assert "highlights" in blob
    assert "start_ms" in blob


def test_report_skipped_stages_status_completed_with_skips():
    """Explicit skipped_stages → status completed_with_skips + skip_reason + empty lists."""
    from core.harness.execution.true_test_runtime import evaluate_result_asserts

    r = handle_report_json_export(
        {
            "app_name": "videosense",
            "task_id": "t-012",
            "skipped_stages": ["subtitle_extractor"],
        }
    )
    assert r.get("status") == "completed_with_skips"
    assert r.get("skip_reason") or r.get("skipped_reason")
    assert (r.get("subtitle") or {}).get("subtitles") == []
    ok, fails, _ = evaluate_result_asserts(
        r,
        [
            {"type": "result.contains", "text": "completed_with_skips"},
            {"type": "result.contains", "text": "skip_reason"},
        ],
    )
    assert ok, fails


def test_not_downloadable_url_fails():
    r = handle_video_downloader(
        {
            "app_name": "videosense",
            "url": "https://example.com/not-downloadable-page",
            "task_id": "t-003",
        }
    )
    assert str(r.get("status") or "").lower() in ("failed", "error", "download_failed")


def test_speech_acoustic_aliases_and_analysis_failed():
    ok = handle_speech_analyzer(
        {
            "app_name": "videosense",
            "task_id": "t-012",
            "audio_ref": "task/t-012/audio.wav",
            "mode": "acoustic_features",
        }
    )
    blob = _blob(ok)
    assert "language_estimate" in blob
    assert "emotion_tendency" in blob
    fail = handle_speech_analyzer(
        {
            "app_name": "videosense",
            "task_id": "t-014",
            "audio_ref": "task/t-014/audio.wav",
            "simulate_failure": True,
        }
    )
    assert "ANALYSIS_FAILED" in _blob(fail)


def test_subtitle_no_soft_lowercase_token():
    r = handle_subtitle_extractor(
        {
            "app_name": "videosense",
            "task_id": "t-011",
            "video_ref": "task/t-011/video.mp4",
            "has_soft_subtitle_track": False,
        }
    )
    assert "no_soft_subtitle_track" in _blob(r)


def test_report_happy_path_stays_completed_not_with_skips():
    r = handle_report_json_export(
        {
            "app_name": "videosense",
            "task_id": "task-asr-report-unit",
            "video_path": "/Users/apple/.aiplat/apps/media/fixtures/with_audio.mp4",
        }
    )
    assert r.get("status") == "completed"
