"""MediaProducer: generates still images, thumbnails, and video clips via fal.ai or ComfyUI."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from ..config import Config
from ..utils.retry import retry

logger = logging.getLogger(__name__)

FAL_BASE = "https://queue.fal.run"


class MediaProducer:
    def __init__(self, config: Config):
        self.config = config
        self.fal_key = config.env("FAL_KEY")
        self.elevenlabs_key = config.env("ELEVENLABS_API_KEY")
        self.image_model = config.get("api.fal.image_model", "fal-ai/flux/schnell")
        self.video_model = config.get(
            "api.fal.video_model", "fal-ai/kling-video/v2/master/text-to-video"
        )
        self.i2v_model = config.get(
            "api.fal.i2v_model", "fal-ai/kling-video/v2/master/image-to-video"
        )
        self.media_dir = config.media_dir
        self.video_backend = config.get("api.video_backend", "fal")

        # Lazy-init ComfyUI client only when needed
        self._comfyui_client = None

    def _headers(self) -> dict:
        return {
            "Authorization": f"Key {self.fal_key}",
            "Content-Type": "application/json",
        }

    @retry(max_retries=2, base_delay=3.0, exceptions=(httpx.HTTPError, RuntimeError))
    async def generate_image(
        self, prompt: str, output_name: str = "scene", width: int = 1080, height: int = 1920,
        return_url: bool = False,
    ) -> Path | tuple[Path, str]:
        """Generate a still image using Flux via fal.ai.

        Args:
            return_url: If True, return (local_path, remote_url) tuple.
                        Useful for passing directly to image-to-video.
        """
        output_dir = self.media_dir / "images"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{output_name}.png"

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{FAL_BASE}/{self.image_model}",
                headers=self._headers(),
                json={
                    "prompt": prompt,
                    "image_size": {"width": width, "height": height},
                    "num_images": 1,
                },
            )
            resp.raise_for_status()
            result = resp.json()

            if "request_id" in result:
                status_url = result.get("status_url")
                response_url = result.get("response_url")
                if not status_url or not response_url:
                    request_id = result["request_id"]
                    status_url = f"{FAL_BASE}/{self.image_model}/requests/{request_id}/status"
                    response_url = f"{FAL_BASE}/{self.image_model}/requests/{request_id}"
                result = await self._poll_result(client, status_url, response_url)

            images = result.get("images", [])
            if not images:
                raise RuntimeError(f"No images in response: {list(result.keys())}")

            img_url = images[0].get("url")
            img_resp = await client.get(img_url, timeout=60)
            img_resp.raise_for_status()
            output_path.write_bytes(img_resp.content)

        logger.info("Generated image: %s", output_path)
        if return_url:
            return output_path, img_url
        return output_path

    @retry(max_retries=2, base_delay=3.0, exceptions=(httpx.HTTPError, RuntimeError))
    async def generate_thumbnail(self, prompt: str, output_name: str = "thumb") -> Path:
        """Generate a thumbnail image using Flux via fal.ai."""
        output_dir = self.media_dir / "images"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{output_name}.png"

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{FAL_BASE}/{self.image_model}",
                headers=self._headers(),
                json={
                    "prompt": prompt,
                    "image_size": {"width": 1080, "height": 1920},
                    "num_images": 1,
                },
            )
            resp.raise_for_status()
            result = resp.json()

            if "request_id" in result:
                status_url = result.get("status_url")
                response_url = result.get("response_url")
                if not status_url or not response_url:
                    request_id = result["request_id"]
                    status_url = f"{FAL_BASE}/{self.image_model}/requests/{request_id}/status"
                    response_url = f"{FAL_BASE}/{self.image_model}/requests/{request_id}"

                result = await self._poll_result(client, status_url, response_url)

            images = result.get("images", [])
            if not images:
                raise RuntimeError(f"No images in response: {list(result.keys())}")

            img_url = images[0].get("url")
            img_resp = await client.get(img_url, timeout=60)
            img_resp.raise_for_status()
            output_path.write_bytes(img_resp.content)

        logger.info("Generated thumbnail: %s", output_path)
        return output_path

    def _get_comfyui(self):
        """Lazy-init and return ComfyUI client."""
        if self._comfyui_client is None:
            from .comfyui import ComfyUIClient
            self._comfyui_client = ComfyUIClient(self.config)
        return self._comfyui_client

    async def _should_use_comfyui(self) -> bool:
        """Check if ComfyUI backend is configured and reachable."""
        if self.video_backend != "comfyui":
            return False
        client = self._get_comfyui()
        if not client.is_available():
            return False
        healthy = await client.health_check()
        if not healthy:
            logger.warning("ComfyUI configured but unreachable, falling back to fal.ai")
            return False
        return True

    @retry(max_retries=2, base_delay=5.0, exceptions=(httpx.HTTPError, RuntimeError))
    async def generate_video_clip(
        self,
        prompt: str,
        output_name: str = "clip",
        duration: str = "5",
        aspect_ratio: str = "9:16",
    ) -> Path:
        """Generate an AI video clip using Kling v2 via fal.ai or LTX-2.3 via ComfyUI.

        Routes to ComfyUI when video_backend is "comfyui" and the server is reachable.
        Falls back to fal.ai otherwise.

        Args:
            prompt: Detailed scene description for the video generation model.
            output_name: Base filename (without extension) for the output clip.
            duration: Clip duration in seconds as a string ("5" or "10").
            aspect_ratio: Output aspect ratio (default "9:16" for vertical video).

        Returns:
            Path to the generated .mp4 clip.
        """
        # Route to ComfyUI/LTX-2.3 if configured
        if await self._should_use_comfyui():
            dur_float = float(duration)
            w, h = (768, 1344) if aspect_ratio == "9:16" else (1344, 768)
            return await self._get_comfyui().text_to_video(
                prompt=prompt, duration=dur_float,
                width=w, height=h, output_name=output_name,
            )

        output_dir = self.media_dir / "clips"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{output_name}.mp4"

        # Kling v2 only accepts "5" or "10" — normalize
        dur_int = int(float(duration))
        normalized_duration = "10" if dur_int > 7 else "5"

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{FAL_BASE}/{self.video_model}",
                headers=self._headers(),
                json={
                    "prompt": prompt,
                    "duration": normalized_duration,
                    "aspect_ratio": aspect_ratio,
                },
            )
            resp.raise_for_status()
            result = resp.json()

            if "request_id" in result:
                status_url = result.get("status_url")
                response_url = result.get("response_url")
                if not status_url or not response_url:
                    request_id = result["request_id"]
                    status_url = f"{FAL_BASE}/{self.video_model}/requests/{request_id}/status"
                    response_url = f"{FAL_BASE}/{self.video_model}/requests/{request_id}"
                # Video generation takes longer — use extended timeout
                result = await self._poll_result(
                    client, status_url, response_url, max_wait=900
                )

            # Kling returns video in result.video.url
            video_info = result.get("video", {})
            video_url = video_info.get("url") if isinstance(video_info, dict) else None

            # Fallback: some models return in different structures
            if not video_url:
                video_url = result.get("video_url")
            if not video_url:
                # Try nested output structure
                output_data = result.get("output", {})
                if isinstance(output_data, dict):
                    video_url = output_data.get("video", {}).get("url")

            if not video_url:
                raise RuntimeError(
                    f"No video URL in response. Keys: {list(result.keys())}"
                )

            video_resp = await client.get(video_url, timeout=120)
            video_resp.raise_for_status()
            output_path.write_bytes(video_resp.content)

        logger.info("Generated video clip: %s (duration=%ss)", output_path, duration)
        return output_path

    @retry(max_retries=2, base_delay=5.0, exceptions=(httpx.HTTPError, RuntimeError))
    async def generate_video_from_image(
        self,
        image_url: str,
        prompt: str = "",
        output_name: str = "clip",
        duration: str = "5",
        aspect_ratio: str = "9:16",
        i2v_model: str | None = None,
    ) -> Path:
        """Generate a video from a still image using image-to-video via fal.ai or ComfyUI.

        Routes to ComfyUI/LTX-2.3 when video_backend is "comfyui" and the server
        is reachable. Falls back to fal.ai otherwise.

        Args:
            image_url: URL or local path of the input image. If local, will upload first.
            prompt: Motion description (e.g. "camera slowly zooms in, flames flicker").
            output_name: Base filename for the output clip.
            duration: Clip duration ("5" or "10").
            aspect_ratio: Output aspect ratio.
            i2v_model: Override the default i2v model for this call.

        Returns:
            Path to the generated .mp4 clip.
        """
        # Route to ComfyUI/LTX-2.3 if configured
        if await self._should_use_comfyui():
            # ComfyUI needs a local file path — download if URL
            if image_url.startswith("http"):
                img_dir = self.media_dir / "images"
                img_dir.mkdir(parents=True, exist_ok=True)
                local_path = img_dir / f"{output_name}_src.png"
                async with httpx.AsyncClient(timeout=60) as dl_client:
                    resp = await dl_client.get(image_url)
                    resp.raise_for_status()
                    local_path.write_bytes(resp.content)
            else:
                local_path = Path(image_url)
            return await self._get_comfyui().image_to_video(
                image_path=local_path, prompt=prompt,
                duration=float(duration), output_name=output_name,
            )

        i2v_model = i2v_model or self.i2v_model
        output_dir = self.media_dir / "clips"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{output_name}.mp4"

        dur_int = int(float(duration))
        normalized_duration = "10" if dur_int > 7 else "5"

        async with httpx.AsyncClient(timeout=120) as client:
            # If image_url is a local file, read and upload to fal
            if not image_url.startswith("http"):
                image_url = await self._upload_image(client, Path(image_url))

            payload = {
                "image_url": image_url,
                "duration": normalized_duration,
                "aspect_ratio": aspect_ratio,
            }
            if prompt:
                payload["prompt"] = prompt

            resp = await client.post(
                f"{FAL_BASE}/{i2v_model}",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            result = resp.json()

            if "request_id" in result:
                status_url = result.get("status_url")
                response_url = result.get("response_url")
                if not status_url or not response_url:
                    request_id = result["request_id"]
                    status_url = f"{FAL_BASE}/{i2v_model}/requests/{request_id}/status"
                    response_url = f"{FAL_BASE}/{i2v_model}/requests/{request_id}"
                result = await self._poll_result(
                    client, status_url, response_url, max_wait=900
                )

            # Kling returns video in result.video.url
            video_info = result.get("video", {})
            video_url = video_info.get("url") if isinstance(video_info, dict) else None
            if not video_url:
                video_url = result.get("video_url")
            if not video_url:
                output_data = result.get("output", {})
                if isinstance(output_data, dict):
                    video_url = output_data.get("video", {}).get("url")
            if not video_url:
                raise RuntimeError(f"No video URL in i2v response. Keys: {list(result.keys())}")

            video_resp = await client.get(video_url, timeout=120)
            video_resp.raise_for_status()
            output_path.write_bytes(video_resp.content)

        logger.info("Generated video from image: %s (duration=%ss)", output_path, duration)
        return output_path

    async def _upload_image(self, client: httpx.AsyncClient, image_path: Path) -> str:
        """Upload a local image to fal.ai storage and return the URL."""
        img_bytes = image_path.read_bytes()
        content_type = "image/png" if image_path.suffix == ".png" else "image/jpeg"

        # Use fal.ai file upload
        resp = await client.put(
            "https://fal.ai/api/storage/upload",
            headers={
                "Authorization": f"Key {self.fal_key}",
                "Content-Type": content_type,
            },
            content=img_bytes,
        )
        if resp.status_code == 200:
            data = resp.json()
            url = data.get("url") or data.get("file_url") or data.get("access_url")
            if url:
                return url

        # Fallback: base64 data URI
        import base64
        b64 = base64.b64encode(img_bytes).decode()
        return f"data:{content_type};base64,{b64}"

    @retry(max_retries=2, base_delay=3.0, exceptions=(httpx.HTTPError, RuntimeError))
    async def generate_sound_effect(
        self,
        prompt: str,
        output_name: str = "sfx",
        duration: float = 5.0,
    ) -> Path:
        """Generate a sound effect using ElevenLabs Sound Generation API directly.

        Args:
            prompt: Description of the sound effect (e.g. "crackling lightning bolt").
            output_name: Base filename for the output audio.
            duration: Duration in seconds (0.5-22).

        Returns:
            Path to the generated audio file.
        """
        output_dir = self.media_dir / "audio" / "sfx"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{output_name}.mp3"

        duration = max(0.5, min(22.0, duration))

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                "https://api.elevenlabs.io/v1/sound-generation",
                headers={
                    "xi-api-key": self.elevenlabs_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": prompt,
                    "duration_seconds": duration,
                },
            )
            resp.raise_for_status()
            output_path.write_bytes(resp.content)

        logger.info("Generated sound effect: %s", output_path)
        return output_path

    async def _poll_result(
        self, client: httpx.AsyncClient, status_url: str, response_url: str, max_wait: int = 600
    ) -> dict:
        """Poll fal.ai queue for result using the URLs from the submit response."""
        for i in range(max_wait // 5):
            resp = await client.get(status_url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status")

            if status == "COMPLETED":
                # Some models include result data in the status response
                if "audio" in data or "video" in data or "images" in data or "output" in data:
                    return data

                # Brief delay — some models need a moment after COMPLETED
                await asyncio.sleep(2)

                # Retry result fetch up to 3 times (404 can be transient)
                for attempt in range(3):
                    result_resp = await client.get(response_url, headers=self._headers())
                    if result_resp.status_code == 404 and attempt < 2:
                        logger.debug("Result not ready yet (404), retrying in 5s...")
                        await asyncio.sleep(5)
                        continue
                    break

                if result_resp.status_code in (400, 422):
                    body = result_resp.text
                    logger.error("fal.ai %d on result fetch: %s", result_resp.status_code, body[:500])
                    raise RuntimeError(f"fal.ai rejected result ({result_resp.status_code}): {body[:300]}")
                result_resp.raise_for_status()
                return result_resp.json()
            if status in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"fal.ai job {status}: {data}")

            if i % 6 == 0:  # Log every 30s
                logger.info("fal.ai job status: %s (waited %ds)", status, i * 5)
            await asyncio.sleep(5)

        raise RuntimeError(f"fal.ai job timed out after {max_wait}s")
