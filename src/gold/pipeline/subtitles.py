"""SubtitleGenerator: creates word-by-word animated ASS subtitles for short-form video."""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Subtitle style configuration
# ---------------------------------------------------------------------------

# Niche-specific accent colors for the highlighted word (ASS &HBBGGRR format)
NICHE_ACCENT_COLORS = {
    "true_crime": "&H002222FF",    # deep red
    "ai_tools": "&H00FFCC00",      # cyan/electric blue
    "personal_finance": "&H0000D4FF",  # gold/amber
    "english_learning": "&H0044CC00",  # green
    "reddit_stories": "&H000088FF",    # orange
    "betrayal_revenge": "&H004444FF",  # dark red
}

DEFAULT_ACCENT_COLOR = "&H0000CCFF"  # yellow-orange default

# Niches with persistent hook cards need subtitles lower to avoid overlap
_PERSISTENT_HOOK_NICHES = {"reddit_stories", "betrayal_revenge"}

def _subtitle_y_pos(niche_id: str) -> int:
    """Get Y position for subtitles based on niche hook card behavior."""
    if niche_id in _PERSISTENT_HOOK_NICHES:
        return 1350  # lower-center, below persistent hook card
    return 960       # vertical center

# ASS header — modern karaoke-highlight style with Montserrat font
# Shows word groups (3-4 words) with the active word highlighted in accent color
ASS_HEADER = """[Script Info]
Title: Gold Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Montserrat,96,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,5,2,2,40,40,250,1
Style: Active,Montserrat,96,{accent_color},&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,110,110,2,0,1,6,2,2,40,40,250,1
Style: Dimmed,Montserrat,96,&H60AAAAAA,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,4,2,2,40,40,250,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _get_ass_header(niche_id: str = "") -> str:
    """Get ASS header with niche-specific accent color."""
    accent = NICHE_ACCENT_COLORS.get(niche_id, DEFAULT_ACCENT_COLOR)
    return ASS_HEADER.replace("{accent_color}", accent)


def _format_ass_time(seconds: float) -> str:
    """Format seconds as ASS timestamp: H:MM:SS.CC"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _build_ass_event(word: str, start: float, end: float, niche_id: str = "") -> str:
    """Build a single ASS Dialogue line for one highlighted word."""
    y = _subtitle_y_pos(niche_id)
    display_word = word.upper()
    styled = r"{\an2\pos(540," + str(y) + r")\fscx110\fscy110\bord6}" + display_word
    return (
        f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},"
        f"Default,,0,0,0,,{styled}"
    )


def _build_group_events(
    words: list[dict],
    group_size: int = 3,
    niche_id: str = "",
) -> list[str]:
    """Build ASS events showing word groups with karaoke-style highlighting.

    Shows a group of words together, with the currently-spoken word highlighted
    in the niche accent color and slightly scaled up, while surrounding words
    appear dimmed. This creates the modern viral caption effect.

    Args:
        words: List of dicts with keys: word, start, end.
        group_size: Number of words to show simultaneously.
        niche_id: For niche-specific accent color selection.

    Returns:
        List of ASS Dialogue lines.
    """
    accent = NICHE_ACCENT_COLORS.get(niche_id, DEFAULT_ACCENT_COLOR)
    events = []

    for i, w in enumerate(words):
        word_text = w["word"].strip()
        if not word_text:
            continue

        start_t = _format_ass_time(w["start"])
        end_t = _format_ass_time(w["end"])

        # Build the word group (context words around the active word)
        half = group_size // 2
        group_start = max(0, i - half)
        group_end = min(len(words), i + half + 1)

        # Build inline styled text: dimmed words + highlighted active word
        parts = []
        for j in range(group_start, group_end):
            other_word = words[j]["word"].strip().upper()
            if not other_word:
                continue
            if j == i:
                # Active word: accent color, scaled up
                parts.append(
                    r"{\c" + accent + r"\fscx115\fscy115\bord6}" + other_word +
                    r"{\c&H00FFFFFF&\fscx100\fscy100\bord5}"
                )
            else:
                # Context word: dimmed
                parts.append(
                    r"{\c&H60AAAAAA&\fscx100\fscy100\bord4}" + other_word +
                    r"{\c&H00FFFFFF&\bord5}"
                )

        y = _subtitle_y_pos(niche_id)
        text = r"{\an2\pos(540," + str(y) + r")}" + " ".join(parts)
        events.append(
            f"Dialogue: 0,{start_t},{end_t},Default,,0,0,0,,{text}"
        )

    return events


class SubtitleGenerator:
    """Generate karaoke-highlight animated subtitles in ASS format.

    Shows word groups with the active word highlighted in the niche accent
    color and scaled up, while surrounding context words appear dimmed.
    Uses Montserrat font for a modern look.
    """

    _whisper_model = None  # class-level cache for the loaded Whisper model

    def __init__(self, words_per_line: int = 1, niche_id: str = ""):
        self.words_per_line = words_per_line
        self.niche_id = niche_id

    # ------------------------------------------------------------------
    # Lazy Whisper model loader (cached on the class)
    # ------------------------------------------------------------------
    @classmethod
    def _get_whisper_model(cls):
        """Load the Whisper 'base' model lazily and cache it on the class."""
        if cls._whisper_model is None:
            import whisper  # noqa: delayed import

            logger.info("Loading Whisper 'base' model (first call — will be cached)…")
            cls._whisper_model = whisper.load_model("base")
            logger.info("Whisper model loaded.")
        return cls._whisper_model

    # ------------------------------------------------------------------
    # Primary method: real word-level timestamps via Whisper
    # ------------------------------------------------------------------
    def generate_from_audio(
        self,
        audio_path: str | Path,
        text: str,
        output_path: str | Path,
        niche_id: str = "",
    ) -> Path:
        """Generate ASS subtitles using Whisper word-level timestamps.

        Uses karaoke-highlight style: shows groups of 3 words with the
        active word highlighted in the niche accent color and scaled up.

        Args:
            audio_path: Path to the voiceover audio file (mp3/wav/etc.).
            text: Original voiceover script (used only by the fallback).
            output_path: Where to save the .ass file.
            niche_id: Niche identifier for accent color selection.

        Returns:
            Path to the written .ass file.
        """
        audio_path = Path(audio_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        niche = niche_id or self.niche_id

        try:
            model = self._get_whisper_model()

            result = model.transcribe(
                str(audio_path),
                word_timestamps=True,
                language="en",
            )

            # Collect every word entry across all segments
            word_entries: list[dict] = []
            for segment in result.get("segments", []):
                for w in segment.get("words", []):
                    word_text = w.get("word", "").strip()
                    if word_text:
                        word_entries.append({
                            "word": word_text,
                            "start": w["start"],
                            "end": w["end"],
                        })

            if not word_entries:
                raise ValueError("Whisper returned no word-level timestamps")

            # Build karaoke-highlight group events
            events = _build_group_events(
                words=word_entries,
                group_size=3,
                niche_id=niche,
            )

            header = _get_ass_header(niche)
            content = header + "\n".join(events) + "\n"
            output_path.write_text(content, encoding="utf-8")

            logger.info(
                "[SUBTITLE] OK: karaoke-highlight subtitles: %s (%d words, niche=%s, accent=%s)",
                output_path.name,
                len(events),
                niche,
                NICHE_ACCENT_COLORS.get(niche, "DEFAULT"),
            )
            return output_path

        except Exception:
            logger.error(
                "[SUBTITLE] FALLBACK: Whisper karaoke generation FAILED — falling back to even-division (NO karaoke highlighting).",
                exc_info=True,
            )
            # Fallback: estimate duration from audio file via Whisper's audio loader,
            # or use a rough default so the caller still gets a subtitle file.
            try:
                import whisper.audio as _wa

                audio = _wa.load_audio(str(audio_path))
                duration = len(audio) / _wa.SAMPLE_RATE
            except Exception:
                duration = 60.0  # safe default
                logger.warning(
                    "Could not determine audio duration; using %.0fs default.", duration
                )
            return self.generate(text, duration, output_path)

    # ------------------------------------------------------------------
    # Word timestamps for Remotion (returns JSON-serializable list)
    # ------------------------------------------------------------------
    def get_word_timestamps(
        self,
        audio_path: str | Path,
    ) -> list[dict]:
        """Get word-level timestamps from audio via Whisper.

        Returns:
            List of dicts with keys: word (str), start (float), end (float).
        """
        audio_path = Path(audio_path)
        model = self._get_whisper_model()
        result = model.transcribe(
            str(audio_path),
            word_timestamps=True,
            language="en",
        )
        words = []
        for segment in result.get("segments", []):
            for w in segment.get("words", []):
                word_text = w.get("word", "").strip()
                if word_text:
                    words.append({
                        "word": word_text,
                        "start": round(w["start"], 3),
                        "end": round(w["end"], 3),
                    })
        logger.info("Extracted %d word timestamps from %s", len(words), audio_path.name)
        return words

    # ------------------------------------------------------------------
    # Fallback method: even division (no Whisper needed)
    # ------------------------------------------------------------------
    def generate(
        self,
        text: str,
        duration: float,
        output_path: Path,
        start_offset: float = 0.3,
        end_pad: float = 0.3,
    ) -> Path:
        """Generate ASS subtitle file with word-by-word display.

        Args:
            text: Full voiceover script text.
            duration: Total audio duration in seconds.
            output_path: Where to save the .ass file.
            start_offset: Delay before first subtitle appears.
            end_pad: Time after last subtitle disappears.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Clean and split text into words
        clean_text = re.sub(r'\s+', ' ', text.strip())
        words = clean_text.split()

        if not words:
            output_path.write_text(_get_ass_header(self.niche_id), encoding="utf-8")
            return output_path

        # Calculate timing
        usable_duration = duration - start_offset - end_pad
        if usable_duration <= 0:
            usable_duration = duration

        time_per_word = usable_duration / len(words)

        # Generate word-by-word events
        events = []
        for i, word in enumerate(words):
            word_start = start_offset + i * time_per_word
            word_end = word_start + time_per_word
            events.append(_build_ass_event(word, word_start, word_end))

        # Write ASS file
        header = _get_ass_header(self.niche_id)
        content = header + "\n".join(events) + "\n"
        output_path.write_text(content, encoding="utf-8")

        logger.warning(
            "[SUBTITLE] DEGRADED: even-division subtitles (NO karaoke): %s (%d words, %.1fs duration)",
            output_path.name, len(words), duration,
        )
        return output_path
