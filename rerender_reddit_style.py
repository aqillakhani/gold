"""Re-render StoryVault videos with new Reddit card subtitle style via Remotion.

Replaces old FFmpeg gameplay render with Remotion RedditStoryVideo composition:
- Reddit post card with progressive text reveal
- Yellow word highlighting synced to voiceover
- Gameplay background
- No separate karaoke subtitles
"""

import asyncio
import json
import logging
import os
import random
import sqlite3
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent / "src"))

FFMPEG_DIR = r"C:\Users\claws\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / "secrets" / ".env", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

from gold.config import Config
from gold.models.db import init_sync_db, create_tables_sync
from gold.pipeline.subtitles import SubtitleGenerator
from gold.pipeline.variation import PlatformVariator

# Already posted — don't re-render
SKIP_IDS = {85}


async def rerender_with_reddit_card(
    content: dict,
    config: Config,
    subtitle_gen: SubtitleGenerator,
    variator: PlatformVariator,
) -> bool:
    """Re-render a reddit_stories/betrayal_revenge video with Reddit card style."""
    from gold.utils.backgrounds import build_background_montage, create_placeholder_background
    from gold.utils.ffmpeg import get_duration
    from gold.utils.remotion_renderer import render_stock_video

    cid = content["id"]
    niche_id = content["niche"]
    niche_config = config.niches.get(niche_id, {})
    media_dir = config.media_dir

    # Find existing voiceover
    audio_dir = media_dir / "audio"
    vo_files = sorted(audio_dir.glob(f"content_{cid}_vo_*"))
    if not vo_files:
        logger.error("[#%d] NO VOICEOVER — skipping", cid)
        return False
    audio_path = vo_files[0]
    audio_duration = await get_duration(audio_path)

    # Get word timestamps via Whisper
    logger.info("[#%d] Getting word timestamps...", cid)
    word_timestamps = subtitle_gen.get_word_timestamps(audio_path)

    # Build gameplay background
    bg_category = niche_config.get("background_category", "mixed")
    try:
        background = await build_background_montage(
            target_duration=int(audio_duration) + 30,
            category=bg_category,
        )
    except RuntimeError:
        bg_dir = media_dir / "backgrounds"
        bg_dir.mkdir(parents=True, exist_ok=True)
        background = bg_dir / "placeholder.mp4"
        if not background.exists():
            create_placeholder_background(background, duration=120.0)

    # Find music
    suno_dir = media_dir / "audio" / "music" / "suno"
    music_files = sorted(suno_dir.glob(f"suno_{niche_id}_*.mp3"))
    music_path = random.choice(music_files) if music_files else None

    # Get hook text
    hook = content["hook"] or content["title"] or ""

    # Extract part info
    import re
    part_number, total_parts = 0, 0
    title = content["title"] or ""
    match = re.search(r'Part\s+(\d+)(?:\s*/\s*(\d+))?', title, re.IGNORECASE)
    if match:
        part_number = int(match.group(1))
        total_parts = int(match.group(2)) if match.group(2) else 3

    # Render via Remotion with RedditStoryVideo composition
    ts = time.strftime("%Y%m%d_%H%M%S")
    output_dir = media_dir / "rendered"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"content_{cid}_master_{ts}.mp4"

    logger.info("[#%d] Rendering via Remotion (RedditStoryVideo)...", cid)
    await render_stock_video(
        clip_paths=[background],
        clip_durations=[audio_duration + 5],
        text_overlays=[""],
        voiceover_path=audio_path,
        music_path=music_path,
        subtitle_words=word_timestamps,
        output_path=output_path,
        total_duration=audio_duration,
        niche_id=niche_id,
        accent_color="#fb923c",
        hook_text=hook,
        music_volume=niche_config.get("music_volume", 0.20),
        crossfade_duration=0.5,
        part_number=part_number,
        total_parts=total_parts,
    )

    # Create platform variants
    variant_paths = await variator.create_variants(output_path, cid)

    # Update DB
    conn = sqlite3.connect(str(config.root / "data" / "gold.db"))
    cur = conn.cursor()
    cur.execute("UPDATE content SET master_video_path = ? WHERE id = ?", (str(output_path), cid))
    for platform, path in variant_paths.items():
        cur.execute(
            "UPDATE content_variant SET video_path = ? WHERE content_id = ? AND platform = ?",
            (str(path), cid, platform),
        )
    conn.commit()
    conn.close()

    logger.info("[#%d] REDDIT CARD re-render DONE: %s", cid, output_path.name)
    return True


async def main():
    config = Config()
    db_path = config.root / "data" / "gold.db"
    init_sync_db(f"sqlite:///{db_path}")
    create_tables_sync()

    subtitle_gen = SubtitleGenerator()
    variator = PlatformVariator(config)

    # Get unposted StoryVault content
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT id, niche, title, hook, script, master_video_path
        FROM content
        WHERE niche IN ('reddit_stories', 'betrayal_revenge')
          AND status = 'READY'
        ORDER BY id
    """)
    rows = [dict(r) for r in cur.fetchall() if r["id"] not in SKIP_IDS]
    conn.close()

    logger.info("=" * 60)
    logger.info("RE-RENDER: %d StoryVault videos with Reddit card style", len(rows))
    logger.info("=" * 60)

    results = {"ok": [], "fail": []}

    for content in rows:
        cid = content["id"]
        logger.info("")
        logger.info("=" * 50)
        logger.info("RE-RENDER #%d [%s] (Reddit card)", cid, content["niche"])
        logger.info("  %s", (content["title"] or "")[:60])
        logger.info("=" * 50)
        try:
            ok = await rerender_with_reddit_card(content, config, subtitle_gen, variator)
            results["ok" if ok else "fail"].append(cid)
        except Exception as e:
            logger.error("[#%d] FAILED: %s", cid, str(e)[:300])
            results["fail"].append(cid)

    logger.info("")
    logger.info("=" * 60)
    logger.info("RE-RENDER COMPLETE")
    logger.info("  Success: %d", len(results["ok"]))
    logger.info("  Failed:  %d", len(results["fail"]))
    if results["fail"]:
        logger.info("  Failed IDs: %s", results["fail"])
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
