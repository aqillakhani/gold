"""Post today's videos to YouTube on the research-backed schedule."""
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / "secrets" / ".env")

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
from gold.platforms.youtube import YouTubeAdapter

# Schedule: (hour, minute, account_id, content_id, description)
SCHEDULE = [
    (12, 0, "betrayal_revenge", 40, "betrayal Part 1"),
    (15, 0, "reddit_stories", 26, "reddit Part 2"),
    (16, 0, "ai_tools", 46, "ai_tools #1"),
    (16, 5, "english_learning", 43, "english #1"),
    (17, 0, "personal_finance", 31, "finance #1"),
    (18, 0, "betrayal_revenge", 41, "betrayal Part 2"),
    (18, 5, "ai_tools", 47, "ai_tools #2"),
    (18, 10, "english_learning", 44, "english #2"),
    (18, 15, "true_crime", 71, "true_crime #1"),
    (19, 0, "personal_finance", 32, "finance #2"),
    (20, 0, "reddit_stories", 27, "reddit Part 3"),
    (20, 5, "ai_tools", 70, "ai_tools #3"),
    (20, 10, "english_learning", 45, "english #3"),
    (20, 15, "true_crime", 72, "true_crime #2"),
    (21, 0, "personal_finance", 33, "finance #3"),
    (22, 0, "betrayal_revenge", 42, "betrayal Part 3"),
    (22, 5, "true_crime", 73, "true_crime #3"),
]


async def post_to_youtube(config, account_id, content_id, description):
    """Post a single video to YouTube."""
    import sqlite3
    db_path = config.root / "data" / "gold.db"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("""
        SELECT video_path, caption, hashtags
        FROM content_variant
        WHERE content_id = ? AND platform = 'youtube'
    """, (content_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        logger.error("No YouTube variant for content #%d", content_id)
        return None

    vpath, caption, hashtags_json = row
    hashtags = json.loads(hashtags_json) if hashtags_json else []

    yt = YouTubeAdapter(config, account_id)
    result = await yt.post(
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
    logger.info("SCHEDULED YOUTUBE POSTING — %s", now.strftime("%Y-%m-%d"))
    logger.info("=" * 60)

    for hour, minute, account_id, content_id, desc in SCHEDULE:
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # If time already passed, skip
        if target < datetime.now():
            logger.info("SKIPPED (past) %02d:%02d — #%d %s", hour, minute, content_id, desc)
            continue

        # Wait until scheduled time
        wait = (target - datetime.now()).total_seconds()
        if wait > 0:
            logger.info("WAITING until %02d:%02d for #%d %s (%.0f min)", hour, minute, content_id, desc, wait / 60)
            await asyncio.sleep(wait)

        # Post
        logger.info("POSTING %02d:%02d — #%d [%s] %s", hour, minute, content_id, account_id, desc)
        try:
            result = await post_to_youtube(config, account_id, content_id, desc)
            if result:
                logger.info("SUCCESS #%d -> %s", content_id, result.get("post_id", "?"))
                posted += 1
            else:
                logger.error("FAILED #%d — no result", content_id)
                failed += 1
        except Exception as e:
            logger.error("FAILED #%d — %s", content_id, str(e)[:150])
            failed += 1

    logger.info("")
    logger.info("=" * 60)
    logger.info("DONE — Posted: %d, Failed: %d", posted, failed)
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
