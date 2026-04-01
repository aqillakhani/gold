"""Post today's videos to YouTube + Instagram."""
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
load_dotenv(Path(__file__).parent / "secrets" / ".env")

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

# 2026-03-29: 1 video per channel per platform
# StoryVault = reddit #84 (Part 2 of lottery story, Part 1=#83 posted 3/27)
# No betrayal today — StoryVault only gets 1 video
TODAY_PLAN = {
    "reddit_stories": [84],
    "ai_tools": [90],
    "true_crime": [71],
    "personal_finance": [87],
    "english_learning": [99],
}

async def main():
    config = Config()
    db_path = config.root / "data" / "gold.db"
    init_sync_db(f"sqlite:///{db_path}")
    create_tables_sync()

    import sqlite3
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    results = {"youtube": [], "instagram": [], "failed": []}

    for niche, content_ids in TODAY_PLAN.items():
        account_id = niche
        
        # Init adapters
        try:
            yt = YouTubeAdapter(config, account_id)
        except Exception as e:
            logger.error("[%s] YouTube adapter init failed: %s", niche, e)
            yt = None

        try:
            ig = InstagramAdapter(config, account_id)
            if not ig.ig_account_id:
                logger.warning("[%s] No IG account_id, skipping Instagram", niche)
                ig = None
        except Exception as e:
            logger.error("[%s] Instagram adapter init failed: %s", niche, e)
            ig = None

        for cid in content_ids:
            # Get variants
            cur.execute("""
                SELECT platform, video_path, caption, hashtags
                FROM content_variant
                WHERE content_id = ? AND platform IN ('youtube', 'instagram')
            """, (cid,))
            variants = {row[0]: {"path": row[1], "caption": row[2], "hashtags": row[3]} for row in cur.fetchall()}

            # YouTube upload
            if yt and "youtube" in variants:
                v = variants["youtube"]
                try:
                    hashtags = json.loads(v["hashtags"]) if v["hashtags"] else []
                    result = await yt.post(
                        video_path=Path(v["path"]),
                        caption=v["caption"] or "",
                        hashtags=hashtags,
                    )
                    results["youtube"].append({"content_id": cid, "niche": niche, "post_id": result["post_id"]})
                    logger.info("YT OK #%d [%s] -> %s", cid, niche, result["post_id"])
                except Exception as e:
                    results["failed"].append({"content_id": cid, "niche": niche, "platform": "youtube", "error": str(e)[:150]})
                    logger.error("YT FAIL #%d [%s]: %s", cid, niche, str(e)[:150])

            # Instagram upload
            if ig and "instagram" in variants:
                v = variants["instagram"]
                try:
                    hashtags = json.loads(v["hashtags"]) if v["hashtags"] else []
                    result = await ig.post(
                        video_path=Path(v["path"]),
                        caption=v["caption"] or "",
                        hashtags=hashtags,
                    )
                    results["instagram"].append({"content_id": cid, "niche": niche, "post_id": result["post_id"]})
                    logger.info("IG OK #%d [%s] -> %s", cid, niche, result["post_id"])
                except Exception as e:
                    results["failed"].append({"content_id": cid, "niche": niche, "platform": "instagram", "error": str(e)[:150]})
                    logger.error("IG FAIL #%d [%s]: %s", cid, niche, str(e)[:150])

            # Small delay between uploads to avoid rate limits
            await asyncio.sleep(3)

    conn.close()

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("POSTING COMPLETE")
    logger.info("=" * 60)
    logger.info("  YouTube: %d posted", len(results["youtube"]))
    logger.info("  Instagram: %d posted", len(results["instagram"]))
    logger.info("  Failed: %d", len(results["failed"]))
    for r in results["youtube"]:
        logger.info("  YT  #%d [%s] -> %s", r["content_id"], r["niche"], r["post_id"])
    for r in results["instagram"]:
        logger.info("  IG  #%d [%s] -> %s", r["content_id"], r["niche"], r["post_id"])
    for r in results["failed"]:
        logger.info("  FAIL #%d [%s/%s]: %s", r["content_id"], r["niche"], r["platform"], r["error"][:80])

if __name__ == "__main__":
    asyncio.run(main())
