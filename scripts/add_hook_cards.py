"""Add niche-specific hook cards to existing production videos.

Renders a 4-second hook card overlay via Remotion (WebM with alpha),
then composites it onto the first 4 seconds of each video using FFmpeg.
"""

import asyncio
import json
import logging
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# FFmpeg path
FFMPEG_DIR = r"C:\Users\claws\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REMOTION_DIR = PROJECT_ROOT / "remotion"
DB_PATH = PROJECT_ROOT / "data" / "gold.db"
RENDERED_DIR = PROJECT_ROOT / "data" / "media" / "rendered"

NICHE_COLORS = {
    "ai_tools": "#3b82f6",
    "crypto_finance": "#22c55e",
    "true_crime": "#ef4444",
}

# Only process these niches (not reddit_stories)
TARGET_NICHES = {"ai_tools", "crypto_finance", "true_crime"}


def get_production_content() -> list[dict]:
    """Query DB for production batch content (IDs 7-24)."""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT id, niche, hook FROM content WHERE id >= 7 AND id <= 24 ORDER BY id"
    ).fetchall()
    db.close()
    return [dict(r) for r in rows if r["niche"] in TARGET_NICHES]


def find_master_video(content_id: int) -> Path | None:
    """Find the master video file for a content ID."""
    matches = list(RENDERED_DIR.glob(f"content_{content_id}_master_*.mp4"))
    return matches[0] if matches else None


async def render_hook_overlay(
    hook_text: str, niche_id: str, output_path: Path
) -> Path:
    """Render a 4-second hook card overlay as WebM with alpha via Remotion."""
    props = {
        "hookText": hook_text,
        "nicheId": niche_id,
        "accentColor": NICHE_COLORS.get(niche_id, "#0ea5e9"),
        "duration": 4,
    }

    props_file = Path(tempfile.mktemp(suffix=".json", prefix="hook_props_"))
    props_file.write_text(json.dumps(props, indent=2), encoding="utf-8")

    entry_point = str(REMOTION_DIR / "src" / "index.ts")
    abs_output = str(output_path.resolve()).replace("\\", "/")

    cmd = " ".join([
        "npx", "remotion", "render",
        entry_point,
        "HookCardOverlay",
        abs_output,
        f"--props={str(props_file)}",
        "--codec=vp8",
        "--concurrency=4",
        "--log=error",
        "--gl=angle",
    ])

    logger.info("Rendering hook overlay for %s: %s", niche_id, hook_text[:50])

    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=str(REMOTION_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "NODE_OPTIONS": "--max-old-space-size=4096"},
    )
    stdout, stderr = await proc.communicate()

    props_file.unlink(missing_ok=True)

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"Hook overlay render failed: {err}")

    if not output_path.exists():
        raise RuntimeError(f"No output at {output_path}")

    return output_path


async def composite_hook_onto_video(
    video_path: Path, overlay_path: Path, output_path: Path
) -> Path:
    """Composite the hook card overlay onto the first 4 seconds of a video."""
    # FFmpeg: overlay the WebM (with alpha) on top of the input video
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(overlay_path),
        "-filter_complex",
        "[0:v][1:v]overlay=0:0:shortest=0:enable='between(t,0,4)'[outv]",
        "-map", "[outv]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"FFmpeg composite failed: {err}")

    return output_path


async def process_one(content: dict) -> bool:
    """Process a single content item: render hook overlay + composite."""
    content_id = content["id"]
    niche = content["niche"]
    hook_text = content["hook"]

    video_path = find_master_video(content_id)
    if not video_path:
        logger.warning("Content %d: no master video found, skipping", content_id)
        return False

    # Skip already-processed videos (backup exists = already has hook card)
    backup_path = video_path.with_suffix(".no_hook.mp4")
    if backup_path.exists():
        logger.info("Content %d: already processed (backup exists), skipping", content_id)
        return True

    if not hook_text:
        logger.warning("Content %d: no hook text, skipping", content_id)
        return False

    logger.info("Content %d [%s]: %s", content_id, niche, hook_text[:50])

    # Render the hook card overlay as WebM with alpha
    overlay_dir = RENDERED_DIR / "hook_overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    overlay_path = overlay_dir / f"hook_{content_id}.webm"

    try:
        await render_hook_overlay(hook_text, niche, overlay_path)
    except Exception as e:
        logger.error("Content %d: hook render failed: %s", content_id, e)
        return False

    # Composite onto the original video
    # Save to a temp file, then replace original
    temp_output = video_path.with_suffix(".hook_temp.mp4")
    try:
        await composite_hook_onto_video(video_path, overlay_path, temp_output)
    except Exception as e:
        logger.error("Content %d: composite failed: %s", content_id, e)
        temp_output.unlink(missing_ok=True)
        return False

    # Backup original, replace with composited version
    backup_path = video_path.with_suffix(".no_hook.mp4")
    if not backup_path.exists():
        video_path.rename(backup_path)
    else:
        video_path.unlink()
    temp_output.rename(video_path)

    # Clean up overlay
    overlay_path.unlink(missing_ok=True)

    size_mb = video_path.stat().st_size / (1024 * 1024)
    logger.info("Content %d: done (%.1f MB)", content_id, size_mb)
    return True


async def main():
    content_list = get_production_content()
    logger.info("Found %d production videos to add hook cards to", len(content_list))

    success = 0
    for content in content_list:
        if await process_one(content):
            success += 1

    logger.info("Done: %d/%d videos updated with hook cards", success, len(content_list))


if __name__ == "__main__":
    asyncio.run(main())
