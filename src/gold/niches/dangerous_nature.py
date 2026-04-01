"""Dangerous Nature & Wildlife Compilation niche engine."""

from __future__ import annotations

import logging

from .base import NicheConfig, NicheEngine

logger = logging.getLogger(__name__)


class DangerousNatureEngine(NicheEngine):
    def __init__(self, config: NicheConfig):
        super().__init__(config)

    async def enrich_idea(self, idea: dict) -> dict:
        """For compilations, idea is a list of clip metadata — pass through."""
        return idea

    async def customize_script(self, script: dict) -> dict:
        """Apply dangerous_nature voiceover tone."""
        return script

    def get_extra_prompt_context(self) -> str:
        return (
            "You are narrating a dangerous wildlife/nature compilation. "
            "For each clip, write 10-15 seconds of narration (~35-50 words). "
            "Tone: Documentary-style, suspenseful, emphasizing danger and intensity. "
            "Use hooks like 'Watch as...', 'What happens next will shock you...', "
            "'This diver had no idea...' "
            "Each narration should stand alone but flow as a compilation. "
            "End each clip's narration with a brief impact statement."
        )
