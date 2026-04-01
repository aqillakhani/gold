"""Production run: generate a batch of videos using the full pipeline.

Uses batch_size from config/settings.yaml to determine how many videos per niche.
Multi-part niches (reddit_stories, betrayal_revenge) generate 1 story = 3 videos each.

Usage:
    python production_run.py                    # all niches
    python production_run.py true_crime ai_tools  # specific niches only
"""

import asyncio
import logging
import os
import sys
import time
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
from gold.pipeline.orchestrator import ContentPipeline


async def main():
    config = Config()
    db_path = config.root / "data" / "gold.db"
    init_sync_db(f"sqlite:///{db_path}")
    create_tables_sync()

    pipeline = ContentPipeline(config)

    # Determine which niches to run
    all_niches = config.settings.get("app", {}).get("active_niches", [])
    requested = [n for n in sys.argv[1:] if n in all_niches]
    niches = requested or all_niches

    # Get batch sizes from config
    batch_sizes = config.settings.get("scheduling", {}).get("batch_size", {})
    default_batch = 3

    logger.info("=" * 60)
    logger.info("PRODUCTION RUN")
    logger.info("=" * 60)

    total_videos = 0
    for niche_id in niches:
        batch = batch_sizes.get(niche_id, default_batch)
        multi_part = config.niches.get(niche_id, {}).get("multi_part", {})
        if multi_part.get("enabled"):
            parts = multi_part.get("parts", 3)
            videos = batch * parts
        else:
            videos = batch
        total_videos += videos
        logger.info("  %s: %d run(s) → %d videos", niche_id, batch, videos)

    logger.info("Total expected: %d videos", total_videos)
    logger.info("=" * 60)

    start = time.time()
    results = {"success": [], "failed": []}

    for niche_id in niches:
        batch = batch_sizes.get(niche_id, default_batch)
        account_id = niche_id  # account_id matches niche_id in our config

        for i in range(batch):
            run_label = f"[{niche_id} {i+1}/{batch}]"
            logger.info("")
            logger.info("=" * 60)
            logger.info("%s Starting...", run_label)
            logger.info("=" * 60)

            try:
                content = await pipeline.generate_content(account_id, niche_id)
                if content:
                    logger.info(
                        "%s SUCCESS: #%d — %s",
                        run_label, content.id,
                        content.title[:60].encode("ascii", "ignore").decode(),
                    )
                    results["success"].append({
                        "niche": niche_id,
                        "content_id": content.id,
                        "title": content.title,
                    })
                else:
                    logger.error("%s FAILED: returned None", run_label)
                    results["failed"].append({"niche": niche_id, "run": i + 1, "error": "None returned"})
            except Exception as e:
                logger.error("%s FAILED: %s", run_label, str(e)[:200])
                results["failed"].append({"niche": niche_id, "run": i + 1, "error": str(e)[:200]})

    elapsed = time.time() - start

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("PRODUCTION RUN COMPLETE (%.1f minutes)", elapsed / 60)
    logger.info("=" * 60)
    logger.info("  Succeeded: %d", len(results["success"]))
    logger.info("  Failed:    %d", len(results["failed"]))
    logger.info("")

    for r in results["success"]:
        title = r["title"][:55].encode("ascii", "ignore").decode()
        logger.info("  OK  #%d [%s] %s", r["content_id"], r["niche"], title)

    for r in results["failed"]:
        logger.info("  FAIL [%s] run %d: %s", r["niche"], r["run"], r["error"][:80])


if __name__ == "__main__":
    asyncio.run(main())
