"""Tech/AI Tools niche engine — enriches ideas with trending AI tool news."""

from __future__ import annotations

import logging

import httpx

from .base import NicheConfig, NicheEngine

logger = logging.getLogger(__name__)


class TechAIEngine(NicheEngine):
    def __init__(self, config: NicheConfig):
        super().__init__(config)

    async def enrich_idea(self, idea: dict) -> dict:
        """Add trending AI tool references."""
        # Could integrate with Product Hunt, Hacker News, etc.
        idea["extra_context"] = "Focus on tools released or updated this week."
        return idea

    async def customize_script(self, script: dict) -> dict:
        """Add screen recording cues and demo steps."""
        for scene in script.get("scenes", []):
            if "demo" in scene.get("description", "").lower():
                scene["text_overlay"] = scene.get("text_overlay", "") + " [DEMO]"
        return script

    def get_extra_prompt_context(self) -> str:
        return (
            "Include specific tool names, pricing, and use cases. "
            "Compare with alternatives. Show practical workflows. "
            "Include affiliate-friendly language like 'link in bio'."
        )
