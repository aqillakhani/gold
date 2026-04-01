"""ASMR/Satisfying niche engine — visual-only pipeline with style rotation."""

from __future__ import annotations

import logging
import random

from .base import NicheConfig, NicheEngine

logger = logging.getLogger(__name__)


class ASMRSatisfyingEngine(NicheEngine):
    def __init__(self, config: NicheConfig):
        super().__init__(config)
        self.niche_config.has_voiceover = False

    def _select_style(self) -> tuple[str, dict]:
        """Select a visual style using weighted random from niche config."""
        styles = self.niche_config.extra.get("styles", {})
        if not styles:
            return "default", {}

        names = list(styles.keys())
        weights = [styles[n].get("weight", 25) for n in names]
        chosen_name = random.choices(names, weights=weights, k=1)[0]
        chosen_style = styles[chosen_name]
        logger.info("Selected ASMR style: %s (weight=%d)", chosen_name, chosen_style.get("weight", 25))
        return chosen_name, chosen_style

    async def enrich_idea(self, idea: dict) -> dict:
        idea["no_voiceover"] = True

        # Select and inject visual style
        style_name, style_data = self._select_style()
        idea["style_name"] = style_name
        idea["style"] = style_data
        idea["image_style_prefix"] = style_data.get("image_style", "")

        # Pick a topic from the style's topic list if available
        style_topics = style_data.get("topics", [])
        if style_topics:
            idea["style_topic"] = random.choice(style_topics)

        idea["extra_context"] = (
            f"Visual style: {style_name}. "
            f"Image style: {style_data.get('image_style', 'cinematic')}. "
            "Pure visual/audio satisfaction. No narration needed."
        )
        return idea

    async def customize_script(self, script: dict) -> dict:
        """Remove voiceover, enhance visual descriptions with style prefix."""
        script["voiceover_script"] = ""
        for scene in script.get("scenes", []):
            scene["description"] = (
                f"Extremely satisfying, smooth, high-quality close-up: {scene.get('description', '')}. "
                "Slow motion, crisp audio of the action, no music overlay."
            )
        return script

    def get_extra_prompt_context(self) -> str:
        return (
            "NO voiceover or narration. Focus on satisfying visuals and sounds. "
            "Describe textures, colors, and movements in extreme detail. "
            "Think close-up shots, smooth movements, rich colors. "
            "Include ambient sound descriptions for atmosphere. "
            "Use the provided visual style to guide ALL image prompts."
        )
