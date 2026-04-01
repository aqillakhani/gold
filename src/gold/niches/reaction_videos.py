"""Reaction Videos niche engine — commentary on viral content."""

from __future__ import annotations

import logging

from .base import NicheConfig, NicheEngine

logger = logging.getLogger(__name__)


class ReactionVideosEngine(NicheEngine):
    def __init__(self, config: NicheConfig):
        super().__init__(config)

    async def enrich_idea(self, idea: dict) -> dict:
        """Try to find a viral video to react to."""
        try:
            from ..utils.reddit import get_viral_videos
            subreddits = ["videos", "funny", "Unexpected", "nextfuckinglevel"]
            videos = await get_viral_videos(subreddits, min_score=1000)
            if videos:
                video = videos[0]
                idea["source_url"] = video.get("url", "")
                idea["source_title"] = video.get("title", "")
                idea["score"] = video.get("score", 0)
        except Exception as e:
            logger.warning("Failed to fetch viral video: %s", e)
        return idea

    async def customize_script(self, script: dict) -> dict:
        return script

    def get_extra_prompt_context(self) -> str:
        return (
            "React with energy and humor. Point out details viewers might miss. "
            "Add commentary that adds value beyond just watching the clip. "
            "Use phrases like 'no way', 'did you see that', 'okay but watch this part'. "
            "End with a question to drive comments."
        )
