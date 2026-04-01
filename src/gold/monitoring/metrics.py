"""Engagement metrics collector — polls platform APIs."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from ..config import Config
from ..models.analytics import EngagementMetric, PostLog
from ..models.db import get_sync_session
from ..platforms.meta import FacebookAdapter, InstagramAdapter
from ..platforms.tiktok import TikTokAdapter
from ..platforms.youtube import YouTubeAdapter

logger = logging.getLogger(__name__)


class MetricsCollector:
    def __init__(self, config: Config):
        self.config = config

    async def collect_all(self) -> None:
        """Collect metrics for all recent posts."""
        session = get_sync_session()
        try:
            # Get posts from last 7 days
            cutoff = datetime.utcnow() - timedelta(days=7)
            stmt = (
                select(PostLog)
                .where(
                    PostLog.posted_at >= cutoff,
                    PostLog.status == "SUCCESS",
                    PostLog.platform_post_id.isnot(None),
                )
            )
            result = session.execute(stmt)
            posts = result.scalars().all()

            logger.info("Collecting metrics for %d recent posts", len(posts))

            for post in posts:
                try:
                    metrics = await self._fetch_metrics(post)
                    if metrics:
                        total = sum(metrics.values())
                        views = metrics.get("views", 0)
                        engagement_rate = (total - views) / max(views, 1) * 100

                        record = EngagementMetric(
                            post_log_id=post.id,
                            platform=post.platform,
                            views=views,
                            likes=metrics.get("likes", 0),
                            comments=metrics.get("comments", 0),
                            shares=metrics.get("shares", 0),
                            engagement_rate=engagement_rate,
                        )
                        session.add(record)
                except Exception as e:
                    logger.warning("Failed to collect metrics for post %d: %s", post.id, e)

            session.commit()
            logger.info("Metrics collection complete")
        finally:
            session.close()

    async def _fetch_metrics(self, post: PostLog) -> dict | None:
        """Fetch metrics for a single post from its platform."""
        adapter_map = {
            "facebook": FacebookAdapter,
            "instagram": InstagramAdapter,
            "youtube": YouTubeAdapter,
            "tiktok": TikTokAdapter,
        }

        adapter_cls = adapter_map.get(post.platform)
        if not adapter_cls:
            return None

        try:
            adapter = adapter_cls(self.config, post.account_id)
            return await adapter.get_metrics(post.platform_post_id)
        except Exception as e:
            logger.warning("[%s] Metrics fetch failed for %s: %s", post.platform, post.platform_post_id, e)
            return None
