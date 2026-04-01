"""Betrayal & Revenge Stories niche engine — dramatic Reddit revenge stories."""

from __future__ import annotations

import logging

from .base import NicheConfig, NicheEngine

logger = logging.getLogger(__name__)


class BetrayalRevengeEngine(NicheEngine):
    def __init__(self, config: NicheConfig):
        super().__init__(config)

    async def enrich_idea(self, idea: dict) -> dict:
        """Fetch a real Reddit post from revenge-specific subreddits."""
        try:
            from ..utils.reddit import get_top_posts
            subreddit = idea.get("subreddit", "NuclearRevenge")
            posts = await get_top_posts(subreddit, time_filter="day", limit=5)
            if posts:
                post = posts[0]
                idea["story_text"] = post.get("selftext", "")[:2000]
                idea["story_title"] = post.get("title", "")
                idea["source_url"] = post.get("url", "")
                idea["score"] = post.get("score", 0)
        except Exception as e:
            logger.warning("Failed to fetch Reddit post: %s", e)
        return idea

    async def customize_script(self, script: dict) -> dict:
        """Select voice dynamically based on narrator's gender/identity in the story."""
        from ..pipeline.voice_selector import select_voice_for_script

        voiceover = script.get("voiceover_script", "")
        title = script.get("title", "")

        if voiceover:
            result = await select_voice_for_script(
                script_text=voiceover,
                title=title,
                niche_id="betrayal_revenge",
            )
            script["_voice_id_override"] = result["voice_id"]
            script["_voice_gender"] = result["gender"]

        return script

    def get_extra_prompt_context(self) -> str:
        return (
            "Tell the story like you're telling a friend the craziest thing you just read. "
            "Build to a satisfying payoff but keep it conversational and engaging. "
            "Use casual cliffhangers ('But here's where it gets wild...'). "
            "Structure as 3 acts: betrayal reveal, complications/twist, justice served. "
            "End with debate prompt: 'Was the revenge justified?'. "
            "Keep the tone casual and relatable — not overly dramatic or documentary-like. "
            "Emphasize the emotional stakes and the satisfaction of karma."
        )
