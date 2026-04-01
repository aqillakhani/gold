"""Remotion video renderer integration.

Calls `npx remotion render` as a subprocess, passing scene data via JSON props file.
Replaces the FFmpeg-based compose_stock_video for niches using stock footage.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Path to the remotion project directory (relative to repo root)
REMOTION_DIR = Path(__file__).resolve().parents[3] / "remotion"


async def render_stock_video(
    clip_paths: list[Path],
    clip_durations: list[float],
    text_overlays: list[str],
    voiceover_path: Path | None,
    music_path: Path | None,
    subtitle_words: list[dict[str, Any]],
    output_path: Path,
    total_duration: float,
    niche_id: str = "ai_tools",
    accent_color: str = "#0ea5e9",
    hook_text: str = "",
    music_volume: float = 0.5,
    crossfade_duration: float = 0.5,
    concurrency: int = 1,
    timeout: int | None = None,
    part_number: int = 0,
    total_parts: int = 0,
    emoji_beats: list[dict] | None = None,
) -> Path:
    """Render a stock footage video using Remotion.

    Args:
        clip_paths: Paths to stock footage clip files (one per scene).
        clip_durations: Duration for each clip in seconds.
        text_overlays: Text to overlay per scene. Empty string = no overlay.
        voiceover_path: Path to voiceover audio file, or None.
        music_path: Path to background music file, or None.
        subtitle_words: List of dicts with keys: word, start, end (seconds).
        output_path: Where to write the final rendered video.
        total_duration: Total video duration in seconds.
        niche_id: Niche identifier for style selection.
        accent_color: Hex color for highlights and active subtitle word.
        music_volume: Volume for background music (0.0-1.0).
        crossfade_duration: Duration of crossfade transitions in seconds.
        concurrency: Number of parallel Remotion render threads.
        timeout: Render timeout in seconds. If None, auto-calculated from duration.

    Returns:
        Path to the rendered output video.

    Raises:
        RuntimeError: If Remotion render fails.
        FileNotFoundError: If the remotion directory or Node.js is not found.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not REMOTION_DIR.exists():
        raise FileNotFoundError(f"Remotion project not found at {REMOTION_DIR}")

    # Copy media files to remotion/public/media/ so staticFile() can access them.
    # Remotion's OffthreadVideo and Audio refuse local file:// URLs — they require
    # either http(s) URLs or staticFile() references from the public/ directory.
    public_media = REMOTION_DIR / "public" / "media"
    public_media.mkdir(parents=True, exist_ok=True)
    copied_files: list[Path] = []

    def _stage_file(src: Path, name: str) -> str:
        """Copy a file into public/media/ and return the staticFile-compatible path."""
        dest = public_media / name
        if not dest.exists() or dest.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dest)
        copied_files.append(dest)
        return f"media/{name}"

    # --- Duration validation & scaling ---
    # Ensure clip durations cover the full video length including crossfade overhead.
    # TransitionSeries crossfades overlap adjacent scenes, so the visible duration is:
    #   visible = sum(clip_durations) - (N-1) * crossfade_duration
    # We need visible >= total_duration, i.e.:
    #   sum(clip_durations) >= total_duration + (N-1) * crossfade_duration
    num_clips = len(clip_paths)
    num_crossfades = max(0, num_clips - 1)
    crossfade_overhead = num_crossfades * crossfade_duration
    required_total = total_duration + crossfade_overhead
    actual_total = sum(clip_durations[:num_clips])

    if actual_total < required_total and actual_total > 0:
        scale = required_total / actual_total
        clip_durations = [round(d * scale, 2) for d in clip_durations]
        new_total = sum(clip_durations[:num_clips])
        logger.warning(
            "Clip durations too short (%.1fs) for %.1fs video + %.1fs crossfade overhead. "
            "Scaled to %.1fs (factor %.2fx).",
            actual_total, total_duration, crossfade_overhead, new_total, scale,
        )
    elif num_clips == 0:
        raise ValueError("No clip paths provided for rendering")

    # Build scenes array for Remotion props
    scenes = []
    for i, clip_path in enumerate(clip_paths):
        rel = _stage_file(Path(clip_path).resolve(), f"clip_{i}{Path(clip_path).suffix}")
        scenes.append({
            "clipPath": rel,
            "duration": clip_durations[i] if i < len(clip_durations) else 7.0,
            "textOverlay": text_overlays[i] if i < len(text_overlays) else "",
        })

    vo_rel = ""
    if voiceover_path:
        vo_rel = _stage_file(voiceover_path.resolve(), f"voiceover{voiceover_path.suffix}")

    music_rel = ""
    if music_path:
        music_rel = _stage_file(music_path.resolve(), f"music{music_path.suffix}")

    # Build props JSON
    props: dict[str, Any] = {
        "scenes": scenes,
        "voiceoverPath": vo_rel,
        "musicPath": music_rel,
        "subtitles": subtitle_words,
        "totalDuration": total_duration,
        "musicVolume": music_volume,
        "crossfadeDuration": crossfade_duration,
        "accentColor": accent_color,
        "nicheId": niche_id,
        "hookText": hook_text,
        "partNumber": part_number,
        "totalParts": total_parts,
        "emojiBeats": emoji_beats or [],
    }

    # Write props to temp file (Windows CLI can't handle inline JSON)
    props_file = Path(tempfile.mktemp(suffix=".json", prefix="remotion_props_"))
    props_file.write_text(json.dumps(props, indent=2), encoding="utf-8")

    # Auto-calculate timeout: ~120s per second of video (CPU render + encode), minimum 900s
    # Previous 60x multiplier caused timeouts on complex scenes (9+ clips, transitions)
    if timeout is None:
        timeout = max(900, int(total_duration * 120))
    # Heap sizing: 2GB for shorts (<90s), 3GB for medium, 4GB for long-form (>5min)
    # Keep conservative to avoid OOM on 16GB systems with other apps running
    if total_duration > 300:
        node_heap = 4096
    elif total_duration > 90:
        node_heap = 3072
    else:
        node_heap = 2048

    logger.info(
        "Remotion render: %d scenes, %.1fs total, niche=%s, output=%s, timeout=%ds, heap=%dMB",
        len(scenes), total_duration, niche_id, output_path.name, timeout, node_heap,
    )
    logger.debug("Props file: %s", props_file)

    # Build the render command
    entry_point = str(REMOTION_DIR / "src" / "index.ts")
    abs_output = str(output_path.resolve()).replace("\\", "/")
    composition_id = "RedditStoryVideo" if niche_id in ("reddit_stories", "betrayal_revenge") else "StockFootageVideo"

    cmd = [
        "npx", "remotion", "render",
        entry_point,
        composition_id,
        abs_output,
        f"--props={str(props_file)}",
        f"--concurrency={concurrency}",
        "--codec=h264",
        "--video-bitrate=4M",
        "--log=verbose",
        "--gl=swangle",
        "--timeout=120000",
        "--disable-web-security",
    ]

    # On Windows, npx must be called via shell (npx.cmd)
    cmd_str = " ".join(cmd)
    logger.info("Running: %s", cmd_str[:200] + " ...")

    proc = None
    timed_out = False
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd_str,
            cwd=str(REMOTION_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={
                **os.environ,
                "NODE_OPTIONS": f"--max-old-space-size={node_heap}",
                "CHROMIUM_FLAGS": "--disable-gpu --disable-gpu-compositing --disable-software-rasterizer --disable-dev-shm-usage --no-sandbox",
            },
        )

        # Stream stderr for progress logging (Remotion writes progress to stderr)
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        last_progress_log = 0.0

        async def _read_stream(stream: asyncio.StreamReader, chunks: list[bytes], name: str) -> None:
            nonlocal last_progress_log
            while True:
                line = await stream.readline()
                if not line:
                    break
                chunks.append(line)
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                # Log progress lines periodically (every 60s) to show it's alive
                now = time.monotonic()
                if now - last_progress_log > 60 or "error" in text.lower():
                    logger.info("Remotion %s: %s", name, text[:200])
                    last_progress_log = now

        # Use a background watchdog to kill the process on timeout.
        # asyncio.wait_for doesn't reliably cancel subprocess reads on Windows.
        async def _watchdog() -> None:
            nonlocal timed_out
            await asyncio.sleep(timeout)
            if proc and proc.returncode is None:
                timed_out = True
                logger.error("Remotion render watchdog: killing after %ds", timeout)
                proc.kill()
                # Also kill any child node.exe processes on Windows
                if os.name == "nt":
                    import subprocess as sp
                    sp.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        capture_output=True,
                    )

        watchdog_task = asyncio.create_task(_watchdog())
        try:
            await asyncio.gather(
                _read_stream(proc.stdout, stdout_chunks, "stdout"),
                _read_stream(proc.stderr, stderr_chunks, "stderr"),
            )
            await proc.wait()
        finally:
            watchdog_task.cancel()
            try:
                await watchdog_task
            except asyncio.CancelledError:
                pass

        if timed_out:
            raise RuntimeError(f"Remotion render timed out after {timeout} seconds")

        stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            raise RuntimeError(
                f"Remotion render failed (exit code {proc.returncode}): {stderr_text[-500:]}"
            )

        if not output_path.exists():
            raise RuntimeError(f"Remotion render produced no output at {output_path}")

        size_mb = output_path.stat().st_size / (1024 * 1024)
        logger.info("Remotion render complete: %s (%.1f MB)", output_path.name, size_mb)
        return output_path

    except RuntimeError:
        raise
    finally:
        # Clean up props file and staged media copies
        if props_file.exists():
            props_file.unlink()
        for f in copied_files:
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass


def whisper_json_to_subtitle_words(whisper_result: dict) -> list[dict[str, Any]]:
    """Convert Whisper transcription result to subtitle word list for Remotion.

    Args:
        whisper_result: Whisper transcription dict with 'segments' containing 'words'.

    Returns:
        List of dicts with keys: word (str), start (float), end (float).
    """
    words = []
    for segment in whisper_result.get("segments", []):
        for word_info in segment.get("words", []):
            words.append({
                "word": word_info.get("word", "").strip(),
                "start": round(word_info.get("start", 0), 3),
                "end": round(word_info.get("end", 0), 3),
            })
    return words
