"""Replace bright/blank stock clips and re-render affected videos.

Identifies clips with YAVG > 180, deletes them, downloads replacements
via the updated stock_footage pipeline (which rejects bright candidates),
then re-renders only the affected master videos.
"""

import asyncio
import json
import logging
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import time
from glob import glob
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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
CACHE_DIR = PROJECT_ROOT / "data" / "media" / "clips" / "cache"

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / "secrets" / ".env")

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
BRIGHTNESS_THRESHOLD = 180  # YAVG above this = too bright

# Bright clips identified by scan (content_id, scene_index, search_query)
BRIGHT_CLIPS = [
    (7, 2, "mobile app design dark interface"),
    (7, 3, "logo neon design dark"),
    (7, 5, "brand identity corporate dark"),
    (14, 1, "financial crisis stock market crash red"),
    (15, 6, "heartbeat monitor hospital dark"),
    (17, 4, "calendar schedule planning dark desk"),
    (18, 5, "trading floor wall street busy"),
    (24, 2, "colorful toy blocks close up dark"),
]

NICHE_COLORS = {
    "ai_tools": "#3b82f6",
    "crypto_finance": "#22c55e",
    "true_crime": "#ef4444",
}
NICHE_MUSIC_KEYWORDS = {
    "ai_tools": ["ambient_tech", "ambient_electronic", "ambient_chillout"],
    "crypto_finance": ["ambient_electronic", "ambient_cinematic", "ambient_tech"],
    "true_crime": ["dark_ambient", "dark_ambient_cinematic", "dark_ambient_tension"],
}


async def replace_bright_clip(content_id: int, scene_idx: int, query: str) -> bool:
    """Delete bright clip and download a replacement."""
    from gold.utils.stock_footage import get_stock_clip_for_scene

    # Find existing clip
    pattern = str(CLIPS_DIR / f"content_{content_id}_stock_{scene_idx}_*")
    matches = sorted(glob(pattern))
    if not matches:
        logger.warning("Content %d scene %d: no clip found to replace", content_id, scene_idx)
        return False

    clip_path = Path(matches[-1])
    ts = clip_path.stem.split("_")[-2] + "_" + clip_path.stem.split("_")[-1]

    # Delete the bright clip
    logger.info("Deleting bright clip: %s", clip_path.name)
    clip_path.unlink()

    # Download replacement via pipeline (which now rejects bright candidates)
    output_path = CLIPS_DIR / f"content_{content_id}_stock_{scene_idx}_{ts}.mp4"

    result = await get_stock_clip_for_scene(
        query=query,
        api_key=PEXELS_API_KEY,
        output_path=output_path,
        target_duration=8.0,
        cache_dir=CACHE_DIR,
        resolution=(1080, 1920),
    )

    if result and result.exists():
        logger.info("Replacement clip downloaded: %s", result.name)
        return True
    else:
        logger.error("Content %d scene %d: failed to download replacement", content_id, scene_idx)
        return False


def find_clips(content_id: int) -> list[Path]:
    pattern = str(CLIPS_DIR / f"content_{content_id}_stock_*")
    return sorted(Path(p) for p in glob(pattern))


def find_voiceover(content_id: int) -> Path | None:
    pattern = str(AUDIO_DIR / f"content_{content_id}_vo_*")
    matches = sorted(glob(pattern))
    return Path(matches[-1]) if matches else None


def pick_music(niche_id: str) -> Path | None:
    keywords = NICHE_MUSIC_KEYWORDS.get(niche_id, ["ambient"])
    all_music = list(MUSIC_DIR.glob("*.mp3"))
    if not all_music:
        return None
    for kw in keywords:
        matches = [m for m in all_music if kw in m.name]
        if matches:
            return random.choice(matches)
    return random.choice(all_music)


def get_audio_duration(audio_path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries",
         "format=duration", "-of", "csv=p=0", str(audio_path)],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


async def rerender_video(content_id: int) -> bool:
    """Re-render a single video using updated clips."""
    from gold.pipeline.subtitles import SubtitleGenerator
    from gold.utils.remotion_renderer import render_stock_video

    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    row = db.execute(
        "SELECT id, niche, hook, scene_descriptions FROM content WHERE id = ?",
        (content_id,),
    ).fetchone()
    db.close()

    if not row:
        logger.error("Content %d not found in DB", content_id)
        return False

    niche = row["niche"]
    hook_text = row["hook"] or ""
    scene_descriptions = json.loads(row["scene_descriptions"]) if row["scene_descriptions"] else []

    clips = find_clips(content_id)
    if not clips:
        logger.error("Content %d: no clips found", content_id)
        return False

    vo_path = find_voiceover(content_id)
    if not vo_path:
        logger.error("Content %d: no voiceover found", content_id)
        return False

    clip_durations = []
    text_overlays = []
    for i, clip in enumerate(clips):
        if i < len(scene_descriptions):
            clip_durations.append(scene_descriptions[i].get("duration", 7.0))
            text_overlays.append(scene_descriptions[i].get("text_overlay", ""))
        else:
            clip_durations.append(7.0)
            text_overlays.append("")

    audio_duration = get_audio_duration(vo_path)

    crossfade_dur = 0.5
    num_crossfades = max(0, len(clips) - 1)
    crossfade_overhead = num_crossfades * crossfade_dur
    raw_total = sum(clip_durations)
    required_total = audio_duration + crossfade_overhead + 1.0
    if raw_total > 0 and raw_total < required_total:
        scale = required_total / raw_total
        clip_durations = [round(d * scale, 2) for d in clip_durations]

    logger.info("Content %d [%s]: %d clips, %.1fs audio", content_id, niche, len(clips), audio_duration)

    subtitle_gen = SubtitleGenerator()
    subtitle_words = subtitle_gen.get_word_timestamps(vo_path)
    logger.info("Content %d: %d word timestamps", content_id, len(subtitle_words))

    music_path = pick_music(niche)
    accent_color = NICHE_COLORS.get(niche, "#0ea5e9")

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

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info("Content %d: re-rendered (%.1f MB) -> %s", content_id, size_mb, output_path.name)
    return True


async def main():
    # Step 1: Replace bright clips
    logger.info("=== STEP 1: Replacing %d bright clips ===", len(BRIGHT_CLIPS))
    replaced = 0
    affected_content_ids = set()
    for content_id, scene_idx, query in BRIGHT_CLIPS:
        affected_content_ids.add(content_id)
        if await replace_bright_clip(content_id, scene_idx, query):
            replaced += 1
    logger.info("Replaced %d/%d bright clips", replaced, len(BRIGHT_CLIPS))

    # Step 2: Re-render only affected videos
    logger.info("=== STEP 2: Re-rendering %d affected videos ===", len(affected_content_ids))
    success = 0
    for cid in sorted(affected_content_ids):
        logger.info("--- Re-rendering content_%d ---", cid)
        if await rerender_video(cid):
            success += 1
    logger.info("Re-rendered %d/%d videos", success, len(affected_content_ids))


if __name__ == "__main__":
    asyncio.run(main())
