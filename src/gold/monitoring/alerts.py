"""Discord webhook notifications for monitoring alerts."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from ..config import Config

logger = logging.getLogger(__name__)


class AlertManager:
    def __init__(self, config: Config):
        self.config = config
        self.webhook_url = config.env("DISCORD_WEBHOOK_URL")

    async def send(self, title: str, message: str, level: str = "info") -> None:
        """Send alert to Discord webhook."""
        if not self.webhook_url:
            logger.warning("Discord webhook URL not configured, skipping alert")
            return

        color_map = {
            "info": 0x58A6FF,
            "warning": 0xF0C040,
            "error": 0xF85149,
            "success": 0x3FB950,
        }

        payload = {
            "embeds": [
                {
                    "title": f"Gold: {title}",
                    "description": message,
                    "color": color_map.get(level, 0x58A6FF),
                    "timestamp": datetime.utcnow().isoformat(),
                    "footer": {"text": "Gold Platform"},
                }
            ]
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(self.webhook_url, json=payload)
                resp.raise_for_status()
            logger.info("Alert sent: %s", title)
        except Exception as e:
            logger.error("Failed to send Discord alert: %s", e)

    async def alert_dead_letter(self, account_id: str, platform: str, error: str) -> None:
        await self.send(
            "Dead Letter",
            f"**Account:** {account_id}\n**Platform:** {platform}\n**Error:** {error[:200]}",
            level="error",
        )

    async def alert_empty_queue(self, account_id: str) -> None:
        await self.send(
            "Empty Queue Warning",
            f"Account **{account_id}** has no READY items in queue!",
            level="warning",
        )

    async def alert_auth_failure(self, account_id: str, platform: str) -> None:
        await self.send(
            "Auth Failure",
            f"Token refresh failed for **{account_id}** on **{platform}**",
            level="error",
        )

    async def daily_summary(self, stats: dict) -> None:
        lines = []
        for account_id, data in stats.items():
            lines.append(
                f"**{account_id}**: {data.get('posted', 0)} posted, "
                f"{data.get('failed', 0)} failed, {data.get('queue', 0)} queued"
            )
        await self.send(
            "Daily Summary",
            "\n".join(lines) or "No activity",
            level="info",
        )
