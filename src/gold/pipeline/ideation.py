"""IdeaGenerator: uses Claude API to generate topic ideas for a niche."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import anthropic
from sqlalchemy import select

from ..config import Config
from ..models.content import Content
from ..models.db import get_sync_session
from ..utils.retry import retry

logger = logging.getLogger(__name__)


class IdeaGenerator:
    def __init__(self, config: Config):
        self.config = config
        self.client = anthropic.Anthropic(api_key=config.env("ANTHROPIC_API_KEY"))
        self.model = config.get("api.anthropic.model", "claude-sonnet-4-20250514")

    def _check_topic_overrides(self, niche_id: str) -> list[dict] | None:
        """Check for manual topic overrides in data/topic_overrides.json."""
        try:
            overrides_path = self.config.root / "data" / "topic_overrides.json"
            if not overrides_path.exists():
                return None
            import json as _json
            overrides = _json.loads(overrides_path.read_text())
            topics = overrides.get(niche_id, [])
            if not topics:
                return None
            # Convert override topics to idea format
            ideas = []
            for topic in topics:
                ideas.append({
                    "title": topic,
                    "hook": topic,
                    "angle": "User-specified topic override",
                    "target_emotion": "curiosity",
                })
            logger.info("Using %d topic override(s) for %s", len(ideas), niche_id)
            # Clear used overrides
            overrides[niche_id] = []
            overrides_path.write_text(_json.dumps(overrides, indent=2))
            return ideas
        except Exception as e:
            logger.warning("Failed to check topic overrides: %s", e)
            return None

    @retry(max_retries=2, base_delay=2.0, exceptions=(anthropic.APIError,))
    async def generate_ideas(self, niche_id: str, count: int = 5) -> list[dict]:
        """Generate topic ideas for a niche, deduped against last 90 days."""
        # Check for manual topic overrides first
        overrides = self._check_topic_overrides(niche_id)
        if overrides:
            return overrides

        niche_config = self.config.niches.get(niche_id, {})
        niche_name = niche_config.get("name", niche_id)
        topics = niche_config.get("topics", [])
        tone = niche_config.get("tone", "engaging")

        # Get recent titles for dedup
        recent_titles = self._get_recent_titles(niche_id, days=90)

        prompt = f"""Generate {count} unique, viral short-form video topic ideas for the "{niche_name}" niche.

Tone: {tone}
Topic categories: {', '.join(topics)}

Recent topics to AVOID duplicating:
{chr(10).join(f'- {t}' for t in recent_titles[-30:]) if recent_titles else '(none yet)'}

For each idea, provide:
1. title: A catchy, clickbait-worthy title (max 80 chars)
2. hook: The first 3-second hook text that stops the scroll
3. angle: The unique angle or surprising element
4. target_emotion: The primary emotion to evoke

Return as a JSON array of objects with keys: title, hook, angle, target_emotion.
Only return the JSON array, no other text."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        ideas = json.loads(text)
        logger.info("Generated %d ideas for %s", len(ideas), niche_id)
        return ideas

    def _get_recent_titles(self, niche_id: str, days: int = 90) -> list[str]:
        try:
            session = get_sync_session()
            cutoff = datetime.utcnow() - timedelta(days=days)
            stmt = (
                select(Content.title)
                .where(Content.niche == niche_id, Content.created_at >= cutoff)
                .order_by(Content.created_at.desc())
            )
            result = session.execute(stmt)
            titles = [row[0] for row in result]
            session.close()
            return titles
        except Exception:
            return []
