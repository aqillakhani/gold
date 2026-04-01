"""ComfyUI API client for LTX-2.3 video generation via Vast.ai."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import httpx

from ..config import Config
from ..utils.retry import retry

logger = logging.getLogger(__name__)

# LTX-2.3 workflow templates for ComfyUI (native node names)
# Flow: CheckpointLoaderSimple → CLIPTextEncode (pos/neg) → LTXVConditioning
#       → EmptyLTXVLatentVideo → LTXVScheduler → SamplerCustom → VAEDecode
#       → VHS_VideoCombine
LTX_TEXT_TO_VIDEO_WORKFLOW = {
    # Node 1: Load checkpoint (MODEL + VAE; CLIP is None for LTX)
    "1": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "ltx-video-2b-v0.9.5.safetensors"},
    },
    # Node 1b: Load T5 text encoder for LTX
    "1b": {
        "class_type": "CLIPLoader",
        "inputs": {
            "clip_name": "t5xxl_fp8_e4m3fn.safetensors",
            "type": "ltxv",
        },
    },
    # Node 2: Encode positive prompt
    "2": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "",  # filled at runtime
            "clip": ["1b", 0],
        },
    },
    # Node 3: Encode negative prompt
    "3": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "blurry, low quality, distorted, watermark, text overlay, garbled text, AI generated, artificial, uncanny",
            "clip": ["1b", 0],
        },
    },
    # Node 4: LTX conditioning (wraps with frame rate)
    "4": {
        "class_type": "LTXVConditioning",
        "inputs": {
            "positive": ["2", 0],
            "negative": ["3", 0],
            "frame_rate": 24.0,
        },
    },
    # Node 5: Empty latent video
    "5": {
        "class_type": "EmptyLTXVLatentVideo",
        "inputs": {
            "width": 768,
            "height": 1344,
            "length": 97,  # adjusted at runtime
            "batch_size": 1,
        },
    },
    # Node 6: LTX scheduler (generates sigmas)
    "6": {
        "class_type": "LTXVScheduler",
        "inputs": {
            "steps": 30,
            "max_shift": 2.05,
            "base_shift": 0.95,
            "stretch": True,
            "terminal": 0.1,
            "latent": ["5", 0],
        },
    },
    # Node 7: Sampler (KSamplerSelect for sampler object)
    "7": {
        "class_type": "KSamplerSelect",
        "inputs": {"sampler_name": "euler"},
    },
    # Node 8: SamplerCustom (uses sigmas from scheduler)
    "8": {
        "class_type": "SamplerCustom",
        "inputs": {
            "model": ["1", 0],
            "add_noise": True,
            "noise_seed": 0,  # randomized at runtime
            "cfg": 4.0,
            "positive": ["4", 0],
            "negative": ["4", 1],
            "sampler": ["7", 0],
            "sigmas": ["6", 0],
            "latent_image": ["5", 0],
        },
    },
    # Node 9: VAE Decode
    "9": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["8", 0],
            "vae": ["1", 2],
        },
    },
    # Node 10: Save as MP4
    "10": {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "frame_rate": 24,
            "loop_count": 0,
            "filename_prefix": "ltx_output",
            "format": "video/h264-mp4",
            "pingpong": False,
            "save_output": True,
            "images": ["9", 0],
        },
    },
}

LTX_IMAGE_TO_VIDEO_WORKFLOW = {
    # Node 1: Load input image
    "1": {
        "class_type": "LoadImage",
        "inputs": {"image": ""},  # filled at runtime (uploaded filename)
    },
    # Node 2: Load checkpoint (MODEL + VAE)
    "2": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "ltx-video-2b-v0.9.5.safetensors"},
    },
    # Node 2b: Load text encoder from LTX checkpoint
    "2b": {
        "class_type": "LTXAVTextEncoderLoader",
        "inputs": {
            "text_encoder": "t5xxl_fp8_e4m3fn.safetensors",
            "ckpt_name": "ltx-video-2b-v0.9.5.safetensors",
            "device": "default",
        },
    },
    # Node 3: Encode positive prompt
    "3": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "",  # filled at runtime
            "clip": ["2b", 0],
        },
    },
    # Node 4: Encode negative prompt
    "4": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "blurry, low quality, distorted, watermark, text overlay",
            "clip": ["2b", 0],
        },
    },
    # Node 5: LTXVImgToVideo (conditioning + latent from image)
    "5": {
        "class_type": "LTXVImgToVideo",
        "inputs": {
            "positive": ["3", 0],
            "negative": ["4", 0],
            "vae": ["2", 2],
            "image": ["1", 0],
            "width": 768,
            "height": 1344,
            "length": 97,  # adjusted at runtime
            "batch_size": 1,
            "strength": 0.8,
        },
    },
    # Node 6: LTX scheduler
    "6": {
        "class_type": "LTXVScheduler",
        "inputs": {
            "steps": 30,
            "max_shift": 2.05,
            "base_shift": 0.95,
            "stretch": True,
            "terminal": 0.1,
            "latent": ["5", 2],
        },
    },
    # Node 7: Sampler select
    "7": {
        "class_type": "KSamplerSelect",
        "inputs": {"sampler_name": "euler"},
    },
    # Node 8: SamplerCustom
    "8": {
        "class_type": "SamplerCustom",
        "inputs": {
            "model": ["2", 0],
            "add_noise": True,
            "noise_seed": 0,
            "cfg": 4.0,
            "positive": ["5", 0],
            "negative": ["5", 1],
            "sampler": ["7", 0],
            "sigmas": ["6", 0],
            "latent_image": ["5", 2],
        },
    },
    # Node 9: VAE Decode
    "9": {
        "class_type": "VAEDecode",
        "inputs": {
            "samples": ["8", 0],
            "vae": ["2", 2],
        },
    },
    # Node 10: Save as MP4
    "10": {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "frame_rate": 24,
            "loop_count": 0,
            "filename_prefix": "ltx_i2v_output",
            "format": "video/h264-mp4",
            "pingpong": False,
            "save_output": True,
            "images": ["9", 0],
        },
    },
}


def _duration_to_frames(duration_sec: float, fps: int = 24) -> int:
    """Convert seconds to LTX frame count (must be 8n+1)."""
    raw = int(duration_sec * fps)
    # LTX requires frame count = 8n + 1
    n = max(1, (raw - 1) // 8)
    return 8 * n + 1


class ComfyUIClient:
    """HTTP client for a ComfyUI server running LTX-2.3 on Vast.ai."""

    def __init__(self, config: Config):
        self.config = config
        self.host = config.get("api.comfyui.host", "")
        self.timeout = config.get("api.comfyui.timeout", 600)
        self.media_dir = config.media_dir

    @property
    def base_url(self) -> str:
        host = self.host.rstrip("/")
        if not host.startswith("http"):
            host = f"http://{host}"
        return host

    def is_available(self) -> bool:
        return bool(self.host)

    @retry(max_retries=2, base_delay=5.0, exceptions=(httpx.HTTPError, RuntimeError))
    async def text_to_video(
        self,
        prompt: str,
        duration: float = 5.0,
        width: int = 768,
        height: int = 1344,
        output_name: str = "ltx_clip",
    ) -> Path:
        """Generate a video clip from a text prompt via LTX-2.3.

        Args:
            prompt: Scene description for video generation.
            duration: Target duration in seconds.
            width: Output width (default 768 for 9:16).
            height: Output height (default 1344 for 9:16).
            output_name: Base filename for the output.

        Returns:
            Path to the downloaded .mp4 file.
        """
        import random as _random

        workflow = json.loads(json.dumps(LTX_TEXT_TO_VIDEO_WORKFLOW))

        # Fill in dynamic values
        workflow["2"]["inputs"]["text"] = prompt
        workflow["8"]["inputs"]["noise_seed"] = _random.randint(0, 2**32 - 1)
        frames = _duration_to_frames(duration)
        workflow["5"]["inputs"]["width"] = width
        workflow["5"]["inputs"]["height"] = height
        workflow["5"]["inputs"]["length"] = frames

        prompt_id = await self._submit_workflow(workflow)
        result = await self._poll_result(prompt_id)
        output_path = await self._download_output(result, output_name)

        logger.info(
            "ComfyUI text-to-video complete: %s (%.1fs, %dx%d, %d frames)",
            output_path.name, duration, width, height, frames,
        )
        return output_path

    @retry(max_retries=2, base_delay=5.0, exceptions=(httpx.HTTPError, RuntimeError))
    async def image_to_video(
        self,
        image_path: Path,
        prompt: str = "",
        duration: float = 5.0,
        output_name: str = "ltx_i2v_clip",
    ) -> Path:
        """Generate a video from a still image via LTX-2.3 image-to-video.

        Args:
            image_path: Path to the input image.
            prompt: Motion/scene description.
            duration: Target duration in seconds.
            output_name: Base filename for the output.

        Returns:
            Path to the downloaded .mp4 file.
        """
        import random as _random

        # Upload image to ComfyUI
        uploaded_name = await self._upload_image(image_path)

        workflow = json.loads(json.dumps(LTX_IMAGE_TO_VIDEO_WORKFLOW))

        workflow["1"]["inputs"]["image"] = uploaded_name
        workflow["3"]["inputs"]["text"] = prompt or "smooth cinematic motion"
        workflow["8"]["inputs"]["noise_seed"] = _random.randint(0, 2**32 - 1)
        workflow["5"]["inputs"]["length"] = _duration_to_frames(duration)

        prompt_id = await self._submit_workflow(workflow)
        result = await self._poll_result(prompt_id)
        output_path = await self._download_output(result, output_name)

        logger.info("ComfyUI image-to-video complete: %s (%.1fs)", output_path.name, duration)
        return output_path

    async def health_check(self) -> bool:
        """Check if the ComfyUI server is reachable."""
        if not self.is_available():
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.base_url}/system_stats")
                return resp.status_code == 200
        except Exception:
            return False

    async def _submit_workflow(self, workflow: dict) -> str:
        """POST workflow to ComfyUI /prompt endpoint, return prompt_id."""
        payload = {"prompt": workflow}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/prompt",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"No prompt_id in ComfyUI response: {data}")

        logger.info("ComfyUI job submitted: %s", prompt_id)
        return prompt_id

    async def _poll_result(self, prompt_id: str) -> dict:
        """Poll /history/{prompt_id} until the job completes."""
        max_polls = self.timeout // 5
        async with httpx.AsyncClient(timeout=30) as client:
            for i in range(max_polls):
                resp = await client.get(f"{self.base_url}/history/{prompt_id}")
                resp.raise_for_status()
                data = resp.json()

                if prompt_id in data:
                    entry = data[prompt_id]
                    status = entry.get("status", {})

                    if status.get("completed", False):
                        outputs = entry.get("outputs", {})
                        if outputs:
                            return outputs
                        raise RuntimeError("ComfyUI job completed but no outputs found")

                    if status.get("status_str") == "error":
                        msgs = status.get("messages", [])
                        raise RuntimeError(f"ComfyUI job failed: {msgs}")

                if i % 6 == 0:
                    logger.info("ComfyUI job %s: polling... (%ds)", prompt_id, i * 5)

                await asyncio.sleep(5)

        raise RuntimeError(f"ComfyUI job timed out after {self.timeout}s")

    async def _download_output(self, outputs: dict, output_name: str) -> Path:
        """Download the generated video from ComfyUI output."""
        output_dir = self.media_dir / "clips"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{output_name}.mp4"

        # Find the video file in outputs — check all output nodes
        filename = None
        subfolder = ""
        for _node_id, node_output in outputs.items():
            # VHS_VideoCombine outputs gifs/videos list
            for key in ("gifs", "videos", "images"):
                items = node_output.get(key, [])
                for item in items:
                    if isinstance(item, dict) and item.get("filename", "").endswith(".mp4"):
                        filename = item["filename"]
                        subfolder = item.get("subfolder", "")
                        break
                if filename:
                    break
            if filename:
                break

        if not filename:
            raise RuntimeError(f"No .mp4 file in ComfyUI outputs: {json.dumps(outputs)[:500]}")

        # Download via /view endpoint
        params = {"filename": filename}
        if subfolder:
            params["subfolder"] = subfolder
        params["type"] = "output"

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(f"{self.base_url}/view", params=params)
            resp.raise_for_status()
            output_path.write_bytes(resp.content)

        logger.info("Downloaded ComfyUI output: %s (%.1f MB)", output_path.name, len(resp.content) / 1_048_576)
        return output_path

    async def _upload_image(self, image_path: Path) -> str:
        """Upload an image to ComfyUI for use in workflows. Returns the filename."""
        img_bytes = image_path.read_bytes()
        filename = image_path.name

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/upload/image",
                files={"image": (filename, img_bytes, "image/png")},
                data={"overwrite": "true"},
            )
            resp.raise_for_status()
            data = resp.json()

        uploaded_name = data.get("name", filename)
        logger.info("Uploaded image to ComfyUI: %s", uploaded_name)
        return uploaded_name
