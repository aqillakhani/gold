"""Psychology Facts niche engine."""

from __future__ import annotations

import logging

from .base import NicheConfig, NicheEngine

logger = logging.getLogger(__name__)


class PsychologyFactsEngine(NicheEngine):
    def __init__(self, config: NicheConfig):
        super().__init__(config)

    async def enrich_idea(self, idea: dict) -> dict:
        idea["extra_context"] = "Cite real psychological studies when possible."
        return idea

    async def customize_script(self, script: dict) -> dict:
        return script

    def get_extra_prompt_context(self) -> str:
        return (
            "Reference real psychological studies and researchers. "
            "Use 'Did you know...' or 'Psychology says...' hooks. "
            "Make it relatable with everyday examples."
        )
