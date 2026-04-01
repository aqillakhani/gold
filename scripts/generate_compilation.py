"""Generate a dangerous_nature viral compilation end-to-end.

Usage:
    python scripts/generate_compilation.py                  # single compilation
    python scripts/generate_compilation.py --batch 3        # 3 compilations
    python scripts/generate_compilation.py --dry-run        # scrape only, don't render
"""

import argparse
import asyncio
import logging
import os
import sys
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


async def main() -> int:
    parser = argparse.ArgumentParser(description="Generate dangerous nature compilations")
    parser.add_argument("--batch", type=int, default=1, help="Number of compilations to create")
    parser.add_argument("--dry-run", action="store_true", help="Scrape clips only, don't render")
    parser.add_argument("--clips", type=int, default=4, help="Clips per compilation (3-4)")
    args = parser.parse_args()

    from gold.config import Config
    from gold.models.db import init_sync_db, create_tables_sync
    from gold.pipeline.compilation import CompilationPipeline

    config = Config()
    db_path = config.root / "data" / "gold.db"
    init_sync_db(f"sqlite:///{db_path}")
    create_tables_sync()

    pipeline = CompilationPipeline(config)

    logger.info("=" * 70)
    logger.info("DANGEROUS NATURE COMPILATION GENERATOR")
    logger.info("  Batch size: %d", args.batch)
    logger.info("  Clips per compilation: %d", args.clips)
    logger.info("=" * 70)

    if args.dry_run:
        logger.info("[DRY RUN] Scraping clips only...")
        from gold.utils.reddit import get_viral_videos
        comp_config = config.niches.get("dangerous_nature", {}).get("compilation", {})
        subreddits = comp_config.get("subreddits", ["NatureIsMetal", "SweatyPalms"])
        videos = await get_viral_videos(subreddits, min_score=3000, limit_per_sub=5)
        logger.info("Found %d viral clips:", len(videos))
        for v in videos:
            logger.info("  [%5d] r/%-20s | %s", v["score"], v["subreddit"], v["title"][:60])
        return 0

    results = {"ok": [], "fail": []}

    for i in range(args.batch):
        logger.info("")
        logger.info("=" * 50)
        logger.info("COMPILATION %d/%d", i + 1, args.batch)
        logger.info("=" * 50)

        try:
            content = await pipeline.create_compilation(
                account_id="dangerous_nature",
                niche_id="dangerous_nature",
                clip_count=args.clips,
            )

            if content:
                results["ok"].append(content.id)
                logger.info("SUCCESS: Compilation #%d — %s", content.id, content.title)
            else:
                results["fail"].append(i + 1)
                logger.error("FAILED: No compilation created for batch %d", i + 1)
        except Exception as e:
            results["fail"].append(i + 1)
            logger.error("ERROR: %s", e, exc_info=True)

    # Summary
    logger.info("")
    logger.info("=" * 70)
    logger.info("COMPILATION COMPLETE")
    logger.info("  Success: %d (IDs: %s)", len(results["ok"]), results["ok"])
    logger.info("  Failed:  %d", len(results["fail"]))
    logger.info("=" * 70)

    return 0 if not results["fail"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
