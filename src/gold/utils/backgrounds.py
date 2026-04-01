"""Background video manager for gameplay overlay style videos."""

from __future__ import annotations

import logging
import random
from collections import deque
from pathlib import Path

logger = logging.getLogger(__name__)

# Supported background video categories
BACKGROUND_CATEGORIES = {
    "gameplay": ["subway_surfers", "minecraft_parkour", "temple_run"],
    "satisfying": ["soap_cutting", "slime", "kinetic_sand", "oddly_satisfying"],
    "cooking": ["cooking", "food_prep", "baking"],
    "nature": ["nature", "water", "clouds", "rain"],
    "crafts": ["pottery", "painting", "calligraphy", "woodworking"],
    "ambient": ["particles", "abstract", "nature"],
}

# Track recently used backgrounds to avoid consecutive repeats
_RECENT_BACKGROUNDS: deque[Path] = deque(maxlen=5)


def get_backgrounds_dir() -> Path:
    """Get the backgrounds directory path."""
    bg_dir = Path("data/backgrounds")
    bg_dir.mkdir(parents=True, exist_ok=True)
    return bg_dir


def list_backgrounds(category: str = "gameplay") -> list[Path]:
    """List available background videos for a category."""
    bg_dir = get_backgrounds_dir() / category
    if not bg_dir.exists():
        return []
    return sorted(bg_dir.glob("*.mp4"))


def get_random_background(category: str = "gameplay") -> Path | None:
    """Get a random background video from the specified category.

    Special category "mixed" pulls from ALL background subdirs
    (gameplay, satisfying, cooking, nature, crafts), giving content
    maximum visual variety like real viral reels.

    Avoids returning any of the last 5 selected backgrounds.
    """
    if category == "mixed":
        videos = []
        for cat in ("gameplay", "satisfying", "cooking", "nature", "crafts"):
            videos.extend(list_backgrounds(cat))
    else:
        videos = list_backgrounds(category)

    if not videos:
        logger.warning(
            "No background videos found in data/backgrounds/%s/. "
            "Please add .mp4 clips.",
            category,
        )
        return None

    # Filter out recently used backgrounds
    available = [v for v in videos if v not in _RECENT_BACKGROUNDS]
    if not available:
        # All videos used recently — reset and pick from full list
        available = videos

    choice = random.choice(available)
    _RECENT_BACKGROUNDS.append(choice)
    return choice


async def build_background_montage(
    target_duration: float = 120.0,
    category: str = "mixed",
    output_path: Path | None = None,
    resolution: tuple[int, int] = (1080, 1920),
    fps: int = 30,
) -> Path:
    """Build a montage from multiple random background clips (no repeats).

    Picks enough clips to cover target_duration, concatenates them via ffmpeg
    concat demuxer with crossfade transitions. Returns the montage path.
    """
    import tempfile
    from .ffmpeg import run_ffmpeg, get_duration

    if category == "mixed":
        all_videos = []
        for cat in ("gameplay", "satisfying", "cooking", "nature", "crafts"):
            all_videos.extend(list_backgrounds(cat))
    else:
        all_videos = list_backgrounds(category)

    if not all_videos:
        raise RuntimeError(f"No background videos found for category '{category}'")

    # Shuffle to get variety, avoid repeats
    random.shuffle(all_videos)

    # Pick clips until we have enough duration (with some buffer)
    # Cap at 8 clips max to keep montage build fast
    max_clips = 8
    selected: list[Path] = []
    total_dur = 0.0
    for vid in all_videos:
        if total_dur >= target_duration + 10 or len(selected) >= max_clips:
            break
        try:
            dur = await get_duration(vid)
            if dur > 1.0:
                selected.append(vid)
                total_dur += dur
        except Exception:
            continue

    if not selected:
        raise RuntimeError("No valid background clips found")

    # If only one clip, just return it directly
    if len(selected) == 1:
        return selected[0]

    logger.info(
        "Building background montage: %d clips, %.1fs total",
        len(selected), total_dur,
    )

    # Output path
    if output_path is None:
        montage_dir = get_backgrounds_dir() / "_montages"
        montage_dir.mkdir(parents=True, exist_ok=True)
        output_path = montage_dir / f"montage_{random.randint(1000,9999)}.mp4"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    w, h = resolution

    # Build concat filter: scale each clip then concatenate
    inputs: list[str] = []
    filter_parts: list[str] = []
    for i, clip in enumerate(selected):
        inputs.extend(["-i", str(clip)])
        filter_parts.append(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1,fps={fps}[v{i}]"
        )

    n = len(selected)
    concat_in = "".join(f"[v{i}]" for i in range(n))
    filter_parts.append(f"{concat_in}concat=n={n}:v=1:a=0[vout]")

    filter_complex = ";".join(filter_parts)

    args = inputs + [
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
        "-pix_fmt", "yuv420p",
        "-an",
        "-y", str(output_path),
    ]

    await run_ffmpeg(args, timeout=900)
    logger.info("Background montage ready: %s", output_path.name)
    return output_path


def create_placeholder_background(
    output_path: Path,
    duration: float = 60.0,
    resolution: tuple[int, int] = (1080, 1920),
) -> Path:
    """Create a simple dark gradient placeholder background if no gameplay clips exist.

    This is a fallback — real gameplay clips should be added to data/backgrounds/gameplay/.
    """
    import asyncio
    from .ffmpeg import run_ffmpeg

    w, h = resolution
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Dark gradient background with subtle animation
    args = [
        "-f", "lavfi",
        "-i", (
            f"color=c=0x0a0a1a:s={w}x{h}:d={duration},"
            f"drawtext=text='':fontcolor=white:fontsize=1"
        ),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-pix_fmt", "yuv420p",
        "-t", str(duration),
        "-y", str(output_path),
    ]

    asyncio.get_event_loop().run_until_complete(run_ffmpeg(args, timeout=60))
    logger.info("Created placeholder background: %s (%.1fs)", output_path.name, duration)
    return output_path
