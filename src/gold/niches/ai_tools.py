"""AI Tools niche engine — reviews and demonstrates AI tools."""

from __future__ import annotations

import logging

from .base import NicheConfig, NicheEngine

logger = logging.getLogger(__name__)


class AIToolsEngine(NicheEngine):
    def __init__(self, config: NicheConfig):
        super().__init__(config)

    async def enrich_idea(self, idea: dict) -> dict:
        idea["extra_context"] = (
            "Focus on practical demonstrations and real use cases. "
            "Compare to alternatives briefly. Include pricing info."
        )
        return idea

    async def customize_script(self, script: dict) -> dict:
        scenes = script.get("scenes", [])
        scene_contexts = [
            "Clean minimal establishing shot: ",
            "Clean minimal detail view: ",
            "Clean minimal UI showcase: ",
            "Clean minimal comparison layout: ",
            "Clean minimal data visualization: ",
            "Clean minimal close-up feature: ",
            "Clean minimal results display: ",
            "Clean minimal verdict summary: ",
        ]
        for i, scene in enumerate(scenes):
            prompt = scene.get("image_prompt", "")
            if prompt and not prompt.startswith("Clean minimal"):
                prefix = scene_contexts[i % len(scene_contexts)]
                scene["image_prompt"] = prefix + prompt
        return script

    def get_extra_prompt_context(self) -> str:
        return (
            "Demonstrate the AI tool with clear before/after examples. "
            "Include pricing tiers and best use cases. "
            "Add affiliate link CTA naturally. "
            "Focus on 'this saved me X hours' angle."
        )
