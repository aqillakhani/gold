"""Sound design utility — adds SFX to video compositions."""

from __future__ import annotations

import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)

# SFX directory structure
SFX_BASE = Path("data/media/audio/sfx")

SFX_CATEGORIES = {
    "transitions": SFX_BASE / "transitions",
    "impacts": SFX_BASE / "impacts",
    "risers": SFX_BASE / "risers",
    "notifications": SFX_BASE / "notifications",
    "money": SFX_BASE / "money",
}

# Niche-specific SFX profiles
NICHE_SFX_PROFILES = {
    "true_crime": {
        "scene_transition": "transitions",
        "hook_reveal": "impacts",
        "tension_build": "risers",
        "hook_volume": 0.6,
        "transition_volume": 0.3,
    },
    "ai_tools": {
        "scene_transition": "transitions",
        "hook_reveal": "notifications",
        "tension_build": None,
        "hook_volume": 0.5,
        "transition_volume": 0.25,
    },
    "personal_finance": {
        "scene_transition": "transitions",
        "hook_reveal": "money",
        "tension_build": None,
        "hook_volume": 0.4,
        "transition_volume": 0.2,
    },
    "reddit_stories": {
        "scene_transition": "transitions",
        "hook_reveal": "impacts",
        "tension_build": None,
        "hook_volume": 0.4,
        "transition_volume": 0.2,
    },
    "betrayal_revenge": {
        "scene_transition": "transitions",
        "hook_reveal": "impacts",
        "tension_build": "risers",
        "hook_volume": 0.5,
        "transition_volume": 0.25,
    },
    "english_learning": {
        "scene_transition": "notifications",
        "hook_reveal": "notifications",
        "tension_build": None,
        "hook_volume": 0.3,
        "transition_volume": 0.15,
    },
}


def get_random_sfx(category: str) -> Path | None:
    """Get a random SFX file from the specified category."""
    sfx_dir = SFX_CATEGORIES.get(category)
    if not sfx_dir or not sfx_dir.exists():
        return None

    sfx_files = list(sfx_dir.glob("*.mp3")) + list(sfx_dir.glob("*.wav"))
    if not sfx_files:
        return None

    return random.choice(sfx_files)


def get_niche_sfx_profile(niche_id: str) -> dict:
    """Get the SFX profile for a niche."""
    return NICHE_SFX_PROFILES.get(niche_id, NICHE_SFX_PROFILES["reddit_stories"])


def get_hook_sfx(niche_id: str) -> tuple[Path | None, float]:
    """Get the hook reveal SFX and volume for a niche.

    Returns (sfx_path, volume) or (None, 0).
    """
    profile = get_niche_sfx_profile(niche_id)
    category = profile.get("hook_reveal")
    if not category:
        return None, 0.0

    sfx = get_random_sfx(category)
    volume = profile.get("hook_volume", 0.4)
    return sfx, volume


def get_transition_sfx(niche_id: str) -> tuple[Path | None, float]:
    """Get a scene transition SFX and volume for a niche.

    Returns (sfx_path, volume) or (None, 0).
    """
    profile = get_niche_sfx_profile(niche_id)
    category = profile.get("scene_transition")
    if not category:
        return None, 0.0

    sfx = get_random_sfx(category)
    volume = profile.get("transition_volume", 0.2)
    return sfx, volume


def get_tension_sfx(niche_id: str) -> tuple[Path | None, float]:
    """Get a tension riser SFX for niches that use them.

    Returns (sfx_path, volume) or (None, 0).
    """
    profile = get_niche_sfx_profile(niche_id)
    category = profile.get("tension_build")
    if not category:
        return None, 0.0

    sfx = get_random_sfx(category)
    return sfx, 0.3


def build_sfx_filter_chain(
    niche_id: str,
    scene_timestamps: list[float],
    total_duration: float,
) -> tuple[list[str], list[str], str]:
    """Build FFmpeg filter chain for SFX overlay.

    Args:
        niche_id: The niche ID for SFX profile selection.
        scene_timestamps: List of timestamps where scenes transition.
        total_duration: Total video duration.

    Returns:
        (input_args, filter_chains, final_mix_label) for FFmpeg integration.
        Returns empty lists if no SFX available.
    """
    profile = get_niche_sfx_profile(niche_id)
    input_args: list[str] = []
    filter_chains: list[str] = []
    sfx_labels: list[str] = []
    input_idx_start = 1  # Input 0 is the video file, SFX start at 1

    # Hook reveal SFX at t=0
    hook_sfx, hook_vol = get_hook_sfx(niche_id)
    if hook_sfx:
        idx = input_idx_start
        input_args.extend(["-i", str(hook_sfx)])
        filter_chains.append(
            f"[{idx}:a]volume={hook_vol},adelay=500|500[sfx_hook]"
        )
        sfx_labels.append("[sfx_hook]")
        input_idx_start += 1

    # Transition SFX at scene boundaries (skip first, limit to 3 to avoid clutter)
    transition_points = scene_timestamps[1:4] if len(scene_timestamps) > 1 else []
    for i, ts in enumerate(transition_points):
        trans_sfx, trans_vol = get_transition_sfx(niche_id)
        if trans_sfx:
            idx = input_idx_start
            input_args.extend(["-i", str(trans_sfx)])
            delay_ms = int(ts * 1000)
            filter_chains.append(
                f"[{idx}:a]volume={trans_vol},adelay={delay_ms}|{delay_ms}[sfx_trans_{i}]"
            )
            sfx_labels.append(f"[sfx_trans_{i}]")
            input_idx_start += 1

    if not sfx_labels:
        return [], [], ""

    # Mix all SFX into one track
    if len(sfx_labels) == 1:
        mix_label = sfx_labels[0].strip("[]")
    else:
        mix_inputs = "".join(sfx_labels)
        mix_label = "sfx_mixed"
        filter_chains.append(
            f"{mix_inputs}amix=inputs={len(sfx_labels)}:duration=longest[{mix_label}]"
        )

    return input_args, filter_chains, mix_label
