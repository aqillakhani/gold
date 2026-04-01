"""PlatformVariator: creates per-platform variants with slight differences."""

from __future__ import annotations

import logging
import random
from pathlib import Path

import yaml

from ..config import Config
from ..utils.ffmpeg import create_variant

logger = logging.getLogger(__name__)

PLATFORMS = ["facebook", "instagram", "youtube", "tiktok"]

# Slight variations per platform to avoid duplicate detection
VARIANT_PARAMS = {
    "facebook":  {"speed_factor": 1.00, "color_temp_shift": 0},
    "instagram": {"speed_factor": 1.01, "color_temp_shift": 50},
    "youtube":   {"speed_factor": 1.02, "color_temp_shift": -30},
    "tiktok":    {"speed_factor": 1.03, "color_temp_shift": 80},
}


class PlatformVariator:
    def __init__(self, config: Config):
        self.config = config
        self._affiliate_links = self._load_affiliate_links()

    def _load_affiliate_links(self) -> dict:
        """Load affiliate links from config/affiliate_links.yaml."""
        try:
            path = self.config.root / "config" / "affiliate_links.yaml"
            if path.exists():
                with open(path) as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning("Could not load affiliate links: %s", e)
        return {}

    def get_affiliate_cta(self, niche_id: str) -> str:
        """Get a random affiliate CTA for a niche, if configured."""
        links = self._affiliate_links.get(niche_id, [])
        active = [l for l in links if l.get("url")]
        if not active:
            return ""
        chosen = random.choice(active)
        return chosen.get("cta", "Link in bio")

    def get_ftc_disclosure(self, niche_id: str) -> str:
        """Get FTC disclosure text for video descriptions."""
        niche_config = self.config.niches.get(niche_id, {})
        ftc = niche_config.get("ftc_disclosure", {})
        return ftc.get("description", "")

    async def create_variants(
        self, master_path: Path, content_id: int, suffix: str = "",
    ) -> dict[str, Path]:
        """Create 4 platform variants from a master video."""
        variants = {}
        output_dir = self.config.media_dir / "rendered" / f"content_{content_id}"
        output_dir.mkdir(parents=True, exist_ok=True)

        for platform in PLATFORMS:
            params = VARIANT_PARAMS[platform].copy()
            # Add slight random jitter to speed
            params["speed_factor"] += random.uniform(-0.005, 0.005)

            output_path = output_dir / f"{platform}{suffix}.mp4"
            result = await create_variant(
                source=master_path,
                output=output_path,
                speed_factor=params["speed_factor"],
                color_temp_shift=params["color_temp_shift"],
            )
            variants[platform] = result
            logger.info("Created %s variant%s: %s", platform, suffix, result)

        return variants

    async def extract_shorts(
        self, master_path: Path, script: dict, content_id: int,
    ) -> list[Path]:
        """Extract 50-60s highlight clips from a long-form master video.

        Uses `shorts_hooks` from the script to identify which sections to cut.
        Each Short gets its own hook text overlay burned in.
        """
        from ..utils.ffmpeg import get_duration, run_ffmpeg

        shorts_hooks = script.get("shorts_hooks", [])
        if not shorts_hooks:
            logger.warning("No shorts_hooks in script, skipping Shorts extraction")
            return []

        scenes = script.get("scenes", [])
        master_duration = await get_duration(master_path)

        # Build a timestamp map: cumulative start time per scene
        scene_starts = []
        cumulative = 0.0
        for scene in scenes:
            scene_starts.append(cumulative)
            cumulative += float(scene.get("duration", 7))

        output_dir = self.config.media_dir / "rendered" / f"content_{content_id}" / "shorts"
        output_dir.mkdir(parents=True, exist_ok=True)

        short_paths = []
        for idx, hook in enumerate(shorts_hooks):
            scene_range = hook.get("scene_range", [])
            hook_text = hook.get("hook_text", "")

            if len(scene_range) < 2:
                continue

            start_scene = scene_range[0] - 1  # 1-indexed in script
            end_scene = scene_range[1] - 1

            if start_scene < 0 or end_scene >= len(scenes):
                logger.warning("Short %d: scene_range %s out of bounds, skipping", idx + 1, scene_range)
                continue

            start_time = scene_starts[start_scene] if start_scene < len(scene_starts) else 0.0
            # End time = start of end_scene + its duration
            end_time = scene_starts[end_scene] + float(scenes[end_scene].get("duration", 7)) if end_scene < len(scene_starts) else master_duration
            end_time = min(end_time, master_duration)

            duration = end_time - start_time
            # Clamp to 50-60s for Shorts
            if duration > 60:
                end_time = start_time + 60
                duration = 60
            if duration < 15:
                logger.warning("Short %d: only %.1fs, too short, skipping", idx + 1, duration)
                continue

            output_path = output_dir / f"short_{idx + 1}.mp4"

            # FFmpeg: cut segment + optional hook text overlay
            ffmpeg_args = [
                "-ss", f"{start_time:.2f}",
                "-i", str(master_path),
                "-t", f"{duration:.2f}",
            ]

            if hook_text:
                # Burn hook text in the first 5 seconds
                escaped = hook_text.replace("'", "\u2019").replace(":", "\\:").replace("%", "%%")
                ffmpeg_args.extend([
                    "-vf",
                    f"drawtext=text='{escaped}':fontsize=48:fontcolor=white"
                    f":borderw=3:bordercolor=black:x=(w-text_w)/2:y=h*0.15"
                    f":enable='between(t,0,5)'",
                ])

            ffmpeg_args.extend([
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-y", str(output_path),
            ])

            try:
                await run_ffmpeg(ffmpeg_args)
                short_paths.append(output_path)
                logger.info(
                    "Extracted Short %d: %.1fs-%.1fs (%.1fs) → %s",
                    idx + 1, start_time, end_time, duration, output_path,
                )
            except Exception as e:
                logger.error("Failed to extract Short %d: %s", idx + 1, e)

        logger.info("Extracted %d Shorts from long-form master", len(short_paths))
        return short_paths
