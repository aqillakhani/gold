"""Test run for video quality upgrades — reddit_stories (gameplay/FFmpeg path)."""
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

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / "secrets" / ".env")

FFMPEG_DIR = r"C:\Users\claws\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("test_upgrades_reddit")


async def test_reddit():
    """Generate one reddit_stories video and verify upgrades."""
    from gold.config import Config
    from gold.pipeline.orchestrator import ContentPipeline
    from gold.models.db import init_sync_db, create_tables_sync

    config = Config()
    db_path = config.root / "data" / "gold.db"
    init_sync_db(f"sqlite:///{db_path}")
    create_tables_sync()

    pipeline = ContentPipeline(config)

    logger.info("=" * 60)
    logger.info("UPGRADE TEST — reddit_stories (gameplay / FFmpeg path)")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Testing these upgrades:")
    logger.info("  1. ASS subtitles at y=1350 (below persistent hook card)")
    logger.info("  2. Progress bar at BOTTOM")
    logger.info("  3. Part badge (if multi-part title)")
    logger.info("  4. Audio post-processing (EQ + loudnorm)")
    logger.info("  5. Multi-voice dialogue (if quotes detected)")
    logger.info("")

    start = time.time()
    content = await pipeline.generate_content("reddit_stories", "reddit_stories")
    elapsed = time.time() - start

    if not content:
        logger.error("FAILED: No content generated")
        return

    logger.info("")
    logger.info("=" * 60)
    logger.info("GENERATION COMPLETE in %.0fs", elapsed)
    logger.info("=" * 60)
    logger.info("  Content ID: %d", content.id)
    logger.info("  Title: %s", content.title)
    logger.info("  Master: %s", content.master_video_path)
    logger.info("  Status: %s", content.status)

    if content.master_video_path and os.path.exists(content.master_video_path):
        size_mb = os.path.getsize(content.master_video_path) / (1024 * 1024)
        logger.info("  Size: %.1f MB", size_mb)
        logger.info("")
        logger.info("VERIFY MANUALLY:")
        logger.info("  [ ] Hook card: persistent Reddit post card (upper area)")
        logger.info("  [ ] Subtitles: 3-word groups BELOW hook card (not overlapping)")
        logger.info("  [ ] Progress bar: thin accent line at BOTTOM")
        logger.info("  [ ] Audio: clean, normalized volume")
    else:
        logger.error("  Output file not found!")

    logger.info("")
    logger.info("Video path: %s", content.master_video_path)


if __name__ == "__main__":
    asyncio.run(test_reddit())
