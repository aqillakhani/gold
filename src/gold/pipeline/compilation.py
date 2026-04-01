"""CompilationPipeline v2: themed viral compilations with original audio.

Format:
  [0-3s]   HOOK: Best clip teaser (original audio, "Wait for it..." text)
  [3-5s]   TITLE CARD: Theme title + narration
  [5-17s]  CLIP 1: Original audio + small context text at top
  [17-19s] TRANSITION: Narration bridge on dark card
  [19-31s] CLIP 2: Original audio + context text
  ...
  [55-60s] OUTRO CARD: "Follow for more" + narration

Key principles:
  - Original clip audio is PRESERVED (the content IS the audio)
  - Narration ONLY during transition cards between clips (never over clips)
  - Each compilation has ONE cohesive theme
  - Best clip first (hook) + best clip near end (completion retention)
  - 60-65s total (just over TikTok 1min+ threshold)
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import Config
from ..models.content import Content, ContentStatus, ContentVariant
from ..models.db import get_sync_session
from .audio import AudioProducer
from .variation import PlatformVariator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Themed compilation templates
# ---------------------------------------------------------------------------

THEMES = [
    {
        "name": "Shark Encounters",
        "title_template": "{n} Shark Encounters That Will Haunt Your Dreams",
        "queries": ["shark attack", "shark encounter", "shark close call", "shark diver"],
        "subreddits": ["NatureIsMetal", "SweatyPalms", "thalassophobia", "TheDepthsBelow"],
    },
    {
        "name": "Near Death Close Calls",
        "title_template": "{n} Near Death Experiences Caught on Camera",
        "queries": ["near death", "close call caught on camera", "almost died", "inches from death"],
        "subreddits": ["SweatyPalms", "CrazyFuckingVideos", "nextfuckinglevel"],
    },
    {
        "name": "Bear Encounters",
        "title_template": "{n} Terrifying Bear Encounters That Will Make You Stay Indoors",
        "queries": ["bear attack", "bear encounter", "bear charge", "grizzly encounter"],
        "subreddits": ["NatureIsMetal", "SweatyPalms", "CrazyFuckingVideos"],
    },
    {
        "name": "Ocean Predators",
        "title_template": "{n} Ocean Moments That Prove the Deep Is Terrifying",
        "queries": ["ocean predator", "deep sea creature", "whale encounter", "giant squid"],
        "subreddits": ["NatureIsMetal", "thalassophobia", "TheDepthsBelow", "NatureIsLit"],
    },
    {
        "name": "Extreme Weather",
        "title_template": "{n} Times Mother Nature Showed Her Fury",
        "queries": ["tornado caught on camera", "lightning strike", "tsunami wave", "extreme storm"],
        "subreddits": ["NatureIsMetal", "CrazyFuckingVideos", "Damnthatsinteresting", "nextfuckinglevel"],
    },
    {
        "name": "Insane Animal Attacks",
        "title_template": "{n} Animal Attacks You Won't Believe Were Caught on Camera",
        "queries": ["animal attack", "lion attack", "crocodile attack", "wild animal charge"],
        "subreddits": ["NatureIsMetal", "CrazyFuckingVideos", "SweatyPalms"],
    },
    {
        "name": "Survival Moments",
        "title_template": "{n} Survival Moments That Gave Everyone Chills",
        "queries": ["survival caught on camera", "miracle save", "rescued just in time", "seconds from disaster"],
        "subreddits": ["SweatyPalms", "nextfuckinglevel", "CrazyFuckingVideos", "Damnthatsinteresting"],
    },
    {
        "name": "Insane Car Crashes",
        "title_template": "{n} Dashcam Moments That Will Make You Drive Slower",
        "queries": ["dashcam crash", "car accident caught on camera", "insane car crash", "near miss driving"],
        "subreddits": ["CrazyFuckingVideos", "IdiotsInCars", "SweatyPalms"],
    },
]


@dataclass
class ClipInfo:
    """Metadata for a single source clip."""

    reddit_id: str
    title: str
    url: str
    subreddit: str
    score: int
    media_url: str
    downloaded_path: Path | None = None
    portrait_path: Path | None = None
    duration: float = 0.0


class CompilationPipeline:
    """Creates themed viral compilations with original audio preserved."""

    def __init__(self, config: Config):
        self.config = config
        self.audio = AudioProducer(config)
        self.variator = PlatformVariator(config)

    async def create_compilation(
        self,
        account_id: str,
        niche_id: str = "dangerous_nature",
        clip_count: int = 4,
        theme: dict | None = None,
    ) -> Content | None:
        """Create a single themed compilation end-to-end."""
        niche_config = self.config.niches.get(niche_id, {})
        comp_config = niche_config.get("compilation", {})
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        # Pick a theme
        if theme is None:
            theme = random.choice(THEMES)
        logger.info("[%s] Theme: %s", niche_id, theme["name"])

        # 1. Discover themed clips (try up to 3 themes if first one has too few)
        clips: list[ClipInfo] = []
        themes_tried: list[str] = []
        for attempt in range(3):
            logger.info("[%s] Step 1: Searching Reddit for '%s' clips (attempt %d)...",
                        niche_id, theme["name"], attempt + 1)
            clips = await self._discover_themed_clips(theme, clip_count + 3)
            themes_tried.append(theme["name"])
            if len(clips) >= 3:
                break
            logger.warning("[%s] Only %d clips for '%s', trying another theme...",
                           niche_id, len(clips), theme["name"])
            theme = random.choice([t for t in THEMES if t["name"] not in themes_tried])

        if len(clips) < 3:
            logger.error("[%s] Tried %d themes, not enough clips found", niche_id, len(themes_tried))
            return None

        # 2. Download clips
        logger.info("[%s] Step 2: Downloading %d clips...", niche_id, len(clips))
        clips = await self._download_clips(clips, ts)
        clips = [c for c in clips if c.downloaded_path and c.downloaded_path.exists()]
        if len(clips) < 3:
            logger.error("[%s] Only %d clips downloaded", niche_id, len(clips))
            return None

        # 3. Convert to portrait
        logger.info("[%s] Step 3: Converting to portrait...", niche_id)
        clips = await self._convert_to_portrait(clips)
        clips = [c for c in clips if c.portrait_path and c.portrait_path.exists() and c.duration > 3]
        if len(clips) < 3:
            logger.error("[%s] Only %d valid portrait clips", niche_id, len(clips))
            return None

        # Take the best clips (by score), limit to clip_count
        clips = sorted(clips, key=lambda c: c.score, reverse=True)[:clip_count]

        # 4. Order clips for maximum retention
        clips = self._order_for_retention(clips)
        logger.info("[%s] Using %d clips, ordered for retention", niche_id, len(clips))
        for i, c in enumerate(clips):
            logger.info("  Clip %d: [%d pts] %s (%.1fs)", i + 1, c.score, c.title[:50], c.duration)

        # 5. Generate transition narration scripts
        logger.info("[%s] Step 4: Generating transition scripts...", niche_id)
        title = theme["title_template"].format(n=len(clips))
        transitions = await self._generate_transitions(clips, theme, title)

        # Create DB record
        session = get_sync_session()
        content = Content(
            account_id=account_id,
            niche=niche_id,
            title=title,
            hook=transitions.get("hook_text", ""),
            script=json.dumps(transitions),
            scene_descriptions=json.dumps([
                {"reddit_id": c.reddit_id, "title": c.title, "subreddit": c.subreddit, "score": c.score}
                for c in clips
            ]),
            status=ContentStatus.GENERATING,
        )
        session.add(content)
        session.commit()
        content_id = content.id

        try:
            # 6. Generate transition audio segments
            logger.info("[%s] Step 5: Generating transition voiceovers...", niche_id)
            voice_config = niche_config.get("voice", {})
            voice_id = voice_config.get("voice_id", "onyx")
            provider = voice_config.get("provider", "fish")

            transition_segments = await self._generate_transition_audio(
                transitions, content_id, ts, voice_id, provider, niche_id,
            )

            # 7. Build video segments (clips with original audio + transition cards)
            logger.info("[%s] Step 6: Building video segments...", niche_id)
            segment_dir = self.config.media_dir / "clips" / f"compilation_{content_id}"
            segment_dir.mkdir(parents=True, exist_ok=True)

            segments = await self._build_segments(
                clips, transitions, transition_segments,
                segment_dir, ts,
            )

            # 8. Background music
            logger.info("[%s] Step 7: Fetching background music...", niche_id)
            music_path = await self.audio.get_context_music(
                {"voiceover_script": title, "music_tags": ["dark_ambient", "tension", "cinematic"]},
                niche_config,
            )

            # 9. Concat all segments + add background music
            logger.info("[%s] Step 8: Composing final compilation...", niche_id)
            output_dir = self.config.media_dir / "rendered"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"content_{content_id}_master_{ts}.mp4"

            from ..utils.ffmpeg import concat_segments_with_music
            master = await concat_segments_with_music(
                segment_paths=segments,
                music_path=music_path,
                output_path=output_path,
                music_volume=niche_config.get("music_volume", 0.15),
            )

            from ..utils.ffmpeg import get_duration
            duration = await get_duration(master)
            logger.info("[%s] Final video: %.1fs", niche_id, duration)

            # 10. Platform variants
            logger.info("[%s] Step 9: Creating platform variants...", niche_id)
            variant_paths = await self.variator.create_variants(master, content_id)

            # Save to DB
            hashtags = niche_config.get("hashtags", [])
            if transitions.get("hashtags"):
                hashtags = transitions["hashtags"]
            captions = niche_config.get("cta", {})

            for platform, path in variant_paths.items():
                variant = ContentVariant(
                    content_id=content_id,
                    platform=platform,
                    video_path=str(path),
                    caption=captions.get(platform, ""),
                    hashtags=json.dumps(hashtags),
                )
                session.add(variant)

            content.master_video_path = str(master)
            content.duration_seconds = duration
            content.status = ContentStatus.READY
            session.commit()

            logger.info(
                "[%s] Compilation #%d READY: %s (%.1fs, %d clips)",
                niche_id, content_id, title, duration, len(clips),
            )
            return content

        except Exception as e:
            logger.error("[%s] Pipeline failed: %s", niche_id, e, exc_info=True)
            content.status = ContentStatus.FAILED
            session.commit()
            return None
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Step helpers
    # ------------------------------------------------------------------

    async def _discover_themed_clips(
        self, theme: dict, limit: int,
    ) -> list[ClipInfo]:
        """Search Reddit for clips matching a specific theme."""
        import httpx

        all_clips: list[ClipInfo] = []
        seen_ids: set[str] = set()

        for subreddit in theme["subreddits"]:
            for query in theme["queries"]:
                try:
                    url = f"https://www.reddit.com/r/{subreddit}/search.json"
                    params = {
                        "q": query,
                        "restrict_sr": "on",
                        "sort": "top",
                        "t": "year",
                        "limit": 25,
                    }
                    async with httpx.AsyncClient(timeout=15) as client:
                        resp = await client.get(
                            url,
                            params=params,
                            headers={"User-Agent": "Gold/1.0 (Content Research)"},
                        )
                        resp.raise_for_status()
                        data = resp.json()

                    for child in data.get("data", {}).get("children", []):
                        post = child.get("data", {})
                        post_id = post.get("id", "")
                        if post_id in seen_ids:
                            continue
                        seen_ids.add(post_id)

                        is_video = post.get("is_video", False)
                        media_url = ""
                        if is_video and post.get("media"):
                            media_url = post["media"].get("reddit_video", {}).get("fallback_url", "")
                        if not media_url:
                            ext_url = post.get("url", "")
                            if any(d in ext_url for d in ["v.redd.it", "youtube.com", "youtu.be", "streamable.com"]):
                                media_url = ext_url

                        if not media_url and not is_video:
                            continue

                        score = post.get("score", 0)
                        if score < 100:
                            continue

                        all_clips.append(ClipInfo(
                            reddit_id=post_id,
                            title=post.get("title", "Unknown"),
                            url=f"https://reddit.com{post.get('permalink', '')}",
                            subreddit=post.get("subreddit", subreddit),
                            score=score,
                            media_url=media_url or post.get("url", ""),
                        ))

                except Exception as e:
                    logger.warning("Search failed r/%s q='%s': %s", subreddit, query, str(e)[:100])

                # Rate limit: don't hammer Reddit
                import asyncio
                await asyncio.sleep(1.5)

        # Sort by score, dedupe, return top
        all_clips.sort(key=lambda c: c.score, reverse=True)
        logger.info("Found %d themed clips for '%s'", len(all_clips), theme["name"])
        return all_clips[:limit]

    async def _download_clips(
        self, clips: list[ClipInfo], ts: str,
    ) -> list[ClipInfo]:
        """Download clips via yt-dlp."""
        from ..utils.video_scraper import download_video

        clip_dir = self.config.media_dir / "clips" / "dangerous_nature"
        clip_dir.mkdir(parents=True, exist_ok=True)

        for i, clip in enumerate(clips):
            output_path = clip_dir / f"clip_{ts}_{i}_{clip.reddit_id}.mp4"
            try:
                # Use the Reddit post URL for yt-dlp (not DASH fallback URL)
                # yt-dlp properly merges video+audio from Reddit post URLs
                download_url = clip.url if "reddit.com" in clip.url else (clip.media_url or clip.url)
                result = await download_video(
                    url=download_url,
                    output_path=output_path,
                    max_duration=15,
                )
                clip.downloaded_path = result
                logger.info("  Downloaded %d/%d: %s", i + 1, len(clips), clip.title[:50])
            except Exception as e:
                logger.warning("  Failed clip %d: %s", i + 1, str(e)[:150])
                clip.downloaded_path = None

        return clips

    async def _convert_to_portrait(self, clips: list[ClipInfo]) -> list[ClipInfo]:
        """Convert clips to 9:16 portrait and measure duration."""
        from ..utils.ffmpeg import crop_to_portrait, get_duration

        for i, clip in enumerate(clips):
            if not clip.downloaded_path:
                continue
            portrait_path = clip.downloaded_path.with_name(
                clip.downloaded_path.stem + "_portrait.mp4"
            )
            try:
                await crop_to_portrait(clip.downloaded_path, portrait_path)
                clip.portrait_path = portrait_path
                clip.duration = await get_duration(portrait_path)
            except Exception as e:
                logger.warning("  Portrait failed clip %d: %s", i + 1, e)

        return clips

    def _order_for_retention(self, clips: list[ClipInfo]) -> list[ClipInfo]:
        """Order clips for maximum watch-through rate.

        Strategy: best clip first (hook), second-best near end (completion),
        weaker clips in the middle.
        """
        if len(clips) <= 2:
            return clips

        by_score = sorted(clips, key=lambda c: c.score, reverse=True)
        hook = by_score[0]          # best = first (hook)
        closer = by_score[1]        # second best = near end
        middle = by_score[2:]       # rest in middle
        random.shuffle(middle)

        return [hook] + middle + [closer]

    async def _generate_transitions(
        self, clips: list[ClipInfo], theme: dict, title: str,
    ) -> dict:
        """Generate short transition narration scripts via Claude."""
        import anthropic

        clips_desc = "\n".join([
            f"Clip {i + 1}: \"{c.title}\" (r/{c.subreddit}, {c.score} pts, {c.duration:.1f}s)"
            for i, c in enumerate(clips)
        ])

        prompt = f"""You are writing TRANSITION narration for a viral compilation video.

Theme: {theme['name']}
Title: {title}

CLIPS (in playback order):
{clips_desc}

Write SHORT transition narrations that play BETWEEN clips on dark transition cards.
The narration does NOT play over the clips — clips keep their original audio.

Rules:
- Title intro: 1 sentence, max 10 words, casual and exciting (plays over title card)
- Each transition: 1 sentence, max 15 words, casual and conversational — like a friend showing you crazy clips. Use words like "okay so", "honestly", "literally", "insane"
- Outro: 1 sentence, max 8 words, call to action
- Context labels: For each clip, write a 3-6 word label shown at the top of the clip (e.g., "Diver meets great white shark")
- Hook text: Shown over the first 3s teaser, max 5 words (e.g., "Wait for it...")
- Tone: Casual, excited, like you're texting a friend about something insane you just saw. NOT documentary style.

Return ONLY JSON:
{{
  "hook_text": "Wait for it...",
  "title_narration": "Nature's most dangerous moments caught on camera",
  "clip_labels": ["label for clip 1", "label for clip 2", ...],
  "transitions": ["bridge after clip 1", "bridge after clip 2", ...],
  "outro_narration": "Follow for more insane moments",
  "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5"]
}}"""

        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        try:
            result = json.loads(text.strip())
        except json.JSONDecodeError:
            logger.warning("Failed to parse transitions JSON, using defaults")
            result = {
                "hook_text": "Wait for it...",
                "title_narration": f"{theme['name']} caught on camera",
                "clip_labels": [c.title[:40] for c in clips],
                "transitions": ["But that's nothing compared to this..." for _ in clips],
                "outro_narration": "Follow for more",
                "hashtags": ["#NatureIsMetal", "#CaughtOnCamera", "#CloseCalls"],
            }

        return result

    async def _generate_transition_audio(
        self,
        transitions: dict,
        content_id: int,
        ts: str,
        voice_id: str,
        provider: str,
        niche_id: str,
    ) -> dict[str, Path]:
        """Generate separate audio files for each transition narration."""
        audio_dir = self.config.media_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        segments: dict[str, Path] = {}

        # Title narration
        title_text = transitions.get("title_narration", "")
        if title_text:
            path = await self.audio.generate_voiceover(
                text=title_text,
                voice_id=voice_id,
                output_name=f"comp_{content_id}_title_{ts}",
                provider=provider,
                niche_id=niche_id,
            )
            segments["title"] = path

        # Transition bridges
        for i, bridge in enumerate(transitions.get("transitions", [])):
            if not bridge:
                continue
            path = await self.audio.generate_voiceover(
                text=bridge,
                voice_id=voice_id,
                output_name=f"comp_{content_id}_bridge_{i}_{ts}",
                provider=provider,
                niche_id=niche_id,
            )
            segments[f"bridge_{i}"] = path

        # Outro narration
        outro_text = transitions.get("outro_narration", "")
        if outro_text:
            path = await self.audio.generate_voiceover(
                text=outro_text,
                voice_id=voice_id,
                output_name=f"comp_{content_id}_outro_{ts}",
                provider=provider,
                niche_id=niche_id,
            )
            segments["outro"] = path

        logger.info("Generated %d transition audio segments", len(segments))
        return segments

    async def _build_segments(
        self,
        clips: list[ClipInfo],
        transitions: dict,
        transition_audio: dict[str, Path],
        segment_dir: Path,
        ts: str,
    ) -> list[Path]:
        """Build video segments — narration embedded into clip starts, no blank screens.

        Format:
        [title_card, clip0_with_narr, clip1_with_narr, ..., clipN_with_narr, outro_card]

        Each clip has its bridge narration overlaid on the first few seconds,
        with original audio ducked during narration then fading back to full.
        Only title and outro use dark cards.
        """
        from ..utils.ffmpeg import (
            build_text_card_video,
            build_clip_with_label,
            get_duration,
        )

        segments: list[Path] = []
        resolution = (1080, 1920)
        fps = 30

        # Clips with narration embedded at start — NO blank screens at all
        clip_labels = transitions.get("clip_labels", [])
        bridges = transitions.get("transitions", [])

        for i, clip in enumerate(clips):
            label = clip_labels[i] if i < len(clip_labels) else ""
            clip_seg_path = segment_dir / f"clip_{i}_{ts}.mp4"

            if i == 0:
                # First clip: title narration overlaid on start (the hook)
                narr = transition_audio.get("title")
            else:
                # Subsequent clips: bridge narration from previous transition
                narr = transition_audio.get(f"bridge_{i - 1}")

            await build_clip_with_label(
                clip_path=clip.portrait_path,
                label_text=label,
                output_path=clip_seg_path,
                max_duration=clip.duration,
                label_position="top",
                narration_path=narr,
                resolution=resolution,
                fps=fps,
            )
            segments.append(clip_seg_path)

        # 3. Outro card (only other blank screen)
        outro_audio = transition_audio.get("outro")
        outro_dur = 3.0
        if outro_audio:
            outro_dur = max(3.0, await get_duration(outro_audio) + 0.5)
        outro_path = segment_dir / f"outro_{ts}.mp4"
        await build_text_card_video(
            text=transitions.get("outro_narration", "Follow for more!"),
            audio_path=outro_audio,
            output_path=outro_path,
            duration=outro_dur,
            resolution=resolution,
            fps=fps,
        )
        segments.append(outro_path)

        logger.info("Built %d segments for compilation", len(segments))
        return segments
