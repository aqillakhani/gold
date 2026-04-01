"""Bootstrap, wire dependencies, and start the Gold platform."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import uvicorn

from .config import Config
from .models.db import create_tables_sync, init_async_db, init_sync_db
from .monitoring.alerts import AlertManager
from .monitoring.dashboard import create_dashboard
from .monitoring.metrics import MetricsCollector
from .scheduling.batch_generator import BatchGenerator
from .scheduling.queue_manager import QueueManager
from .scheduling.scheduler import PostScheduler

logger = logging.getLogger(__name__)


class GoldApp:
    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self._setup_logging()
        self._init_db()

        self.queue_manager = QueueManager(self.config)
        self.batch_generator = BatchGenerator(self.config)
        self.scheduler = PostScheduler(self.config)
        self.alerts = AlertManager(self.config)
        self.metrics = MetricsCollector(self.config)
        self.dashboard = create_dashboard(self.config)

    def _setup_logging(self) -> None:
        log_level = self.config.get("app.log_level", "INFO")
        log_file = self.config.root / self.config.get("app.log_file", "data/logs/gold.log")
        log_file.parent.mkdir(parents=True, exist_ok=True)

        logging.basicConfig(
            level=getattr(logging, log_level),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(str(log_file), encoding="utf-8"),
            ],
        )

    def _init_db(self) -> None:
        init_sync_db(self.config.db_url_sync)
        init_async_db(self.config.db_url)
        create_tables_sync()
        logger.info("Database initialized at %s", self.config.data_dir / "gold.db")

    async def _post_callback(self, account_id: str, platform: str | None = None) -> None:
        """Called by scheduler to post content for an account/platform."""
        try:
            await self.queue_manager.process_account(account_id, platform=platform)
        except Exception as e:
            logger.error("Post callback failed for %s/%s: %s", account_id, platform, e)
            await self.alerts.send(
                "Post Failed",
                f"Account: {account_id}\nPlatform: {platform}\nError: {str(e)[:200]}",
                level="error",
            )

    async def _batch_callback(self) -> None:
        """Called nightly to generate content + produce TikTok posting guide."""
        try:
            await self.batch_generator.run()
        except Exception as e:
            logger.error("Batch generation failed: %s", e)
            await self.alerts.send(
                "Batch Generation Failed", str(e)[:500], level="error"
            )

        # Generate daily TikTok posting guide for manual uploads
        try:
            from .scheduling.tiktok_guide import generate_daily_guide
            guide = generate_daily_guide(self.config)
            if guide:
                logger.info("TikTok guide ready: %s", guide)
        except Exception as e:
            logger.error("TikTok guide generation failed: %s", e)

    async def _metrics_callback(self) -> None:
        """Called periodically to collect engagement metrics."""
        try:
            await self.metrics.collect_all()
        except Exception as e:
            logger.error("Metrics collection failed: %s", e)

    def run(self) -> None:
        """Start the Gold platform (scheduler + dashboard)."""
        logger.info("Starting Gold Platform v%s", self.config.get("app.version", "0.1.0"))
        logger.info("Dry run: %s", self.config.dry_run)

        # Setup scheduler
        self.scheduler.setup(
            post_callback=self._post_callback,
            batch_callback=self._batch_callback,
        )
        self.scheduler.start()

        # Run dashboard (this blocks)
        port = self.config.get("monitoring.dashboard_port", 8420)
        logger.info("Dashboard at http://localhost:%d", port)

        uvicorn.run(
            self.dashboard,
            host="0.0.0.0",
            port=port,
            log_level="info",
        )

    async def generate_now(self, account_id: str | None = None) -> None:
        """Generate content immediately (for testing/CLI use)."""
        if account_id:
            accounts = [a for a in self.config.accounts.get("accounts", []) if a["id"] == account_id]
        else:
            accounts = self.config.accounts.get("accounts", [])

        active_niches = self.config.get("app.active_niches", None)
        if active_niches:
            accounts = [a for a in accounts if a["niche"] in active_niches]

        for acct in accounts:
            logger.info("Generating content for %s...", acct["id"])
            await self.batch_generator._fill_buffer(acct["id"], acct["niche"])
