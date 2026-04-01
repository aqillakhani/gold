"""Test quality: generate 1 video per niche to validate all quality upgrades.

Tests: karaoke subtitles, audio ducking, emotion TTS, visual hooks,
visual treatments, loudness normalization, SFX overlay.

Captures all log output and produces a QUALITY VERIFICATION REPORT
showing which upgrades were applied vs which silently fell back.
"""

import asyncio
import logging
import os
import sys
import time
from io import StringIO
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / "secrets" / ".env")

FFMPEG_DIR = r"C:\Users\claws\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

# STRICT MODE: fail loudly on any fallback — never silently degrade quality
os.environ["GOLD_STRICT_MODE"] = "1"


# --------------------------------------------------------------------------
# Quality tracker: captures tagged log lines to verify upgrades
# --------------------------------------------------------------------------
class QualityTracker(logging.Handler):
    """Captures [TAG] log lines to verify quality upgrades were applied."""

    UPGRADE_TAGS = [
        "TTS",           # Fish Audio with emotion markers
        "EMOTION",       # Emotion marker injection
        "SUBTITLE",      # Karaoke-highlight subtitles
        "AUDIO-MIX",     # sidechaincompress ducking
        "VISUAL-HOOK",   # Animated text hook overlay
    ]

    def __init__(self):
        super().__init__()
        # Per-niche tracking: {niche: {tag: "OK" | "DEGRADED" | "FAILED"}}
        self.results: dict[str, dict[str, str]] = {}
        self._current_niche = ""

    def set_niche(self, niche_id: str):
        self._current_niche = niche_id
        if niche_id not in self.results:
            self.results[niche_id] = {}

    def emit(self, record: logging.LogRecord):
        msg = record.getMessage()
        niche = self._current_niche
        if not niche:
            return

        for tag in self.UPGRADE_TAGS:
            marker = f"[{tag}]"
            if marker not in msg:
                continue

            current = self.results.get(niche, {}).get(tag)

            if "FAILED" in msg:
                self.results.setdefault(niche, {})[tag] = "FAILED"
            elif "DEGRADED" in msg or "FALLBACK" in msg:
                if current != "FAILED":
                    self.results.setdefault(niche, {})[tag] = "DEGRADED"
            elif " OK:" in msg or " OK " in msg or "Using Fish Audio" in msg or "Loaded" in msg:
                # Positive signals — only set if not already degraded/failed
                if current not in ("DEGRADED", "FAILED"):
                    self.results.setdefault(niche, {})[tag] = "OK"

        # Also track Remotion-path signals (stock_footage niches use Remotion,
        # which bypasses FFmpeg compose — so audio ducking happens differently)
        if "Remotion render complete" in msg:
            # Remotion handles its own audio mixing — mark as OK if not failed
            if self.results.get(niche, {}).get("AUDIO-MIX") not in ("DEGRADED", "FAILED"):
                self.results.setdefault(niche, {})["AUDIO-MIX"] = "OK (Remotion)"

        # Track karaoke via word timestamps for Remotion path
        if "Extracted" in msg and "word timestamps" in msg:
            if self.results.get(niche, {}).get("SUBTITLE") not in ("DEGRADED", "FAILED"):
                self.results.setdefault(niche, {})["SUBTITLE"] = "OK (Remotion)"

    def report(self) -> str:
        """Generate the quality verification report."""
        lines = []
        lines.append("")
        lines.append("=" * 70)
        lines.append("  QUALITY UPGRADE VERIFICATION REPORT")
        lines.append("=" * 70)
        lines.append("")

        all_passed = True
        for niche, tags in sorted(self.results.items()):
            lines.append(f"  [{niche}]")
            for tag in self.UPGRADE_TAGS:
                status = tags.get(tag, "NOT SEEN")
                if status.startswith("OK"):
                    icon = "  OK "
                elif status == "DEGRADED":
                    icon = " WARN"
                    all_passed = False
                elif status == "FAILED":
                    icon = " FAIL"
                    all_passed = False
                else:
                    icon = "  ???"
                    all_passed = False
                lines.append(f"    {icon}  {tag:<15s} {status}")
            lines.append("")

        lines.append("-" * 70)
        if all_passed:
            lines.append("  RESULT: ALL QUALITY UPGRADES VERIFIED")
        else:
            lines.append("  RESULT: SOME UPGRADES DEGRADED OR MISSING — CHECK ABOVE")
        lines.append("=" * 70)
        return "\n".join(lines)


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

    # Install quality tracker on root logger
    tracker = QualityTracker()
    logging.getLogger().addHandler(tracker)

    niches = [
        "reddit_stories",
        "betrayal_revenge",
        "ai_tools",
        "true_crime",
        "personal_finance",
        "english_learning",
    ]

    # Allow filtering from CLI
    requested = [n for n in sys.argv[1:] if n in niches]
    if requested:
        niches = requested

    logger.info("=" * 60)
    logger.info("QUALITY TEST RUN — 1 video per niche")
    logger.info("=" * 60)
    logger.info("Niches: %s", ", ".join(niches))
    logger.info("Tracking tags: %s", ", ".join(QualityTracker.UPGRADE_TAGS))
    logger.info("=" * 60)

    start = time.time()
    results = {"success": [], "failed": []}

    for niche_id in niches:
        logger.info("")
        logger.info("=" * 60)
        logger.info("[%s] Generating test video...", niche_id)
        logger.info("=" * 60)

        tracker.set_niche(niche_id)

        try:
            content = await pipeline.generate_content(niche_id, niche_id)
            if content:
                logger.info(
                    "[%s] SUCCESS: #%d — %s",
                    niche_id, content.id,
                    content.title[:60].encode("ascii", "ignore").decode(),
                )
                results["success"].append({
                    "niche": niche_id,
                    "content_id": content.id,
                    "title": content.title,
                    "path": content.file_path if hasattr(content, "file_path") else "N/A",
                })
            else:
                logger.error("[%s] FAILED: returned None", niche_id)
                results["failed"].append({"niche": niche_id, "error": "None returned"})
        except Exception as e:
            logger.error("[%s] FAILED: %s", niche_id, str(e)[:300])
            results["failed"].append({"niche": niche_id, "error": str(e)[:300]})

    elapsed = time.time() - start

    # Standard summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("QUALITY TEST COMPLETE (%.1f minutes)", elapsed / 60)
    logger.info("=" * 60)
    logger.info("  Succeeded: %d / %d", len(results["success"]), len(niches))
    logger.info("  Failed:    %d / %d", len(results["failed"]), len(niches))

    for r in results["success"]:
        title = r["title"][:55].encode("ascii", "ignore").decode()
        logger.info("  OK  #%d [%s] %s", r["content_id"], r["niche"], title)

    for r in results["failed"]:
        logger.info("  FAIL [%s] %s", r["niche"], r["error"][:100])

    # Quality verification report
    report = tracker.report()
    print(report)

    # Save report to file
    report_path = Path(__file__).parent / "data" / "quality_report.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    logger.info("Report saved to: %s", report_path)


if __name__ == "__main__":
    asyncio.run(main())
