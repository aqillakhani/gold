"""Generate a daily TikTok posting guide for manual uploads."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from ..config import Config
from ..models.content import Content, ContentStatus, ContentVariant
from ..models.db import get_sync_session
from ..models.queue import QueueItem, QueueStatus

logger = logging.getLogger(__name__)

# Research-backed TikTok posting times (EST)
TIKTOK_TIMES = {
    "reddit_stories":    ["10:00 AM", "3:00 PM", "8:00 PM"],
    "betrayal_revenge":  ["12:00 PM", "6:00 PM", "10:00 PM"],
    "ai_tools":          ["8:00 AM", "1:00 PM", "6:00 PM"],
    "true_crime":        ["10:00 AM", "3:00 PM", "8:00 PM"],
    "personal_finance":  ["9:00 AM", "2:00 PM", "7:00 PM"],
    "english_learning":  ["8:00 AM", "1:00 PM", "6:00 PM"],
}

TIKTOK_ACCOUNTS = {
    "reddit_stories":    "@storyvault",
    "betrayal_revenge":  "@storyvault",
    "ai_tools":          "@toolstack",
    "true_crime":        "@coldcases",
    "personal_finance":  "@smartstack",
    "english_learning":  "@fluentin60",
}


def generate_daily_guide(config: Config) -> Path | None:
    """Generate today's TikTok posting guide as a markdown file.

    Queries content that's READY or recently queued for YouTube/IG,
    finds matching TikTok variants, and writes a guide with file paths,
    captions, hashtags, and recommended posting times.

    Returns path to the generated guide, or None if no content.
    """
    session = get_sync_session()
    try:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        guide_dir = config.data_dir / "tiktok_guides"
        guide_dir.mkdir(parents=True, exist_ok=True)
        guide_path = guide_dir / f"tiktok_guide_{today}.md"

        # Find today's content: READY content that has TikTok variants
        # and YouTube queue items scheduled for today (meaning it's today's batch)
        stmt = (
            select(QueueItem.content_variant_id)
            .where(
                QueueItem.platform == "youtube",
                QueueItem.status.in_([QueueStatus.READY, QueueStatus.POSTING, QueueStatus.POSTED]),
            )
        )
        result = session.execute(stmt)
        yt_variant_ids = {r[0] for r in result.fetchall()}

        if not yt_variant_ids:
            logger.info("No queued content for TikTok guide")
            return None

        # Get content IDs from those YouTube variants
        stmt = select(ContentVariant.content_id).where(
            ContentVariant.id.in_(yt_variant_ids)
        )
        result = session.execute(stmt)
        content_ids = {r[0] for r in result.fetchall()}

        # Get TikTok variants for those content pieces
        stmt = (
            select(ContentVariant, Content)
            .join(Content, ContentVariant.content_id == Content.id)
            .where(
                ContentVariant.content_id.in_(content_ids),
                ContentVariant.platform == "tiktok",
                Content.status == ContentStatus.READY,
            )
            .order_by(Content.niche, Content.id)
        )
        result = session.execute(stmt)
        rows = result.all()

        if not rows:
            logger.info("No TikTok variants found for today's content")
            return None

        # Group by niche
        by_niche: dict[str, list[tuple]] = {}
        for variant, content in rows:
            niche = content.niche
            if niche not in by_niche:
                by_niche[niche] = []
            by_niche[niche].append((variant, content))

        # Build markdown
        lines = [
            f"# TikTok Posting Guide — {today}",
            "",
            f"Generated at {datetime.now().strftime('%I:%M %p EST')}",
            "",
            "---",
            "",
        ]

        total = 0
        for niche, items in by_niche.items():
            account = TIKTOK_ACCOUNTS.get(niche, f"@{niche}")
            times = TIKTOK_TIMES.get(niche, ["10:00 AM", "3:00 PM", "8:00 PM"])

            lines.append(f"## {account} ({niche})")
            lines.append("")

            for i, (variant, content) in enumerate(items):
                post_time = times[i % len(times)]
                hashtags = json.loads(variant.hashtags) if variant.hashtags else []
                hashtag_str = " ".join(hashtags)
                video_path = variant.video_path or "NO VIDEO"

                lines.append(f"### Post {i + 1} — {post_time} EST")
                lines.append("")
                lines.append(f"**Video:** `{video_path}`")
                lines.append("")
                lines.append(f"**Caption:**")
                lines.append(f"```")
                lines.append(f"{variant.caption or content.title}")
                lines.append(f"```")
                lines.append("")
                lines.append(f"**Hashtags:** `{hashtag_str}`")
                lines.append("")
                if variant.cta:
                    lines.append(f"**CTA:** {variant.cta}")
                    lines.append("")
                lines.append("---")
                lines.append("")
                total += 1

        lines.append(f"**Total: {total} videos to post across {len(by_niche)} accounts**")

        guide_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("TikTok guide generated: %s (%d videos)", guide_path.name, total)
        return guide_path

    finally:
        session.close()
