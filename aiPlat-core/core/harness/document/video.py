"""

import logging
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





__all__ = ["probe_duration_ms", "extract_audio", "extract_keyframes", "VideoParser"]





class VideoParser:

    """Phase 45: Orchestrates full video processing pipeline.



    Pipeline:

      1. probe duration → 2. extract audio → 3. transcribe audio

      → 4. extract keyframes → 5. OCR/describe frames

      → 6. return structured VideoParseResult



    Falls back gracefully if ffmpeg/ffprobe are not available.

    """

    def __init__(self, *, frame_interval_seconds: int = 15):

        self._interval = max(1, int(frame_interval_seconds))



    def probe(self, video_path: str) -> Optional[int]:

        """Get video duration in ms. Returns None if ffprobe unavailable."""

        try:

            return probe_duration_ms(video_path)

        except RuntimeError:

            return None



    async def transcribe_audio(self, video_path: str) -> str:

        """Extract and transcribe audio track."""

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:

            audio_path = f.name

        try:

            extract_audio(video_path, audio_path)

            try:

                from core.harness.utils.model_injection import create_selected_adapter

                adapter = create_selected_adapter(model_name="audio")

                if adapter and hasattr(adapter, "transcribe"):

                    result = await adapter.transcribe(audio_path)

                    return str(result) if result else ""

            except Exception:

                logging.getLogger(__name__).debug('transcribe_audio failed', exc_info=True)
            return ""

        except RuntimeError:

            return ""

        finally:

            try:

                os.unlink(audio_path)

            except OSError:

                pass  # noqa: cleanup-best-effort



    async def describe_frames(self, video_path: str) -> List[Dict[str, Any]]:

        """Extract keyframes and return frame metadata."""

        import tempfile

        frames_dir = tempfile.mkdtemp(prefix="video_frames_")

        try:

            frames = extract_keyframes(video_path, frames_dir, self._interval)

            return frames

        except RuntimeError:

            return []

        finally:

            try:

                shutil.rmtree(frames_dir, ignore_errors=True)

            except Exception:

                logging.getLogger(__name__).debug('describe_frames failed', exc_info=True)


    async def parse(self, video_path: str) -> Dict[str, Any]:

        """Full pipeline: probe → transcribe → extract frames.



        Returns:

            {

                "duration_ms": int,

                "transcript": str,

                "keyframe_count": int,

                "status": "ok" | "partial",

            }

        """

        result = {

            "duration_ms": None,

            "transcript": "",

            "keyframe_count": 0,

            "status": "partial",

            "source": video_path,

        }



        dur = self.probe(video_path)

        result["duration_ms"] = dur



        transcript = await self.transcribe_audio(video_path)

        result["transcript"] = transcript[:10000] if transcript else ""



        frames = await self.describe_frames(video_path)

        result["keyframe_count"] = len(frames)



        if dur is not None or transcript or frames:

            result["status"] = "ok"

        return result





class VideoSummarizer:

    """AI-powered video content understanding (G1 L3→L4 enabler).



    Extends VideoParser's probe→transcribe→keyframes pipeline with LLM-driven

    summarization: generates a natural-language description of what happens in

    the video, including key topics, tone, and action segments.

    """



    def __init__(self, parser: Optional[VideoParser] = None):

        self._parser = parser or VideoParser()



    async def summarize(self, video_path: str, max_segments: int = 5) -> Dict[str, Any]:

        """Full video understanding: parse → summarize → return structured result.



        Returns:

            {

                "duration_ms": int, "transcript": str, "keyframe_count": int,

                "summary": str, "topics": [str], "action_segments": [str],

                "status": "ok" | "partial",

            }

        """

        parsed = await self._parser.parse(video_path)

        result = {

            "duration_ms": parsed.get("duration_ms"),

            "transcript": parsed.get("transcript", "")[:2000],

            "keyframe_count": parsed.get("keyframe_count", 0),

            "status": parsed.get("status", "partial"),

        }

        transcript = (parsed.get("transcript") or "").strip()

        if not transcript or len(transcript) < 50:

            result["summary"] = "(insufficient audio for summarization)"

            result["topics"] = []

            result["action_segments"] = []

            return result



        try:

            from core.harness.utils.model_injection import best_model_for_purpose

            from core.harness.syscalls.llm import sys_llm_generate



            prompt = (

                "You are a video content analyst. Below is the transcript of a video.\n"

                "Produce a concise summary (2-3 sentences), a list of main topics (max 5), "

                "and a list of key action segments with timestamps if available.\n\n"

                f"TRANSCRIPT:\n{transcript[:6000]}\n\n"

                "Respond in JSON: {\"summary\":\"...\", \"topics\":[...], \"action_segments\":[...]}"

            )

            resp = await sys_llm_generate(

                model=None,

                prompt=prompt,

                model_name=best_model_for_purpose("doc_llm"),

                temperature=0.0,

            )

            import json as _json

            raw = str(resp)

            try:

                analysis = _json.loads(raw)

            except Exception:

                import re as _re

                m = _re.search(r'\{[\s\S]*\}', raw)

                analysis = _json.loads(m.group(0)) if m else {}

            result["summary"] = analysis.get("summary", raw[:200])

            result["topics"] = analysis.get("topics", [])[:5]

            result["action_segments"] = analysis.get("action_segments", [])[:5]

        except Exception:

            result["summary"] = f"Video transcript ({len(transcript)} chars)"

            result["topics"] = []

            result["action_segments"] = []

        return result


