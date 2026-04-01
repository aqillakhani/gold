"""English Learning niche engine — vocabulary and grammar lessons for non-native speakers."""

from __future__ import annotations

import logging

from .base import NicheConfig, NicheEngine

logger = logging.getLogger(__name__)


class EnglishLearningEngine(NicheEngine):
    def __init__(self, config: NicheConfig):
        super().__init__(config)

    async def enrich_idea(self, idea: dict) -> dict:
        idea["extra_context"] = (
            "Target non-native English speakers at intermediate level. "
            "Include difficulty level context for vocabulary words."
        )
        return idea

    async def customize_script(self, script: dict) -> dict:
        """Ensure text_overlay has vocabulary words in LARGE text."""
        scenes = script.get("scenes", [])
        for scene in scenes:
            overlay = scene.get("text_overlay", "")
            if overlay and not overlay.isupper():
                scene["text_overlay"] = overlay.upper()
        return script

    def get_extra_prompt_context(self) -> str:
        return (
            "Speak slowly and clearly. Pause after key words. "
            "Use simple example sentences. "
            "Target non-native speakers — avoid idioms in explanations "
            "(but teach idioms as topics). "
            "Include 3-5 repetitions of new words. "
            "End with a practice prompt: 'Try using this word in a comment'. "
            "Structure: Word/concept → Definition → 3 examples → Common mistake → Practice prompt."
        )
