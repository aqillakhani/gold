"""APScheduler setup with warmup gate, platform-optimized times, and jitter.

Posting schedule based on 2025-2026 research (Buffer 9.6M posts, 7M+ TikTok):
- YouTube Shorts: 3x/day evening (6 PM, 8 PM, 10 PM EST) — best Fri/Sat/Thu
- TikTok: 3x/day spread (10 AM, 3 PM, 8 PM EST) — best Thu/Fri/Sat
- Instagram Reels: 2x/day max (9 AM, 8 PM EST) — best Thu/Wed/Tue
- Facebook: 2x/day (1 PM, 7 PM EST)
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import Config

logger = logging.getLogger(__name__)

# Default platform posting slots (hour in EST/UTC-5)
# Each slot is (hour_start, hour_end) — scheduler picks random hour within range
# Used for single-video niches (ai_tools, true_crime, personal_finance, english_learning)
PLATFORM_SLOTS = {
    "youtube":   [(18, 19), (20, 21), (22, 23)],  # 6-7 PM, 8-9 PM, 10-11 PM
    "tiktok":    [(10, 11), (15, 16), (20, 21)],   # 10-11 AM, 3-4 PM, 8-9 PM
    "instagram": [(9, 10), (20, 21)],               # 9-10 AM, 8-9 PM (max 2/day)
    "facebook":  [(13, 15), (19, 21)],               # 1-3 PM, 7-9 PM
}

# Multi-part niches post 1 part per day (3-day story arc).
# reddit_stories and betrayal_revenge share StoryVault — offset times.
MULTI_PART_SLOTS = {
    "reddit_stories": {
        "youtube":   [(18, 19)],     # 6 PM
        "tiktok":    [(20, 21)],     # 8 PM
        "instagram": [(9, 10)],      # 9 AM
        "facebook":  [(13, 14)],
    },
    "betrayal_revenge": {
        "youtube":   [(20, 21)],     # 8 PM (offset from reddit)
        "tiktok":    [(18, 19)],     # 6 PM
        "instagram": [(20, 21)],     # 8 PM
        "facebook":  [(19, 20)],
    },
}

# Max posts per day per platform — 1/day while channels grow
PLATFORM_MAX_POSTS = {
    "youtube": 1,
    "tiktok": 1,
    "instagram": 1,
    "facebook": 1,
}

# Niche-specific time adjustments (offset hours from default PLATFORM_SLOTS)
# Only applies to non-multi-part niches (multi-part niches use MULTI_PART_SLOTS directly)
NICHE_TIME_OFFSETS = {
    "true_crime":        0,    # evening bingers — default works
    "ai_tools":         -2,    # tech audience slightly earlier
    "personal_finance": -1,    # professional audience slightly earlier
    "english_learning": -2,    # global audience, earlier windows
}


class PostScheduler:
    def __init__(self, config: Config):
        self.config = config
        self.scheduler = AsyncIOScheduler()
        self.jitter_minutes = config.get("scheduling.jitter_minutes", 15)
        self.posts_per_day = config.get("scheduling.posts_per_day_per_account", 3)
        self.batch_hour = config.get("scheduling.batch_generation_hour", 2)
        self.automated_platforms = set(
            config.get("scheduling.automated_platforms", ["youtube", "instagram"])
        )

    def _is_warmup_complete(self, account_id: str) -> bool:
        """Check if an account has completed warmup."""
        accounts = self.config.accounts.get("accounts", [])
        acct = next((a for a in accounts if a["id"] == account_id), None)
        if not acct:
            return False
        return acct.get("warmup_complete", False)

    def _get_active_accounts(self) -> list[dict]:
        """Get accounts that are active niches and warmup-complete."""
        active_niches = self.config.get("active_niches", [])
        accounts = self.config.accounts.get("accounts", [])
        active = []
        for acct in accounts:
            if active_niches and acct["niche"] not in active_niches:
                continue
            active.append(acct)
        return active

    def setup(self, post_callback, batch_callback) -> None:
        """Schedule per-platform posting jobs and the nightly batch generator.

        Each platform gets its own optimized posting times rather than
        all platforms posting simultaneously.
        """
        accounts = self._get_active_accounts()

        # Schedule nightly batch generation
        self.scheduler.add_job(
            batch_callback,
            CronTrigger(hour=self.batch_hour, minute=0),
            id="batch_generator",
            name="Nightly batch content generation",
            replace_existing=True,
        )

        # Create a warmup-gated wrapper for the post callback
        async def _warmup_gated_post(account_id: str, platform: str):
            if not self._is_warmup_complete(account_id):
                logger.warning(
                    "[%s] Warmup not complete — skipping automated post. "
                    "Set warmup_complete: true in accounts.yaml to enable.",
                    account_id,
                )
                return
            await post_callback(account_id, platform)

        # Schedule per-platform posting jobs with optimized times
        slot = 0
        for acct in accounts:
            account_id = acct["id"]
            niche = acct.get("niche", "")
            niche_offset = NICHE_TIME_OFFSETS.get(niche, 0)
            platforms = list(acct.get("platforms", {}).keys())
            is_multi_part = niche in MULTI_PART_SLOTS

            for platform in platforms:
                if platform not in self.automated_platforms:
                    continue
                if is_multi_part:
                    # Multi-part niches use dedicated staggered slots
                    niche_slots = MULTI_PART_SLOTS[niche]
                    slots_for_platform = niche_slots.get(
                        platform, niche_slots.get("youtube", [(12, 13)])
                    )
                    num_posts = len(slots_for_platform)
                else:
                    # Single-video niches use default platform slots + niche offset
                    slots_for_platform = PLATFORM_SLOTS.get(
                        platform, PLATFORM_SLOTS["youtube"]
                    )
                    num_posts = min(
                        self.posts_per_day,
                        PLATFORM_MAX_POSTS.get(platform, 3),
                    )

                for post_num in range(num_posts):
                    slot_idx = min(post_num, len(slots_for_platform) - 1)
                    window = slots_for_platform[slot_idx]

                    # Multi-part slots are already niche-specific, no offset needed
                    offset = 0 if is_multi_part else niche_offset
                    hour = random.randint(window[0], window[1] - 1) + offset
                    hour = max(0, min(23, hour))
                    minute = random.randint(0, 59)

                    label = f"part{post_num + 1}" if is_multi_part else f"#{post_num + 1}"
                    self.scheduler.add_job(
                        _warmup_gated_post,
                        CronTrigger(hour=hour, minute=minute),
                        args=[account_id, platform],
                        id=f"post_{account_id}_{platform}_{post_num}",
                        name=f"{account_id}/{platform} {label}",
                        replace_existing=True,
                        jitter=self.jitter_minutes * 60,
                    )
                    slot += 1

            if is_multi_part:
                logger.info(
                    "Scheduled multi-part posting for %s: YT/TT=3 parts, IG=1 hook",
                    account_id,
                )

        logger.info(
            "Scheduled %d posting jobs for %d accounts + nightly batch",
            slot, len(accounts),
        )

    def start(self) -> None:
        self.scheduler.start()
        logger.info("Scheduler started")

    def shutdown(self) -> None:
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")

    def get_jobs(self) -> list[dict]:
        """Get all scheduled jobs for dashboard display."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
            })
        return jobs

    def get_warmup_status(self) -> dict[str, bool]:
        """Get warmup status for all accounts (for dashboard display)."""
        accounts = self._get_active_accounts()
        return {acct["id"]: acct.get("warmup_complete", False) for acct in accounts}
