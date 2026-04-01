"""Nightly batch generator: fills queue to 3-day buffer."""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta

from sqlalchemy import func, select

from ..config import Config
from ..models.content import Content, ContentStatus, ContentVariant
from ..models.db import get_sync_session
from ..models.queue import QueueItem, QueueStatus
from ..pipeline.orchestrator import ContentPipeline

logger = logging.getLogger(__name__)


class BatchGenerator:
    def __init__(self, config: Config):
        self.config = config
        self.pipeline = ContentPipeline(config)
        self.buffer_days = config.get("scheduling.buffer_days", 3)
        self.posts_per_day = config.get("scheduling.posts_per_day_per_account", 2)
        self.stagger_minutes = config.get("scheduling.stagger_minutes", 144)
        self.jitter_minutes = config.get("scheduling.jitter_minutes", 15)

    async def run(self) -> None:
        """Generate content for all accounts to maintain buffer."""
        all_accounts = self.config.accounts.get("accounts", [])
        active_niches = self.config.get("app.active_niches", None)
        if active_niches:
            accounts = [a for a in all_accounts if a["niche"] in active_niches]
        else:
            accounts = all_accounts
        logger.info("Batch generation started for %d accounts", len(accounts))

        for acct in accounts:
            account_id = acct["id"]
            niche_id = acct["niche"]
            try:
                await self._fill_buffer(account_id, niche_id)
            except Exception as e:
                logger.error("[%s] Batch generation failed: %s", account_id, e)

        logger.info("Batch generation complete")

    async def _fill_buffer(self, account_id: str, niche_id: str) -> None:
        """Fill queue to buffer_days for a single account."""
        session = get_sync_session()
        try:
            # Count existing READY/RETRY items
            stmt = select(func.count(QueueItem.id)).where(
                QueueItem.account_id == account_id,
                QueueItem.status.in_([QueueStatus.READY, QueueStatus.RETRY]),
            )
            result = session.execute(stmt)
            existing = result.scalar() or 0

            target = self.buffer_days * self.posts_per_day * 4  # 4 platforms
            needed_contents = max(0, (target - existing) // 4)

            if needed_contents == 0:
                logger.info("[%s] Buffer full (%d items), skipping", account_id, existing)
                return

            logger.info(
                "[%s] Need %d content pieces (have %d queue items, target %d)",
                account_id, needed_contents, existing, target,
            )

            for i in range(needed_contents):
                content = await self.pipeline.generate_content(account_id, niche_id)
                if content and content.status == ContentStatus.READY:
                    self._enqueue_content(session, content, account_id)
                    logger.info(
                        "[%s] Enqueued content #%d (%d/%d)",
                        account_id, content.id, i + 1, needed_contents,
                    )
        finally:
            session.close()

    def _enqueue_content(self, session, content: Content, account_id: str) -> None:
        """Create queue items for all variants of a content piece."""
        # Reload variants
        stmt = select(ContentVariant).where(ContentVariant.content_id == content.id)
        result = session.execute(stmt)
        variants = result.scalars().all()

        now = datetime.utcnow()
        # Find the latest scheduled item to stagger after it
        latest_stmt = (
            select(func.max(QueueItem.scheduled_at))
            .where(QueueItem.account_id == account_id)
        )
        latest_result = session.execute(latest_stmt)
        latest_time = latest_result.scalar() or now

        base_time = max(now, latest_time) + timedelta(minutes=self.stagger_minutes)
        jitter = timedelta(minutes=random.uniform(-self.jitter_minutes, self.jitter_minutes))

        for variant in variants:
            item = QueueItem(
                content_variant_id=variant.id,
                account_id=account_id,
                platform=variant.platform,
                status=QueueStatus.READY,
                scheduled_at=base_time + jitter,
            )
            session.add(item)

        session.commit()
