"""AudioProducer: Fish Audio, ElevenLabs, and OpenAI TTS for voiceover, background music."""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Any

import httpx

from ..config import Config
from ..utils.music_search import find_and_download_music
from ..utils.retry import retry

logger = logging.getLogger(__name__)


class AudioProducer:
    def __init__(self, config: Config):
        self.config = config
        self.fish_key = config.env("FISH_API_KEY")
        self.elevenlabs_key = config.env("ELEVENLABS_API_KEY")
        self.openai_key = config.env("OPENAI_API_KEY")
        self.media_dir = config.media_dir

    @retry(max_retries=2, base_delay=3.0, exceptions=(httpx.HTTPError,))
    async def generate_voiceover(
        self,
        text: str,
        voice_id: str,
        output_name: str = "voiceover",
        provider: str = "fish",
        speed: float | None = None,
        niche_id: str = "",
    ) -> Path:
        """Generate voiceover audio from text."""
        output_dir = self.media_dir / "audio"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{output_name}.mp3"

        if provider == "fish" and self.fish_key:
            logger.info("[TTS] Using Fish Audio (emotion markers enabled, niche=%s)", niche_id)
            await self._fish_tts(text, voice_id, output_path, speed=speed, niche_id=niche_id)
        elif provider == "elevenlabs" and self.elevenlabs_key:
            logger.warning("[TTS] FALLBACK to ElevenLabs — Fish Audio unavailable (no key?). Emotion markers LOST.")
            await self._elevenlabs_tts(text, voice_id, output_path)
        else:
            logger.warning("[TTS] FALLBACK to OpenAI — both Fish Audio and ElevenLabs unavailable. Emotion markers LOST.")
            await self._openai_tts(text, output_path)

        await self._post_process_voice(output_path)
        logger.info("Generated voiceover: %s (provider=%s)", output_path, provider)
        return output_path

    async def _post_process_voice(self, audio_path: Path) -> Path:
        """Apply EQ and loudness normalization to TTS output.

        Applies:
        - High-pass filter at 80Hz (removes rumble)
        - Low-pass filter at 12kHz (removes harsh artifacts)
        - Loudness normalization to -16 LUFS (perceptually consistent)

        Args:
            audio_path: Path to the generated voiceover audio file.

        Returns:
            Path to the processed audio file (original path, in-place replacement).
        """
        import asyncio
        import os

        processed = audio_path.with_name(audio_path.stem + "_eq" + audio_path.suffix)

        ffmpeg_bin = "ffmpeg"
        # Check WinGet FFmpeg path on Windows
        winget_ffmpeg = r"C:\Users\claws\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
        if os.path.exists(winget_ffmpeg):
            ffmpeg_bin = winget_ffmpeg

        cmd = [
            ffmpeg_bin,
            "-y", "-i", str(audio_path),
            "-af", "highpass=f=80,lowpass=f=12000,loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a", "libmp3lame", "-b:a", "192k",
            str(processed),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.warning("[TTS] Audio post-processing failed: %s", stderr.decode()[:200])
            return audio_path  # Return original on failure

        # Replace original with processed
        processed.replace(audio_path)
        logger.info("[TTS] Post-processed: EQ (80Hz-12kHz) + loudnorm (-16 LUFS)")
        return audio_path

    async def _elevenlabs_tts(self, text: str, voice_id: str, output: Path) -> None:
        model = self.config.get("api.elevenlabs.model", "eleven_multilingual_v2")
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": self.elevenlabs_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": model,
                    "voice_settings": {
                        "stability": 0.3,
                        "similarity_boost": 0.6,
                        "style": 0.8,
                        "use_speaker_boost": True,
                    },
                },
            )
            resp.raise_for_status()
            output.write_bytes(resp.content)

    # Niche-specific emotion markers for Fish Audio S1
    # These tags trigger expressive speech patterns in the TTS model
    NICHE_EMOTION_MARKERS = {
        "true_crime": {
            "sentence_end_tags": ["(dramatic pause)", "(breath)"],
            "question_tag": "(whisper)",
            "revelation_words": {
                "dead": "(lowered voice)",
                "murdered": "(lowered voice)",
                "discovered": "(dramatic pause)",
                "confession": "(dramatic pause)",
                "guilty": "(dramatic pause)",
                "evidence": "(breath)",
                "disappeared": "(lowered voice)",
                "body": "(lowered voice)",
            },
        },
        "reddit_stories": {
            "sentence_end_tags": ["(break)", "(breath)"],
            "question_tag": "(break)",
            "revelation_words": {
                "cheated": "(dramatic pause)",
                "betrayed": "(dramatic pause)",
                "kicked out": "(break)",
                "divorce": "(breath)",
                "fired": "(dramatic pause)",
            },
        },
        "betrayal_revenge": {
            "sentence_end_tags": ["(dramatic pause)", "(breath)"],
            "question_tag": "(dramatic pause)",
            "revelation_words": {
                "revenge": "(dramatic pause)",
                "betrayed": "(lowered voice)",
                "secret": "(whisper)",
                "truth": "(dramatic pause)",
                "exposed": "(breath)",
            },
        },
        "ai_tools": {
            "sentence_end_tags": ["(break)"],
            "question_tag": "(break)",
            "revelation_words": {},
        },
        "personal_finance": {
            "sentence_end_tags": ["(break)"],
            "question_tag": "(break)",
            "revelation_words": {
                "free": "(breath)",
                "thousand": "(dramatic pause)",
                "million": "(dramatic pause)",
            },
        },
        "english_learning": {
            "sentence_end_tags": ["(break)", "(break)"],  # extra pauses for learners
            "question_tag": "(break)",
            "revelation_words": {},
        },
        "dangerous_nature": {
            "sentence_end_tags": ["(break)"],  # light pauses, keep it flowing
            "question_tag": "(break)",
            "revelation_words": {
                "watch": "(excited)",
                "insane": "(excited)",
                "terrifying": "(breath)",
                "incredible": "(excited)",
                "massive": "(excited)",
                "deadly": "(breath)",
                "survived": "(excited)",
                "attacks": "(breath)",
                "close call": "(excited)",
            },
        },
    }

    @staticmethod
    def _add_prosody_markers(text: str, niche_id: str = "") -> str:
        """Insert Fish Audio paralanguage and emotion markers for expressive speech.

        Adds:
        - (breath) at paragraph breaks
        - (break) / (dramatic pause) between sentences (niche-specific)
        - Emotion markers before key revelation words (true_crime, betrayal, etc.)
        - (whisper) before questions in true crime for dramatic effect
        """
        import re

        # Add (breath) at paragraph boundaries (double newline or long gap)
        text = re.sub(r'\n\s*\n', ' (breath) ', text)

        # Get niche-specific markers
        niche_markers = AudioProducer.NICHE_EMOTION_MARKERS.get(niche_id, {})
        if niche_markers:
            logger.info("[EMOTION] Loaded %d emotion markers for niche=%s", len(niche_markers.get("revelation_words", {})), niche_id)
        else:
            logger.warning("[EMOTION] No emotion markers found for niche=%s — using bare defaults", niche_id)
        sentence_tags = niche_markers.get("sentence_end_tags", ["(break)"])
        question_tag = niche_markers.get("question_tag", "(break)")
        revelation_words = niche_markers.get("revelation_words", {})

        # Add sentence-end markers (cycle through available tags for variety)
        tag_idx = [0]

        def _get_next_tag() -> str:
            tag = sentence_tags[tag_idx[0] % len(sentence_tags)]
            tag_idx[0] += 1
            return tag

        # Add markers after sentences ending with . ! followed by uppercase
        text = re.sub(
            r'([.!])\s+(?=[A-Z])',
            lambda m: f'{m.group(1)} {_get_next_tag()} ',
            text,
        )

        # Questions get the question-specific tag
        text = re.sub(
            r'(\?)\s+(?=[A-Z])',
            lambda m: f'{m.group(1)} {question_tag} ',
            text,
        )

        # Insert emotion markers before revelation/key words (case-insensitive)
        for word, marker in revelation_words.items():
            # Only insert if not already preceded by a marker
            pattern = rf'(?<!\()(\b{re.escape(word)}\b)'
            text = re.sub(pattern, f'{marker} {word}', text, count=1, flags=re.IGNORECASE)

        # Clean up any double markers
        text = re.sub(r'\([^)]+\)\s*\([^)]+\)', lambda m: m.group(0).split(')')[0] + ')', text)

        return text.strip()

    async def _fish_tts(self, text: str, voice_id: str, output: Path, speed: float | None = None, niche_id: str = "") -> None:
        """Generate TTS via Fish Audio API (s1 model).

        Prosody params tuned for natural, expressive speech:
        - normalize=false: preserves natural intonation with paralanguage markers
        - temperature 0.8: more vocal variation for expressiveness
        - top_p 0.8: keeps prosody coherent while allowing expression
        - repetition_penalty 1.1: allows natural speech repetition
        - speed: from niche config (default 0.95 for slightly slower delivery)
        - niche_id: enables niche-specific emotion tags (dramatic pauses, whispers, etc.)
        """
        # Inject paralanguage + emotion markers for natural, expressive speech
        processed_text = self._add_prosody_markers(text, niche_id=niche_id)

        async with httpx.AsyncClient(timeout=120) as client:
            body: dict = {
                "text": processed_text,
                "format": "mp3",
                "mp3_bitrate": 192,
                "latency": "normal",
                "normalize": False,
                "temperature": 0.8,
                "top_p": 0.8,
                "repetition_penalty": 1.1,
                "speed": speed if speed is not None else 0.95,
            }
            if voice_id:
                body["reference_id"] = voice_id
            resp = await client.post(
                "https://api.fish.audio/v1/tts",
                headers={
                    "Authorization": f"Bearer {self.fish_key}",
                    "Content-Type": "application/json",
                    "model": "s1",
                },
                json=body,
            )
            resp.raise_for_status()
            output.write_bytes(resp.content)

    async def _openai_tts(self, text: str, output: Path) -> None:
        model = self.config.get("api.openai.tts_model", "tts-1")
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.openai_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "input": text,
                    "voice": "onyx",
                    "response_format": "mp3",
                },
            )
            resp.raise_for_status()
            output.write_bytes(resp.content)

    async def get_background_music(self, style: str = "ambient", output_name: str = "bgm") -> Path | None:
        """Get background music from local library. Returns None if no music available."""
        music_dir = self.media_dir / "audio" / "music"
        if not music_dir.exists():
            return None

        # Try style-specific match first (local files)
        for ext in ("mp3", "wav", "ogg"):
            matches = list(music_dir.glob(f"*{style}*.{ext}"))
            if matches:
                choice = random.choice(matches)
                logger.info("Selected local music: %s (from %d matches)", choice.name, len(matches))
                return choice

        # Fallback: any music file in the directory
        for ext in ("mp3", "wav", "ogg"):
            all_files = list(music_dir.glob(f"*.{ext}"))
            if all_files:
                choice = random.choice(all_files)
                logger.info("No '%s' music found, using fallback: %s", style, choice.name)
                return choice

        return None

    async def get_context_music(
        self,
        script: dict[str, Any],
        niche_config: dict[str, Any],
    ) -> Path | None:
        """Get context-aware background music based on the video's script content.

        Priority: Suno AI (custom per-video) → Jamendo (keyword search) → local library.

        Args:
            script: Script dict (may contain music_tags, music_speed from Claude).
            niche_config: Niche config dict with music.style fallback.

        Returns:
            Path to the music file, or None.
        """
        niche_id = niche_config.get("id", "")

        # 1. Try Suno AI first (generates unique track per video)
        suno_key = self.config.env("SUNO_API_KEY", "")
        if suno_key:
            from ..utils.suno_music import get_suno_music
            cache_dir = self.media_dir / "audio" / "music" / "suno"
            path = await get_suno_music(
                api_key=suno_key,
                niche_id=niche_id,
                cache_dir=cache_dir,
            )
            if path:
                return path
            logger.info("Suno failed, falling back to Jamendo")

        # 2. Try Jamendo (keyword-based search)
        music_tags = script.get("music_tags", [])
        music_speed = script.get("music_speed", "low")

        if not music_tags:
            music_tags = self._default_music_tags(niche_config)
            logger.info("No music_tags in script, using niche defaults: %s", music_tags)

        speed_overrides = {
            "personal_finance": "low",
            "ai_tools": "low",
            "true_crime": "low",
            "betrayal_revenge": "low",
            "english_learning": "verylow",
        }
        if niche_id in speed_overrides:
            music_speed = speed_overrides[niche_id]
            logger.info("Speed override for %s: %s", niche_id, music_speed)

        jamendo_id = self.config.env("JAMENDO_CLIENT_ID", "")
        if jamendo_id:
            cache_dir = self.media_dir / "audio" / "music" / "jamendo"
            path = await find_and_download_music(
                client_id=jamendo_id,
                tags=music_tags,
                speed=music_speed,
                cache_dir=cache_dir,
            )
            if path:
                return path
            logger.info("Jamendo returned no results, falling back to local library")

        # 3. Fallback: local library
        style = niche_config.get("music", {}).get("style", "ambient")
        return await self.get_background_music(style=style)

    @staticmethod
    def _default_music_tags(niche_config: dict[str, Any]) -> list[str]:
        """Generate default Jamendo music tags from niche config."""
        niche_id = niche_config.get("id", "")
        tone = niche_config.get("tone", "")
        music_style = niche_config.get("music", {}).get("style", "ambient")

        # Niche-specific sensible defaults
        # NOTE: Avoid "electronic" — Jamendo returns high-energy EDM that
        # competes with voiceover.  Prefer ambient/chillout/cinematic.
        defaults: dict[str, list[str]] = {
            "personal_finance": ["ambient", "inspiring", "soft", "cinematic"],
            "ai_tools": ["ambient", "chillout", "soft", "cinematic"],
            "true_crime": ["cinematic", "piano", "suspense", "orchestral"],
            "reddit_stories": ["lofi", "ambient", "chill", "soft"],
            "betrayal_revenge": ["lofi", "ambient", "chill", "soft"],
            "english_learning": ["lofi", "positive", "upbeat", "soft"],
            "horror_stories": ["dark", "ambient", "atmospheric", "soft"],
            "psychology_facts": ["ambient", "soft", "cinematic", "relaxing"],
        }

        if niche_id in defaults:
            return defaults[niche_id]

        # Build from tone keywords
        tags = [music_style]
        if "excited" in tone or "enthusiastic" in tone:
            tags.extend(["energetic", "upbeat"])
        elif "serious" in tone or "dark" in tone:
            tags.extend(["dark", "cinematic"])
        elif "professional" in tone:
            tags.extend(["inspiring", "cinematic"])
        else:
            tags.append("ambient")
        return tags
