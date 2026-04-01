"""Suno AI music generation via Apiframe — custom background tracks per video.

Generates unique instrumental tracks via the Apiframe Suno API
based on niche-specific mood prompts. Each video gets a custom track
matched to its emotional tone.

Requires SUNO_API_KEY in secrets/.env (get from https://app.apiframe.ai/dashboard/api-keys).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from ..utils.retry import retry

logger = logging.getLogger(__name__)

APIFRAME_BASE = "https://api.apiframe.pro"

# Niche-specific music generation prompts
NICHE_MUSIC_PROMPTS = {
    "reddit_stories": {
        "tags": "lofi hip hop, chill beats, mellow",
        "prompt": "Mellow lo-fi hip hop beat with soft vinyl crackle, warm Rhodes piano chords, "
                  "laid-back drum pattern, gentle bass. Perfect for storytelling podcast background. "
                  "Calm, nostalgic, slightly melancholic.",
    },
    "betrayal_revenge": {
        "tags": "dark lofi, atmospheric, moody",
        "prompt": "Dark moody lo-fi beat with deep bass, minor key piano melody, subtle tension. "
                  "Suspenseful but not overwhelming. Builds slight intensity. "
                  "Think true crime podcast underscore meets lo-fi.",
    },
    "true_crime": {
        "tags": "cinematic piano, dark orchestral, suspense",
        "prompt": "Sparse isolated piano notes with subtle cello undertones and pulsing low bass. "
                  "Desolate string arrangements that build slow tension. Think true crime documentary "
                  "underscore — investigative, unsettling, minimal. No melody, no drums, just atmosphere "
                  "and suspense. Occasional reversed reverb swells.",
    },
    "ai_tools": {
        "tags": "modern synthwave, clean electronic, futuristic",
        "prompt": "Modern clean synthwave with smooth pads, subtle arpeggiated patterns, "
                  "crisp hi-hats at low volume. Think Apple keynote or product demo music — "
                  "sleek, professional, forward-looking. Light energy without being distracting. "
                  "No heavy bass drops or EDM builds.",
    },
    "personal_finance": {
        "tags": "motivational, uplifting, acoustic, warm",
        "prompt": "Warm motivational track with gentle acoustic guitar fingerpicking, "
                  "uplifting piano chords, soft shaker percussion. Confident and trustworthy. "
                  "Think financial advisor commercial — professional, encouraging, optimistic. "
                  "Builds subtle confidence without being cheesy or over-the-top.",
    },
    "english_learning": {
        "tags": "calm acoustic, friendly, gentle",
        "prompt": "Gentle calm acoustic background with soft ukulele or guitar, "
                  "very light percussion, warm and friendly. Educational content underscore — "
                  "approachable, clean, never distracting. Think language learning app music.",
    },
}


@retry(max_retries=2, base_delay=5.0, exceptions=(httpx.HTTPError,))
async def generate_suno_track(
    api_key: str,
    niche_id: str,
    custom_prompt: str | None = None,
) -> str:
    """Submit a music generation request to Apiframe Suno API.

    Returns task_id for polling.
    """
    profile = NICHE_MUSIC_PROMPTS.get(niche_id, NICHE_MUSIC_PROMPTS["reddit_stories"])

    prompt = custom_prompt or profile["prompt"]
    tags = profile["tags"]

    body = {
        "prompt": prompt,
        "tags": tags,
        "title": f"{niche_id} background",
        "make_instrumental": True,
        "model": "V4_5",
    }

    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{APIFRAME_BASE}/suno-imagine",
            json=body,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

    task_id = data.get("task_id")
    if not task_id:
        raise RuntimeError(f"Suno API error: no task_id in response: {data}")

    logger.info("Suno generation started: task_id=%s, niche=%s", task_id, niche_id)
    return task_id


async def poll_suno_result(
    api_key: str,
    task_id: str,
    timeout: int = 300,
    poll_interval: int = 10,
) -> dict | None:
    """Poll Apiframe for generation result.

    Returns first song data dict with audio_url, or None if failed/timed out.
    """
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }
    elapsed = 0

    async with httpx.AsyncClient(timeout=30) as client:
        while elapsed < timeout:
            resp = await client.post(
                f"{APIFRAME_BASE}/fetch",
                json={"task_id": task_id},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

            status = data.get("status", "")

            if status == "finished":
                songs = data.get("songs", [])
                if songs:
                    song = songs[0]
                    logger.info(
                        "Suno track ready: '%s' — %s",
                        song.get("title", "?"),
                        song.get("audio_url", "")[:60],
                    )
                    return song
                logger.warning("Suno finished but no songs in response")
                return None

            if status in ("error", "failed"):
                logger.error("Suno generation failed: %s", data)
                return None

            pct = data.get("percentage", 0)
            if elapsed % 30 == 0:
                logger.info("Suno generating... %s%% (waited %ds)", pct, elapsed)

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

    logger.warning("Suno generation timed out after %ds", timeout)
    return None


async def download_suno_track(
    song_data: dict,
    output_dir: Path,
    niche_id: str,
) -> Path | None:
    """Download a completed Suno track to local storage."""
    audio_url = song_data.get("audio_url")
    if not audio_url:
        logger.error("No audio_url in Suno song data")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    song_id = song_data.get("song_id", "unknown")
    filename = f"suno_{niche_id}_{song_id}.mp3"
    output_path = output_dir / filename

    if output_path.exists() and output_path.stat().st_size > 10_000:
        logger.info("Suno track already cached: %s", filename)
        return output_path

    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resp = await client.get(audio_url)
        resp.raise_for_status()
        output_path.write_bytes(resp.content)

    size_kb = output_path.stat().st_size / 1024
    logger.info("Downloaded Suno track: %s (%.0f KB)", filename, size_kb)
    return output_path


async def get_suno_music(
    api_key: str,
    niche_id: str,
    cache_dir: Path | None = None,
    custom_prompt: str | None = None,
) -> Path | None:
    """Generate and download a custom Suno track for a niche.

    Full flow: generate → poll → download.
    """
    if not api_key:
        logger.warning("No SUNO_API_KEY configured — skipping Suno music")
        return None

    if cache_dir is None:
        cache_dir = Path("data/media/audio/music/suno")

    try:
        task_id = await generate_suno_track(api_key, niche_id, custom_prompt)
        song_data = await poll_suno_result(api_key, task_id, timeout=300)
        if not song_data:
            return None
        return await download_suno_track(song_data, cache_dir, niche_id)

    except Exception as e:
        logger.error("Suno music generation failed: %s", e)
        return None
