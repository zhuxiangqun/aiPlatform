"""
Video media tools — ffmpeg/ffprobe wrappers for frame/audio extraction.

These are NOT AI model inference; they are general media tool wrappers.
They live in core because they are prerequisites for the model inference
pipeline (transcriber requires audio extraction, OCR requires frame extraction).

Callers:
  - platform/kb/video.py (ingest_video_document)
  - Any agent that needs to process video files
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def _run(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def _require_bin(name: str) -> str:
    p = shutil.which(name)
    if not p:
        raise RuntimeError(f"{name}_not_found")
    return p


def probe_duration_ms(video_path: str) -> int:
    ffprobe = _require_bin("ffprobe")
    cp = _run([
        ffprobe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path,
    ])
    try:
        return int(float((cp.stdout or "0").strip()) * 1000)
    except Exception:
        return 0


def extract_audio(video_path: str, audio_path: str) -> None:
    ffmpeg = _require_bin("ffmpeg")
    _run([ffmpeg, "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", audio_path])


def extract_keyframes(video_path: str, frames_dir: str, interval_seconds: int = 15) -> List[Dict[str, Any]]:
    ffmpeg = _require_bin("ffmpeg")
    Path(frames_dir).mkdir(parents=True, exist_ok=True)
    out_tpl = str(Path(frames_dir) / "frame_%05d.jpg")
    fps_expr = f"fps=1/{max(1, int(interval_seconds))}"
    _run([ffmpeg, "-y", "-i", video_path, "-vf", fps_expr, out_tpl])
    files = sorted(Path(frames_dir).glob("frame_*.jpg"))
    out: List[Dict[str, Any]] = []
    for idx, p in enumerate(files):
        out.append({"local_path": str(p), "time_ms": idx * max(1, int(interval_seconds)) * 1000})
    return out


__all__ = ["probe_duration_ms", "extract_audio", "extract_keyframes"]
