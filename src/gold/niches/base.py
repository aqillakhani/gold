"""NicheEngine ABC and NicheConfig dataclass."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NicheConfig:
    id: str
    name: str
    tone: str = "engaging"
    target_duration: int = 40
    has_voiceover: bool = True
    topics: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    cta: dict[str, str] = field(default_factory=dict)
    voice: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


class NicheEngine(ABC):
    """Base class for niche-specific content enrichment."""

    def __init__(self, config: NicheConfig):
        self.niche_config = config

    @abstractmethod
    async def enrich_idea(self, idea: dict) -> dict:
        """Add niche-specific data to an idea (e.g., live prices, trending tools)."""
        ...

    @abstractmethod
    async def customize_script(self, script: dict) -> dict:
        """Apply niche-specific modifications to a script."""
        ...

    def get_extra_prompt_context(self) -> str:
        """Return extra context to inject into prompts."""
        return ""
