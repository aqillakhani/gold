"""Detect emotional beats in scripts for emoji overlay reactions."""

from __future__ import annotations

import logging
import random

logger = logging.getLogger(__name__)

EMOJI_KEYWORDS: dict[str, list[str]] = {
    "\U0001f631": [  # 😱
        "shocking",
        "insane",
        "unbelievable",
        "crazy",
        "horrifying",
        "terrifying",
        "nightmare",
    ],
    "\U0001f480": [  # 💀
        "dead",
        "killed",
        "murder",
        "death",
        "dies",
        "fatal",
        "corpse",
    ],
    "\U0001f525": [  # 🔥
        "fire",
        "viral",
        "exploded",
        "blew up",
        "incredible",
        "amazing",
        "insane",
    ],
    "\U0001f4b0": [  # 💰
        "money",
        "million",
        "thousand",
        "salary",
        "income",
        "profit",
        "rich",
        "wealth",
        "dollar",
    ],
    "\U0001f62d": [  # 😭
        "cried",
        "crying",
        "tears",
        "heartbreak",
        "devastating",
        "emotional",
        "sobbing",
    ],
    "\U0001f4a1": [  # 💡
        "discovered",
        "realized",
        "figured out",
        "breakthrough",
        "found out",
        "secret",
    ],
    "\u26a0\ufe0f": [  # ⚠️
        "warning",
        "danger",
        "careful",
        "risk",
        "scam",
        "fraud",
        "beware",
    ],
}


def detect_emoji_beats(
    script: str,
    subtitle_words: list[dict],
) -> list[dict]:
    """Detect emotional beats in script and map to emoji + timestamp.

    Args:
        script: Full script text.
        subtitle_words: List of dicts with keys: word, start, end (seconds).

    Returns:
        List of dicts with keys: emoji, timestampSec, x (0-100), y (0-100).
    """
    beats: list[dict] = []
    script_lower = script.lower()

    for emoji, keywords in EMOJI_KEYWORDS.items():
        for kw in keywords:
            idx = script_lower.find(kw)
            if idx == -1:
                continue
            # Find the word timestamp closest to this character position
            word_pos = len(script_lower[:idx].split())
            if word_pos < len(subtitle_words):
                ts = subtitle_words[min(word_pos, len(subtitle_words) - 1)]["start"]
                beats.append(
                    {
                        "emoji": emoji,
                        "timestampSec": round(float(ts), 2),
                        "x": random.randint(15, 85),
                        "y": random.randint(20, 40),
                    }
                )
            break  # Only one match per emoji type

    # Always add an IG-style heart pop in first 5-10s to simulate like action
    like_time = random.uniform(5.0, 8.0)
    like_beat = {
        "emoji": "\u2764\ufe0f",  # ❤️
        "timestampSec": round(like_time, 2),
        "x": random.randint(70, 85),  # right side (like button area)
        "y": random.randint(45, 55),  # mid-right
    }

    # Sort by time and limit to 4 max (excluding the like beat)
    beats.sort(key=lambda b: b["timestampSec"])
    if len(beats) > 3:
        # Evenly sample 3 beats (save 1 slot for like)
        step = len(beats) / 3
        beats = [beats[int(i * step)] for i in range(3)]

    # Insert like beat and re-sort
    beats.insert(0, like_beat)
    beats.sort(key=lambda b: b["timestampSec"])

    # Ensure minimum 3s gap between beats
    filtered: list[dict] = []
    for beat in beats:
        if not filtered or beat["timestampSec"] - filtered[-1]["timestampSec"] >= 3.0:
            filtered.append(beat)

    logger.info("Emoji beats detected: %d (including IG-like heart)", len(filtered))
    return filtered
