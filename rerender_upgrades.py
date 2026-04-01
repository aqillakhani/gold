"""Re-render existing READY videos with current pipeline upgrades.

Upgrades applied:
- Karaoke-highlight subtitles (3-word groups, Montserrat, niche accent colors)
- Progress bar (blue 4px line at bottom)
- Audio ducking (sidechaincompress)
- Part badge for multi-part stories
- CTA overlay
- Hook card overlay (gameplay)
- Loudness normalization (-14 LUFS)
- Visual treatments + SFX (stock_footage)

Reuses existing voiceover audio — does NOT regenerate TTS.
Regenerates subtitles from existing audio via Whisper.
"""

import asyncio
import json
import logging
import os
import sqlite3
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
from gold.pipeline.subtitles import SubtitleGenerator
from gold.pipeline.variation import PlatformVariator

# Skip: already posted, already have karaoke subs, or already re-rendered this session
SKIP_IDS = {
    85, 88, 91, 92, 100, 134, 135, 136, 137, 138, 139,
    # Already re-rendered (completed before process was killed)
    25, 40, 83, 84, 95, 96, 97,          # gameplay
    31, 43, 46, 71, 86, 87, 89, 90,      # stock_footage
    93, 94, 98, 99, 103, 105, 109, 110,   # stock_footage
}

# Niche -> video_style mapping
GAMEPLAY_NICHES = {"reddit_stories", "betrayal_revenge"}
STOCK_NICHES = {"ai_tools", "true_crime", "personal_finance", "english_learning"}


def get_content_to_rerender(db_path: Path) -> list[dict]:
    """Get all READY content that needs re-rendering."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT id, niche, title, hook, script, scene_descriptions, master_video_path
        FROM content WHERE status = 'READY' ORDER BY id
    """)
    rows = cur.fetchall()
    conn.close()

    result = []
    for r in rows:
        if r["id"] in SKIP_IDS:
            continue
        result.append(dict(r))
    return result


def find_voiceover(content_id: int, media_dir: Path) -> Path | None:
    """Find existing voiceover audio file for a content ID."""
    audio_dir = media_dir / "audio"
    matches = sorted(audio_dir.glob(f"content_{content_id}_vo_*"))
    return matches[0] if matches else None


def find_music(content_id: int, media_dir: Path, niche_id: str) -> Path | None:
    """Find existing music file for a content — check niche-specific suno first."""
    import random
    audio_dir = media_dir / "audio"

    # Check for content-specific music
    for pattern in [f"content_{content_id}_music_*", f"content_{content_id}_suno_*"]:
        matches = sorted(audio_dir.glob(pattern))
        if matches:
            return matches[0]

    # Check suno directory for niche-specific music
    suno_dir = audio_dir / "music" / "suno"
    if suno_dir.exists():
        niche_files = sorted(suno_dir.glob(f"suno_{niche_id}_*.mp3"))
        if niche_files:
            return random.choice(niche_files)
        # Fallback to any suno file
        all_files = sorted(suno_dir.glob("*.mp3"))
        if all_files:
            return random.choice(all_files)

    # Check safe music directory
    safe_dir = audio_dir / "music" / "safe"
    if safe_dir.exists():
        safe_files = sorted(safe_dir.glob("*.mp3"))
        if safe_files:
            return safe_files[0]

    return None


def find_background(media_dir: Path) -> Path | None:
    """Find a background montage for gameplay videos."""
    clips_dir = media_dir / "clips" / "cache"
    if clips_dir.exists():
        mp4s = sorted(clips_dir.glob("*.mp4"))
        if mp4s:
            return mp4s[0]

    # Check backgrounds dir
    bg_dir = media_dir / "backgrounds"
    if bg_dir.exists():
        mp4s = sorted(bg_dir.glob("*.mp4"))
        if mp4s:
            return mp4s[0]
    return None


async def rerender_gameplay(
    content: dict,
    config: Config,
    subtitle_gen: SubtitleGenerator,
    variator: PlatformVariator,
) -> bool:
    """Re-render a gameplay-style video (reddit_stories, betrayal_revenge)."""
    from gold.utils.backgrounds import build_background_montage, create_placeholder_background
    from gold.utils.ffmpeg import compose_gameplay_video, get_duration, run_ffmpeg

    cid = content["id"]
    niche_id = content["niche"]
    niche_config = config.niches.get(niche_id, {})
    media_dir = config.media_dir

    # Find existing voiceover
    audio_path = find_voiceover(cid, media_dir)
    if not audio_path:
        logger.error("[#%d] NO VOICEOVER FOUND — skipping", cid)
        return False

    audio_duration = await get_duration(audio_path)

    # Find music
    music_path = find_music(cid, media_dir, niche_id)

    # Build background montage
    bg_category = niche_config.get("background_category", "mixed")
    try:
        background = await build_background_montage(
            target_duration=int(audio_duration) + 30,
            category=bg_category,
        )
    except RuntimeError:
        bg_dir = media_dir / "backgrounds"
        bg_dir.mkdir(parents=True, exist_ok=True)
        background = bg_dir / "placeholder.mp4"
        if not background.exists():
            create_placeholder_background(background, duration=120.0)

    # Regenerate karaoke subtitles
    subtitle_dir = media_dir / "subtitles"
    subtitle_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    subtitle_path = subtitle_dir / f"content_{cid}_subs_{ts}.ass"
    subtitle_gen.generate_from_audio(
        audio_path=audio_path,
        text=content["script"],
        output_path=subtitle_path,
        niche_id=niche_id,
    )

    # Extract part info
    import re
    part_number, total_parts = 0, 0
    title = content["title"] or ""
    match = re.search(r'Part\s+(\d+)(?:\s*/\s*(\d+))?', title, re.IGNORECASE)
    if match:
        part_number = int(match.group(1))
        total_parts = int(match.group(2)) if match.group(2) else 3

    # Get hook and subreddit from content
    hook_text = content["hook"] or ""
    # Try to extract subreddit from scene_descriptions or title
    subreddit = "AskReddit"
    try:
        scenes = json.loads(content["scene_descriptions"])
        if isinstance(scenes, dict):
            subreddit = scenes.get("subreddit", "AskReddit")
    except (json.JSONDecodeError, TypeError):
        pass

    # Add part label to subreddit display if multi-part
    subreddit_display = f"r/{subreddit}"
    if part_number > 0:
        subreddit_display += f" \u2022 Part {part_number}"

    # Compose with all upgrades
    output_dir = media_dir / "rendered"
    output_path = output_dir / f"content_{cid}_master_{ts}.mp4"

    master = await compose_gameplay_video(
        background_video=background,
        audio_path=audio_path,
        music_path=music_path,
        subtitle_path=subtitle_path,
        output_path=output_path,
        target_duration=audio_duration,
        hook_text=hook_text,
        subreddit=subreddit_display,
        resolution=(
            config.get("video.resolution.width", 1080),
            config.get("video.resolution.height", 1920),
        ),
        fps=config.get("video.fps", 30),
        music_volume=niche_config.get("music_volume", 0.30),
        niche_id=niche_id,
        part_number=part_number,
        total_parts=total_parts,
    )

    # Loudness normalization
    normalized_path = output_path.with_name(output_path.stem + "_loud.mp4")
    await run_ffmpeg([
        "-i", str(master),
        "-c:v", "copy",
        "-af", "loudnorm=I=-14:TP=-1:LRA=11",
        str(normalized_path),
    ])
    normalized_path.replace(master)

    # Create platform variants
    variant_paths = await variator.create_variants(master, cid)

    # Update DB
    conn = sqlite3.connect(str(config.root / "data" / "gold.db"))
    cur = conn.cursor()
    cur.execute("UPDATE content SET master_video_path = ? WHERE id = ?", (str(master), cid))
    for platform, path in variant_paths.items():
        cur.execute(
            "UPDATE content_variant SET video_path = ? WHERE content_id = ? AND platform = ?",
            (str(path), cid, platform),
        )
    conn.commit()
    conn.close()

    logger.info("[#%d] GAMEPLAY re-render DONE: %s", cid, master.name)
    return True


async def rerender_stock_footage(
    content: dict,
    config: Config,
    subtitle_gen: SubtitleGenerator,
    variator: PlatformVariator,
) -> bool:
    """Re-render a stock_footage-style video via Remotion."""
    from gold.pipeline.emoji_beats import detect_emoji_beats
    from gold.utils.ffmpeg import build_visual_treatment_filter, get_duration, run_ffmpeg
    from gold.utils.remotion_renderer import render_stock_video
    from gold.utils.sound_design import build_sfx_filter_chain

    cid = content["id"]
    niche_id = content["niche"]
    niche_config = config.niches.get(niche_id, {})
    media_dir = config.media_dir

    # Find existing voiceover
    audio_path = find_voiceover(cid, media_dir)
    if not audio_path:
        logger.error("[#%d] NO VOICEOVER FOUND — skipping", cid)
        return False

    audio_duration = await get_duration(audio_path)

    # Find existing stock clips
    clips_dir = media_dir / "clips"
    stock_clips = sorted(clips_dir.glob(f"content_{cid}_stock_*"))
    if not stock_clips:
        logger.error("[#%d] NO STOCK CLIPS FOUND — skipping", cid)
        return False

    # Get clip durations
    clip_durations = []
    for clip in stock_clips:
        try:
            dur = await get_duration(clip)
            clip_durations.append(dur)
        except Exception:
            clip_durations.append(7.0)

    # Parse scene descriptions for text overlays
    text_overlays = []
    try:
        scenes = json.loads(content["scene_descriptions"])
        if isinstance(scenes, list):
            text_overlays = [s.get("text_overlay", "") if isinstance(s, dict) else "" for s in scenes]
    except (json.JSONDecodeError, TypeError):
        pass
    # Pad to match clip count
    while len(text_overlays) < len(stock_clips):
        text_overlays.append("")

    # Regenerate word timestamps for Remotion subtitles
    subtitle_words = subtitle_gen.get_word_timestamps(audio_path)

    # Find music
    music_path = find_music(cid, media_dir, niche_id)

    # Visual config
    visual_config = niche_config.get("visual", {})
    crossfade_dur = visual_config.get("transition_duration", 0.5)
    accent_color = visual_config.get("accent_color", "#0ea5e9")
    hook_text = content["hook"] or ""

    # Part info
    import re
    part_number, total_parts = 0, 0
    title = content["title"] or ""
    match = re.search(r'Part\s+(\d+)(?:\s*/\s*(\d+))?', title, re.IGNORECASE)
    if match:
        part_number = int(match.group(1))
        total_parts = int(match.group(2)) if match.group(2) else 3

    # Emoji beats
    voiceover_script = content["script"] or ""
    emoji_beats = detect_emoji_beats(voiceover_script, subtitle_words)

    # Render via Remotion
    ts = time.strftime("%Y%m%d_%H%M%S")
    output_dir = media_dir / "rendered"
    output_path = output_dir / f"content_{cid}_master_{ts}.mp4"

    await render_stock_video(
        clip_paths=stock_clips,
        clip_durations=clip_durations,
        text_overlays=text_overlays,
        voiceover_path=audio_path,
        music_path=music_path,
        subtitle_words=subtitle_words,
        output_path=output_path,
        total_duration=audio_duration,
        niche_id=niche_id,
        accent_color=accent_color,
        hook_text=hook_text,
        music_volume=niche_config.get("music_volume", 0.6),
        crossfade_duration=crossfade_dur,
        part_number=part_number,
        total_parts=total_parts,
        emoji_beats=emoji_beats,
    )

    # Post-process: visual treatments
    treatment_filter = build_visual_treatment_filter(visual_config)
    if treatment_filter:
        treated_path = output_path.with_name(output_path.stem + "_treated.mp4")
        await run_ffmpeg([
            "-i", str(output_path),
            "-vf", treatment_filter,
            "-c:a", "copy",
            "-c:v", "libx264", "-crf", "20", "-preset", "medium",
            "-maxrate", "4M", "-bufsize", "8M",
            str(treated_path),
        ])
        treated_path.replace(output_path)

    # SFX overlay
    scene_timestamps = [sum(clip_durations[:i]) for i in range(len(clip_durations))]
    sfx_inputs, sfx_filters, sfx_label = build_sfx_filter_chain(
        niche_id, scene_timestamps, audio_duration,
    )
    if sfx_inputs and sfx_label:
        sfx_path = output_path.with_name(output_path.stem + "_sfx.mp4")
        filter_str = ";".join(sfx_filters + [
            f"[0:a][{sfx_label}]amix=inputs=2:duration=first:normalize=0[aout]"
        ])
        await run_ffmpeg(
            ["-i", str(output_path)] + sfx_inputs +
            ["-filter_complex", filter_str, "-map", "0:v", "-map", "[aout]",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             str(sfx_path)],
        )
        sfx_path.replace(output_path)

    # Create platform variants
    variant_paths = await variator.create_variants(output_path, cid)

    # Update DB
    conn = sqlite3.connect(str(config.root / "data" / "gold.db"))
    cur = conn.cursor()
    cur.execute("UPDATE content SET master_video_path = ? WHERE id = ?", (str(output_path), cid))
    for platform, path in variant_paths.items():
        cur.execute(
            "UPDATE content_variant SET video_path = ? WHERE content_id = ? AND platform = ?",
            (str(path), cid, platform),
        )
    conn.commit()
    conn.close()

    logger.info("[#%d] STOCK_FOOTAGE re-render DONE: %s", cid, output_path.name)
    return True


async def main():
    config = Config()
    db_path = config.root / "data" / "gold.db"
    init_sync_db(f"sqlite:///{db_path}")
    create_tables_sync()

    subtitle_gen = SubtitleGenerator()
    variator = PlatformVariator(config)

    contents = get_content_to_rerender(db_path)
    logger.info("=" * 60)
    logger.info("RE-RENDER: %d videos with current upgrades", len(contents))
    logger.info("=" * 60)

    gameplay_items = [c for c in contents if c["niche"] in GAMEPLAY_NICHES]
    stock_items = [c for c in contents if c["niche"] in STOCK_NICHES]

    logger.info("  Gameplay (FFmpeg): %d videos", len(gameplay_items))
    logger.info("  Stock footage (Remotion): %d videos", len(stock_items))
    logger.info("")

    results = {"ok": [], "fail": []}

    # Process gameplay videos first (faster — FFmpeg only)
    for content in gameplay_items:
        cid = content["id"]
        logger.info("")
        logger.info("=" * 50)
        logger.info("RE-RENDER #%d [%s] (gameplay)", cid, content["niche"])
        logger.info("=" * 50)
        try:
            ok = await rerender_gameplay(content, config, subtitle_gen, variator)
            results["ok" if ok else "fail"].append(cid)
        except Exception as e:
            logger.error("[#%d] FAILED: %s", cid, str(e)[:300])
            results["fail"].append(cid)

    # Process stock footage videos (slower — Remotion)
    for content in stock_items:
        cid = content["id"]
        logger.info("")
        logger.info("=" * 50)
        logger.info("RE-RENDER #%d [%s] (stock_footage)", cid, content["niche"])
        logger.info("=" * 50)
        try:
            ok = await rerender_stock_footage(content, config, subtitle_gen, variator)
            results["ok" if ok else "fail"].append(cid)
        except Exception as e:
            logger.error("[#%d] FAILED: %s", cid, str(e)[:300])
            results["fail"].append(cid)

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("RE-RENDER COMPLETE")
    logger.info("=" * 60)
    logger.info("  Success: %d", len(results["ok"]))
    logger.info("  Failed:  %d", len(results["fail"]))
    if results["fail"]:
        logger.info("  Failed IDs: %s", results["fail"])


if __name__ == "__main__":
    asyncio.run(main())
