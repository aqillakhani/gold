"""Horror Stories niche engine — dramatic narration with creepy visuals."""

from __future__ import annotations

import logging

from .base import NicheConfig, NicheEngine

logger = logging.getLogger(__name__)


class HorrorStoriesEngine(NicheEngine):
    def __init__(self, config: NicheConfig):
        super().__init__(config)

    async def enrich_idea(self, idea: dict) -> dict:
        idea["extra_context"] = (
            "Draw from public domain horror stories, urban legends, "
            "and creepypasta-style narratives."
        )
        return idea

    async def customize_script(self, script: dict) -> dict:
        """Add ambient audio cues and dramatic pauses."""
        for i, scene in enumerate(script.get("scenes", [])):
            scene["description"] = (
                f"Dark, eerie, atmospheric: {scene.get('description', '')}. "
                "Low lighting, shadow details, unsettling perspective."
            )
            if i == 0:
                scene["audio_cue"] = "soft_rain_start"
            elif i == len(script.get("scenes", [])) - 1:
                scene["audio_cue"] = "sudden_silence_then_thunder"
        return script

    def get_extra_prompt_context(self) -> str:
        return (
            "Write in first person for immersion. Build suspense gradually. "
            "End with a twist or cliffhanger. Use sensory descriptions. "
            "Keep language atmospheric but accessible. "
            "Include a 'Part 2?' hook at the end for engagement."
        )
