"""Personal Finance niche engine — practical money tips and financial literacy."""

from __future__ import annotations

import logging

from .base import NicheConfig, NicheEngine

logger = logging.getLogger(__name__)


class PersonalFinanceEngine(NicheEngine):
    def __init__(self, config: NicheConfig):
        super().__init__(config)

    async def enrich_idea(self, idea: dict) -> dict:
        idea["extra_context"] = (
            "Focus on practical, actionable financial advice with real numbers. "
            "Include specific dollar amounts and percentages where possible."
        )
        return idea

    async def customize_script(self, script: dict) -> dict:
        return script

    def get_extra_prompt_context(self) -> str:
        return (
            "Explain concepts in simple, jargon-free language. "
            "Use real numbers and examples. Include specific dollar amounts. "
            "Focus on actionable takeaways the viewer can implement today. "
            "Include FTC disclosure naturally. "
            "Never give specific investment advice — frame as 'strategies to consider'. "
            "Target audience: 18-35 year olds trying to build wealth."
        )
