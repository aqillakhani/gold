"""ContentPipeline: orchestrates the full content generation pipeline."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime

from ..config import Config
from ..models.content import Content, ContentStatus, ContentVariant
from ..models.db import get_sync_session
from ..niches.registry import load_niches
from .audio import AudioProducer
from .emoji_beats import detect_emoji_beats
from .ideation import IdeaGenerator
from .media import MediaProducer
from .multi_voice import detect_dialogue, get_voice_for_speaker
from .quality import QualityGate
from .renderer import VideoRenderer
from .scripting import ScriptWriter
from .subtitles import SubtitleGenerator
from .variation import PlatformVariator

logger = logging.getLogger(__name__)


def _extract_part_info(title: str) -> tuple[int, int]:
    """Extract (part_number, total_parts) from title like '... — Part 2'.

    Args:
        title: Content title that may contain part information.

    Returns:
        Tuple of (part_number, total_parts). Returns (0, 0) if no part info found.
    """
    match = re.search(r'Part\s+(\d+)(?:\s*/\s*(\d+))?', title, re.IGNORECASE)
    if match:
        part = int(match.group(1))
        total = int(match.group(2)) if match.group(2) else 3
        return (part, total)
    return (0, 0)


class ContentPipeline:
    """Chains all pipeline steps: ideation, scripting, background video, audio, render, vary, QC."""

    def __init__(self, config: Config):
        self.config = config
        self.ideation = IdeaGenerator(config)
        self.scripting = ScriptWriter(config)
        self.media = MediaProducer(config)
        self.audio = AudioProducer(config)
        self.renderer = VideoRenderer(config)
        self.variator = PlatformVariator(config)
        self.quality = QualityGate(config)
        self.subtitles = SubtitleGenerator()
        self.niche_engines = load_niches(config)

    async def generate_content(self, account_id: str, niche_id: str) -> Content | None:
        """Generate a single piece of content end-to-end.

        For niches with multi_part enabled, generates one script and produces
        separate videos for each part (e.g., 3 videos from one story).
        """
        start = time.time()
        niche_config = self.config.niches.get(niche_id, {})
        has_voiceover = niche_config.get("has_voiceover", True)
        video_style = niche_config.get("video_style", "gameplay")
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        # Check for multi-part mode
        multi_part = niche_config.get("multi_part", {})
        if multi_part.get("enabled"):
            return await self._generate_multi_part_content(
                account_id, niche_id, niche_config, ts,
            )

        # 1. Ideation
        logger.info("[%s] Step 1: Generating ideas...", account_id)
        ideas = await self.ideation.generate_ideas(niche_id, count=3)
        if not ideas:
            logger.error("No ideas generated for %s", niche_id)
            return None
        idea = ideas[0]

        # 2. Scripting
        logger.info("[%s] Step 2: Writing script for '%s'...", account_id, idea.get("title"))
        script = await self.scripting.write_script(niche_id, idea)

        # 2b. Niche-specific script customization (e.g. voice gender override)
        engine = self.niche_engines.get(niche_id)
        if engine:
            script = await engine.customize_script(script)

        # Create DB record
        session = get_sync_session()
        content = Content(
            account_id=account_id,
            niche=niche_id,
            title=idea.get("title", "Untitled"),
            hook=script.get("hook_text", idea.get("hook", "")),
            script=script.get("voiceover_script", ""),
            scene_descriptions=json.dumps(script.get("scenes", script.get("clips", []))),
            status=ContentStatus.GENERATING,
        )
        session.add(content)
        session.commit()
        content_id = content.id

        try:
            if video_style == "gameplay":
                master = await self._produce_gameplay_video(
                    content_id, account_id, niche_id, niche_config,
                    script, has_voiceover, ts,
                )
            elif video_style == "slides":
                master = await self._produce_slides_video(
                    content_id, account_id, niche_config,
                    script, has_voiceover, ts,
                )
            elif video_style == "image_to_video":
                master = await self._produce_image_to_video(
                    content_id, account_id, niche_config,
                    script, ts,
                )
            elif video_style == "infographic":
                master = await self._produce_infographic_video(
                    content_id, account_id, niche_config,
                    script, has_voiceover, ts,
                )
            elif video_style in ("ken_burns", "ai_clips"):
                master = await self._produce_kenburns_video(
                    content_id, account_id, niche_config,
                    script, has_voiceover, ts,
                )
            elif video_style == "stock_footage":
                master = await self._produce_stock_footage_video(
                    content_id, account_id, niche_id, niche_config,
                    script, has_voiceover, ts,
                )
            elif video_style == "cinematic_doc":
                master = await self._produce_cinematic_doc_video(
                    content_id, account_id, niche_config,
                    script, ts,
                )
            else:
                master = await self._produce_gameplay_video(
                    content_id, account_id, niche_id, niche_config,
                    script, has_voiceover, ts,
                )

            # Visual hook overlay (first 2 seconds — attention-grabbing text + SFX)
            hook_text = script.get("hook_text", idea.get("title", ""))
            if hook_text and video_style != "cinematic_doc":
                from ..utils.ffmpeg import add_visual_hook
                hooked_path = master.parent / f"{master.stem}_hooked{master.suffix}"
                try:
                    master = await add_visual_hook(
                        video_path=master,
                        hook_text=hook_text,
                        output_path=hooked_path,
                        niche_id=niche_id,
                    )
                    logger.info("[%s] [VISUAL-HOOK] OK: added visual hook '%s' (niche=%s)", account_id, hook_text[:30], niche_id)
                except Exception as e:
                    logger.error("[%s] [VISUAL-HOOK] FAILED — video has NO visual hook: %s", account_id, e)

            # Generate thumbnail
            thumb_prompt = script.get("thumbnail_prompt", idea.get("title", ""))
            thumbnail = await self.media.generate_thumbnail(
                prompt=thumb_prompt,
                output_name=f"content_{content_id}_thumb_{ts}",
            )

            # Platform variants — Shorts extraction for cinematic_doc
            shorts_extraction = niche_config.get("shorts_extraction", False)
            if video_style == "cinematic_doc" and shorts_extraction:
                logger.info("[%s] Step 5: Extracting Shorts + creating variants...", account_id)
                short_paths = await self.variator.extract_shorts(
                    master_path=master,
                    script=script,
                    content_id=content_id,
                )
                # YouTube = long-form master; other platforms = first Short
                variant_paths = {}
                variant_paths["youtube"] = master
                if short_paths:
                    # Use the first extracted Short for non-YouTube platforms
                    short_master = short_paths[0]
                    short_variants = await self.variator.create_variants(
                        short_master, content_id, suffix="_short",
                    )
                    for plat in ("facebook", "instagram", "tiktok"):
                        if plat in short_variants:
                            variant_paths[plat] = short_variants[plat]
                else:
                    # Fallback: use long-form master for all
                    logger.warning("[%s] No Shorts extracted, using master for all platforms", account_id)
                    variant_paths = await self.variator.create_variants(master, content_id)
            else:
                logger.info("[%s] Step 5: Creating platform variants...", account_id)
                variant_paths = await self.variator.create_variants(master, content_id)

            # Quality gate
            logger.info("[%s] Step 6: Running quality checks...", account_id)
            passed, issues = await self.quality.check(
                master, script.get("voiceover_script", "")
            )

            if not passed:
                logger.warning("[%s] Quality gate failed: %s", account_id, issues)
                content.status = ContentStatus.FAILED
                session.commit()
                session.close()
                return None

            # Save variants to DB
            captions = script.get("captions", {})
            hashtags = script.get("hashtags", [])
            for platform, path in variant_paths.items():
                variant = ContentVariant(
                    content_id=content_id,
                    platform=platform,
                    video_path=str(path),
                    caption=captions.get(platform, ""),
                    hashtags=json.dumps(hashtags),
                    cta=niche_config.get("cta", {}).get(platform, ""),
                )
                session.add(variant)

            content.master_video_path = str(master)
            content.thumbnail_path = str(thumbnail)
            content.status = ContentStatus.READY
            session.commit()

            elapsed = time.time() - start
            logger.info(
                "[%s] Content #%d ready in %.1fs: %s",
                account_id, content_id, elapsed, content.title,
            )
            return content

        except Exception as e:
            logger.error("[%s] Pipeline failed for content #%d: %s", account_id, content_id, e)
            content.status = ContentStatus.FAILED
            session.commit()
            raise
        finally:
            session.close()

    async def _generate_multi_part_content(
        self, account_id: str, niche_id: str, niche_config: dict, ts: str,
    ) -> Content | None:
        """Generate a multi-part video series (e.g., 3-part Reddit story).

        Produces one script with multiple parts, then renders each part as a
        separate gameplay video with its own Content record.
        Returns the first part's Content record.
        """
        from ..utils.backgrounds import build_background_montage, create_placeholder_background
        from ..utils.ffmpeg import compose_gameplay_video, get_duration

        multi_cfg = niche_config["multi_part"]
        num_parts = multi_cfg.get("parts", 3)
        has_voiceover = niche_config.get("has_voiceover", True)

        # 1. Ideation
        logger.info("[%s] Multi-part Step 1: Generating ideas...", account_id)
        ideas = await self.ideation.generate_ideas(niche_id, count=3)
        if not ideas:
            logger.error("No ideas generated for %s", niche_id)
            return None
        idea = ideas[0]

        # 2. Scripting (returns script with `parts` array)
        logger.info("[%s] Multi-part Step 2: Writing %d-part script for '%s'...",
                     account_id, num_parts, idea.get("title"))
        script = await self.scripting.write_script(niche_id, idea)

        # 2b. Niche-specific customization
        engine = self.niche_engines.get(niche_id)
        if engine:
            script = await engine.customize_script(script)

        parts = script.get("parts", [])
        if not parts:
            # Fallback: if LLM didn't return parts array, treat as single video
            logger.warning("[%s] Script has no 'parts' array, falling back to single video", account_id)
            parts = [{"voiceover_script": script.get("voiceover_script", ""),
                       "part_label": "Part 1", "part_hook": script.get("hook_text", "")}]

        hook_text = script.get("hook_text", idea.get("hook", ""))
        base_title = idea.get("title", "Untitled")

        # 3. Build background montage (shared across all parts)
        bg_category = niche_config.get("background_category", "gameplay")
        try:
            background = await build_background_montage(
                target_duration=120, category=bg_category,
            )
        except RuntimeError:
            bg_dir = self.config.media_dir / "backgrounds"
            bg_dir.mkdir(parents=True, exist_ok=True)
            background = bg_dir / "placeholder.mp4"
            if not background.exists():
                create_placeholder_background(background, duration=120.0)

        # Background music (shared across parts for consistency)
        music_path = await self.audio.get_context_music(script, niche_config)

        first_content = None
        session = get_sync_session()

        try:
            for i, part in enumerate(parts[:num_parts]):
                part_num = i + 1
                part_label = part.get("part_label", f"Part {part_num}")
                part_vo = part.get("voiceover_script", "")
                part_hook = part.get("part_hook", hook_text)
                part_title = f"{base_title} — {part_label}"

                logger.info("[%s] === %s of %d ===", account_id, part_label, num_parts)

                # Create DB record for this part
                content = Content(
                    account_id=account_id,
                    niche=niche_id,
                    title=part_title,
                    hook=part_hook if part_num == 1 else f"{part_label}: {part_hook}",
                    script=part_vo,
                    scene_descriptions="[]",
                    status=ContentStatus.GENERATING,
                )
                session.add(content)
                session.commit()
                content_id = content.id

                # Voiceover for this part
                audio_path = None
                if has_voiceover and part_vo:
                    voice_config = niche_config.get("voice", {})
                    voice_id = (script.get("_voice_id_override")
                                or voice_config.get("voice_id", "onyx"))
                    audio_path = await self.audio.generate_voiceover(
                        text=part_vo,
                        voice_id=voice_id,
                        output_name=f"content_{content_id}_vo_{ts}",
                        provider=voice_config.get("provider", "elevenlabs"),
                        speed=voice_config.get("speed"),
                        niche_id=niche_id,
                    )

                # Subtitles for this part
                subtitle_path = None
                if audio_path and part_vo:
                    subtitle_dir = self.config.media_dir / "subtitles"
                    subtitle_dir.mkdir(parents=True, exist_ok=True)
                    subtitle_path = subtitle_dir / f"content_{content_id}_subs_{ts}.ass"
                    self._generate_subtitles(part_vo, audio_path, subtitle_path, niche_id=niche_id)

                # Get audio duration for progress bar
                audio_duration = None
                if audio_path:
                    from ..utils.ffmpeg import get_duration
                    audio_duration = await get_duration(audio_path)

                # Compose this part
                output_dir = self.config.media_dir / "rendered"
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / f"content_{content_id}_master_{ts}.mp4"

                # Hook card: show story title + part label
                subreddit = script.get("subreddit", "AskReddit")
                display_hook = hook_text  # same story title across all parts

                master = await compose_gameplay_video(
                    background_video=background,
                    audio_path=audio_path,
                    music_path=music_path,
                    subtitle_path=subtitle_path,
                    output_path=output_path,
                    target_duration=audio_duration,
                    hook_text=display_hook,
                    subreddit=f"r/{subreddit} • {part_label}",
                    resolution=(
                        self.config.get("video.resolution.width", 1080),
                        self.config.get("video.resolution.height", 1920),
                    ),
                    fps=self.config.get("video.fps", 30),
                    music_volume=niche_config.get("music_volume", 0.30),
                    niche_id=niche_id,
                    part_number=i + 1,
                    total_parts=num_parts,
                )

                # Loudness normalization — target -14 LUFS (YouTube standard)
                from ..utils.ffmpeg import run_ffmpeg
                logger.info("[%s] %s: Normalizing audio loudness to -14 LUFS", account_id, part_label)
                normalized_path = output_path.with_name(output_path.stem + "_loud.mp4")
                await run_ffmpeg([
                    "-i", str(master),
                    "-c:v", "copy",
                    "-af", "loudnorm=I=-14:TP=-1:LRA=11",
                    str(normalized_path),
                ])
                normalized_path.replace(master)

                # Thumbnail (only for Part 1)
                if part_num == 1:
                    thumb_prompt = script.get("thumbnail_prompt", base_title)
                    thumbnail = await self.media.generate_thumbnail(
                        prompt=thumb_prompt,
                        output_name=f"content_{content_id}_thumb_{ts}",
                    )
                    content.thumbnail_path = str(thumbnail)

                # Platform variants
                variant_paths = await self.variator.create_variants(master, content_id)

                # Quality gate
                passed, issues = await self.quality.check(master, part_vo)
                if not passed:
                    logger.warning("[%s] %s quality gate failed: %s", account_id, part_label, issues)
                    content.status = ContentStatus.FAILED
                    session.commit()
                    continue

                # Save variants
                captions = script.get("captions", {})
                hashtags = script.get("hashtags", [])
                for platform, path in variant_paths.items():
                    variant = ContentVariant(
                        content_id=content_id,
                        platform=platform,
                        video_path=str(path),
                        caption=f"{part_label}/3 | {captions.get(platform, '')}",
                        hashtags=json.dumps(hashtags),
                        cta=niche_config.get("cta", {}).get(platform, ""),
                    )
                    session.add(variant)

                content.master_video_path = str(master)
                content.status = ContentStatus.READY
                session.commit()

                if first_content is None:
                    first_content = content

                logger.info("[%s] %s ready: content #%d", account_id, part_label, content_id)

            elapsed = time.time() - self._start_time if hasattr(self, '_start_time') else 0
            logger.info("[%s] All %d parts generated for '%s'", account_id, num_parts, base_title)
            return first_content

        except Exception as e:
            logger.error("[%s] Multi-part pipeline failed: %s", account_id, e)
            raise
        finally:
            session.close()

    def _generate_subtitles(self, voiceover_text, audio_path, output_path, niche_id: str = ""):
        """Generate subtitles using Whisper (with fallback to even-division)."""
        return self.subtitles.generate_from_audio(
            audio_path=audio_path,
            text=voiceover_text,
            output_path=output_path,
            niche_id=niche_id,
        )

    async def _produce_gameplay_video(
        self, content_id, account_id, niche_id, niche_config,
        script, has_voiceover, ts,
    ):
        """Produce a video using gameplay background + voiceover + word-by-word subtitles."""
        from ..utils.backgrounds import build_background_montage, create_placeholder_background
        from ..utils.ffmpeg import compose_gameplay_video, get_duration

        # 3. Build background montage from random clips (no repeats)
        logger.info("[%s] Step 3: Building gameplay background montage...", account_id)
        bg_category = niche_config.get("background_category", "gameplay")
        target_dur = niche_config.get("target_duration", 90)
        try:
            background = await build_background_montage(
                target_duration=target_dur + 30,  # buffer for safety
                category=bg_category,
            )
        except RuntimeError:
            logger.warning("[%s] No background clips found, using placeholder", account_id)
            bg_dir = self.config.media_dir / "backgrounds"
            bg_dir.mkdir(parents=True, exist_ok=True)
            background = bg_dir / "placeholder.mp4"
            if not background.exists():
                create_placeholder_background(background, duration=120.0)

        # 4. Audio
        audio_path = None
        if has_voiceover and script.get("voiceover_script"):
            logger.info("[%s] Step 4a: Generating voiceover...", account_id)
            voice_config = niche_config.get("voice", {})
            # Allow niche engine to override voice_id (e.g. betrayal_revenge gender detection)
            voice_id = script.get("_voice_id_override") or voice_config.get("voice_id", "onyx")
            audio_path = await self.audio.generate_voiceover(
                text=script["voiceover_script"],
                voice_id=voice_id,
                output_name=f"content_{content_id}_vo_{ts}",
                provider=voice_config.get("provider", "elevenlabs"),
                speed=voice_config.get("speed"),
                niche_id=niche_id,
            )

        # Background music — context-aware selection based on script content
        music_path = await self.audio.get_context_music(script, niche_config)

        # 4b. Generate word-by-word subtitles (Whisper-timed)
        subtitle_path = None
        if has_voiceover and script.get("voiceover_script") and audio_path:
            logger.info("[%s] Step 4b: Generating Whisper-timed subtitles...", account_id)
            subtitle_dir = self.config.media_dir / "subtitles"
            subtitle_dir.mkdir(parents=True, exist_ok=True)
            subtitle_path = subtitle_dir / f"content_{content_id}_subs_{ts}.ass"
            self._generate_subtitles(script["voiceover_script"], audio_path, subtitle_path)

        # 5. Compose final video
        logger.info("[%s] Step 5: Composing gameplay video...", account_id)
        output_dir = self.config.media_dir / "rendered"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"content_{content_id}_master_{ts}.mp4"

        master = await compose_gameplay_video(
            background_video=background,
            audio_path=audio_path,
            music_path=music_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
            hook_text=script.get("hook_text", ""),
            subreddit=f"r/{script.get('subreddit', 'AskReddit')}",
            resolution=(
                self.config.get("video.resolution.width", 1080),
                self.config.get("video.resolution.height", 1920),
            ),
            fps=self.config.get("video.fps", 30),
        )

        return master

    async def _produce_slides_video(
        self, content_id, account_id, niche_config,
        script, has_voiceover, ts,
    ):
        """Produce a video using text slides + voiceover + word-by-word subtitles.

        Clean infographic style for crypto/finance content.
        """
        from ..utils.ffmpeg import compose_slides_video, get_duration

        # 3. Get slide texts from the script
        logger.info("[%s] Step 3: Preparing text slides...", account_id)
        slide_texts = script.get("slide_texts", [])
        if not slide_texts:
            voiceover = script.get("voiceover_script", "")
            sentences = [s.strip() for s in voiceover.replace("!", ".").replace("?", ".").split(".") if s.strip()]
            step = max(1, len(sentences) // 8)
            slide_texts = [s[:60] for s in sentences[::step]][:10]
            if not slide_texts:
                slide_texts = ["CRYPTO UPDATE"]

        # 4a. Voiceover
        audio_path = None
        audio_duration = None
        if has_voiceover and script.get("voiceover_script"):
            logger.info("[%s] Step 4a: Generating voiceover...", account_id)
            voice_config = niche_config.get("voice", {})
            audio_path = await self.audio.generate_voiceover(
                text=script["voiceover_script"],
                voice_id=voice_config.get("voice_id", "onyx"),
                output_name=f"content_{content_id}_vo_{ts}",
                provider=voice_config.get("provider", "elevenlabs"),
                speed=voice_config.get("speed"),
                niche_id=niche_id,
            )
            if audio_path and audio_path.exists():
                audio_duration = await get_duration(audio_path)

        music_path = await self.audio.get_context_music(script, niche_config)

        # 4b. Subtitles (Whisper-timed)
        subtitle_path = None
        if has_voiceover and script.get("voiceover_script") and audio_path:
            logger.info("[%s] Step 4b: Generating Whisper-timed subtitles...", account_id)
            subtitle_dir = self.config.media_dir / "subtitles"
            subtitle_dir.mkdir(parents=True, exist_ok=True)
            subtitle_path = subtitle_dir / f"content_{content_id}_subs_{ts}.ass"
            self._generate_subtitles(script["voiceover_script"], audio_path, subtitle_path)

        # 5. Compose
        logger.info("[%s] Step 5: Composing slides video...", account_id)
        output_dir = self.config.media_dir / "rendered"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"content_{content_id}_master_{ts}.mp4"

        master = await compose_slides_video(
            slide_texts=slide_texts,
            audio_path=audio_path,
            music_path=music_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
            audio_duration=audio_duration,
            resolution=(
                self.config.get("video.resolution.width", 1080),
                self.config.get("video.resolution.height", 1920),
            ),
            fps=self.config.get("video.fps", 30),
        )

        return master

    async def _produce_image_to_video(
        self, content_id, account_id, niche_config, script, ts,
    ):
        """Produce ASMR/fantasy video: Flux images → i2v model → ambient audio → compose."""
        from ..utils.ffmpeg import compose_asmr_video

        scenes = script.get("scenes", [])
        if not scenes:
            raise RuntimeError("Script has no 'scenes' array for image_to_video style")

        # Determine i2v model: niche config override > global config
        i2v_model = niche_config.get("i2v_model") or None  # None = use MediaProducer default

        # Cost estimation
        i2v_name = i2v_model or self.media.i2v_model
        cost_per_sec = 0.01 if "minimax" in i2v_name else 0.029
        image_cost = 0.015  # Flux/Schnell per image
        total_scene_seconds = sum(float(s.get("duration", 7)) for s in scenes)
        estimated_cost = (len(scenes) * image_cost) + (total_scene_seconds * cost_per_sec) + 0.02  # +SFX
        logger.info(
            "[%s] Estimated cost: $%.3f (%d scenes × %s, %.0fs total)",
            account_id, estimated_cost, len(scenes), i2v_name.split("/")[-1], total_scene_seconds,
        )

        logger.info("[%s] Step 3: Generating %d AI video clips from images...", account_id, len(scenes))

        clip_paths = []
        text_overlays = []

        for i, scene in enumerate(scenes):
            image_prompt = scene.get("image_prompt", "")
            if not image_prompt:
                continue

            motion_prompt = scene.get("motion_prompt", "")
            text_overlay = scene.get("text_overlay", "")
            duration = str(scene.get("duration", "7"))

            # Generate Flux image (keep URL for image-to-video)
            logger.info("[%s] Scene %d/%d: Generating image...", account_id, i + 1, len(scenes))
            img_path, img_url = await self.media.generate_image(
                prompt=image_prompt,
                output_name=f"content_{content_id}_scene_{i}_{ts}",
                width=1080, height=1920,
                return_url=True,
            )

            # Animate image to video via configurable i2v model
            logger.info("[%s] Scene %d/%d: Animating to video (%s)...", account_id, i + 1, len(scenes), i2v_name.split("/")[-1])
            clip_path = await self.media.generate_video_from_image(
                image_url=img_url,
                prompt=motion_prompt,
                output_name=f"content_{content_id}_clip_{i}_{ts}",
                duration=duration,
                aspect_ratio="9:16",
                i2v_model=i2v_model,
            )
            clip_paths.append(clip_path)
            text_overlays.append(text_overlay)

        if not clip_paths:
            raise RuntimeError("No video clips were generated")

        # Generate ONE continuous ambient sound track (instead of per-scene SFX)
        ambient_desc = script.get("ambient_description", "")
        ambient_path = None
        if ambient_desc:
            logger.info("[%s] Step 4: Generating continuous ambient track...", account_id)
            try:
                ambient_duration = min(22.0, max(15.0, total_scene_seconds))
                ambient_path = await self.media.generate_sound_effect(
                    prompt=ambient_desc,
                    output_name=f"content_{content_id}_ambient_{ts}",
                    duration=ambient_duration,
                )
            except Exception as e:
                logger.warning("[%s] Ambient sound generation failed: %s", account_id, e)
        else:
            # Fallback: try per-scene sound_effect or ambient_sound from first scene
            first_sound = (
                scenes[0].get("ambient_sound", "")
                or scenes[0].get("sound_effect", "")
            )
            if first_sound:
                try:
                    ambient_duration = min(22.0, max(15.0, total_scene_seconds))
                    ambient_path = await self.media.generate_sound_effect(
                        prompt=first_sound,
                        output_name=f"content_{content_id}_ambient_{ts}",
                        duration=ambient_duration,
                    )
                except Exception as e:
                    logger.warning("[%s] Fallback ambient generation failed: %s", account_id, e)

        # Build sfx_paths list: ambient track as single entry for compose_asmr_video
        sfx_paths = [ambient_path] + [None] * (len(clip_paths) - 1)

        # Background music — context-aware selection
        music_path = await self.audio.get_context_music(script, niche_config)

        # Compose final video
        logger.info("[%s] Step 5: Composing ASMR video...", account_id)
        output_dir = self.config.media_dir / "rendered"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"content_{content_id}_master_{ts}.mp4"

        master = await compose_asmr_video(
            clip_paths=clip_paths,
            sfx_paths=sfx_paths,
            text_overlays=text_overlays,
            music_path=music_path,
            output_path=output_path,
            resolution=(
                self.config.get("video.resolution.width", 1080),
                self.config.get("video.resolution.height", 1920),
            ),
            fps=self.config.get("video.fps", 30),
        )
        return master

    async def _produce_infographic_video(
        self, content_id, account_id, niche_config,
        script, has_voiceover, ts,
    ):
        """Produce infographic video: voiceover FIRST → scale scene durations → Flux images → Ken Burns → subtitles."""
        from ..utils.ffmpeg import apply_ken_burns, compose_clips_video, get_duration

        scenes = script.get("scenes", [])
        if not scenes:
            raise RuntimeError("Script has no 'scenes' array for infographic style")

        # --- VOICEOVER FIRST (so we know exact duration to fill) ---
        audio_path = None
        audio_duration = None
        if has_voiceover and script.get("voiceover_script"):
            logger.info("[%s] Step 3a: Generating voiceover FIRST...", account_id)
            voice_config = niche_config.get("voice", {})
            # Allow niche engine to override voice_id (e.g. true_crime gender detection)
            voice_id = script.get("_voice_id_override") or voice_config.get("voice_id", "onyx")
            audio_path = await self.audio.generate_voiceover(
                text=script["voiceover_script"],
                voice_id=voice_id,
                output_name=f"content_{content_id}_vo_{ts}",
                provider=voice_config.get("provider", "elevenlabs"),
                speed=voice_config.get("speed"),
                niche_id=niche_id,
            )
            audio_duration = await get_duration(audio_path)
            logger.info("[%s] Voiceover duration: %.1fs", account_id, audio_duration)

        # --- SCALE SCENE DURATIONS to match voiceover ---
        raw_total = sum(float(s.get("duration", 7)) for s in scenes)
        if audio_duration and raw_total > 0:
            # Scale each scene proportionally so total matches voiceover + 1s buffer
            target_total = audio_duration + 1.0
            scale_factor = target_total / raw_total
            for scene in scenes:
                orig = float(scene.get("duration", 7))
                scene["duration"] = round(orig * scale_factor, 1)
            new_total = sum(float(s["duration"]) for s in scenes)
            logger.info(
                "[%s] Scaled scene durations: %.1fs → %.1fs (voiceover: %.1fs)",
                account_id, raw_total, new_total, audio_duration,
            )

        # --- GENERATE IMAGES + KEN BURNS ---
        logger.info("[%s] Step 3b: Generating %d infographic images...", account_id, len(scenes))

        ken_burns_clips = []
        text_overlays = []

        for i, scene in enumerate(scenes):
            image_prompt = scene.get("image_prompt", "")
            if not image_prompt:
                continue

            duration = float(scene.get("duration", 7))
            effect = scene.get("ken_burns", "zoom_in")
            text_overlay = scene.get("text_overlay", "")

            # Generate infographic image
            logger.info("[%s] Scene %d/%d: Generating infographic...", account_id, i + 1, len(scenes))
            img_path = await self.media.generate_image(
                prompt=image_prompt,
                output_name=f"content_{content_id}_infographic_{i}_{ts}",
                width=1080, height=1920,
            )

            # Apply Ken Burns
            clip_dir = self.config.media_dir / "clips"
            clip_dir.mkdir(parents=True, exist_ok=True)
            clip_path = clip_dir / f"content_{content_id}_kb_{i}_{ts}.mp4"
            await apply_ken_burns(
                image_path=img_path, output_path=clip_path,
                duration=duration, effect=effect,
                resolution=(
                    self.config.get("video.resolution.width", 1080),
                    self.config.get("video.resolution.height", 1920),
                ),
                fps=self.config.get("video.fps", 30),
            )
            ken_burns_clips.append(clip_path)
            text_overlays.append(text_overlay)

        if not ken_burns_clips:
            raise RuntimeError("No infographic clips generated")

        # --- SUBTITLES ---
        subtitle_path = None
        if has_voiceover and script.get("voiceover_script") and audio_path:
            logger.info("[%s] Step 4: Generating subtitles...", account_id)
            subtitle_dir = self.config.media_dir / "subtitles"
            subtitle_dir.mkdir(parents=True, exist_ok=True)
            subtitle_path = subtitle_dir / f"content_{content_id}_subs_{ts}.ass"
            self._generate_subtitles(script["voiceover_script"], audio_path, subtitle_path)

        # Background music — context-aware selection
        music_path = await self.audio.get_context_music(script, niche_config)

        # --- COMPOSE: clips + voiceover + subtitles + music ---
        logger.info("[%s] Step 5: Composing infographic video...", account_id)
        output_dir = self.config.media_dir / "rendered"
        output_dir.mkdir(parents=True, exist_ok=True)

        if audio_path or subtitle_path:
            # First compose clips into a silent video
            silent_path = output_dir / f"content_{content_id}_silent_{ts}.mp4"
            await compose_clips_video(
                clip_paths=ken_burns_clips,
                text_overlays=text_overlays,
                music_path=None,
                output_path=silent_path,
                resolution=(
                    self.config.get("video.resolution.width", 1080),
                    self.config.get("video.resolution.height", 1920),
                ),
                fps=self.config.get("video.fps", 30),
            )
            # Then use gameplay compose to add voiceover + subtitles + music
            from ..utils.ffmpeg import compose_gameplay_video
            output_path = output_dir / f"content_{content_id}_master_{ts}.mp4"
            master = await compose_gameplay_video(
                background_video=silent_path,
                audio_path=audio_path,
                music_path=music_path,
                subtitle_path=subtitle_path,
                output_path=output_path,
                target_duration=audio_duration,
                resolution=(
                    self.config.get("video.resolution.width", 1080),
                    self.config.get("video.resolution.height", 1920),
                ),
                fps=self.config.get("video.fps", 30),
            )
        else:
            output_path = output_dir / f"content_{content_id}_master_{ts}.mp4"
            master = await compose_clips_video(
                clip_paths=ken_burns_clips,
                text_overlays=text_overlays,
                music_path=music_path,
                output_path=output_path,
                resolution=(
                    self.config.get("video.resolution.width", 1080),
                    self.config.get("video.resolution.height", 1920),
                ),
                fps=self.config.get("video.fps", 30),
            )

        return master

    async def _produce_stock_footage_video(
        self, content_id, account_id, niche_id, niche_config,
        script, has_voiceover, ts,
    ):
        """Produce stock footage video: voiceover FIRST → Pexels clips → Remotion render with hook cards."""
        from ..utils.ffmpeg import apply_ken_burns, get_duration
        from ..utils.remotion_renderer import render_stock_video
        from ..utils.stock_footage import get_stock_clip_for_scene

        scenes = script.get("scenes", [])
        if not scenes:
            raise RuntimeError("Script has no 'scenes' array for stock_footage style")

        # --- VOICEOVER FIRST ---
        audio_path = None
        audio_duration = None
        if has_voiceover and script.get("voiceover_script"):
            logger.info("[%s] Step 3a: Generating voiceover FIRST...", account_id)
            voice_config = niche_config.get("voice", {})
            voice_id = script.get("_voice_id_override") or voice_config.get("voice_id", "onyx")
            audio_path = await self.audio.generate_voiceover(
                text=script["voiceover_script"],
                voice_id=voice_id,
                output_name=f"content_{content_id}_vo_{ts}",
                provider=voice_config.get("provider", "elevenlabs"),
                speed=voice_config.get("speed"),
                niche_id=niche_id,
            )
            audio_duration = await get_duration(audio_path)
            logger.info("[%s] Voiceover duration: %.1fs", account_id, audio_duration)

        # --- SCALE SCENE DURATIONS ---
        # Account for crossfade overhead: TransitionSeries crossfades overlap adjacent
        # scenes, so visible = sum(durations) - (N-1) * crossfade.
        # We need sum(durations) >= audio_duration + (N-1) * crossfade + buffer.
        raw_total = sum(float(s.get("duration", 7)) for s in scenes)
        crossfade_dur_val = niche_config.get("visual", {}).get("transition_duration", 0.5)
        num_crossfades = max(0, len(scenes) - 1)
        crossfade_overhead = num_crossfades * crossfade_dur_val
        if audio_duration and raw_total > 0:
            target_total = audio_duration + crossfade_overhead + 1.0
            scale_factor = target_total / raw_total
            for scene in scenes:
                orig = float(scene.get("duration", 7))
                scene["duration"] = round(orig * scale_factor, 1)
            new_total = sum(float(s["duration"]) for s in scenes)
            logger.info(
                "[%s] Scaled scene durations: %.1fs → %.1fs (voiceover: %.1fs, crossfade overhead: %.1fs)",
                account_id, raw_total, new_total, audio_duration, crossfade_overhead,
            )

        # --- FETCH CLIPS (stock footage or AI-generated) ---
        visual_config = niche_config.get("visual", {})
        logger.info("[%s] Step 3b: Fetching %d clips (source: %s)...", account_id, len(scenes), visual_config.get("footage_source", "pexels"))

        import os
        pexels_key = self.config.get("api.pexels.key", "")
        if not pexels_key:
            pexels_key = os.environ.get("PEXELS_API_KEY", "")

        clip_dir = self.config.media_dir / "clips"
        clip_dir.mkdir(parents=True, exist_ok=True)
        cache_dir = self.config.media_dir / "stock_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        resolution = (
            self.config.get("video.resolution.width", 1080),
            self.config.get("video.resolution.height", 1920),
        )

        stock_clips = []
        text_overlays = []
        clip_durations = []

        # AI video generation setup (ComfyUI/fal via MediaProducer)
        footage_source = visual_config.get("footage_source", "pexels")
        ai_video_available = footage_source == "ai_video"
        strict_mode = os.environ.get("GOLD_STRICT_MODE", "") == "1"

        # Check if AI video backend (ComfyUI/fal) is available
        if ai_video_available:
            use_comfyui = await self.media._should_use_comfyui()
            if not use_comfyui and strict_mode:
                raise RuntimeError(
                    f"[{account_id}] STRICT MODE: footage_source=ai_video but video backend unavailable."
                )
            if not use_comfyui:
                logger.warning("[%s] AI video backend unavailable, falling back to Pexels", account_id)
                ai_video_available = False

        for i, scene in enumerate(scenes):
            duration = float(scene.get("duration", 7))
            text_overlay = scene.get("text_overlay", "")
            search_query = scene.get("search_keywords", scene.get("image_prompt", "stock footage"))

            clip_path = clip_dir / f"content_{content_id}_stock_{i}_{ts}.mp4"

            result = None

            # Option 1: AI video generation (LTX-2.3 via ComfyUI or Kling via fal)
            if ai_video_available:
                video_prompt = scene.get("image_prompt", search_query)
                clip_name = f"content_{content_id}_stock_{i}_{ts}"
                try:
                    result = await self.media.generate_video_clip(
                        prompt=video_prompt,
                        output_name=clip_name,
                        duration=str(min(duration, 10)),
                        aspect_ratio="9:16",
                    )
                    if result:
                        logger.info("[%s] Scene %d/%d: AI video (%.1fs)", account_id, i + 1, len(scenes), duration)
                except Exception as e:
                    if strict_mode:
                        raise RuntimeError(
                            f"[{account_id}] STRICT MODE: AI video failed for scene {i+1}: {e}"
                        ) from e
                    logger.warning("[%s] AI video failed for scene %d: %s — falling back", account_id, i + 1, e)
                    result = None

            # Option 2: Pexels stock footage (default or fallback)
            if result is None and pexels_key:
                try:
                    result = await get_stock_clip_for_scene(
                        query=search_query,
                        api_key=pexels_key,
                        output_path=clip_path,
                        target_duration=duration,
                        cache_dir=cache_dir,
                        resolution=resolution,
                    )
                except Exception as e:
                    logger.warning("[%s] Pexels search failed for scene %d: %s", account_id, i + 1, e)

            # Fallback 3: AI image + Ken Burns
            if result is None:
                logger.info("[%s] Scene %d: AI image + Ken Burns", account_id, i + 1)
                image_prompt = scene.get("image_prompt", "abstract background")
                img_path = await self.media.generate_image(
                    prompt=image_prompt,
                    output_name=f"content_{content_id}_fallback_{i}_{ts}",
                    width=resolution[0], height=resolution[1],
                )
                effect = scene.get("ken_burns", "zoom_in")
                await apply_ken_burns(
                    image_path=img_path, output_path=clip_path,
                    duration=duration, effect=effect,
                    resolution=resolution,
                    fps=self.config.get("video.fps", 30),
                )

            stock_clips.append(clip_path)
            text_overlays.append(text_overlay)
            clip_durations.append(duration)

        if not stock_clips:
            raise RuntimeError("No stock clips produced")

        # --- SUBTITLES (JSON word list for Remotion) ---
        subtitle_words = []
        if has_voiceover and script.get("voiceover_script") and audio_path:
            logger.info("[%s] Step 4: Generating word timestamps for Remotion...", account_id)
            subtitle_words = self.subtitles.get_word_timestamps(audio_path)

        # --- BACKGROUND MUSIC ---
        music_path = await self.audio.get_context_music(script, niche_config)

        # --- COMPOSE via Remotion (includes niche-specific hook cards) ---
        logger.info("[%s] Step 5: Rendering stock footage video via Remotion...", account_id)
        output_dir = self.config.media_dir / "rendered"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"content_{content_id}_master_{ts}.mp4"

        visual_config = niche_config.get("visual", {})
        crossfade_dur = visual_config.get("transition_duration", 0.5)
        accent_color = visual_config.get("accent_color", "#0ea5e9")
        hook_text = script.get("hook_text", "")
        if not hook_text:
            # Fallback: read hook from DB (set during content creation from script/idea)
            session = get_sync_session()
            db_content = session.query(Content).filter_by(id=content_id).first()
            if db_content and db_content.hook:
                hook_text = db_content.hook
                logger.info("[%s] Using hook from DB: %s", account_id, hook_text[:50])

        # Extract part info from title for multi-part stories
        title = script.get("title", "")
        part_number, total_parts = _extract_part_info(title)

        # Detect emoji beats from script and subtitle words
        voiceover_script = script.get("voiceover_script", "")
        emoji_beats = detect_emoji_beats(voiceover_script, subtitle_words)

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

        # Post-process: apply niche-specific visual treatments (color grade, vignette, grain)
        from ..utils.ffmpeg import build_visual_treatment_filter, run_ffmpeg
        treatment_filter = build_visual_treatment_filter(visual_config)
        if treatment_filter:
            logger.info("[%s] Applying visual treatments: %s", account_id, treatment_filter)
            treated_path = output_path.with_name(output_path.stem + "_treated.mp4")
            await run_ffmpeg([
                "-i", str(output_path),
                "-vf", treatment_filter,
                "-c:a", "copy",
                "-c:v", "libx264", "-crf", "20", "-preset", "medium",
                "-maxrate", "4M", "-bufsize", "8M",
                str(treated_path),
            ])
            # Replace original with treated version
            treated_path.replace(output_path)

        # SFX overlay — add transition and hook sound effects
        from ..utils.sound_design import build_sfx_filter_chain
        scene_timestamps = [sum(clip_durations[:i]) for i in range(len(clip_durations))]
        sfx_inputs, sfx_filters, sfx_label = build_sfx_filter_chain(
            niche_id, scene_timestamps, audio_duration,
        )
        if sfx_inputs and sfx_label:
            logger.info("[%s] Adding SFX overlay (%d effects)", account_id, len(sfx_inputs) // 2)
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

        # Loudness normalization — target -14 LUFS (YouTube standard)
        logger.info("[%s] Normalizing audio loudness to -14 LUFS", account_id)
        normalized_path = output_path.with_name(output_path.stem + "_loud.mp4")
        await run_ffmpeg([
            "-i", str(output_path),
            "-c:v", "copy",
            "-af", "loudnorm=I=-14:TP=-1:LRA=11",
            str(normalized_path),
        ])
        normalized_path.replace(output_path)

        return output_path

    async def _produce_ai_clips_video(
        self, content_id, account_id, niche_config, script, ts,
    ):
        """Produce a video from AI-generated clips with text overlays and music."""
        from ..utils.ffmpeg import compose_clips_video

        clips_data = script.get("clips", [])
        if not clips_data:
            raise RuntimeError("Script has no 'clips' array for ai_clips video style")

        logger.info(
            "[%s] Step 3: Generating %d AI video clips...", account_id, len(clips_data)
        )
        clip_paths = []
        text_overlays = []

        for i, clip_info in enumerate(clips_data):
            video_prompt = clip_info.get("video_prompt", "")
            if not video_prompt:
                continue

            duration = str(clip_info.get("duration", "5"))
            text_overlay = clip_info.get("text_overlay", "")

            logger.info(
                "[%s] Generating clip %d/%d (duration=%ss): %s",
                account_id, i + 1, len(clips_data), duration,
                video_prompt[:80] + "..." if len(video_prompt) > 80 else video_prompt,
            )

            clip_path = await self.media.generate_video_clip(
                prompt=video_prompt,
                output_name=f"content_{content_id}_clip_{i}_{ts}",
                duration=duration,
                aspect_ratio="9:16",
            )
            clip_paths.append(clip_path)
            text_overlays.append(text_overlay)

        if not clip_paths:
            raise RuntimeError("No clips were generated successfully")

        logger.info("[%s] Step 4: Getting background music...", account_id)
        music_path = await self.audio.get_context_music(script, niche_config)

        logger.info("[%s] Step 5: Composing AI clips video...", account_id)
        output_dir = self.config.media_dir / "rendered"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"content_{content_id}_master_{ts}.mp4"

        master = await compose_clips_video(
            clip_paths=clip_paths,
            text_overlays=text_overlays,
            music_path=music_path,
            output_path=output_path,
            resolution=(
                self.config.get("video.resolution.width", 1080),
                self.config.get("video.resolution.height", 1920),
            ),
            fps=self.config.get("video.fps", 30),
        )

        return master

    async def _produce_cinematic_doc_video(
        self, content_id, account_id, niche_config, script, ts,
    ):
        """Produce long-form cinematic documentary video.

        Pipeline: voiceover FIRST → scale 20-30 scene durations → for each scene
        try Pexels stock footage, fallback to AI image + i2v animation → compose
        all clips with voiceover + subtitles + background music.
        """
        from ..utils.ffmpeg import apply_ken_burns, compose_stock_video, get_duration
        from ..utils.stock_footage import get_stock_clip_for_scene

        scenes = script.get("scenes", [])
        if not scenes:
            raise RuntimeError("Script has no 'scenes' array for cinematic_doc style")

        visual_config = niche_config.get("visual", {})
        footage_source = visual_config.get("footage_source", "pexels")
        fallback_mode = visual_config.get("fallback", "ai_image")
        footage_orientation = visual_config.get("footage_orientation", "portrait")

        resolution = (
            self.config.get("video.resolution.width", 1080),
            self.config.get("video.resolution.height", 1920),
        )
        fps = self.config.get("video.fps", 30)

        # --- VOICEOVER FIRST (determines total video length) ---
        audio_path = None
        audio_duration = None
        voice_config = niche_config.get("voice", {})
        if script.get("voiceover_script"):
            logger.info("[%s] Step 3a: Generating voiceover FIRST (long-form)...", account_id)
            voice_id = script.get("_voice_id_override") or voice_config.get("voice_id", "onyx")
            _niche_id = niche_config.get("niche", {}).get("id", "")
            audio_path = await self.audio.generate_voiceover(
                text=script["voiceover_script"],
                voice_id=voice_id,
                output_name=f"content_{content_id}_vo_{ts}",
                provider=voice_config.get("provider", "elevenlabs"),
                speed=voice_config.get("speed"),
                niche_id=_niche_id,
            )
            audio_duration = await get_duration(audio_path)
            logger.info("[%s] Voiceover duration: %.1fs (%.1f min)", account_id, audio_duration, audio_duration / 60)

        # --- SCALE SCENE DURATIONS to match voiceover ---
        raw_total = sum(float(s.get("duration", 7)) for s in scenes)
        if audio_duration and raw_total > 0:
            target_total = audio_duration + 2.0  # small buffer
            scale_factor = target_total / raw_total
            for scene in scenes:
                orig = float(scene.get("duration", 7))
                scene["duration"] = round(orig * scale_factor, 1)
            new_total = sum(float(s["duration"]) for s in scenes)
            logger.info(
                "[%s] Scaled %d scene durations: %.1fs → %.1fs (voiceover: %.1fs)",
                account_id, len(scenes), raw_total, new_total, audio_duration,
            )

        # --- FETCH/GENERATE CLIPS (Pexels stock + AI fallback) ---
        logger.info("[%s] Step 3b: Generating %d clips for cinematic doc...", account_id, len(scenes))

        import os
        pexels_key = self.config.get("api.pexels.key", "") or os.environ.get("PEXELS_API_KEY", "")

        clip_dir = self.config.media_dir / "clips"
        clip_dir.mkdir(parents=True, exist_ok=True)
        cache_dir = self.config.media_dir / "stock_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        stock_clips = []
        text_overlays = []
        clip_durations = []

        # AI video generation setup (ComfyUI/fal via MediaProducer)
        ai_video_available = footage_source == "ai_video"
        strict_mode = os.environ.get("GOLD_STRICT_MODE", "") == "1"

        # Check if AI video backend (ComfyUI/fal) is available
        if ai_video_available:
            use_comfyui = await self.media._should_use_comfyui()
            if not use_comfyui and strict_mode:
                raise RuntimeError(
                    f"[{account_id}] STRICT MODE: footage_source=ai_video but video backend unavailable."
                )
            if not use_comfyui:
                logger.warning("[%s] AI video backend unavailable, falling back to Pexels", account_id)
                ai_video_available = False

        for i, scene in enumerate(scenes):
            duration = float(scene.get("duration", 7))
            text_overlay = scene.get("text_overlay", "")
            search_query = scene.get("search_keywords", scene.get("image_prompt", "stock footage"))
            clip_path = clip_dir / f"content_{content_id}_doc_{i}_{ts}.mp4"

            result = None

            # Option 1: AI video generation (LTX-2.3 via ComfyUI or Kling via fal)
            if ai_video_available:
                video_prompt = scene.get("image_prompt", search_query)
                clip_name = f"content_{content_id}_doc_{i}_{ts}"
                try:
                    result = await self.media.generate_video_clip(
                        prompt=video_prompt,
                        output_name=clip_name,
                        duration=str(min(duration, 10)),
                        aspect_ratio="9:16",
                    )
                    if result:
                        logger.info("[%s] Scene %d/%d: AI video clip (%.1fs)", account_id, i + 1, len(scenes), duration)
                except Exception as e:
                    if strict_mode:
                        raise RuntimeError(
                            f"[{account_id}] STRICT MODE: AI video failed for scene {i+1}: {e}"
                        ) from e
                    logger.warning("[%s] AI video failed for scene %d: %s — falling back", account_id, i + 1, e)
                    result = None

            # Option 2: Pexels stock footage
            if result is None and pexels_key:
                try:
                    result = await get_stock_clip_for_scene(
                        query=search_query,
                        api_key=pexels_key,
                        output_path=clip_path,
                        target_duration=duration,
                        cache_dir=cache_dir,
                        resolution=resolution,
                    )
                    if result:
                        logger.info("[%s] Scene %d/%d: Pexels clip (%.1fs)", account_id, i + 1, len(scenes), duration)
                except Exception as e:
                    logger.warning("[%s] Pexels failed for scene %d: %s", account_id, i + 1, e)

            # Fallback: AI image + animation (i2v or Ken Burns)
            if result is None:
                image_prompt = scene.get("image_prompt", "abstract cinematic background")
                logger.info("[%s] Scene %d/%d: AI fallback → generating image...", account_id, i + 1, len(scenes))

                if fallback_mode == "ai_image":
                    # Generate image then animate with i2v (ComfyUI/fal) or Ken Burns
                    img_path, img_url = await self.media.generate_image(
                        prompt=image_prompt,
                        output_name=f"content_{content_id}_doc_img_{i}_{ts}",
                        width=resolution[0], height=resolution[1],
                        return_url=True,
                    )

                    # Try i2v animation first (more cinematic), fall back to Ken Burns
                    motion_prompt = scene.get("motion_prompt", "slow cinematic camera movement")
                    try:
                        clip_path = await self.media.generate_video_from_image(
                            image_url=img_url,
                            prompt=motion_prompt,
                            output_name=f"content_{content_id}_doc_clip_{i}_{ts}",
                            duration=str(min(duration, 10)),  # i2v clips max ~10s
                            aspect_ratio="9:16",
                        )
                    except Exception as e:
                        logger.warning("[%s] Scene %d i2v failed, using Ken Burns: %s", account_id, i + 1, e)
                        effect = scene.get("ken_burns", "zoom_in")
                        await apply_ken_burns(
                            image_path=img_path, output_path=clip_path,
                            duration=duration, effect=effect,
                            resolution=resolution, fps=fps,
                        )
                else:
                    # Pure Ken Burns fallback
                    img_path = await self.media.generate_image(
                        prompt=image_prompt,
                        output_name=f"content_{content_id}_doc_img_{i}_{ts}",
                        width=resolution[0], height=resolution[1],
                    )
                    effect = scene.get("ken_burns", "zoom_in")
                    await apply_ken_burns(
                        image_path=img_path, output_path=clip_path,
                        duration=duration, effect=effect,
                        resolution=resolution, fps=fps,
                    )

            stock_clips.append(clip_path)
            text_overlays.append(text_overlay)
            clip_durations.append(duration)

        if not stock_clips:
            raise RuntimeError("No clips produced for cinematic doc")

        # --- SUBTITLES ---
        subtitle_path = None
        if script.get("voiceover_script") and audio_path:
            logger.info("[%s] Step 4: Generating subtitles...", account_id)
            subtitle_dir = self.config.media_dir / "subtitles"
            subtitle_dir.mkdir(parents=True, exist_ok=True)
            subtitle_path = subtitle_dir / f"content_{content_id}_subs_{ts}.ass"
            self._generate_subtitles(script["voiceover_script"], audio_path, subtitle_path)

        # --- BACKGROUND MUSIC ---
        music_path = await self.audio.get_context_music(script, niche_config)

        # --- COMPOSE ---
        logger.info("[%s] Step 5: Composing cinematic doc video (%d clips)...", account_id, len(stock_clips))
        output_dir = self.config.media_dir / "rendered"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"content_{content_id}_master_{ts}.mp4"

        crossfade_dur = visual_config.get("transition_duration", 0.5)

        await compose_stock_video(
            clip_paths=stock_clips,
            clip_durations=clip_durations,
            text_overlays=text_overlays,
            audio_path=audio_path,
            music_path=music_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
            total_duration=audio_duration,
            crossfade_duration=crossfade_dur,
            resolution=resolution,
            fps=fps,
        )

        return output_path

    async def _produce_kenburns_video(
        self, content_id, account_id, niche_config,
        script, has_voiceover, ts,
    ):
        """Produce a video using AI images + Ken Burns effects (legacy/fallback)."""
        from ..utils.ffmpeg import get_duration

        logger.info("[%s] Step 3: Generating scene images...", account_id)
        scenes = script.get("scenes", [])
        ken_burns_effects = ["zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"]
        video_clips = []
        for i, scene in enumerate(scenes):
            image = await self.media.generate_image(
                prompt=scene.get("image_prompt", scene.get("description", "")),
                output_name=f"content_{content_id}_scene_{i}_{ts}",
            )
            effect = scene.get("ken_burns", ken_burns_effects[i % len(ken_burns_effects)])
            duration = scene.get("duration", 5)
            clip = await self.renderer.render_ken_burns(
                image_path=image,
                duration=duration,
                effect=effect,
                output_name=f"content_{content_id}_kb_{i}_{ts}",
            )
            video_clips.append(clip)

        slideshow = await self.renderer.render_slideshow(
            clips=video_clips,
            output_name=f"content_{content_id}_slideshow_{ts}",
        )

        audio_path = None
        if has_voiceover and script.get("voiceover_script"):
            voice_config = niche_config.get("voice", {})
            audio_path = await self.audio.generate_voiceover(
                text=script["voiceover_script"],
                voice_id=voice_config.get("voice_id", "onyx"),
                output_name=f"content_{content_id}_vo_{ts}",
                provider=voice_config.get("provider", "elevenlabs"),
                speed=voice_config.get("speed"),
                niche_id=niche_id,
            )

        music_path = await self.audio.get_context_music(script, niche_config)

        subtitle_path = None
        if has_voiceover and script.get("voiceover_script") and audio_path:
            audio_duration = await get_duration(audio_path)
            subtitle_dir = self.config.media_dir / "subtitles"
            subtitle_dir.mkdir(parents=True, exist_ok=True)
            subtitle_path = subtitle_dir / f"content_{content_id}_subs_{ts}.ass"
            self._generate_subtitles(script["voiceover_script"], audio_path, subtitle_path)

        master = await self.renderer.render(
            video_clips=[slideshow],
            audio_path=audio_path,
            music_path=music_path,
            subtitle_path=subtitle_path,
            output_name=f"content_{content_id}_master_{ts}",
        )

        return master
