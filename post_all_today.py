"""Post 1 video per account to YouTube + Instagram + TikTok."""
import asyncio
import json
import logging
import os
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
from gold.platforms.youtube import YouTubeAdapter
from gold.platforms.meta import InstagramAdapter
from gold.platforms.tiktok import TikTokAdapter

# 2026-03-30: 1 video per account, 3 platforms (YT + IG + TikTok)
# StoryVault = reddit #85 (Part 3 of lottery story)
# Previous: Part 1=#83 posted 3/27, Part 2=#84 posted 3/29
TODAY_PLAN = {
    "reddit_stories": 85,      # Part 3 lottery story
    "ai_tools": 91,            # AI Watches Your Screen
    "true_crime": 92,          # Crime Scene Cleaner
    "personal_finance": 88,    # $800/Month Selling Projects
    "english_learning": 100,   # Accent Stress Pattern
}


async def post_youtube(config, account_id, content_id, variant):
    """Post a single video to YouTube."""
    yt = YouTubeAdapter(config, account_id)
    hashtags = json.loads(variant["hashtags"]) if variant["hashtags"] else []
    result = await yt.post(
        video_path=Path(variant["path"]),
        caption=variant["caption"] or "",
        hashtags=hashtags,
    )
    return result


async def post_instagram(config, account_id, content_id, variant):
    """Post a single video to Instagram."""
    ig = InstagramAdapter(config, account_id)
    if not ig.ig_account_id:
        raise RuntimeError(f"No IG account_id for {account_id}")
    hashtags = json.loads(variant["hashtags"]) if variant["hashtags"] else []
    result = await ig.post(
        video_path=Path(variant["path"]),
        caption=variant["caption"] or "",
        hashtags=hashtags,
    )
    return result


async def post_tiktok(config, account_id, content_id, variant):
    """Post a single video to TikTok."""
    tt = TikTokAdapter(config, account_id)
    hashtags = json.loads(variant["hashtags"]) if variant["hashtags"] else []
    result = await tt.post(
        video_path=Path(variant["path"]),
        caption=variant["caption"] or "",
        hashtags=hashtags,
    )
    return result


async def main():
    config = Config()
    db_path = config.root / "data" / "gold.db"
    init_sync_db(f"sqlite:///{db_path}")
    create_tables_sync()

    import sqlite3
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    results = {"youtube": [], "instagram": [], "tiktok": [], "failed": []}

    for niche, cid in TODAY_PLAN.items():
        logger.info("")
        logger.info("=" * 50)
        logger.info("POSTING #%d [%s]", cid, niche)
        logger.info("=" * 50)

        # Get all variants for this content
        cur.execute("""
            SELECT platform, video_path, caption, hashtags
            FROM content_variant
            WHERE content_id = ? AND platform IN ('youtube', 'instagram', 'tiktok')
        """, (cid,))
        variants = {
            row[0]: {"path": row[1], "caption": row[2], "hashtags": row[3]}
            for row in cur.fetchall()
        }

        # YouTube
        if "youtube" in variants:
            try:
                result = await post_youtube(config, niche, cid, variants["youtube"])
                results["youtube"].append({"content_id": cid, "niche": niche, "post_id": result["post_id"]})
                logger.info("  YT OK  #%d [%s] -> %s", cid, niche, result["post_id"])
            except Exception as e:
                results["failed"].append({"content_id": cid, "niche": niche, "platform": "youtube", "error": str(e)[:200]})
                logger.error("  YT FAIL #%d [%s]: %s", cid, niche, str(e)[:200])

        await asyncio.sleep(3)

        # Instagram
        if "instagram" in variants:
            try:
                result = await post_instagram(config, niche, cid, variants["instagram"])
                results["instagram"].append({"content_id": cid, "niche": niche, "post_id": result["post_id"]})
                logger.info("  IG OK  #%d [%s] -> %s", cid, niche, result["post_id"])
            except Exception as e:
                results["failed"].append({"content_id": cid, "niche": niche, "platform": "instagram", "error": str(e)[:200]})
                logger.error("  IG FAIL #%d [%s]: %s", cid, niche, str(e)[:200])

        await asyncio.sleep(3)

        # TikTok
        if "tiktok" in variants:
            try:
                result = await post_tiktok(config, niche, cid, variants["tiktok"])
                results["tiktok"].append({"content_id": cid, "niche": niche, "post_id": result["post_id"]})
                logger.info("  TT OK  #%d [%s] -> %s", cid, niche, result["post_id"])
            except Exception as e:
                results["failed"].append({"content_id": cid, "niche": niche, "platform": "tiktok", "error": str(e)[:200]})
                logger.error("  TT FAIL #%d [%s]: %s", cid, niche, str(e)[:200])

        # Delay between accounts to avoid rate limits
        await asyncio.sleep(5)

    conn.close()

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("POSTING COMPLETE")
    logger.info("=" * 60)
    logger.info("  YouTube:   %d posted", len(results["youtube"]))
    logger.info("  Instagram: %d posted", len(results["instagram"]))
    logger.info("  TikTok:    %d posted", len(results["tiktok"]))
    logger.info("  Failed:    %d", len(results["failed"]))
    logger.info("")
    for platform in ["youtube", "instagram", "tiktok"]:
        for r in results[platform]:
            logger.info("  %s #%d [%s] -> %s", platform.upper()[:2], r["content_id"], r["niche"], r["post_id"])
    for r in results["failed"]:
        logger.info("  FAIL #%d [%s/%s]: %s", r["content_id"], r["niche"], r["platform"], r["error"][:100])


if __name__ == "__main__":
    asyncio.run(main())
