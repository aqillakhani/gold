"""Per-platform rate limit tracking."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from ..models.analytics import RateLimitUsage
from ..models.db import get_sync_session

logger = logging.getLogger(__name__)

PLATFORM_LIMITS = {
    "facebook": {"calls_per_window": 200, "window_hours": 1},
    "instagram": {"calls_per_window": 100, "window_hours": 24},
    "youtube": {"calls_per_window": 6, "window_hours": 24},
    "tiktok": {"calls_per_window": 15, "window_hours": 24},
}


class RateLimiter:
    def can_post(self, platform: str, account_id: str) -> bool:
        """Check if posting is allowed under rate limits."""
        limits = PLATFORM_LIMITS.get(platform)
        if not limits:
            return True

        session = get_sync_session()
        try:
            window_start = datetime.utcnow() - timedelta(hours=limits["window_hours"])
            stmt = select(RateLimitUsage).where(
                RateLimitUsage.platform == platform,
                RateLimitUsage.account_id == account_id,
                RateLimitUsage.window_start >= window_start,
            )
            result = session.execute(stmt)
            records = result.scalars().all()
            total_calls = sum(r.calls_made for r in records)
            return total_calls < limits["calls_per_window"]
        finally:
            session.close()

    def record_call(self, platform: str, account_id: str) -> None:
        """Record an API call for rate tracking."""
        session = get_sync_session()
        try:
            now = datetime.utcnow()
            limits = PLATFORM_LIMITS.get(platform, {"window_hours": 1})
            record = RateLimitUsage(
                platform=platform,
                account_id=account_id,
                calls_made=1,
                window_start=now,
                window_end=now + timedelta(hours=limits["window_hours"]),
            )
            session.add(record)
            session.commit()
        finally:
            session.close()
