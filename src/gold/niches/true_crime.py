"""True Crime niche engine — investigative case breakdowns."""

from __future__ import annotations

import logging
import re

from .base import NicheConfig, NicheEngine

logger = logging.getLogger(__name__)

# Fish Audio voice IDs for dynamic selection (primary TTS provider)
VOICE_MAP = {
    "male_narrator": "fd176117735446968cca7911ee4da42b",   # DEEP STORY — dramatic, mysterious
    "female_narrator": "933563129e564b19a115bedd57b7406a",  # Sarah — calm, authoritative female
}

# Keywords that suggest female protagonist/victim focus
FEMALE_INDICATORS = [
    r"\bshe\b", r"\bher\b", r"\bwoman\b", r"\bwife\b", r"\bmother\b",
    r"\bdaughter\b", r"\bgirlfriend\b", r"\bsister\b", r"\bfemale\b",
    r"\bwaitress\b", r"\bnurse\b", r"\bqueen\b", r"\blady\b",
]
MALE_INDICATORS = [
    r"\bhe\b", r"\bhis\b", r"\bman\b", r"\bhusband\b", r"\bfather\b",
    r"\bson\b", r"\bboyfriend\b", r"\bbrother\b", r"\bmale\b",
    r"\bking\b", r"\bdetective\b",
]


def detect_protagonist_gender(text: str) -> str:
    """Analyze script text to detect predominant gender of protagonist/subject."""
    text_lower = text.lower()
    female_count = sum(len(re.findall(p, text_lower)) for p in FEMALE_INDICATORS)
    male_count = sum(len(re.findall(p, text_lower)) for p in MALE_INDICATORS)
    if female_count > male_count * 1.3:
        return "female"
    return "male"


class TrueCrimeEngine(NicheEngine):
    def __init__(self, config: NicheConfig):
        super().__init__(config)

    async def enrich_idea(self, idea: dict) -> dict:
        idea["extra_context"] = (
            "Use only publicly available information from court records, "
            "news reports, and official sources. Present facts objectively."
        )
        return idea

    async def customize_script(self, script: dict) -> dict:
        # Dynamic voice selection based on protagonist gender
        voiceover = script.get("voiceover_script", "")
        title = script.get("title", "")
        analysis_text = f"{title} {voiceover}"

        if analysis_text.strip():
            gender = detect_protagonist_gender(analysis_text)
            if gender == "female":
                script["_voice_id_override"] = VOICE_MAP["female_narrator"]
                logger.info("True Crime: Female protagonist detected — using female narrator")
            else:
                script["_voice_id_override"] = VOICE_MAP["male_narrator"]
                logger.info("True Crime: Male protagonist detected — using male narrator")

        # Enhance image prompts with dark documentary style
        for scene in script.get("scenes", []):
            if "image_prompt" in scene:
                scene["image_prompt"] = (
                    f"Dark investigative documentary style: {scene['image_prompt']}. "
                    "Muted colors, dramatic shadows, evidence board aesthetic."
                )
        return script

    def get_extra_prompt_context(self) -> str:
        return (
            "Present the case chronologically with key evidence. "
            "Be respectful of victims. Avoid sensationalism. "
            "End with current case status or unanswered questions. "
            "Use phrases like 'investigators discovered' and 'evidence suggests'."
        )
