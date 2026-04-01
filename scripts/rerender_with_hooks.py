"""Re-render all 18 production videos (IDs 7-24) from scratch with hook cards.

Reads existing clips, voiceovers, and scene descriptions from the DB,
generates word timestamps via Whisper, and calls render_stock_video()
with the hook_text from the DB so hook cards are baked into the Remotion render.
"""

import asyncio
import json
import logging
import os
import random
import sqlite3
import sys
from glob import glob
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# FFmpeg path
FFMPEG_DIR = r"C:\Users\claws\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "gold.db"
CLIPS_DIR = PROJECT_ROOT / "data" / "media" / "clips"
AUDIO_DIR = PROJECT_ROOT / "data" / "media" / "audio"
MUSIC_DIR = AUDIO_DIR / "music" / "jamendo"
RENDERED_DIR = PROJECT_ROOT / "data" / "media" / "rendered"

# Add src to path so we can import gold modules
sys.path.insert(0, str(PROJECT_ROOT / "src"))

TARGET_NICHES = {"ai_tools", "crypto_finance", "true_crime"}

NICHE_COLORS = {
    "ai_tools": "#3b82f6",
    "crypto_finance": "#22c55e",
    "true_crime": "#ef4444",
}

# Music selection by niche
NICHE_MUSIC_KEYWORDS = {
    "ai_tools": ["ambient_tech", "ambient_electronic", "ambient_chillout"],
    "crypto_finance": ["ambient_electronic", "ambient_cinematic", "ambient_tech"],
    "true_crime": ["dark_ambient", "dark_ambient_cinematic", "dark_ambient_tension"],
}


def get_content_data() -> list[dict]:
    """Query DB for production content (IDs 7-24) with scene descriptions and hooks."""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT id, niche, hook, scene_descriptions FROM content "
        "WHERE id >= 7 AND id <= 24 ORDER BY id"
    ).fetchall()
    db.close()
    return [dict(r) for r in rows if r["niche"] in TARGET_NICHES]


def find_clips(content_id: int) -> list[Path]:
    """Find all stock clips for a content ID, sorted by index."""
    pattern = str(CLIPS_DIR / f"content_{content_id}_stock_*")
    return sorted(Path(p) for p in glob(pattern))


def find_voiceover(content_id: int) -> Path | None:
    """Find the voiceover audio file for a content ID."""
    pattern = str(AUDIO_DIR / f"content_{content_id}_vo_*")
    matches = sorted(glob(pattern))
    return Path(matches[-1]) if matches else None


def pick_music(niche_id: str) -> Path | None:
    """Pick a music file matching the niche's mood."""
    keywords = NICHE_MUSIC_KEYWORDS.get(niche_id, ["ambient"])
    all_music = list(MUSIC_DIR.glob("*.mp3"))
    if not all_music:
        return None

    # Try to find a match by keyword
    for kw in keywords:
        matches = [m for m in all_music if kw in m.name]
        if matches:
            return random.choice(matches)

    # Fallback to any music file
    return random.choice(all_music)


def get_audio_duration(audio_path: Path) -> float:
    """Get audio duration using ffprobe."""
    import subprocess
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-show_entries",
            "format=duration", "-of", "csv=p=0", str(audio_path),
        ],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


async def process_one(content: dict, subtitle_gen) -> bool:
    """Re-render a single content item from scratch with hook card."""
    from gold.utils.remotion_renderer import render_stock_video

    content_id = content["id"]
    niche = content["niche"]
    hook_text = content["hook"] or ""
    scene_descriptions = json.loads(content["scene_descriptions"]) if content["scene_descriptions"] else []

    # Find source assets
    clips = find_clips(content_id)
    if not clips:
        logger.error("Content %d: no clips found, skipping", content_id)
        return False

    vo_path = find_voiceover(content_id)
    if not vo_path:
        logger.error("Content %d: no voiceover found, skipping", content_id)
        return False

    # Get clip durations and text overlays from scene descriptions
    clip_durations = []
    text_overlays = []
    for i, clip in enumerate(clips):
        if i < len(scene_descriptions):
            clip_durations.append(scene_descriptions[i].get("duration", 7.0))
            text_overlays.append(scene_descriptions[i].get("text_overlay", ""))
        else:
            clip_durations.append(7.0)
            text_overlays.append("")

    # Get audio duration for total video duration
    audio_duration = get_audio_duration(vo_path)

    # Scale clip durations to cover audio + crossfade overhead (same logic as orchestrator)
    crossfade_dur = 0.5
    num_crossfades = max(0, len(clips) - 1)
    crossfade_overhead = num_crossfades * crossfade_dur
    raw_total = sum(clip_durations)
    required_total = audio_duration + crossfade_overhead + 1.0
    if raw_total > 0 and raw_total < required_total:
        scale = required_total / raw_total
        clip_durations = [round(d * scale, 2) for d in clip_durations]
        logger.info(
            "Content %d: scaled scene durations %.1fs -> %.1fs (vo=%.1fs, cf_overhead=%.1fs)",
            content_id, raw_total, sum(clip_durations), audio_duration, crossfade_overhead,
        )
    logger.info(
        "Content %d [%s]: %d clips, %.1fs audio, hook='%s'",
        content_id, niche, len(clips), audio_duration, hook_text[:50],
    )

    # Generate word timestamps via Whisper
    logger.info("Content %d: generating word timestamps...", content_id)
    subtitle_words = subtitle_gen.get_word_timestamps(vo_path)
    logger.info("Content %d: got %d word timestamps", content_id, len(subtitle_words))

    # Pick background music
    music_path = pick_music(niche)

    # Accent color
    accent_color = NICHE_COLORS.get(niche, "#0ea5e9")

    # Output path — use a new temp name, then swap
    import time
    ts = time.strftime("%Y%m%d_%H%M%S")
    output_path = RENDERED_DIR / f"content_{content_id}_master_{ts}.mp4"

    try:
        await render_stock_video(
            clip_paths=clips,
            clip_durations=clip_durations,
            text_overlays=text_overlays,
            voiceover_path=vo_path,
            music_path=music_path,
            subtitle_words=subtitle_words,
            output_path=output_path,
            total_duration=audio_duration,
            niche_id=niche,
            accent_color=accent_color,
            hook_text=hook_text,
            music_volume=0.6,
            crossfade_duration=0.5,
        )
    except Exception as e:
        logger.error("Content %d: render failed: %s", content_id, e)
        output_path.unlink(missing_ok=True)
        return False

    # Remove old master videos (keep backups with .old suffix)
    old_masters = list(RENDERED_DIR.glob(f"content_{content_id}_master_*.mp4"))
    for old in old_masters:
        if old != output_path:
            backup = old.with_suffix(".old.mp4")
            if not backup.exists():
                old.rename(backup)
                logger.info("Content %d: backed up old master to %s", content_id, backup.name)
            else:
                old.unlink()

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info("Content %d: re-rendered successfully (%.1f MB) -> %s", content_id, size_mb, output_path.name)
    return True


async def main():
    from gold.pipeline.subtitles import SubtitleGenerator

    content_list = get_content_data()
    logger.info("Found %d videos to re-render with hook cards", len(content_list))

    # Pre-load Whisper model once
    subtitle_gen = SubtitleGenerator()
    logger.info("Pre-loading Whisper model...")
    subtitle_gen._get_whisper_model()

    success = 0
    for i, content in enumerate(content_list):
        logger.info("=== Processing %d/%d (content ID %d) ===", i + 1, len(content_list), content["id"])
        if await process_one(content, subtitle_gen):
            success += 1

    logger.info("Done: %d/%d videos re-rendered with hook cards", success, len(content_list))


if __name__ == "__main__":
    asyncio.run(main())
