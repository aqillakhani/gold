"""Test the new Reddit card subtitle style on one existing reddit_stories video."""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

FFMPEG_DIR = r"C:\Users\claws\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / "secrets" / ".env", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def main():
    import sqlite3
    from gold.config import Config
    from gold.models.db import init_sync_db, create_tables_sync
    from gold.pipeline.subtitles import SubtitleGenerator
    from gold.utils.ffmpeg import get_duration
    from gold.utils.remotion_renderer import render_stock_video
    from gold.utils.backgrounds import build_background_montage

    config = Config()
    db_path = config.root / "data" / "gold.db"
    init_sync_db(f"sqlite:///{db_path}")
    create_tables_sync()

    # Use content #25 (reddit_stories) as test
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT id, niche, title, hook, script FROM content WHERE id = 25")
    row = cur.fetchone()
    conn.close()

    cid, niche, title, hook, script_text = row
    logger.info("Testing Reddit card style on: #%d — %s", cid, title)

    # Find voiceover
    audio_dir = config.media_dir / "audio"
    vo_files = sorted(audio_dir.glob(f"content_{cid}_vo_*"))
    if not vo_files:
        logger.error("No voiceover found for #%d", cid)
        return
    vo_path = vo_files[0]
    vo_duration = await get_duration(vo_path)
    logger.info("Voiceover: %s (%.1fs)", vo_path.name, vo_duration)

    # Get word timestamps via Whisper
    logger.info("Getting word timestamps...")
    sub_gen = SubtitleGenerator()
    word_timestamps = sub_gen.get_word_timestamps(vo_path)
    logger.info("Got %d word timestamps", len(word_timestamps))

    # Build gameplay background
    logger.info("Building gameplay background...")
    niche_config = config.niches.get(niche, {})
    bg_category = niche_config.get("background_category", "mixed")
    background = await build_background_montage(
        target_duration=int(vo_duration) + 30,
        category=bg_category,
    )

    # Find music
    import random
    suno_dir = config.media_dir / "audio" / "music" / "suno"
    music_files = sorted(suno_dir.glob(f"suno_{niche}_*.mp3"))
    music_path = random.choice(music_files) if music_files else None

    # Render via Remotion with RedditStoryVideo composition
    ts = time.strftime("%Y%m%d_%H%M%S")
    output_path = config.media_dir / "rendered" / f"reddit_style_test_{ts}.mp4"

    logger.info("Rendering via Remotion (RedditStoryVideo)...")
    await render_stock_video(
        clip_paths=[background],
        clip_durations=[vo_duration + 5],
        text_overlays=[""],
        voiceover_path=vo_path,
        music_path=music_path,
        subtitle_words=word_timestamps,
        output_path=output_path,
        total_duration=vo_duration,
        niche_id="reddit_stories",  # This triggers RedditStoryVideo composition
        accent_color="#fb923c",
        hook_text=hook or title,
        music_volume=0.20,
        crossfade_duration=0.5,
    )

    logger.info("SUCCESS: %s", output_path)
    logger.info("Check: %s", output_path.resolve())


if __name__ == "__main__":
    asyncio.run(main())
