"""Load all niches from YAML config and resolve engine classes."""

from __future__ import annotations

import importlib
import logging
from typing import Any

from ..config import Config
from .base import NicheConfig, NicheEngine

logger = logging.getLogger(__name__)


def _resolve_class(class_path: str) -> type:
    """Resolve 'gold.niches.crypto_finance.CryptoFinanceEngine' to the class."""
    module_path, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def load_niches(config: Config) -> dict[str, NicheEngine]:
    """Load all niche engines from configuration."""
    engines: dict[str, NicheEngine] = {}

    for niche_id, niche_data in config.niches.items():
        engine_class_path = niche_data.get("engine_class", "")
        if not engine_class_path:
            logger.warning("No engine_class for niche %s, skipping", niche_id)
            continue

        # Collect known fields and pass everything else into 'extra'
        _known_keys = {
            "id", "name", "tone", "target_duration", "has_voiceover",
            "topics", "hashtags", "cta", "voice", "engine_class",
            "video_style",
        }
        extra = {k: v for k, v in niche_data.items() if k not in _known_keys}

        niche_cfg = NicheConfig(
            id=niche_id,
            name=niche_data.get("name", niche_id),
            tone=niche_data.get("tone", "engaging"),
            target_duration=niche_data.get("target_duration", 40),
            has_voiceover=niche_data.get("has_voiceover", True),
            topics=niche_data.get("topics", []),
            hashtags=niche_data.get("hashtags", []),
            cta=niche_data.get("cta", {}),
            voice=niche_data.get("voice", {}),
            extra=extra,
        )

        try:
            engine_cls = _resolve_class(engine_class_path)
            engines[niche_id] = engine_cls(niche_cfg)
            logger.info("Loaded niche engine: %s -> %s", niche_id, engine_class_path)
        except Exception as e:
            logger.error("Failed to load niche %s: %s", niche_id, e)

    return engines
