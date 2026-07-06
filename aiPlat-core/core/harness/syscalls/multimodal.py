"""Syscall: multimodal processing — audio/browser/video → Agent context.
Registered syscall: sys_multimodal_process
Provides Agent access to multimodal input through standard syscall boundary.
"""
import os, sys, json


async def sys_multimodal_process(file_path: str = "", file_type: str = "", url: str = "", action: str = "") -> dict:
    """Process multimodal input through standard syscall boundary.

    Args:
        file_path: Path to audio/video/image file
        file_type: "audio" | "video" | "image" (auto-detect if empty)
        url: URL for browser operations
        action: Browser action ("navigate" | "screenshot" | "click" | "get_text")

    Returns:
        dict with success/error and processed result
    """
    from core.harness.multimodal import get_multimodal_integrator
    integrator = await get_multimodal_integrator()

    # Browser action
    if url and action:
        result = await integrator.capture_browser(command=action, url=url)
        return result

    # File-based multimodal
    if file_path and os.path.exists(file_path):
        if not file_type:
            ext = os.path.splitext(file_path)[1].lower()
            audio_exts = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}
            video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
            if ext in audio_exts:
                file_type = "audio"
            elif ext in video_exts:
                file_type = "video"
            else:
                file_type = "image"

        result = await integrator.process_multimodal_input(file_path, file_type)
        return result

    return {"success": False, "error": "No valid input. Provide file_path, url+action, or both.", "source": "sys_multimodal"}
