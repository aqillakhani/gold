"""Re-render a single video by content_id. Designed to run as isolated subprocess."""

import asyncio
import json
import logging
import os
import random
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

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / "secrets" / ".env")

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
    from gold.pipeline.subtitles import SubtitleGenerator
    from gold.utils.ffmpeg import compose_stock_video

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

    # Generate ASS subtitle file — use Whisper for word timestamps
    subtitle_gen = SubtitleGenerator()
    subtitle_path = RENDERED_DIR / f"content_{content_id}_subs.ass"
    try:
        subtitle_gen.generate_from_audio(vo_path, "", subtitle_path)
    except Exception as e:
        logger.warning("Whisper failed (%s), using even-division subtitles", e)
        # Read the script text from DB for fallback
        db2 = sqlite3.connect(str(DB_PATH))
        script_text = db2.execute(
            "SELECT script FROM content WHERE id = ?", (content_id,)
        ).fetchone()
        db2.close()
        subtitle_gen.generate(script_text[0] if script_text else "", audio_duration, subtitle_path)
    logger.info("Content %d: generated ASS subtitles at %s", content_id, subtitle_path.name)

    music_path = pick_music(niche)

    ts = time.strftime("%Y%m%d_%H%M%S")
    output_path = RENDERED_DIR / f"content_{content_id}_master_{ts}.mp4"

    try:
        await compose_stock_video(
            clip_paths=clips,
            clip_durations=clip_durations,
            text_overlays=text_overlays,
            audio_path=vo_path,
            music_path=music_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
            total_duration=audio_duration,
            crossfade_duration=0.5,
            music_volume=0.6,
        )
    except Exception as e:
        logger.error("Content %d: render failed: %s", content_id, e)
        output_path.unlink(missing_ok=True)
        return False
    finally:
        # Clean up temporary subtitle file
        subtitle_path.unlink(missing_ok=True)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info("Content %d: re-rendered (%.1f MB) -> %s", content_id, size_mb, output_path.name)
    return True


if __name__ == "__main__":
    content_id = int(sys.argv[1])
    logger.info("=== Re-rendering content_%d (isolated process) ===", content_id)
    success = asyncio.run(rerender_video(content_id))
    sys.exit(0 if success else 1)
