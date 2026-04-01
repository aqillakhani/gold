"""Post today's videos to Instagram Reels on schedule."""
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / "secrets" / ".env", override=True)

FFMPEG_DIR = r"C:\Users\claws\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

from gold.config import Config
from gold.models.db import init_sync_db, create_tables_sync
from gold.platforms.meta import InstagramAdapter

# IG schedule: max 2 per account per day
# Catch-up posts (missed morning slots) go now, rest at scheduled time
# (hour, minute, account_id, content_id, description)
# 2026-03-29: 1 video per IG account — post immediately
SCHEDULE = [
    (0, 0, "reddit_stories", 84, "reddit Part 2 (lottery story)"),
    (0, 0, "ai_tools", 90, "ai_tools — customer churn predictor"),
    (0, 0, "english_learning", 99, "english — polite word that's rude"),
    (0, 0, "personal_finance", 87, "finance — spare room income"),
    (0, 0, "true_crime", 71, "true_crime — art restorer"),
]


async def post_to_instagram(config, account_id, content_id, description):
    """Post a single video to Instagram."""
    import sqlite3
    db_path = config.root / "data" / "gold.db"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("""
        SELECT video_path, caption, hashtags
        FROM content_variant
        WHERE content_id = ? AND platform = 'instagram'
    """, (content_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        logger.error("No Instagram variant for content #%d", content_id)
        return None

    vpath, caption, hashtags_json = row
    hashtags = json.loads(hashtags_json) if hashtags_json else []

    ig = InstagramAdapter(config, account_id)
    result = await ig.post(
        video_path=Path(vpath),
        caption=caption or "",
        hashtags=hashtags,
    )
    return result


async def main():
    config = Config()
    db_path = config.root / "data" / "gold.db"
    init_sync_db(f"sqlite:///{db_path}")
    create_tables_sync()

    now = datetime.now()
    posted = 0
    failed = 0

    logger.info("=" * 60)
    logger.info("SCHEDULED INSTAGRAM POSTING — %s", now.strftime("%Y-%m-%d"))
    logger.info("=" * 60)

    for hour, minute, account_id, content_id, desc in SCHEDULE:
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if target < datetime.now():
            # Past time — post immediately with small delay
            logger.info("POSTING NOW (catch-up) — #%d [%s] %s", content_id, account_id, desc)
        else:
            wait = (target - datetime.now()).total_seconds()
            if wait > 0:
                logger.info("WAITING until %02d:%02d for #%d %s (%.0f min)", hour, minute, content_id, desc, wait / 60)
                await asyncio.sleep(wait)
            logger.info("POSTING %02d:%02d — #%d [%s] %s", hour, minute, content_id, account_id, desc)

        try:
            result = await post_to_instagram(config, account_id, content_id, desc)
            if result:
                logger.info("IG SUCCESS #%d -> %s", content_id, result.get("post_id", "?"))
                posted += 1
            else:
                logger.error("IG FAILED #%d — no result", content_id)
                failed += 1
        except Exception as e:
            logger.error("IG FAILED #%d — %s", content_id, str(e)[:200])
            failed += 1

        # Delay between posts to avoid rate limits
        await asyncio.sleep(30)

    logger.info("")
    logger.info("=" * 60)
    logger.info("IG DONE — Posted: %d, Failed: %d", posted, failed)
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
