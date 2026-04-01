"""Reddit JSON API scraper — no auth needed for public subreddits."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

REDDIT_BASE = "https://www.reddit.com"
USER_AGENT = "Gold/1.0 (Content Research Bot)"


async def get_top_posts(
    subreddit: str,
    time_filter: str = "day",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Fetch top posts from a subreddit.

    Args:
        subreddit: Subreddit name (without r/).
        time_filter: One of: hour, day, week, month, year, all.
        limit: Max posts to return (max 100).
    """
    url = f"{REDDIT_BASE}/r/{subreddit}/top.json"
    params = {"t": time_filter, "limit": min(limit, 100)}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        data = resp.json()

    posts = []
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        posts.append({
            "id": post.get("id"),
            "title": post.get("title", ""),
            "selftext": post.get("selftext", ""),
            "score": post.get("score", 0),
            "num_comments": post.get("num_comments", 0),
            "url": f"https://reddit.com{post.get('permalink', '')}",
            "subreddit": post.get("subreddit", subreddit),
            "is_video": post.get("is_video", False),
            "media_url": _extract_media_url(post),
            "created_utc": post.get("created_utc", 0),
        })

    logger.info("Fetched %d posts from r/%s (top/%s)", len(posts), subreddit, time_filter)
    return posts


async def get_post_content(permalink: str) -> dict[str, Any]:
    """Fetch full content of a specific Reddit post.

    Args:
        permalink: The post's permalink path (e.g., /r/AmItheAsshole/comments/xyz/...).
    """
    url = f"{REDDIT_BASE}{permalink}.json"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            url,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        data = resp.json()

    if not data or not isinstance(data, list):
        return {}

    post_data = data[0].get("data", {}).get("children", [{}])[0].get("data", {})
    return {
        "title": post_data.get("title", ""),
        "selftext": post_data.get("selftext", ""),
        "score": post_data.get("score", 0),
        "num_comments": post_data.get("num_comments", 0),
        "subreddit": post_data.get("subreddit", ""),
    }


async def get_viral_videos(
    subreddits: list[str],
    min_score: int = 1000,
    limit_per_sub: int = 5,
) -> list[dict[str, Any]]:
    """Fetch viral video posts from multiple subreddits.

    Returns posts that have video content and meet the minimum score.
    """
    all_videos = []

    for sub in subreddits:
        try:
            posts = await get_top_posts(sub, time_filter="day", limit=25)
            for post in posts:
                if post["score"] >= min_score and (post["is_video"] or post["media_url"]):
                    all_videos.append(post)
                    if len(all_videos) >= limit_per_sub * len(subreddits):
                        break
        except Exception as e:
            logger.warning("Failed to fetch from r/%s: %s", sub, e)

    # Sort by score descending
    all_videos.sort(key=lambda p: p["score"], reverse=True)
    logger.info("Found %d viral videos across %d subreddits", len(all_videos), len(subreddits))
    return all_videos


def _extract_media_url(post: dict) -> str:
    """Extract the best media URL from a Reddit post."""
    # Reddit-hosted video
    if post.get("is_video") and post.get("media"):
        reddit_video = post["media"].get("reddit_video", {})
        return reddit_video.get("fallback_url", "")

    # External video link
    url = post.get("url", "")
    if any(domain in url for domain in ["v.redd.it", "youtube.com", "youtu.be", "streamable.com"]):
        return url

    return ""
