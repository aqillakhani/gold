"""Jamendo music search and download for context-aware background music.

Searches the Jamendo API for royalty-free instrumental tracks based on
AI-generated mood/genre tags from the video script. Downloads and caches
tracks locally to avoid re-downloading.

Requires a free Jamendo client_id from https://devportal.jamendo.com
Set JAMENDO_CLIENT_ID in your .env file.
"""

from __future__ import annotations

import hashlib
import logging
import random
from pathlib import Path
from typing import Any

import httpx

from ..utils.retry import retry

logger = logging.getLogger(__name__)

JAMENDO_API_BASE = "https://api.jamendo.com/v3.0"

# Map descriptive mood words to Jamendo-compatible tags
MOOD_TAG_MAP = {
    # Techy (mapped to calm variants — avoid hype)
    # NOTE: "electronic" tag on Jamendo returns high-energy EDM that drowns
    # voiceover.  Map everything to ambient/chillout instead.
    "hip-hop": "chillout",
    "hip hop": "chillout",
    "trap": "chillout",
    "edm": "chillout",
    "synth": "ambient",
    "electronic": "ambient",
    "upbeat": "chillout",
    "hype": "chillout",
    "energetic": "chillout",
    "techy": "ambient",
    "futuristic": "ambient",
    "cyberpunk": "ambient",
    "modern": "ambient",
    # Dark / Moody
    "dark": "dark",
    "mysterious": "dark",
    "suspenseful": "ambient",
    "noir": "dark",
    "eerie": "dark",
    "haunting": "ambient",
    "atmospheric": "ambient",
    # Calm / Chill
    "lofi": "lofi",
    "lo-fi": "lofi",
    "chill": "chillout",
    "relaxed": "relaxing",
    "ambient": "ambient",
    "soft": "chillout",
    "calm": "chillout",
    "minimal": "ambient",
    # Cinematic (mapped to calmer variants)
    "cinematic": "cinematic",
    "epic": "cinematic",
    "dramatic": "cinematic",
    "orchestral": "orchestral",
    "inspiring": "inspiring",
    "emotional": "ambient",
    "piano": "piano",
    # Corporate / tech (subtle underscore style)
    "corporate": "corporate",
    "technology": "ambient",
    "business": "corporate",
}


def _normalize_tags(raw_tags: list[str]) -> list[str]:
    """Normalize raw AI-generated tags to Jamendo-compatible tags."""
    normalized = []
    for tag in raw_tags:
        tag_lower = tag.lower().strip()
        # Check direct mapping
        if tag_lower in MOOD_TAG_MAP:
            normalized.append(MOOD_TAG_MAP[tag_lower])
        else:
            # Use as-is if it's a simple word (Jamendo accepts freeform tags)
            cleaned = tag_lower.replace(" ", "").replace("-", "")
            if cleaned.isalpha() and len(cleaned) <= 20:
                normalized.append(tag_lower)
    # Deduplicate while preserving order
    seen = set()
    result = []
    for t in normalized:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


@retry(max_retries=2, base_delay=2.0, exceptions=(httpx.HTTPError,))
async def search_jamendo_tracks(
    client_id: str,
    tags: list[str],
    speed: str = "medium",
    limit: int = 10,
    duration_min: int = 60,
    duration_max: int = 300,
) -> list[dict[str, Any]]:
    """Search Jamendo for instrumental tracks matching tags and speed.

    Args:
        client_id: Jamendo API client ID.
        tags: List of mood/genre tags (e.g. ["electronic", "energetic", "hiphop"]).
        speed: Tempo filter — verylow, low, medium, high, veryhigh.
        limit: Max number of results.
        duration_min: Minimum track duration in seconds.
        duration_max: Maximum track duration in seconds.

    Returns:
        List of track dicts with keys: id, name, artist, duration, audio_url, tags.
    """
    normalized = _normalize_tags(tags)
    if not normalized:
        normalized = ["ambient", "cinematic"]  # safe default — calm, non-distracting

    params: dict[str, Any] = {
        "client_id": client_id,
        "format": "json",
        "limit": limit,
        "vocalinstrumental": "instrumental",
        "audioformat": "mp32",  # 320kbps mp3
        "order": "relevance",
        "fuzzytags": "+".join(normalized),
        "include": "musicinfo",
    }

    if speed and speed in ("verylow", "low", "medium", "high", "veryhigh"):
        params["speed"] = speed

    if duration_min and duration_max:
        params["durationbetween"] = f"{duration_min}_{duration_max}"

    logger.info(
        "Jamendo search: tags=%s, speed=%s, duration=%d-%ds",
        normalized, speed, duration_min, duration_max,
    )

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{JAMENDO_API_BASE}/tracks/", params=params)
        resp.raise_for_status()
        data = resp.json()

    results = data.get("results", [])
    if not results:
        logger.warning("Jamendo: no results for tags=%s, speed=%s", normalized, speed)
        return []

    tracks = []
    for track in results:
        audio_url = track.get("audiodownload") or track.get("audio")
        if not audio_url:
            continue
        tracks.append({
            "id": track.get("id"),
            "name": track.get("name", "Unknown"),
            "artist": track.get("artist_name", "Unknown"),
            "duration": track.get("duration", 0),
            "audio_url": audio_url,
            "tags": normalized,
        })

    logger.info("Jamendo: found %d tracks for tags=%s", len(tracks), normalized)
    return tracks


async def download_jamendo_track(
    track: dict[str, Any],
    cache_dir: Path,
) -> Path:
    """Download a Jamendo track to local cache. Skips if already cached.

    Args:
        track: Track dict from search_jamendo_tracks().
        cache_dir: Directory to store downloaded tracks.

    Returns:
        Path to the downloaded MP3 file.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Use track ID + hash for stable filename
    track_id = track["id"]
    tags_str = "_".join(track.get("tags", [])[:3])
    filename = f"jamendo_{track_id}_{tags_str}.mp3"
    cached_path = cache_dir / filename

    if cached_path.exists() and cached_path.stat().st_size > 10_000:
        logger.info("Jamendo cache hit: %s", cached_path.name)
        return cached_path

    audio_url = track["audio_url"]
    logger.info(
        "Downloading Jamendo track: %s by %s (%ds) → %s",
        track["name"], track["artist"], track["duration"], cached_path.name,
    )

    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resp = await client.get(audio_url)
        resp.raise_for_status()
        cached_path.write_bytes(resp.content)

    size_kb = cached_path.stat().st_size / 1024
    logger.info("Downloaded: %s (%.0f KB)", cached_path.name, size_kb)
    return cached_path


async def find_and_download_music(
    client_id: str,
    tags: list[str],
    speed: str = "medium",
    cache_dir: Path | None = None,
    duration_min: int = 60,
    duration_max: int = 300,
) -> Path | None:
    """Search Jamendo and download the best matching track.

    Searches with the given tags, picks a random track from top results
    to add variety, downloads it to the cache directory.

    Args:
        client_id: Jamendo API client ID.
        tags: Mood/genre tags from the script.
        speed: Tempo filter.
        cache_dir: Where to cache downloaded tracks.
        duration_min: Minimum track duration.
        duration_max: Maximum track duration.

    Returns:
        Path to downloaded track, or None if search/download fails.
    """
    if not client_id:
        logger.warning("No Jamendo client_id configured — skipping music search")
        return None

    try:
        tracks = await search_jamendo_tracks(
            client_id=client_id,
            tags=tags,
            speed=speed,
            limit=10,
            duration_min=duration_min,
            duration_max=duration_max,
        )

        if not tracks:
            # Retry with fewer tags (broader search)
            if len(tags) > 1:
                logger.info("Retrying Jamendo with fewer tags: %s", tags[:2])
                tracks = await search_jamendo_tracks(
                    client_id=client_id,
                    tags=tags[:2],
                    speed=speed,
                    limit=10,
                    duration_min=duration_min,
                    duration_max=duration_max,
                )

        if not tracks:
            return None

        # Pick from top 5 randomly for variety
        choice = random.choice(tracks[:min(5, len(tracks))])
        logger.info(
            "Selected: '%s' by %s (tags: %s)",
            choice["name"], choice["artist"], choice["tags"],
        )

        if cache_dir is None:
            cache_dir = Path("data/media/audio/music/jamendo")

        return await download_jamendo_track(choice, cache_dir)

    except Exception as e:
        logger.error("Jamendo music search failed: %s", e)
        return None
