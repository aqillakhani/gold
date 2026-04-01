"""Video downloader for reaction videos — uses yt-dlp to download from Reddit, YouTube, TikTok."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def _find_ytdlp() -> list[str]:
    """Find yt-dlp executable or fall back to python -m yt_dlp.

    Returns a list of command parts (1 element for direct exe, 3 for module fallback).
    """
    path = shutil.which("yt-dlp")
    if path:
        return [path]
    # Fallback: use as Python module
    import sys
    return [sys.executable, "-m", "yt_dlp"]


async def download_video(
    url: str,
    output_path: Path,
    max_duration: int = 30,
) -> Path:
    """Download a video from URL, capped at max_duration seconds for fair use.

    Args:
        url: Video URL (Reddit, YouTube, TikTok, etc.).
        output_path: Where to save the downloaded video.
        max_duration: Maximum duration in seconds (for fair use compliance).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ytdlp_cmd = _find_ytdlp()

    # Use yt-dlp to download, then ffmpeg to trim if needed
    temp_path = output_path.with_suffix(".temp.mp4")

    cmd = ytdlp_cmd + [
        "--no-playlist",
        "--merge-output-format", "mp4",
        "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--no-check-certificates",
        "--no-warnings",
        "--quiet",
        "-o", str(temp_path),
        url,
    ]

    logger.info("Downloading video from: %s", url)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

    if proc.returncode != 0:
        err = stderr.decode(errors="replace")
        raise RuntimeError(f"yt-dlp failed ({proc.returncode}): {err[:300]}")

    if not temp_path.exists():
        raise RuntimeError(f"yt-dlp did not produce output file: {temp_path}")

    # Trim to max_duration using ffmpeg
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        trim_cmd = [
            ffmpeg,
            "-i", str(temp_path),
            "-t", str(max_duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac",
            "-y", str(output_path),
        ]
        trim_proc = await asyncio.create_subprocess_exec(
            *trim_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(trim_proc.communicate(), timeout=60)
        temp_path.unlink(missing_ok=True)
    else:
        # No ffmpeg, just rename
        temp_path.rename(output_path)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info("Downloaded video: %s (%.1f MB)", output_path.name, size_mb)
    return output_path
