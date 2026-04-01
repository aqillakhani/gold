"""Queue manager: picks READY items, posts them, handles failures."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from ..config import Config
from ..models.analytics import PostLog
from ..models.content import ContentVariant
from ..models.db import get_sync_session
from ..models.queue import QueueItem, QueueStatus
from ..platforms.base import PlatformAdapter
from ..platforms.meta import FacebookAdapter, InstagramAdapter
from ..platforms.rate_limiter import RateLimiter
from ..platforms.tiktok import TikTokAdapter
from ..platforms.youtube import YouTubeAdapter

logger = logging.getLogger(__name__)

# Auto-pin engagement questions per niche
ENGAGEMENT_COMMENTS = {
    "reddit_stories": [
        "What would you have done in this situation? \ud83d\udc47",
        "Who do you think was in the wrong here?",
        "Has anything like this ever happened to you?",
    ],
    "personal_finance": [
        "What's your biggest money mistake? Tell me below \ud83d\udc47",
        "Are you investing, saving, or paying off debt first?",
        "What's ONE financial goal you're working toward this year?",
    ],
    "betrayal_revenge": [
        "Was the revenge justified? YES or NO - vote below \ud83d\udc47",
        "Pick a side: Team OP or Team Betrayer?",
        "What would YOU have done in this situation?",
    ],
    "english_learning": [
        "Try using ONE of these words in a sentence below! \ud83d\udc47",
        "Which word was new to you? Comment below!",
        "Pause and REPEAT - comment when you've practiced!",
    ],
    "ai_tools": [
        "Which AI tool is your favorite? \ud83d\udc47",
        "Have you tried this one yet? What do you think?",
        "What AI tool should we review next?",
    ],
    "true_crime": [
        "What's the most disturbing case you know about? \ud83d\udc47",
        "Do you think this case will ever be solved?",
        "What detail stood out to you most?",
    ],
}


class QueueManager:
    def __init__(self, config: Config):
        self.config = config
        self.rate_limiter = RateLimiter()
        self._adapters: dict[str, dict[str, PlatformAdapter]] = {}

    def _get_adapter(self, account_id: str, platform: str) -> PlatformAdapter:
        """Get or create a platform adapter for an account."""
        key = f"{account_id}:{platform}"
        if key not in self._adapters:
            if platform == "facebook":
                adapter = FacebookAdapter(self.config, account_id)
            elif platform == "instagram":
                adapter = InstagramAdapter(self.config, account_id)
            elif platform == "youtube":
                adapter = YouTubeAdapter(self.config, account_id)
            elif platform == "tiktok":
                adapter = TikTokAdapter(self.config, account_id)
            else:
                raise ValueError(f"Unknown platform: {platform}")
            self._adapters[key] = adapter
        return self._adapters[key]

    async def process_account(
        self, account_id: str, platform: str | None = None,
    ) -> None:
        """Process the next READY queue item for an account.

        Args:
            account_id: Account to process.
            platform: If given, only process items for this platform.
        """
        session = get_sync_session()
        try:
            # Get next READY items for this account
            conditions = [
                QueueItem.account_id == account_id,
                QueueItem.status.in_([QueueStatus.READY, QueueStatus.RETRY]),
                QueueItem.scheduled_at <= datetime.utcnow(),
            ]
            if platform:
                conditions.append(QueueItem.platform == platform)
            stmt = (
                select(QueueItem)
                .where(*conditions)
                .order_by(QueueItem.scheduled_at)
                .limit(1 if platform else 4)
            )
            result = session.execute(stmt)
            items = result.scalars().all()

            if not items:
                logger.info("[%s] No READY items in queue", account_id)
                return

            for item in items:
                await self._post_item(session, item)

        finally:
            session.close()

    async def _post_item(self, session, item: QueueItem) -> None:
        """Post a single queue item."""
        # Check rate limits
        if not self.rate_limiter.can_post(item.platform, item.account_id):
            logger.warning(
                "[%s] Rate limited on %s, skipping", item.account_id, item.platform
            )
            return

        # Check dry run mode
        if self.config.dry_run:
            logger.info(
                "[DRY RUN] Would post to %s for %s (variant %d)",
                item.platform, item.account_id, item.content_variant_id,
            )
            item.status = QueueStatus.POSTED
            item.posted_at = datetime.utcnow()
            session.commit()
            return

        item.status = QueueStatus.POSTING
        session.commit()

        try:
            # Get variant details
            variant_stmt = select(ContentVariant).where(
                ContentVariant.id == item.content_variant_id
            )
            variant = session.execute(variant_stmt).scalar_one_or_none()
            if not variant:
                raise RuntimeError(f"Variant {item.content_variant_id} not found")

            adapter = self._get_adapter(item.account_id, item.platform)
            video_path = Path(variant.video_path) if variant.video_path else None
            if not video_path or not video_path.exists():
                raise RuntimeError(f"Video not found: {variant.video_path}")

            hashtags = json.loads(variant.hashtags) if variant.hashtags else []

            result = await adapter.post(
                video_path=video_path,
                caption=variant.caption,
                hashtags=hashtags,
            )

            # Success
            item.status = QueueStatus.POSTED
            item.posted_at = datetime.utcnow()
            item.platform_post_id = result.get("post_id", "")
            self.rate_limiter.record_call(item.platform, item.account_id)

            # Log the post
            log = PostLog(
                queue_item_id=item.id,
                account_id=item.account_id,
                platform=item.platform,
                platform_post_id=result.get("post_id", ""),
                status="SUCCESS",
                response_data=json.dumps(result.get("response", {})),
            )
            session.add(log)
            session.commit()

            logger.info(
                "[%s] Posted to %s: %s",
                item.account_id, item.platform, result.get("post_id"),
            )

            # Auto-pin engagement comment
            post_id = result.get("post_id")
            if post_id and hasattr(adapter, "post_comment"):
                niche = item.account_id  # account_id matches niche id
                comments = ENGAGEMENT_COMMENTS.get(niche, [])
                if comments:
                    import random
                    comment_text = random.choice(comments)
                    await adapter.post_comment(post_id, comment_text)

        except Exception as e:
            item.retry_count += 1
            if item.retry_count >= item.max_retries:
                item.status = QueueStatus.DEAD_LETTER
                logger.error(
                    "[%s] Dead letter on %s after %d retries: %s",
                    item.account_id, item.platform, item.retry_count, e,
                )
            else:
                item.status = QueueStatus.RETRY
                logger.warning(
                    "[%s] Retry %d/%d on %s: %s",
                    item.account_id, item.retry_count, item.max_retries, item.platform, e,
                )
            item.error_message = str(e)[:1000]
            session.commit()
