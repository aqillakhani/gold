"""VideoRenderer: FFmpeg compositing of clips + audio + subtitles."""

from __future__ import annotations

import logging
from pathlib import Path

from ..config import Config
from ..utils.ffmpeg import composite_video

logger = logging.getLogger(__name__)


class VideoRenderer:
    def __init__(self, config: Config):
        self.config = config
        self.resolution = (
            config.get("video.resolution.width", 1080),
            config.get("video.resolution.height", 1920),
        )
        self.fps = config.get("video.fps", 30)

    async def render(
        self,
        video_clips: list[Path],
        audio_path: Path | None = None,
        music_path: Path | None = None,
        subtitle_path: Path | None = None,
        output_name: str = "master",
    ) -> Path:
        """Render final master video from clips + audio."""
        output_dir = self.config.media_dir / "rendered"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{output_name}.mp4"

        result = await composite_video(
            video_clips=video_clips,
            audio_path=audio_path,
            music_path=music_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
            resolution=self.resolution,
            fps=self.fps,
        )

        logger.info("Rendered master video: %s (%.1f MB)", result, result.stat().st_size / 1e6)
        return result

    async def render_ken_burns(
        self,
        image_path: Path,
        duration: float = 5.0,
        effect: str = "zoom_in",
        output_name: str = "kb_clip",
    ) -> Path:
        """Apply Ken Burns effect to a single image."""
        from ..utils.ffmpeg import apply_ken_burns

        output_dir = self.config.media_dir / "clips"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{output_name}.mp4"

        return await apply_ken_burns(
            image_path=image_path,
            output_path=output_path,
            duration=duration,
            effect=effect,
            resolution=self.resolution,
            fps=self.fps,
        )

    async def render_slideshow(
        self,
        clips: list[Path],
        output_name: str = "slideshow",
    ) -> Path:
        """Combine Ken Burns clips into a slideshow."""
        from ..utils.ffmpeg import create_slideshow

        output_dir = self.config.media_dir / "rendered"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{output_name}.mp4"

        return await create_slideshow(
            clips=clips,
            output_path=output_path,
            resolution=self.resolution,
            fps=self.fps,
        )
