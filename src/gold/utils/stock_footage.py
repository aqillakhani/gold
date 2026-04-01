"""Pexels video search and download utility for stock footage clips.

Provides helpers to search the Pexels Videos API, select the best matching
portrait-oriented clip, download it with caching, and trim/scale it to the
target resolution using FFmpeg.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import asyncio

import httpx

from .ffmpeg import run_ffmpeg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

VideoFileInfo = dict[str, Any]  # keys: url, width, height, quality
PexelsVideoEntry = dict[str, Any]  # keys: id, duration, video_files, ...
StockClipInfo = dict[str, Any]  # keys: url, width, height, duration, id


# ---------------------------------------------------------------------------
# Pexels API search
# ---------------------------------------------------------------------------

PEXELS_API_BASE = "https://api.pexels.com/videos/search"


async def search_pexels_videos(
    query: str,
    api_key: str,
    orientation: str = "portrait",
    per_page: int = 5,
    min_duration: int = 5,
) -> list[StockClipInfo]:
    """Search the Pexels Videos API and return matching clip metadata.

    Args:
        query: Search query string (e.g. "city skyline night").
        api_key: Pexels API key for the Authorization header.
        orientation: Video orientation filter - "portrait", "landscape", or "square".
        per_page: Number of results to request from the API (max 80).
        min_duration: Minimum clip duration in seconds; shorter clips are dropped.

    Returns:
        List of dicts with keys: ``url``, ``width``, ``height``, ``duration``, ``id``.
        The ``url``/``width``/``height`` fields come from the best video file
        selected for each result (see :func:`_best_video_file`).

    Raises:
        httpx.HTTPStatusError: On non-2xx HTTP response from Pexels.
        ValueError: If the API response cannot be parsed.
    """
    params: dict[str, Any] = {
        "query": query,
        "orientation": orientation,
        "per_page": per_page,
        "size": "medium",
    }
    headers = {"Authorization": api_key}

    logger.debug(
        "Searching Pexels: query=%r orientation=%s per_page=%d",
        query, orientation, per_page,
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(PEXELS_API_BASE, params=params, headers=headers)
        response.raise_for_status()

    data: dict[str, Any] = response.json()
    raw_videos: list[dict[str, Any]] = data.get("videos", [])

    results: list[StockClipInfo] = []
    for video in raw_videos:
        duration: int = video.get("duration", 0)
        if duration < min_duration:
            logger.debug(
                "Skipping Pexels video %s - duration %ds < min %ds",
                video.get("id"), duration, min_duration,
            )
            continue

        video_files: list[dict[str, Any]] = video.get("video_files", [])
        if not video_files:
            continue

        best = _best_video_file(video_files)
        if best is None:
            continue

        results.append(
            {
                "id": video["id"],
                "duration": duration,
                "url": best["link"],
                "width": best.get("width", 0),
                "height": best.get("height", 0),
            }
        )

    logger.info(
        "Pexels search %r: %d/%d results passed min_duration=%ds filter",
        query, len(results), len(raw_videos), min_duration,
    )
    return results


def _best_video_file(video_files: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Select the best video file entry from a Pexels video file list.

    Selection criteria (in priority order):

    1. Prefer portrait orientation (height >= width).
    2. Prefer HD quality (height >= 1080).
    3. Prefer highest resolution (height * width).

    Args:
        video_files: List of video file dicts from the Pexels API response.

    Returns:
        The best-matching file dict, or ``None`` if the list is empty.
    """
    if not video_files:
        return None

    def sort_key(f: dict[str, Any]) -> tuple[int, int, int]:
        w: int = f.get("width") or 0
        h: int = f.get("height") or 0
        is_portrait = int(h >= w)   # 1 = portrait, 0 = not
        is_hd = int(h >= 1080)      # 1 = HD or better
        area = h * w                # higher resolution preferred
        return (is_portrait, is_hd, area)

    sorted_files = sorted(video_files, key=sort_key, reverse=True)
    return sorted_files[0]


# ---------------------------------------------------------------------------
# Download and trim
# ---------------------------------------------------------------------------

async def download_and_trim_clip(
    url: str,
    output_path: Path,
    target_duration: float,
    resolution: tuple[int, int] = (1080, 1920),
    fps: int = 30,
) -> Path:
    """Download a video from a URL and trim/scale it to the target spec.

    The clip is:

    - Trimmed to ``target_duration`` seconds starting from the beginning.
    - Scaled to ``resolution`` with ``force_original_aspect_ratio=increase``
      then centre-cropped to exact pixel dimensions.
    - Encoded with libx264 (preset fast, CRF 20) at ``fps`` frames per second.
    - Audio is stripped (callers mix their own voiceover/music tracks).

    Args:
        url: Direct download URL for the video file.
        output_path: Destination file path (parents created if needed).
        target_duration: Output clip length in seconds.
        resolution: Output (width, height) in pixels. Defaults to 1080x1920 (9:16).
        fps: Output frame rate. Defaults to 30.

    Returns:
        The resolved ``output_path`` after a successful encode.

    Raises:
        httpx.HTTPError: If the HTTP download fails.
        RuntimeError: If FFmpeg exits with a non-zero return code.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Stream download to a temporary sibling file
    tmp_path = output_path.with_suffix(".download.tmp")
    logger.info("Downloading stock clip: %.80s -> %s", url, tmp_path.name)

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with tmp_path.open("wb") as fh:
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    fh.write(chunk)

    size_mb = tmp_path.stat().st_size / 1_048_576
    logger.debug("Download complete: %s (%.1f MB)", tmp_path.name, size_mb)

    w, h = resolution
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},"
        f"setsar=1,"
        f"fps={fps}"
    )

    args = [
        "-stream_loop", "-1",
        "-ss", "0",
        "-t", str(target_duration),
        "-i", str(tmp_path),
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-an",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-y", str(output_path),
    ]

    try:
        await run_ffmpeg(args, timeout=300)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    logger.info(
        "Trimmed stock clip: %s (%.1fs, %dx%d @ %dfps)",
        output_path.name, target_duration, w, h, fps,
    )
    return output_path


# ---------------------------------------------------------------------------
# Brightness validation
# ---------------------------------------------------------------------------

MAX_BRIGHTNESS_YAVG = 200  # clips above this are considered "too bright / blank"


async def _check_clip_brightness(clip_path: Path) -> float:
    """Sample the middle frame of a clip and return the average luminance (YAVG).

    Uses FFmpeg signalstats filter on a single frame at the clip midpoint.
    Returns 0.0 if the check fails for any reason (fail-open so pipeline isn't blocked).
    """
    try:
        # Get duration via ffprobe
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return 0.0

        proc = await asyncio.create_subprocess_exec(
            ffprobe, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(clip_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        duration = float(stdout.decode().strip() or "0")
        midpoint = max(duration / 2, 0.5)

        # Extract YAVG from signalstats at midpoint
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            return 0.0

        proc = await asyncio.create_subprocess_exec(
            ffmpeg_bin,
            "-ss", str(midpoint),
            "-i", str(clip_path),
            "-frames:v", "1",
            "-vf", "signalstats,metadata=print:file=-",
            "-f", "null", "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        # YAVG appears in stdout metadata output
        output = stdout.decode(errors="replace") + stderr.decode(errors="replace")
        for line in output.splitlines():
            if "YAVG" in line and "=" in line:
                val = line.split("=")[-1].strip()
                return float(val)
        return 0.0
    except Exception as exc:
        logger.debug("Brightness check failed for %s: %s", clip_path.name, exc)
        return 0.0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def get_stock_clip_for_scene(
    query: str,
    api_key: str,
    output_path: Path,
    target_duration: float,
    cache_dir: Path,
    resolution: tuple[int, int] = (1080, 1920),
) -> Path | None:
    """Search, select, and download the best Pexels stock clip for a scene.

    Applies a two-level cache:

    1. ``output_path`` - if the file already exists it is returned immediately.
    2. ``cache_dir`` - trimmed clips are cached by Pexels video ID so the same
       source is never re-downloaded across multiple calls.

    Selection strategy: prefer portrait-oriented clips; among those pick the
    one whose duration is closest to ``target_duration``.

    Args:
        query: Descriptive search query for the scene content.
        api_key: Pexels API key.
        output_path: Final destination for the trimmed clip.
        target_duration: Desired clip length in seconds.
        cache_dir: Directory for caching downloads keyed by Pexels video ID.
        resolution: Output (width, height). Defaults to 1080x1920.

    Returns:
        Path to the ready clip, or ``None`` if no suitable clip was found.
    """
    output_path = Path(output_path)
    cache_dir = Path(cache_dir)

    # Fast path: already rendered
    if output_path.exists():
        logger.debug("Stock clip cache hit (output exists): %s", output_path.name)
        return output_path

    # Search Pexels
    candidates = await search_pexels_videos(
        query=query,
        api_key=api_key,
        orientation="portrait",
        per_page=10,
        min_duration=max(3, int(target_duration)),
    )

    if not candidates:
        logger.warning(
            "No Pexels results for query %r - cannot supply stock clip", query
        )
        return None

    # Prefer portrait; fall back to all candidates if none qualify
    portrait_pool = [c for c in candidates if c["height"] >= c["width"]]
    pool = portrait_pool if portrait_pool else candidates

    # Sort by duration proximity to target
    ranked = sorted(pool, key=lambda c: abs(c["duration"] - target_duration))

    cache_dir.mkdir(parents=True, exist_ok=True)

    # Try candidates in order; reject clips that are too bright
    for candidate in ranked:
        pexels_id: int = candidate["id"]
        clip_url: str = candidate["url"]

        logger.info(
            "Trying Pexels clip id=%s duration=%ds (target=%.1fs) for query %r",
            pexels_id, candidate["duration"], target_duration, query,
        )

        cached_path = cache_dir / f"pexels_{pexels_id}_{resolution[0]}x{resolution[1]}.mp4"

        if not cached_path.exists():
            await download_and_trim_clip(
                url=clip_url,
                output_path=cached_path,
                target_duration=target_duration,
                resolution=resolution,
            )
        else:
            logger.info("Stock clip ID cache hit: %s", cached_path.name)

        # Brightness gate: reject clips with high average luminance
        yavg = await _check_clip_brightness(cached_path)
        if yavg > MAX_BRIGHTNESS_YAVG:
            logger.warning(
                "Rejecting Pexels clip id=%s — too bright (YAVG=%.1f > %d). Trying next candidate.",
                pexels_id, yavg, MAX_BRIGHTNESS_YAVG,
            )
            continue

        # Clip passed — copy to output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cached_path, output_path)
        logger.info("Stock clip ready: %s (YAVG=%.1f)", output_path.name, yavg)
        return output_path

    # All candidates were too bright — use the best one anyway with a warning
    logger.warning(
        "All %d Pexels candidates for query %r exceeded brightness threshold. "
        "Using best match anyway.",
        len(ranked), query,
    )
    best = ranked[0]
    cached_path = cache_dir / f"pexels_{best['id']}_{resolution[0]}x{resolution[1]}.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cached_path, output_path)
    logger.info("Stock clip ready (fallback): %s", output_path)
    return output_path
