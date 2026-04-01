"""Reddit Stories niche engine — enriches ideas with real Reddit posts."""

from __future__ import annotations

import logging

from .base import NicheConfig, NicheEngine

logger = logging.getLogger(__name__)


class RedditStoriesEngine(NicheEngine):
    def __init__(self, config: NicheConfig):
        super().__init__(config)

    async def enrich_idea(self, idea: dict) -> dict:
        """Try to fetch a real Reddit post to base the story on.

        When multi_part is enabled, prefer longer posts (1500+ chars)
        for richer 3-part narratives.
        """
        try:
            from ..utils.reddit import get_top_posts
            subreddit = idea.get("subreddit", "AmItheAsshole")
            prefer_long = self.config.get("multi_part", {}).get("prefer_long_stories", False)
            posts = await get_top_posts(subreddit, time_filter="day", limit=15)
            if posts:
                if prefer_long:
                    # Sort by length, prefer posts with 1500+ chars for multi-part
                    long_posts = [p for p in posts if len(p.get("selftext", "")) >= 1500]
                    post = long_posts[0] if long_posts else posts[0]
                    # Allow more text for longer stories
                    idea["story_text"] = post.get("selftext", "")[:4000]
                else:
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
                niche_id="reddit_stories",
            )
            script["_voice_id_override"] = result["voice_id"]
            script["_voice_gender"] = result["gender"]

        return script

    def get_extra_prompt_context(self) -> str:
        return (
            "Retell the Reddit story in a dramatic, conversational tone. "
            "React to key moments ('wait, it gets worse'). "
            "Add your verdict at the end and ask viewers to comment. "
            "Make it feel like telling a wild story to a friend."
        )
