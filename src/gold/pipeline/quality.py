"""QualityGate: automated checks on generated content."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from ..config import Config
from ..utils.ffmpeg import get_duration

logger = logging.getLogger(__name__)

BANNED_WORDS = [
    "kill yourself", "suicide", "self-harm", "racial slur",
    "child abuse", "terrorism", "bomb threat",
]


class QualityGate:
    def __init__(self, config: Config):
        self.config = config
        self.min_duration = config.get("quality_gate.min_duration", 15)
        self.max_duration = config.get("quality_gate.max_duration", 60)
        self.max_file_size_mb = config.get("quality_gate.max_file_size_mb", 100)
        self.moderation_enabled = config.get("quality_gate.moderation_enabled", True)
        self.openai_key = config.env("OPENAI_API_KEY")

    async def check(self, video_path: Path, script_text: str = "") -> tuple[bool, list[str]]:
        """Run all quality checks. Returns (passed, list_of_issues)."""
        issues: list[str] = []

        # Duration check
        try:
            duration = await get_duration(video_path)
            if duration < self.min_duration:
                issues.append(f"Too short: {duration:.1f}s < {self.min_duration}s")
            if duration > self.max_duration:
                issues.append(f"Too long: {duration:.1f}s > {self.max_duration}s")
        except Exception as e:
            issues.append(f"Could not read duration: {e}")

        # File size check
        size_mb = video_path.stat().st_size / (1024 * 1024)
        if size_mb > self.max_file_size_mb:
            issues.append(f"File too large: {size_mb:.1f}MB > {self.max_file_size_mb}MB")
        if size_mb < 0.1:
            issues.append(f"File suspiciously small: {size_mb:.3f}MB")

        # Banned words check
        text_lower = script_text.lower()
        for word in BANNED_WORDS:
            if word in text_lower:
                issues.append(f"Banned content detected: '{word}'")

        # OpenAI Moderation API (free)
        if self.moderation_enabled and script_text and self.openai_key:
            mod_issues = await self._moderation_check(script_text)
            issues.extend(mod_issues)

        passed = len(issues) == 0
        if not passed:
            logger.warning("Quality gate FAILED for %s: %s", video_path.name, issues)
        else:
            logger.info("Quality gate PASSED for %s", video_path.name)

        return passed, issues

    async def _moderation_check(self, text: str) -> list[str]:
        """Check text against OpenAI moderation API."""
        issues = []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/moderations",
                    headers={"Authorization": f"Bearer {self.openai_key}"},
                    json={"input": text},
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                if results and results[0].get("flagged"):
                    categories = results[0].get("categories", {})
                    flagged = [cat for cat, val in categories.items() if val]
                    issues.append(f"Moderation flagged: {', '.join(flagged)}")
        except Exception as e:
            logger.warning("Moderation API error (non-blocking): %s", e)
        return issues
