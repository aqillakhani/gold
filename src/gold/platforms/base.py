"""PlatformAdapter ABC — base class for all platform integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class PlatformAdapter(ABC):
    """Base class for posting content to a social media platform."""

    platform_name: str = ""

    @abstractmethod
    async def post(
        self,
        video_path: Path,
        caption: str,
        hashtags: list[str],
        thumbnail_path: Path | None = None,
    ) -> dict:
        """Post content and return platform response with post_id."""
        ...

    @abstractmethod
    async def refresh_auth(self) -> None:
        """Refresh authentication tokens if needed."""
        ...

    @abstractmethod
    async def get_metrics(self, post_id: str) -> dict:
        """Fetch engagement metrics for a post."""
        ...

    @abstractmethod
    async def check_rate_limit(self) -> bool:
        """Return True if posting is allowed under current rate limits."""
        ...
