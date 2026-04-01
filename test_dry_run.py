"""Dry-run test: generate 1 video per active niche through the full pipeline.

Pipeline v6: 3 styles across 6 niches:
  - reddit_stories:    gameplay background + voiceover + Whisper-timed subtitles
  - personal_finance:  Pexels stock footage + crossfade + voiceover + subtitles + music
  - ai_tools:          Pexels stock footage + crossfade + voiceover + subtitles + music
  - true_crime:        Pexels stock footage + crossfade + voiceover + subtitles + music
  - betrayal_revenge:  gameplay background + voiceover + Whisper-timed subtitles
  - english_learning:  Pexels stock footage + crossfade + voiceover + subtitles + music
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / "secrets" / ".env")

from gold.config import Config
from gold.models import *
from gold.models.db import init_sync_db, create_tables_sync
from gold.pipeline.ideation import IdeaGenerator
from gold.pipeline.scripting import ScriptWriter
from gold.pipeline.media import MediaProducer
from gold.pipeline.audio import AudioProducer
from gold.pipeline.subtitles import SubtitleGenerator
from gold.utils.ffmpeg import (
    run_ffmpeg, get_duration, apply_ken_burns,
    compose_gameplay_video, compose_slides_video, compose_clips_video,
    compose_asmr_video, compose_stock_video,
)
from gold.utils.stock_footage import get_stock_clip_for_scene
from gold.utils.remotion_renderer import render_stock_video
from gold.utils.backgrounds import build_background_montage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# FFmpeg path fix for this session
FFMPEG_DIR = r"C:\Users\claws\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

ALL_NICHES = ["reddit_stories", "ai_tools", "personal_finance", "true_crime", "betrayal_revenge", "english_learning"]
# Support running specific niches via CLI: python test_dry_run.py reddit_stories personal_finance
LAUNCH_NICHES = [n for n in sys.argv[1:] if n in ALL_NICHES] or ALL_NICHES


def save_prompts(prompt_log: list[dict], output_path: Path) -> None:
    """Save all prompts and responses to a readable text file for review."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("GOLD DRY RUN v3 - MULTI-STYLE PIPELINE\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")

        for entry in prompt_log:
            f.write("-" * 60 + "\n")
            f.write(f"NICHE: {entry.get('niche', 'unknown')}\n")
            f.write(f"STEP:  {entry.get('step', 'unknown')}\n")
            f.write("-" * 60 + "\n\n")
            f.write("PROMPT:\n")
            f.write(entry.get("prompt", "(no prompt)") + "\n\n")
            if entry.get("response"):
                f.write("RESPONSE:\n")
                resp = entry["response"]
                if isinstance(resp, dict):
                    f.write(json.dumps(resp, indent=2, ensure_ascii=False) + "\n")
                else:
                    f.write(str(resp) + "\n")
            f.write("\n\n")

    logger.info("Prompts saved to %s", output_path)


async def ensure_background_video(config: Config) -> Path:
    """Build a montage from multiple random background clips for visual variety.

    Picks clips from the 'mixed' pool (gameplay, satisfying, cooking, nature, crafts),
    shuffles them, and concatenates into one long background video. No clip repeats.
    Falls back to a placeholder if no clips exist.
    """
    bg_dir = Path("data/backgrounds")
    bg_dir.mkdir(parents=True, exist_ok=True)

    # Check if ANY background videos exist across all categories
    all_videos = []
    for cat in ("gameplay", "satisfying", "cooking", "nature", "crafts"):
        cat_dir = bg_dir / cat
        if cat_dir.exists():
            all_videos.extend(cat_dir.glob("*.mp4"))

    if all_videos:
        logger.info("Found %d total background videos, building montage...", len(all_videos))
        montage_path = bg_dir / "_montages" / "dry_run_montage.mp4"
        return await build_background_montage(
            target_duration=180.0,  # plenty of buffer for voiceover
            category="mixed",
            output_path=montage_path,
            resolution=(1080, 1920),
            fps=30,
        )

    # Create a dark animated placeholder for testing
    logger.info("No background videos found. Creating test placeholder...")
    gameplay_dir = bg_dir / "gameplay"
    gameplay_dir.mkdir(parents=True, exist_ok=True)
    placeholder = gameplay_dir / "test_placeholder.mp4"

    w, h = 1080, 1920
    args = [
        "-f", "lavfi",
        "-i", (
            f"color=c=0x0a0a2e:s={w}x{h}:d=120,"
            f"drawtext=fontfile=/Windows/Fonts/arial.ttf:"
            f"text='GAMEPLAY BACKGROUND':"
            f"fontcolor=0x333355:fontsize=40:"
            f"x=(w-text_w)/2:y=(h-text_h)/2"
        ),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-pix_fmt", "yuv420p",
        "-t", "120",
        "-y", str(placeholder),
    ]
    await run_ffmpeg(args, timeout=60)
    logger.info("Created placeholder background: %s", placeholder)
    return placeholder


async def test_gameplay_niche(config, niche_id, niche_config, idea, script, prompt_log, ts, background):
    """Pipeline for gameplay-background niches (reddit_stories, betrayal_revenge)."""
    result_steps = {}
    voiceover_text = script.get("voiceover_script", "")

    # Voiceover
    audio_path = None
    audio_duration = None
    subtitle_path = None
    if voiceover_text:
        logger.info("[%s] STEP 4a: Generating voiceover...", niche_id)
        audio = AudioProducer(config)
        # Allow niche engine to override voice_id (e.g. betrayal_revenge gender detection)
        voice_id = script.get("_voice_id_override") or niche_config.get("voice", {}).get("voice_id", "pNInz6obpgDQGcFmaJgB")
        audio_path = await audio.generate_voiceover(
            text=voiceover_text,
            voice_id=voice_id,
            output_name=f"test_{niche_id}_vo_{ts}",
            provider=niche_config.get("voice", {}).get("provider", "elevenlabs"),
            speed=niche_config.get("voice", {}).get("speed"),
        )
        audio_duration = await get_duration(audio_path)
        result_steps["voiceover"] = {
            "path": str(audio_path),
            "size_kb": round(audio_path.stat().st_size / 1024, 1),
            "duration_s": round(audio_duration, 1),
        }
        logger.info("[%s] Voiceover: %.1fs", niche_id, audio_duration)

        # Whisper-timed subtitles
        logger.info("[%s] STEP 4b: Generating Whisper-timed subtitles...", niche_id)
        sub_gen = SubtitleGenerator()
        subtitle_dir = config.media_dir / "subtitles"
        subtitle_dir.mkdir(parents=True, exist_ok=True)
        subtitle_path = subtitle_dir / f"test_{niche_id}_subs_{ts}.ass"
        sub_gen.generate_from_audio(
            audio_path=audio_path,
            text=voiceover_text,
            output_path=subtitle_path,
        )
        result_steps["subtitles"] = {"path": str(subtitle_path)}
        logger.info("[%s] Subtitles: %s", niche_id, subtitle_path.name)

    # Background music
    audio_prod = AudioProducer(config)
    music_path = await audio_prod.get_context_music(script, niche_config)

    # Compose — pass explicit duration so background loops to fill voiceover
    logger.info("[%s] STEP 5: Composing gameplay video...", niche_id)
    output_dir = config.media_dir / "videos"
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / f"test_{niche_id}_final_{ts}.mp4"

    # Hook text for the opening card
    hook_text = script.get("hook_text", "") or idea.get("hook", "")

    await compose_gameplay_video(
        background_video=background,
        audio_path=audio_path,
        music_path=music_path,
        subtitle_path=subtitle_path,
        output_path=final_path,
        target_duration=audio_duration if audio_path else None,
        hook_text=hook_text,
        resolution=(1080, 1920),
        fps=30,
        music_volume=niche_config.get("music_volume", 0.35),
    )

    return final_path, result_steps


async def test_slides_niche(config, niche_id, niche_config, idea, script, prompt_log, ts):
    """Pipeline for text-slides niches (personal_finance)."""
    result_steps = {}
    voiceover_text = script.get("voiceover_script", "")

    # Get slide texts
    slide_texts = script.get("slide_texts", [])
    if not slide_texts:
        voiceover = voiceover_text or ""
        sentences = [s.strip() for s in voiceover.replace("!", ".").replace("?", ".").split(".") if s.strip()]
        step = max(1, len(sentences) // 8)
        slide_texts = [s[:60] for s in sentences[::step]][:10]
        if not slide_texts:
            slide_texts = ["CRYPTO UPDATE"]
    result_steps["slides"] = {"count": len(slide_texts), "texts": slide_texts}
    logger.info("[%s] Slides: %d texts", niche_id, len(slide_texts))

    # Voiceover
    audio_path = None
    audio_duration = None
    subtitle_path = None
    if voiceover_text:
        logger.info("[%s] STEP 4a: Generating voiceover...", niche_id)
        audio = AudioProducer(config)
        voice_id = niche_config.get("voice", {}).get("voice_id", "pNInz6obpgDQGcFmaJgB")
        audio_path = await audio.generate_voiceover(
            text=voiceover_text,
            voice_id=voice_id,
            output_name=f"test_{niche_id}_vo_{ts}",
            provider=niche_config.get("voice", {}).get("provider", "elevenlabs"),
            speed=niche_config.get("voice", {}).get("speed"),
        )
        audio_duration = await get_duration(audio_path)
        result_steps["voiceover"] = {
            "path": str(audio_path),
            "size_kb": round(audio_path.stat().st_size / 1024, 1),
            "duration_s": round(audio_duration, 1),
        }
        logger.info("[%s] Voiceover: %.1fs", niche_id, audio_duration)

        # Whisper-timed subtitles
        logger.info("[%s] STEP 4b: Generating Whisper-timed subtitles...", niche_id)
        sub_gen = SubtitleGenerator()
        subtitle_dir = config.media_dir / "subtitles"
        subtitle_dir.mkdir(parents=True, exist_ok=True)
        subtitle_path = subtitle_dir / f"test_{niche_id}_subs_{ts}.ass"
        sub_gen.generate_from_audio(
            audio_path=audio_path,
            text=voiceover_text,
            output_path=subtitle_path,
        )
        result_steps["subtitles"] = {"path": str(subtitle_path)}
        logger.info("[%s] Subtitles: %s", niche_id, subtitle_path.name)

    # Background music
    audio_prod = AudioProducer(config)
    music_path = await audio_prod.get_context_music(script, niche_config)

    # Compose slides video
    logger.info("[%s] STEP 5: Composing slides video...", niche_id)
    output_dir = config.media_dir / "videos"
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / f"test_{niche_id}_final_{ts}.mp4"

    await compose_slides_video(
        slide_texts=slide_texts,
        audio_path=audio_path,
        music_path=music_path,
        subtitle_path=subtitle_path,
        output_path=final_path,
        audio_duration=audio_duration,
        resolution=(1080, 1920),
        fps=30,
    )

    return final_path, result_steps


async def test_image_to_video_niche(config, niche_id, niche_config, idea, script, prompt_log, ts):
    """Pipeline for Flux images + i2v model + ambient audio (asmr_satisfying)."""
    result_steps = {}

    scenes_data = script.get("scenes", [])
    if not scenes_data:
        raise RuntimeError("Script has no 'scenes' array for image_to_video style")

    # Determine i2v model
    i2v_model = niche_config.get("i2v_model") or None
    media = MediaProducer(config)
    i2v_name = i2v_model or media.i2v_model

    # Cost estimation
    cost_per_sec = 0.01 if "minimax" in i2v_name else 0.029
    total_scene_seconds = sum(float(s.get("duration", 7)) for s in scenes_data)
    estimated_cost = (len(scenes_data) * 0.015) + (total_scene_seconds * cost_per_sec) + 0.02
    logger.info(
        "[%s] Estimated cost: $%.3f (%d scenes × %s, %.0fs total)",
        niche_id, estimated_cost, len(scenes_data), i2v_name.split("/")[-1], total_scene_seconds,
    )

    logger.info("[%s] STEP 3: Generating %d AI video clips from images...", niche_id, len(scenes_data))

    clip_paths = []
    text_overlays = []

    for i, scene in enumerate(scenes_data):
        image_prompt = scene.get("image_prompt", "")
        if not image_prompt:
            continue

        motion_prompt = scene.get("motion_prompt", "")
        text_overlay = scene.get("text_overlay", "")
        duration = str(scene.get("duration", "7"))

        logger.info(
            "[%s] Scene %d/%d: Generating image + video...",
            niche_id, i + 1, len(scenes_data),
        )

        # Generate Flux image (keep URL for image-to-video)
        img_path, img_url = await media.generate_image(
            prompt=image_prompt,
            output_name=f"test_{niche_id}_scene_{i}_{ts}",
            width=1080, height=1920,
            return_url=True,
        )

        # Animate image to video via configurable i2v model
        logger.info("[%s] Scene %d/%d: Animating to video (%s)...", niche_id, i + 1, len(scenes_data), i2v_name.split("/")[-1])
        clip_path = await media.generate_video_from_image(
            image_url=img_url,
            prompt=motion_prompt,
            output_name=f"test_{niche_id}_clip_{i}_{ts}",
            duration=duration,
            aspect_ratio="9:16",
            i2v_model=i2v_model,
        )
        clip_paths.append(clip_path)
        text_overlays.append(text_overlay)

    if not clip_paths:
        raise RuntimeError("No video clips were generated")

    result_steps["scenes"] = {"count": len(clip_paths)}

    # Generate ONE continuous ambient sound track (instead of per-scene SFX)
    ambient_desc = script.get("ambient_description", "")
    ambient_path = None
    if ambient_desc:
        logger.info("[%s] STEP 4a: Generating continuous ambient track...", niche_id)
        try:
            ambient_duration = min(22.0, max(15.0, total_scene_seconds))
            ambient_path = await media.generate_sound_effect(
                prompt=ambient_desc,
                output_name=f"test_{niche_id}_ambient_{ts}",
                duration=ambient_duration,
            )
        except Exception as e:
            logger.warning("[%s] Ambient sound generation failed: %s", niche_id, e)
    else:
        # Fallback: try per-scene ambient_sound or sound_effect from first scene
        first_sound = (
            scenes_data[0].get("ambient_sound", "")
            or scenes_data[0].get("sound_effect", "")
        )
        if first_sound:
            try:
                ambient_duration = min(22.0, max(15.0, total_scene_seconds))
                ambient_path = await media.generate_sound_effect(
                    prompt=first_sound,
                    output_name=f"test_{niche_id}_ambient_{ts}",
                    duration=ambient_duration,
                )
            except Exception as e:
                logger.warning("[%s] Fallback ambient generation failed: %s", niche_id, e)

    sfx_paths = [ambient_path] + [None] * (len(clip_paths) - 1)
    logger.info("[%s] Generated %d video clips, ambient=%s", niche_id, len(clip_paths), bool(ambient_path))

    # Background music
    logger.info("[%s] STEP 4b: Getting background music...", niche_id)
    audio_prod = AudioProducer(config)
    music_path = await audio_prod.get_context_music(script, niche_config)

    # Compose ASMR video (clips + ambient + text overlays + music)
    logger.info("[%s] STEP 5: Composing ASMR video...", niche_id)
    output_dir = config.media_dir / "videos"
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / f"test_{niche_id}_final_{ts}.mp4"

    await compose_asmr_video(
        clip_paths=clip_paths,
        sfx_paths=sfx_paths,
        text_overlays=text_overlays,
        music_path=music_path,
        output_path=final_path,
        resolution=(1080, 1920),
        fps=30,
    )

    return final_path, result_steps


async def test_infographic_niche(config, niche_id, niche_config, idea, script, prompt_log, ts):
    """Pipeline for Flux infographic images + Ken Burns + voiceover + subtitles.

    VOICEOVER-FIRST: generates audio first, then scales scene durations to match.
    """
    result_steps = {}

    scenes_data = script.get("scenes", [])
    if not scenes_data:
        raise RuntimeError("Script has no 'scenes' array for infographic style")

    voiceover_text = script.get("voiceover_script", "")

    # --- VOICEOVER FIRST (so we know exact duration to fill) ---
    audio_path = None
    audio_duration = None
    subtitle_path = None
    if voiceover_text:
        logger.info("[%s] STEP 3a: Generating voiceover FIRST...", niche_id)
        audio = AudioProducer(config)
        # Allow niche engine to override voice_id (e.g. true_crime gender detection)
        voice_id = script.get("_voice_id_override") or niche_config.get("voice", {}).get("voice_id", "pNInz6obpgDQGcFmaJgB")
        audio_path = await audio.generate_voiceover(
            text=voiceover_text,
            voice_id=voice_id,
            output_name=f"test_{niche_id}_vo_{ts}",
            provider=niche_config.get("voice", {}).get("provider", "elevenlabs"),
            speed=niche_config.get("voice", {}).get("speed"),
        )
        audio_duration = await get_duration(audio_path)
        result_steps["voiceover"] = {
            "path": str(audio_path),
            "size_kb": round(audio_path.stat().st_size / 1024, 1),
            "duration_s": round(audio_duration, 1),
        }
        logger.info("[%s] Voiceover: %.1fs", niche_id, audio_duration)

    # --- SCALE SCENE DURATIONS to match voiceover ---
    raw_total = sum(float(s.get("duration", 7)) for s in scenes_data)
    if audio_duration and raw_total > 0:
        target_total = audio_duration + 1.0
        scale_factor = target_total / raw_total
        for scene in scenes_data:
            orig = float(scene.get("duration", 7))
            scene["duration"] = round(orig * scale_factor, 1)
        new_total = sum(float(s["duration"]) for s in scenes_data)
        logger.info(
            "[%s] Scaled scene durations: %.1fs -> %.1fs (voiceover: %.1fs)",
            niche_id, raw_total, new_total, audio_duration,
        )

    # --- GENERATE IMAGES + KEN BURNS ---
    logger.info("[%s] STEP 3b: Generating %d infographic images...", niche_id, len(scenes_data))

    media = MediaProducer(config)
    ken_burns_clips = []
    text_overlays = []

    for i, scene in enumerate(scenes_data):
        image_prompt = scene.get("image_prompt", "")
        if not image_prompt:
            continue

        duration = float(scene.get("duration", 7))
        effect = scene.get("ken_burns", "zoom_in")
        text_overlay = scene.get("text_overlay", "")

        logger.info("[%s] Scene %d/%d: Generating infographic...", niche_id, i + 1, len(scenes_data))
        img_path = await media.generate_image(
            prompt=image_prompt,
            output_name=f"test_{niche_id}_infographic_{i}_{ts}",
            width=1080, height=1920,
        )

        # Apply Ken Burns
        logger.info("[%s] Scene %d/%d: Applying Ken Burns (%s, %.1fs)...", niche_id, i + 1, len(scenes_data), effect, duration)
        clip_path = config.media_dir / "clips" / f"test_{niche_id}_kb_{i}_{ts}.mp4"
        clip_path.parent.mkdir(parents=True, exist_ok=True)
        await apply_ken_burns(
            image_path=img_path, output_path=clip_path,
            duration=duration, effect=effect,
            resolution=(1080, 1920), fps=30,
        )
        ken_burns_clips.append(clip_path)
        text_overlays.append(text_overlay)

    if not ken_burns_clips:
        raise RuntimeError("No infographic clips generated")

    result_steps["scenes"] = {"count": len(ken_burns_clips)}
    logger.info("[%s] Generated %d Ken Burns clips from infographics", niche_id, len(ken_burns_clips))

    # --- SUBTITLES ---
    if voiceover_text and audio_path:
        logger.info("[%s] STEP 4: Generating Whisper-timed subtitles...", niche_id)
        sub_gen = SubtitleGenerator()
        subtitle_dir = config.media_dir / "subtitles"
        subtitle_dir.mkdir(parents=True, exist_ok=True)
        subtitle_path = subtitle_dir / f"test_{niche_id}_subs_{ts}.ass"
        sub_gen.generate_from_audio(
            audio_path=audio_path,
            text=voiceover_text,
            output_path=subtitle_path,
        )
        result_steps["subtitles"] = {"path": str(subtitle_path)}

    # Background music
    audio_prod = AudioProducer(config)
    music_path = await audio_prod.get_context_music(script, niche_config)

    # --- COMPOSE: clips + voiceover + subtitles + music ---
    logger.info("[%s] STEP 5: Composing infographic video...", niche_id)
    output_dir = config.media_dir / "videos"
    output_dir.mkdir(parents=True, exist_ok=True)

    if audio_path or subtitle_path:
        # First compose clips into silent video
        silent_path = output_dir / f"test_{niche_id}_silent_{ts}.mp4"
        await compose_clips_video(
            clip_paths=ken_burns_clips,
            text_overlays=text_overlays,
            music_path=None,
            output_path=silent_path,
            resolution=(1080, 1920),
            fps=30,
        )
        # Then add voiceover + subtitles + music using gameplay compose
        final_path = output_dir / f"test_{niche_id}_final_{ts}.mp4"
        await compose_gameplay_video(
            background_video=silent_path,
            audio_path=audio_path,
            music_path=music_path,
            subtitle_path=subtitle_path,
            output_path=final_path,
            target_duration=audio_duration,
            resolution=(1080, 1920),
            fps=30,
        )
    else:
        final_path = output_dir / f"test_{niche_id}_final_{ts}.mp4"
        await compose_clips_video(
            clip_paths=ken_burns_clips,
            text_overlays=text_overlays,
            music_path=music_path,
            output_path=final_path,
            resolution=(1080, 1920),
            fps=30,
        )

    return final_path, result_steps


async def test_cinematic_doc_niche(config, niche_id, niche_config, idea, script, prompt_log, ts):
    """Pipeline for long-form cinematic doc: voiceover FIRST → Pexels + AI clips → compose."""
    result_steps = {}

    scenes_data = script.get("scenes", [])
    if not scenes_data:
        raise RuntimeError("Script has no 'scenes' array for cinematic_doc style")

    voiceover_text = script.get("voiceover_script", "")
    word_count = len(voiceover_text.split()) if voiceover_text else 0
    logger.info("[%s] Long-form script: %d words, %d scenes, %d chapters",
                niche_id, word_count, len(scenes_data), len(script.get("chapters", [])))

    # Log chapters
    for ch in script.get("chapters", []):
        logger.info("[%s]   Chapter: %s @ %s", niche_id, ch.get("title"), ch.get("approximate_timestamp"))

    # Log shorts_hooks
    for sh in script.get("shorts_hooks", []):
        logger.info("[%s]   Short: '%s' (scenes %s)", niche_id, sh.get("hook_text"), sh.get("scene_range"))

    # --- VOICEOVER FIRST ---
    audio_path = None
    audio_duration = None
    subtitle_path = None
    if voiceover_text:
        logger.info("[%s] STEP 3a: Generating voiceover FIRST (long-form, %d words)...", niche_id, word_count)
        audio = AudioProducer(config)
        voice_id = script.get("_voice_id_override") or niche_config.get("voice", {}).get("voice_id", "pNInz6obpgDQGcFmaJgB")
        audio_path = await audio.generate_voiceover(
            text=voiceover_text,
            voice_id=voice_id,
            output_name=f"test_{niche_id}_vo_{ts}",
            provider=niche_config.get("voice", {}).get("provider", "elevenlabs"),
            speed=niche_config.get("voice", {}).get("speed"),
        )
        audio_duration = await get_duration(audio_path)
        result_steps["voiceover"] = {
            "path": str(audio_path),
            "size_kb": round(audio_path.stat().st_size / 1024, 1),
            "duration_s": round(audio_duration, 1),
            "word_count": word_count,
        }
        logger.info("[%s] Voiceover: %.1fs (%.1f min)", niche_id, audio_duration, audio_duration / 60)

    # --- SCALE SCENE DURATIONS ---
    raw_total = sum(float(s.get("duration", 20)) for s in scenes_data)
    if audio_duration and raw_total > 0:
        target_total = audio_duration + 2.0
        scale_factor = target_total / raw_total
        for scene in scenes_data:
            orig = float(scene.get("duration", 20))
            scene["duration"] = round(orig * scale_factor, 1)
        new_total = sum(float(s["duration"]) for s in scenes_data)
        logger.info("[%s] Scaled scene durations: %.1fs -> %.1fs (voiceover: %.1fs)",
                    niche_id, raw_total, new_total, audio_duration)

    # --- FETCH STOCK CLIPS (with AI image fallback) ---
    logger.info("[%s] STEP 3b: Fetching %d clips (Pexels + AI fallback)...", niche_id, len(scenes_data))

    pexels_key = os.environ.get("PEXELS_API_KEY", "")
    clip_dir = config.media_dir / "clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = config.media_dir / "stock_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    media = MediaProducer(config)
    stock_clips = []
    text_overlays = []
    clip_durations = []
    pexels_hits = 0
    ai_fallbacks = 0

    for i, scene in enumerate(scenes_data):
        duration = float(scene.get("duration", 20))
        text_overlay = scene.get("text_overlay", "")
        search_query = scene.get("search_keywords", scene.get("image_prompt", "stock footage"))
        clip_path = clip_dir / f"test_{niche_id}_doc_{i}_{ts}.mp4"

        # Try Pexels first
        result = None
        if pexels_key:
            try:
                result = await get_stock_clip_for_scene(
                    query=search_query,
                    api_key=pexels_key,
                    output_path=clip_path,
                    target_duration=duration,
                    cache_dir=cache_dir,
                    resolution=(1080, 1920),
                )
                if result:
                    pexels_hits += 1
                    logger.info("[%s] Scene %d/%d: Pexels OK (%s, %.1fs)",
                                niche_id, i + 1, len(scenes_data), search_query, duration)
            except Exception as e:
                logger.warning("[%s] Scene %d Pexels failed: %s", niche_id, i + 1, e)

        # Fallback: AI image + Ken Burns (skip i2v for test to save cost)
        if result is None:
            ai_fallbacks += 1
            logger.info("[%s] Scene %d/%d: AI fallback → image + Ken Burns", niche_id, i + 1, len(scenes_data))
            image_prompt = scene.get("image_prompt", "abstract cinematic background, dark moody lighting")
            img_path = await media.generate_image(
                prompt=image_prompt,
                output_name=f"test_{niche_id}_doc_img_{i}_{ts}",
                width=1080, height=1920,
            )
            effect = scene.get("ken_burns", "zoom_in")
            await apply_ken_burns(
                image_path=img_path, output_path=clip_path,
                duration=duration, effect=effect,
                resolution=(1080, 1920), fps=30,
            )

        stock_clips.append(clip_path)
        text_overlays.append(text_overlay)
        clip_durations.append(duration)

    logger.info("[%s] Clips: %d Pexels, %d AI fallback", niche_id, pexels_hits, ai_fallbacks)
    result_steps["scenes"] = {
        "count": len(stock_clips),
        "pexels_hits": pexels_hits,
        "ai_fallbacks": ai_fallbacks,
    }

    # --- SUBTITLES ---
    if voiceover_text and audio_path:
        logger.info("[%s] STEP 4: Generating Whisper-timed subtitles...", niche_id)
        sub_gen = SubtitleGenerator()
        subtitle_dir = config.media_dir / "subtitles"
        subtitle_dir.mkdir(parents=True, exist_ok=True)
        subtitle_path = subtitle_dir / f"test_{niche_id}_subs_{ts}.ass"
        sub_gen.generate_from_audio(
            audio_path=audio_path,
            text=voiceover_text,
            output_path=subtitle_path,
        )
        result_steps["subtitles"] = {"path": str(subtitle_path)}

    # --- BACKGROUND MUSIC ---
    audio_prod = AudioProducer(config)
    music_path = await audio_prod.get_context_music(script, niche_config)

    # --- COMPOSE via Remotion ---
    logger.info("[%s] STEP 5: Composing cinematic doc video (%d clips)...", niche_id, len(stock_clips))
    output_dir = config.media_dir / "videos"
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / f"test_{niche_id}_final_{ts}.mp4"

    visual_config = niche_config.get("visual", {})
    crossfade_dur = visual_config.get("transition_duration", 0.5)

    hook_text = script.get("hook_text", "") or idea.get("hook", "")
    if hook_text:
        logger.info("[%s] Hook card: %s", niche_id, hook_text[:60])

    # Niche accent color
    accent_colors = {
        "personal_finance": "#22c55e",
        "ai_tools": "#3b82f6",
        "true_crime": "#ef4444",
        "english_learning": "#f59e0b",
    }

    # Use word timestamps for animated subtitles
    subtitle_words = []
    if voiceover_text and audio_path:
        sub_gen = SubtitleGenerator()
        subtitle_words = sub_gen.get_word_timestamps(audio_path)
        logger.info("[%s] Got %d word timestamps for Remotion", niche_id, len(subtitle_words))

    await render_stock_video(
        clip_paths=stock_clips,
        clip_durations=clip_durations,
        text_overlays=text_overlays,
        voiceover_path=audio_path,
        music_path=music_path,
        subtitle_words=subtitle_words,
        output_path=final_path,
        total_duration=audio_duration or sum(clip_durations),
        niche_id=niche_id,
        accent_color=accent_colors.get(niche_id, "#22c55e"),
        hook_text=hook_text,
        music_volume=niche_config.get("music_volume", 0.5),
        crossfade_duration=crossfade_dur,
        concurrency=4,
    )

    # Log chapter markers and shorts info
    chapters = script.get("chapters", [])
    if chapters:
        result_steps["chapters"] = chapters
        logger.info("[%s] YouTube chapters: %d", niche_id, len(chapters))

    shorts_hooks = script.get("shorts_hooks", [])
    if shorts_hooks:
        result_steps["shorts_hooks"] = len(shorts_hooks)
        logger.info("[%s] Shorts hooks: %d extractable", niche_id, len(shorts_hooks))

    return final_path, result_steps


async def test_stock_footage_niche(config, niche_id, niche_config, idea, script, prompt_log, ts):
    """Pipeline for Pexels stock footage + crossfade + voiceover + subtitles + music."""
    result_steps = {}

    scenes_data = script.get("scenes", [])
    if not scenes_data:
        raise RuntimeError("Script has no 'scenes' array for stock_footage style")

    voiceover_text = script.get("voiceover_script", "")

    # --- VOICEOVER FIRST ---
    audio_path = None
    audio_duration = None
    subtitle_path = None
    if voiceover_text:
        logger.info("[%s] STEP 3a: Generating voiceover FIRST...", niche_id)
        audio = AudioProducer(config)
        voice_id = script.get("_voice_id_override") or niche_config.get("voice", {}).get("voice_id", "pNInz6obpgDQGcFmaJgB")
        audio_path = await audio.generate_voiceover(
            text=voiceover_text,
            voice_id=voice_id,
            output_name=f"test_{niche_id}_vo_{ts}",
            provider=niche_config.get("voice", {}).get("provider", "elevenlabs"),
            speed=niche_config.get("voice", {}).get("speed"),
        )
        audio_duration = await get_duration(audio_path)
        result_steps["voiceover"] = {
            "path": str(audio_path),
            "size_kb": round(audio_path.stat().st_size / 1024, 1),
            "duration_s": round(audio_duration, 1),
        }
        logger.info("[%s] Voiceover: %.1fs", niche_id, audio_duration)

    # --- SCALE SCENE DURATIONS ---
    raw_total = sum(float(s.get("duration", 7)) for s in scenes_data)
    if audio_duration and raw_total > 0:
        target_total = audio_duration + 1.0
        scale_factor = target_total / raw_total
        for scene in scenes_data:
            orig = float(scene.get("duration", 7))
            scene["duration"] = round(orig * scale_factor, 1)
        new_total = sum(float(s["duration"]) for s in scenes_data)
        logger.info(
            "[%s] Scaled scene durations: %.1fs -> %.1fs (voiceover: %.1fs)",
            niche_id, raw_total, new_total, audio_duration,
        )

    # --- FETCH STOCK CLIPS ---
    logger.info("[%s] STEP 3b: Fetching %d stock clips from Pexels...", niche_id, len(scenes_data))

    pexels_key = os.environ.get("PEXELS_API_KEY", "")
    clip_dir = config.media_dir / "clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = config.media_dir / "stock_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    stock_clips = []
    text_overlays = []
    clip_durations = []

    for i, scene in enumerate(scenes_data):
        duration = float(scene.get("duration", 7))
        text_overlay = scene.get("text_overlay", "")
        search_query = scene.get("search_keywords", scene.get("image_prompt", "stock footage"))

        clip_path = clip_dir / f"test_{niche_id}_stock_{i}_{ts}.mp4"

        # Try Pexels first
        result = None
        if pexels_key:
            try:
                result = await get_stock_clip_for_scene(
                    query=search_query,
                    api_key=pexels_key,
                    output_path=clip_path,
                    target_duration=duration,
                    cache_dir=cache_dir,
                    resolution=(1080, 1920),
                )
                if result:
                    logger.info("[%s] Scene %d/%d: Pexels clip OK (%s)", niche_id, i + 1, len(scenes_data), search_query)
            except Exception as e:
                logger.warning("[%s] Scene %d Pexels failed: %s", niche_id, i + 1, e)

        # Fallback to AI image + Ken Burns
        if result is None:
            logger.info("[%s] Scene %d/%d: Fallback → AI image + Ken Burns", niche_id, i + 1, len(scenes_data))
            media = MediaProducer(config)
            image_prompt = scene.get("image_prompt", "abstract technology background")
            img_path = await media.generate_image(
                prompt=image_prompt,
                output_name=f"test_{niche_id}_fallback_{i}_{ts}",
                width=1080, height=1920,
            )
            effect = scene.get("ken_burns", "zoom_in")
            await apply_ken_burns(
                image_path=img_path, output_path=clip_path,
                duration=duration, effect=effect,
                resolution=(1080, 1920), fps=30,
            )

        stock_clips.append(clip_path)
        text_overlays.append(text_overlay)
        clip_durations.append(duration)

    if not stock_clips:
        raise RuntimeError("No stock clips produced")

    result_steps["scenes"] = {"count": len(stock_clips)}
    logger.info("[%s] Prepared %d clips for composition", niche_id, len(stock_clips))

    # --- WORD TIMESTAMPS for Remotion ---
    subtitle_words = []
    if voiceover_text and audio_path:
        logger.info("[%s] STEP 4: Extracting word timestamps via Whisper...", niche_id)
        sub_gen = SubtitleGenerator()
        subtitle_words = sub_gen.get_word_timestamps(audio_path)
        result_steps["subtitles"] = {"word_count": len(subtitle_words)}
        logger.info("[%s] Got %d word timestamps", niche_id, len(subtitle_words))

    # --- BACKGROUND MUSIC ---
    audio_prod = AudioProducer(config)
    music_path = await audio_prod.get_context_music(script, niche_config)

    # --- COMPOSE via REMOTION ---
    logger.info("[%s] STEP 5: Rendering via Remotion (animated captions + transitions)...", niche_id)
    output_dir = config.media_dir / "videos"
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / f"test_{niche_id}_final_{ts}.mp4"

    visual_config = niche_config.get("visual", {})
    crossfade_dur = visual_config.get("transition_duration", 0.5)

    # Niche-specific accent colors
    accent_colors = {
        "personal_finance": "#22c55e",
        "ai_tools": "#3b82f6",
        "true_crime": "#ef4444",
        "english_learning": "#f59e0b",
    }

    # Hook text for the opening card
    hook_text = script.get("hook_text", "") or idea.get("hook", "")
    if hook_text:
        logger.info("[%s] Hook card: %s", niche_id, hook_text[:60])

    await render_stock_video(
        clip_paths=stock_clips,
        clip_durations=clip_durations,
        text_overlays=text_overlays,
        voiceover_path=audio_path,
        music_path=music_path,
        subtitle_words=subtitle_words,
        output_path=final_path,
        total_duration=audio_duration or sum(clip_durations),
        niche_id=niche_id,
        accent_color=accent_colors.get(niche_id, "#0ea5e9"),
        hook_text=hook_text,
        music_volume=niche_config.get("music_volume", 0.6),
        crossfade_duration=crossfade_dur,
        concurrency=1,
    )

    return final_path, result_steps


async def test_niche(config: Config, niche_id: str, prompt_log: list[dict], background: Path) -> dict:
    """Run the full pipeline for a single niche, routing to the correct video style."""
    niche_config = config.niches[niche_id]
    video_style = niche_config.get("video_style", "gameplay")
    ts = int(time.time())
    result: dict = {"niche": niche_id, "video_style": video_style, "steps": {}, "success": False}

    try:
        # ---- Step 1: Ideation ----
        logger.info("=" * 60)
        logger.info("[%s] STEP 1: Generating ideas... (style: %s)", niche_id, video_style)

        ideation = IdeaGenerator(config)
        ideas = await ideation.generate_ideas(niche_id, count=3)
        idea = ideas[0]

        result["steps"]["ideation"] = {"title": idea.get("title"), "hook": idea.get("hook")}
        prompt_log.append({"niche": niche_id, "step": "ideation", "response": idea})
        logger.info("[%s] Idea: %s", niche_id, idea.get("title"))

        # ---- Step 2: Scripting ----
        logger.info("[%s] STEP 2: Writing script...", niche_id)

        scripting = ScriptWriter(config)
        scripting_prompt = scripting._build_prompt(niche_id, idea, niche_config)
        script = await scripting.write_script(niche_id, idea)

        voiceover_text = script.get("voiceover_script", "")
        word_count = len(voiceover_text.split()) if voiceover_text else 0
        result["steps"]["scripting"] = {
            "has_voiceover": bool(voiceover_text),
            "voiceover_words": word_count,
            "has_slides": bool(script.get("slide_texts")),
            "has_clips": bool(script.get("clips")),
        }
        prompt_log.append({"niche": niche_id, "step": "scripting", "prompt": scripting_prompt, "response": script})
        logger.info("[%s] Script: voiceover=%s (%d words), slides=%s, clips=%s",
                     niche_id, bool(voiceover_text), word_count,
                     bool(script.get("slide_texts")), bool(script.get("clips")))

        # ---- Step 2b: Niche-specific script customization (e.g. voice gender) ----
        from gold.niches.registry import load_niches
        niche_engines = load_niches(config)
        engine = niche_engines.get(niche_id)
        if engine:
            script = await engine.customize_script(script)
            if script.get("_voice_id_override"):
                logger.info("[%s] Voice override: %s", niche_id, script["_voice_id_override"])

        # ---- Step 3: Thumbnail ----
        logger.info("[%s] STEP 3: Generating thumbnail...", niche_id)

        media = MediaProducer(config)
        thumb_prompt = script.get("thumbnail_prompt", idea.get("title", "thumbnail"))
        prompt_log.append({"niche": niche_id, "step": "thumbnail", "prompt": thumb_prompt})
        thumb_path = await media.generate_thumbnail(
            prompt=thumb_prompt,
            output_name=f"test_{niche_id}_thumb_{ts}",
        )
        result["steps"]["thumbnail"] = {"path": str(thumb_path)}
        logger.info("[%s] Thumbnail: %s", niche_id, thumb_path.name)

        # ---- Steps 4-5: Style-specific pipeline ----
        if video_style == "gameplay":
            final_path, extra_steps = await test_gameplay_niche(
                config, niche_id, niche_config, idea, script, prompt_log, ts, background,
            )
        elif video_style == "slides":
            final_path, extra_steps = await test_slides_niche(
                config, niche_id, niche_config, idea, script, prompt_log, ts,
            )
        elif video_style == "image_to_video":
            final_path, extra_steps = await test_image_to_video_niche(
                config, niche_id, niche_config, idea, script, prompt_log, ts,
            )
        elif video_style == "cinematic_doc":
            final_path, extra_steps = await test_cinematic_doc_niche(
                config, niche_id, niche_config, idea, script, prompt_log, ts,
            )
        elif video_style == "stock_footage":
            final_path, extra_steps = await test_stock_footage_niche(
                config, niche_id, niche_config, idea, script, prompt_log, ts,
            )
        elif video_style == "infographic":
            final_path, extra_steps = await test_infographic_niche(
                config, niche_id, niche_config, idea, script, prompt_log, ts,
            )
        elif video_style in ("ai_clips", "ken_burns"):
            # Legacy fallback — use image_to_video
            final_path, extra_steps = await test_image_to_video_niche(
                config, niche_id, niche_config, idea, script, prompt_log, ts,
            )
        else:
            final_path, extra_steps = await test_gameplay_niche(
                config, niche_id, niche_config, idea, script, prompt_log, ts, background,
            )

        result["steps"].update(extra_steps)

        final_size = final_path.stat().st_size / (1024 * 1024)
        duration = await get_duration(final_path)
        result["steps"]["render"] = {
            "path": str(final_path),
            "size_mb": round(final_size, 2),
            "duration_s": round(duration, 1),
        }
        logger.info(
            "[%s] Final video: %s (%.2f MB, %.1fs)",
            niche_id, final_path.name, final_size, duration,
        )

        result["success"] = True
        logger.info("[%s] SUCCESS!", niche_id)

    except Exception as e:
        logger.error("[%s] FAILED: %s", niche_id, e, exc_info=True)
        result["error"] = str(e)

    return result


async def main() -> None:
    """Entry point: run the dry-run pipeline for all three launch niches."""
    config = Config()
    init_sync_db(config.db_url_sync)
    create_tables_sync()

    logger.info("Starting dry run v6 — STOCK FOOTAGE PIPELINE")
    logger.info("Niches:")
    logger.info("  reddit_stories:    gameplay bg + voiceover + Whisper subtitles (~$0.12)")
    logger.info("  personal_finance:  Pexels stock footage + crossfade + voiceover + subs (~$0.10)")
    logger.info("  ai_tools:          Pexels stock footage + crossfade + voiceover + subs (~$0.10)")
    logger.info("  true_crime:        Pexels stock footage + crossfade + voiceover + subs (~$0.10)")
    logger.info("  betrayal_revenge:  gameplay bg + voiceover + Whisper subtitles (~$0.12)")
    logger.info("  english_learning:  Pexels stock footage + crossfade + voiceover + subs (~$0.10)")
    logger.info("This will call Anthropic, ElevenLabs, Pexels, and optionally fal.ai APIs.")
    start = time.time()

    # Ensure we have a background video (needed for ALL gameplay niches)
    gameplay_niches = {"reddit_stories", "betrayal_revenge"}
    background = None
    if gameplay_niches & set(LAUNCH_NICHES):
        background = await ensure_background_video(config)

    prompt_log: list[dict] = []

    results: list[dict] = []

    for niche_id in LAUNCH_NICHES:
        r = await test_niche(config, niche_id, prompt_log, background)
        results.append(r)
        logger.info("")

    elapsed = time.time() - start

    # Summary
    logger.info("=" * 60)
    logger.info("DRY RUN v3 SUMMARY (%.1f minutes)", elapsed / 60)
    logger.info("=" * 60)
    for r in results:
        status = "OK" if r["success"] else f"FAILED: {r.get('error', 'unknown')[:80]}"
        logger.info("  %-20s [%-8s] %s", r["niche"], r.get("video_style", "?"), status)
        if r["success"]:
            render = r["steps"].get("render", {})
            logger.info(
                "    -> %s (%.2f MB, %.1fs)",
                Path(render.get("path", "")).name,
                render.get("size_mb", 0),
                render.get("duration_s", 0),
            )

    # Save results
    results_path = config.data_dir / "dry_run_results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info("Full results saved to %s", results_path)

    # Save prompts
    prompts_path = config.data_dir / "dry_run_prompts.txt"
    save_prompts(prompt_log, prompts_path)

    successes = sum(1 for r in results if r["success"])
    logger.info("Result: %d/%d niches succeeded", successes, len(LAUNCH_NICHES))

    # Cost estimate
    logger.info("")
    logger.info("COST PER VIDEO:")
    logger.info("  reddit_stories    (gameplay):       ~$0.12 (voiceover + thumbnail)")
    logger.info("  personal_finance  (stock_footage):  ~$0.10 (Pexels FREE + voiceover + thumbnail)")
    logger.info("  ai_tools          (stock_footage):  ~$0.10 (Pexels FREE + voiceover + thumbnail)")
    logger.info("  true_crime        (stock_footage):  ~$0.10 (Pexels FREE + voiceover + thumbnail)")
    logger.info("  betrayal_revenge  (gameplay):       ~$0.12 (voiceover + thumbnail)")
    logger.info("  english_learning  (stock_footage):  ~$0.10 (Pexels FREE + voiceover + thumbnail)")
    logger.info("  DAILY TOTAL (6 niches x 2):       ~$1.28")


if __name__ == "__main__":
    asyncio.run(main())
