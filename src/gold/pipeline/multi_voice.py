"""Multi-voice dialogue detection and TTS routing for story niches."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpeechSegment:
    """A segment of speech attributed to a specific speaker."""

    text: str
    speaker: str  # "narrator", "male", "female"
    start_char: int
    end_char: int


# Female attribution patterns
_FEMALE_ATTR = re.compile(
    r"\b(?:she|her|mom|mother|wife|girlfriend|sister|daughter|aunt|grandma|woman|girl|lady)\s+"
    r"(?:said|replied|yelled|whispered|asked|screamed|told|cried|shouted|muttered|snapped)",
    re.IGNORECASE,
)

# Male attribution patterns
_MALE_ATTR = re.compile(
    r"\b(?:he|him|dad|father|husband|boyfriend|brother|son|uncle|grandpa|boss|guy|man)\s+"
    r"(?:said|replied|yelled|whispered|asked|screamed|told|cried|shouted|muttered|snapped)",
    re.IGNORECASE,
)

# Quote extraction — finds text in quotes
_QUOTE_RE = re.compile(r"""["'\u201c\u201d]([^"'\u201c\u201d]{3,120})["'\u201c\u201d]""")


def detect_dialogue(script: str) -> list[SpeechSegment]:
    """Split a script into narrator and character speech segments.

    Finds quoted dialogue near gendered attribution phrases and assigns
    speakers. Everything outside quotes is narrator.

    Args:
        script: Full script text.

    Returns:
        Ordered list of SpeechSegment with speaker assignments.
    """
    if not script or len(script) < 20:
        return [
            SpeechSegment(text=script, speaker="narrator", start_char=0, end_char=len(script))
        ]

    # Find all quotes with their positions
    quotes: list[tuple[int, int, str]] = []  # (start, end, text)
    for match in _QUOTE_RE.finditer(script):
        quotes.append((match.start(), match.end(), match.group(1)))

    if not quotes:
        return [
            SpeechSegment(text=script, speaker="narrator", start_char=0, end_char=len(script))
        ]

    # For each quote, check surrounding context (100 chars before/after) for attribution
    attributed: list[tuple[int, int, str, str]] = []  # (start, end, text, speaker)

    for q_start, q_end, q_text in quotes:
        # Check narrow context around the quote for closest attribution
        context_before = script[max(0, q_start - 60) : q_start]
        context_after = script[q_end : min(len(script), q_end + 60)]

        # Find closest attribution by checking distance of match end to quote
        best_speaker = None
        best_dist = 999

        for ctx, is_before in [(context_before, True), (context_after, False)]:
            for pattern, spk in [(_FEMALE_ATTR, "female"), (_MALE_ATTR, "male")]:
                match = None
                for m in pattern.finditer(ctx):
                    match = m  # Take last match (closest to quote if before)
                if match:
                    dist = (len(ctx) - match.end()) if is_before else match.start()
                    if dist < best_dist:
                        best_dist = dist
                        best_speaker = spk

        if best_speaker:
            attributed.append((q_start, q_end, q_text, best_speaker))
        # Unattributed quotes stay as narrator

    if not attributed:
        return [
            SpeechSegment(text=script, speaker="narrator", start_char=0, end_char=len(script))
        ]

    # Build segments: narrator text between dialogues, character during
    segments: list[SpeechSegment] = []
    last_end = 0

    for q_start, q_end, q_text, speaker in sorted(attributed, key=lambda x: x[0]):
        # Narrator segment before this dialogue
        if q_start > last_end:
            narrator_text = script[last_end:q_start].strip()
            if narrator_text:
                segments.append(
                    SpeechSegment(
                        text=narrator_text,
                        speaker="narrator",
                        start_char=last_end,
                        end_char=q_start,
                    )
                )

        # Character dialogue
        segments.append(
            SpeechSegment(
                text=q_text, speaker=speaker, start_char=q_start, end_char=q_end
            )
        )
        last_end = q_end

    # Trailing narrator text
    if last_end < len(script):
        trailing = script[last_end:].strip()
        if trailing:
            segments.append(
                SpeechSegment(
                    text=trailing,
                    speaker="narrator",
                    start_char=last_end,
                    end_char=len(script),
                )
            )

    logger.info(
        "Dialogue detection: %d segments (%d narrator, %d male, %d female)",
        len(segments),
        sum(1 for s in segments if s.speaker == "narrator"),
        sum(1 for s in segments if s.speaker == "male"),
        sum(1 for s in segments if s.speaker == "female"),
    )
    return segments


# Default character voice IDs for Fish Audio
# These can be overridden in niche config YAML
DEFAULT_VOICE_MAP: dict[str, str] = {
    "narrator": "",  # Uses the niche's default voice
    "male": "",  # Placeholder — set from config
    "female": "",  # Placeholder — set from config
}


def get_voice_for_speaker(
    speaker: str,
    narrator_voice_id: str,
    voice_map: dict[str, str] | None = None,
) -> str:
    """Get the Fish Audio voice ID for a speaker role.

    Falls back to narrator voice if character voice not configured.

    Args:
        speaker: Speaker role ("narrator", "male", "female").
        narrator_voice_id: Default voice ID to use for narrator.
        voice_map: Optional voice mapping for character roles.

    Returns:
        Fish Audio voice ID for the speaker.
    """
    if voice_map is None:
        voice_map = DEFAULT_VOICE_MAP

    if speaker == "narrator":
        return narrator_voice_id

    character_voice = voice_map.get(speaker, "")
    if character_voice:
        return character_voice

    # Fallback to narrator if character voice not set
    logger.debug("No voice configured for speaker '%s', using narrator voice", speaker)
    return narrator_voice_id
