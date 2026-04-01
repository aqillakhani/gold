"""Test run for video quality upgrades — verifies all new features are active."""
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
logger = logging.getLogger("test_upgrades")


async def test_ai_tools():
    """Generate one ai_tools video and verify upgrades."""
    from gold.config import Config
    from gold.pipeline.orchestrator import ContentPipeline
    from gold.models.db import init_sync_db, create_tables_sync

    config = Config()
    db_path = config.root / "data" / "gold.db"
    init_sync_db(f"sqlite:///{db_path}")
    create_tables_sync()

    pipeline = ContentPipeline(config)

    logger.info("=" * 60)
    logger.info("UPGRADE TEST RUN — ai_tools (stock_footage / Remotion path)")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Expected upgrades in output:")
    logger.info("  1. TikTok-style word-group captions (not single word)")
    logger.info("  2. Progress bar at top")
    logger.info("  3. Emoji reactions at story beats")
    logger.info("  4. Hook card: AI Tools 'Tech Terminal' style")
    logger.info("  5. Audio post-processing (EQ + loudnorm)")
    logger.info("  6. Part badge (only if title has 'Part X')")
    logger.info("")

    start = time.time()
    content = await pipeline.generate_content("ai_tools", "ai_tools")
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

    # Verify output file
    if content.master_video_path and os.path.exists(content.master_video_path):
        size_mb = os.path.getsize(content.master_video_path) / (1024 * 1024)
        logger.info("  Size: %.1f MB", size_mb)
        logger.info("")
        logger.info("VERIFY MANUALLY: Open the video and check:")
        logger.info("  [ ] Subtitles: 2-3 word groups with background pill (NOT single word)")
        logger.info("  [ ] Subtitles: Centered vertically (NOT at bottom)")
        logger.info("  [ ] Subtitles: Active word highlighted in blue (#60a5fa)")
        logger.info("  [ ] Subtitles: Spring bounce animation on each group")
        logger.info("  [ ] Progress bar: thin blue line at very top growing left→right")
        logger.info("  [ ] Hook card: Tech Terminal style with typewriter text (first 4s)")
        logger.info("  [ ] Emoji: 1-4 emoji pop-ups at dramatic moments")
        logger.info("  [ ] Audio: Voice sounds clean, no rumble, normalized volume")
    else:
        logger.error("  Output file not found!")

    logger.info("")
    logger.info("Video path: %s", content.master_video_path)


if __name__ == "__main__":
    asyncio.run(test_ai_tools())
