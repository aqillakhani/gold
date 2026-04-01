#!/usr/bin/env python3
"""Download royalty-free background videos from Pexels for the Gold platform.

Usage:
    python scripts/download_backgrounds.py --all --count 5
    python scripts/download_backgrounds.py --category satisfying --count 3
    python scripts/download_backgrounds.py --category cooking --count 5
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PEXELS_BASE = "https://api.pexels.com"

# Search queries per category — tuned for vertical satisfying-style backgrounds
CATEGORY_QUERIES: dict[str, list[str]] = {
    "gameplay": [
        "colorful mobile game screen",
        "abstract neon tunnel animation",
        "retro arcade game colorful",
        "parkour running first person",
        "colorful abstract motion",
        "hypnotic pattern loop",
    ],
    "satisfying": [
        "satisfying close up texture",
        "oddly satisfying process",
        "smooth pouring liquid",
        "colorful paint mixing",
        "soap cutting satisfying",
        "kinetic sand satisfying",
        "slime stretching colorful",
        "pressure washing satisfying",
        "carpet cleaning satisfying",
        "organizing drawers satisfying",
        "peeling sticker satisfying",
        "sand art bottle",
    ],
    "cooking": [
        "cooking close up hands",
        "food preparation kitchen",
        "baking dough kneading",
        "chopping vegetables close up",
    ],
    "nature": [
        "nature close up macro",
        "flowing water stream",
        "rain drops slow motion",
        "clouds timelapse sky",
    ],
    "crafts": [
        "pottery wheel hands clay",
        "painting brush canvas",
        "calligraphy ink writing",
        "woodworking carving close up",
    ],
}

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920


def _get_api_key() -> str:
    """Load Pexels API key from secrets/.env or environment."""
    key = os.environ.get("PEXELS_API_KEY", "")
    if key:
        return key

    env_path = Path("secrets/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("PEXELS_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    return key

    logger.error(
        "PEXELS_API_KEY not found. Add it to secrets/.env or set as environment variable.\n"
        "Get a free key at https://www.pexels.com/api/"
    )
    sys.exit(1)


def _find_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg not found in PATH")
    return path


async def search_videos(
    client: httpx.AsyncClient, api_key: str, query: str, per_page: int = 10
) -> list[dict]:
    """Search Pexels for videos matching query."""
    resp = await client.get(
        f"{PEXELS_BASE}/videos/search",
        headers={"Authorization": api_key},
        params={
            "query": query,
            "per_page": per_page,
            "orientation": "portrait",
            "size": "medium",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("videos", [])


def _pick_best_file(video: dict) -> str | None:
    """Pick the best video file URL — prefer HD portrait."""
    files = video.get("video_files", [])
    # Sort by height desc, prefer portrait aspect
    portrait_files = [
        f for f in files
        if f.get("height", 0) >= 720
        and f.get("width", 0) < f.get("height", 0)
    ]
    if not portrait_files:
        # Fallback to any HD file
        portrait_files = [f for f in files if f.get("height", 0) >= 720]
    if not portrait_files:
        portrait_files = files

    if not portrait_files:
        return None

    # Pick highest quality
    best = max(portrait_files, key=lambda f: f.get("height", 0))
    return best.get("link")


async def download_and_convert(
    client: httpx.AsyncClient,
    url: str,
    output_path: Path,
) -> bool:
    """Download video and convert to 1080x1920 using FFmpeg."""
    # Download raw video
    raw_path = output_path.with_suffix(".raw.mp4")
    try:
        async with client.stream("GET", url, timeout=120) as resp:
            resp.raise_for_status()
            with open(raw_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)

        # Convert to target resolution
        ffmpeg = _find_ffmpeg()
        cmd = [
            ffmpeg,
            "-i", str(raw_path),
            "-vf", f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase,crop={TARGET_WIDTH}:{TARGET_HEIGHT}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-an",  # Strip audio (we add our own)
            "-pix_fmt", "yuv420p",
            "-t", "120",  # Max 2 minutes
            "-y", str(output_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=300)
        if proc.returncode != 0:
            logger.error("FFmpeg failed: %s", proc.stderr.decode(errors="replace")[:300])
            return False

        logger.info("  Saved: %s", output_path.name)
        return True

    except Exception as e:
        logger.error("  Download/convert failed: %s", e)
        return False
    finally:
        if raw_path.exists():
            raw_path.unlink()


async def download_category(
    api_key: str, category: str, count: int, bg_dir: Path
) -> int:
    """Download `count` videos for a given category."""
    queries = CATEGORY_QUERIES.get(category, [])
    if not queries:
        logger.error("Unknown category: %s", category)
        return 0

    out_dir = bg_dir / category
    out_dir.mkdir(parents=True, exist_ok=True)

    # Check existing files to avoid re-downloading
    existing = list(out_dir.glob("*.mp4"))
    existing_count = len(existing)
    logger.info("Category '%s': %d existing, downloading %d more", category, existing_count, count)

    downloaded = 0
    file_idx = existing_count + 1

    async with httpx.AsyncClient(timeout=60) as client:
        for query in queries:
            if downloaded >= count:
                break

            logger.info("  Searching: '%s'", query)
            videos = await search_videos(client, api_key, query, per_page=count * 2)

            for video in videos:
                if downloaded >= count:
                    break

                url = _pick_best_file(video)
                if not url:
                    continue

                # Generate filename from category
                safe_cat = category.replace(" ", "_")
                output_path = out_dir / f"{safe_cat}_{file_idx:02d}.mp4"

                logger.info("  Downloading video %d/%d...", downloaded + 1, count)
                success = await download_and_convert(client, url, output_path)
                if success:
                    downloaded += 1
                    file_idx += 1

    return downloaded


async def main():
    parser = argparse.ArgumentParser(description="Download background videos from Pexels")
    parser.add_argument(
        "--category", "-c",
        choices=list(CATEGORY_QUERIES.keys()),
        help="Category to download",
    )
    parser.add_argument("--all", action="store_true", help="Download all categories")
    parser.add_argument("--count", "-n", type=int, default=5, help="Videos per category (default: 5)")
    parser.add_argument("--bg-dir", type=str, default="data/backgrounds", help="Background video directory")
    args = parser.parse_args()

    if not args.category and not args.all:
        parser.error("Specify --category or --all")

    api_key = _get_api_key()
    bg_dir = Path(args.bg_dir)
    bg_dir.mkdir(parents=True, exist_ok=True)

    categories = list(CATEGORY_QUERIES.keys()) if args.all else [args.category]
    total = 0

    for cat in categories:
        n = await download_category(api_key, cat, args.count, bg_dir)
        total += n

    logger.info("Done! Downloaded %d videos total.", total)


if __name__ == "__main__":
    asyncio.run(main())
