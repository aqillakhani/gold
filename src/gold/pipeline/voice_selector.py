"""Dynamic voice selection for story niches based on script content.

Analyzes the voiceover script to determine the narrator's profile
(gender, age, emotional tone) and selects the best Fish Audio voice.
Used by reddit_stories and betrayal_revenge niches where the narrator
IS the protagonist and should match the character.
"""

from __future__ import annotations

import json
import logging

import anthropic

logger = logging.getLogger(__name__)

# Fish Audio voice catalog for story niches
# Each voice has a gender, age range, tone, and best-fit scenarios
STORY_VOICES = {
    "male_default": {
        "id": "d67524ad1936410896ad120583cb1117",  # Andrew
        "gender": "male",
        "age": "adult",
        "tone": "deep, storytelling, natural",
        "best_for": "general male narration, dramatic stories",
    },
    "female_default": {
        "id": "933563129e564b19a115bedd57b7406a",  # Sarah
        "gender": "female",
        "age": "adult",
        "tone": "sincere, intimate, storytelling",
        "best_for": "female protagonist stories, emotional narratives",
    },
    "male_deep": {
        "id": "fd176117735446968cca7911ee4da42b",  # DEEP STORY
        "gender": "male",
        "age": "adult",
        "tone": "deep, dramatic, mysterious, authoritative",
        "best_for": "dark stories, revenge, serious content",
    },
}


async def select_voice_for_script(
    script_text: str,
    title: str = "",
    niche_id: str = "reddit_stories",
    available_voices: dict[str, dict] | None = None,
) -> dict:
    """Analyze a script and select the best voice for narration.

    Uses Claude to determine:
    - Narrator gender (from the protagonist's perspective)
    - Emotional tone of the story
    - Recommended voice characteristics

    Returns dict with: voice_id, voice_key, gender, reasoning
    """
    voices = available_voices or STORY_VOICES

    # Build voice options for Claude
    voice_desc = "\n".join([
        f"- {key}: {v['gender']}, {v['tone']} (best for: {v['best_for']})"
        for key, v in voices.items()
    ])

    prompt = f"""Analyze this story script and select the best narrator voice.

TITLE: {title}
NICHE: {niche_id}

SCRIPT (first 500 chars):
{script_text[:500]}

AVAILABLE VOICES:
{voice_desc}

The narrator IS the protagonist telling their own story in first person.
Select the voice that best matches the narrator's identity and the story's tone.

Return ONLY JSON:
{{
  "voice_key": "male_default or female_default or male_deep",
  "gender": "male or female",
  "reasoning": "one sentence explaining why"
}}"""

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        result = json.loads(text.strip())
        voice_key = result.get("voice_key", "male_default")

        if voice_key not in voices:
            voice_key = "male_default"

        voice = voices[voice_key]
        logger.info(
            "[VOICE-SELECT] %s -> %s (%s): %s",
            niche_id, voice_key, result.get("gender", "?"),
            result.get("reasoning", "no reason"),
        )

        return {
            "voice_id": voice["id"],
            "voice_key": voice_key,
            "gender": result.get("gender", voice["gender"]),
            "reasoning": result.get("reasoning", ""),
        }

    except Exception as e:
        logger.warning("[VOICE-SELECT] Claude analysis failed, using default: %s", e)
        default = voices.get("male_default", list(voices.values())[0])
        return {
            "voice_id": default["id"],
            "voice_key": "male_default",
            "gender": "male",
            "reasoning": f"fallback — analysis failed: {str(e)[:80]}",
        }
