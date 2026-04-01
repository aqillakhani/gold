"""AI video clip generation via Wan2.1 on a Vast.ai ComfyUI instance.

Generates 5-15 second portrait video clips from text prompts, designed as
a drop-in replacement for Pexels stock footage in the content pipeline.

Requires a running ComfyUI instance with Wan2.1 model loaded.
Set VASTAI_COMFYUI_URL in your .env (e.g. http://195.142.145.66:8188).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx

from .ffmpeg import run_ffmpeg

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ComfyUI Wan2.1 Workflow
# ---------------------------------------------------------------------------

# Wan2.1 T2V workflow for native ComfyUI nodes.
# Uses: UNETLoader → CLIPLoader → VAELoader → CLIPTextEncode → WanImageToVideo
#       → KSampler → VAEDecode → SaveAnimatedWEBP
# The ComfyUI instance must have wan2.1_t2v_1.3B_bf16.safetensors,
# umt5_xxl_fp8_e4m3fn_scaled.safetensors, and wan_2.1_vae.safetensors

_NEGATIVE_PROMPT = (
    "blurry, low quality, distorted, watermark, text, logo, static, "
    "slideshow, ken burns, zoom, still image, photo, jpeg artifacts"
)


def _build_wan_workflow(
    prompt: str,
    width: int = 480,
    height: int = 832,
    num_frames: int = 81,
    steps: int = 30,
    cfg: float = 6.0,
    seed: int = -1,
    model_file: str = "wan2.1_t2v_1.3B_bf16.safetensors",
    clip_prefix: str = "wan_output",
) -> dict:
    """Build a native ComfyUI workflow for Wan2.1 text-to-video."""
    import random as _rnd
    if seed < 0:
        seed = _rnd.randint(0, 2**31 - 1)

    return {
        # Node 1: Load diffusion model
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": model_file,
                "weight_dtype": "default",
            },
        },
        # Node 2: Load text encoder
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "type": "wan",
            },
        },
        # Node 3: Load VAE
        "3": {
            "class_type": "VAELoader",
            "inputs": {
                "vae_name": "wan_2.1_vae.safetensors",
            },
        },
        # Node 4: Encode positive prompt
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": prompt,
                "clip": ["2", 0],
            },
        },
        # Node 5: Encode negative prompt
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": _NEGATIVE_PROMPT,
                "clip": ["2", 0],
            },
        },
        # Node 6: WanImageToVideo (without start_image = T2V mode)
        # Outputs: [positive_cond, negative_cond, latent]
        "6": {
            "class_type": "WanImageToVideo",
            "inputs": {
                "positive": ["4", 0],
                "negative": ["5", 0],
                "vae": ["3", 0],
                "width": width,
                "height": height,
                "length": num_frames,
                "batch_size": 1,
            },
        },
        # Node 7: KSampler
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": "uni_pc",
                "scheduler": "simple",
                "positive": ["6", 0],
                "negative": ["6", 1],
                "latent_image": ["6", 2],
                "denoise": 1.0,
            },
        },
        # Node 8: VAE Decode
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["7", 0],
                "vae": ["3", 0],
            },
        },
        # Node 9: Save as animated WEBP
        "9": {
            "class_type": "SaveAnimatedWEBP",
            "inputs": {
                "images": ["8", 0],
                "filename_prefix": clip_prefix,
                "fps": 16,
                "lossless": False,
                "quality": 95,
                "method": "default",
            },
        },
    }


# ---------------------------------------------------------------------------
# Scene prompt enhancement
# ---------------------------------------------------------------------------

NICHE_STYLE_PREFIXES = {
    "true_crime": "Dark cinematic scene, moody lighting, deep shadows, red and blue tones, noir aesthetic, ",
    "ai_tools": "Clean modern tech environment, blue ambient glow, futuristic, sleek, ",
    "personal_finance": "Warm professional setting, golden hour lighting, prosperity, clean, ",
    "english_learning": "Bright friendly classroom or conversation setting, clean, warm lighting, ",
    "reddit_stories": "Dramatic scene, vivid colors, emotional lighting, cinematic, ",
    "betrayal_revenge": "Dark dramatic scene, tense atmosphere, shadows, emotional intensity, ",
}

QUALITY_SUFFIX = (
    " high quality, cinematic, 4K, smooth motion, professional videography, "
    "detailed textures, natural movement, realistic lighting"
)


def enhance_prompt_for_video(
    raw_prompt: str,
    niche_id: str,
) -> str:
    """Enhance a scene description into a video generation prompt.

    Adds niche-specific style prefix and quality suffix to guide Wan2.1
    toward producing clips that match the channel's visual identity.
    """
    prefix = NICHE_STYLE_PREFIXES.get(niche_id, "Cinematic scene, ")
    return f"{prefix}{raw_prompt},{QUALITY_SUFFIX}"


# ---------------------------------------------------------------------------
# ComfyUI API client
# ---------------------------------------------------------------------------

async def _queue_prompt(
    base_url: str,
    workflow: dict[str, Any],
    timeout: float = 30.0,
) -> str:
    """Submit a workflow to ComfyUI and return the prompt_id."""
    client_id = str(uuid.uuid4())
    payload = {
        "prompt": workflow,
        "client_id": client_id,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{base_url}/prompt", json=payload)
        resp.raise_for_status()
        data = resp.json()
    prompt_id = data.get("prompt_id", "")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI returned no prompt_id: {data}")
    logger.info("ComfyUI prompt queued: %s", prompt_id)
    return prompt_id


async def _poll_completion(
    base_url: str,
    prompt_id: str,
    poll_interval: float = 5.0,
    max_wait: float = 600.0,
) -> dict[str, Any]:
    """Poll ComfyUI /history until the prompt completes or times out."""
    elapsed = 0.0
    async with httpx.AsyncClient(timeout=30.0) as client:
        while elapsed < max_wait:
            resp = await client.get(f"{base_url}/history/{prompt_id}")
            resp.raise_for_status()
            history = resp.json()

            if prompt_id in history:
                entry = history[prompt_id]
                status = entry.get("status", {})
                if status.get("completed", False) or status.get("status_str") == "success":
                    return entry
                if status.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI prompt failed: {status}")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

    raise TimeoutError(f"ComfyUI prompt {prompt_id} did not complete within {max_wait}s")


async def _download_output(
    base_url: str,
    history_entry: dict[str, Any],
    output_path: Path,
) -> Path:
    """Download the first output file from a completed ComfyUI prompt."""
    outputs = history_entry.get("outputs", {})

    # Find the first node output with images/videos
    for node_id, node_out in outputs.items():
        files = node_out.get("images", []) or node_out.get("gifs", [])
        if files:
            file_info = files[0]
            filename = file_info.get("filename", "")
            subfolder = file_info.get("subfolder", "")
            file_type = file_info.get("type", "output")

            params = {
                "filename": filename,
                "subfolder": subfolder,
                "type": file_type,
            }

            output_path.parent.mkdir(parents=True, exist_ok=True)
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.get(f"{base_url}/view", params=params)
                resp.raise_for_status()
                output_path.write_bytes(resp.content)

            logger.info("Downloaded AI video: %s (%.1f MB)", output_path.name, len(resp.content) / 1_048_576)
            return output_path

    raise RuntimeError(f"No output files found in ComfyUI history entry")


# ---------------------------------------------------------------------------
# Post-processing: scale/trim to target spec
# ---------------------------------------------------------------------------

async def _postprocess_clip(
    raw_path: Path,
    output_path: Path,
    target_duration: float,
    resolution: tuple[int, int] = (1080, 1920),
    fps: int = 30,
) -> Path:
    """Scale, trim, and re-encode an AI-generated clip to the target spec.

    Wan2.1 outputs animated WEBP at lower resolution and 16fps.
    FFmpeg can't reliably decode animated WEBP on Windows, so we first
    extract frames via PIL, then encode with FFmpeg.
    """
    w, h = resolution

    # Convert animated WEBP to raw frames dir, then pipe to FFmpeg
    from PIL import Image
    import tempfile
    import shutil

    frames_dir = raw_path.parent / f"{raw_path.stem}_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    try:
        img = Image.open(raw_path)
        n_frames = getattr(img, "n_frames", 1)
        source_fps = 16  # Wan2.1 default

        for i in range(n_frames):
            img.seek(i)
            frame = img.convert("RGB")
            frame.save(frames_dir / f"frame_{i:05d}.png")

        logger.info("Extracted %d frames from animated WEBP", n_frames)

        # Encode frames to video with FFmpeg
        # If we have fewer frames than needed for target_duration, loop the clip
        gen_seconds = n_frames / source_fps
        need_loop = target_duration > gen_seconds + 0.5

        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},"
            f"setsar=1,"
            f"fps={fps}"
        )

        args = ["-framerate", str(source_fps)]
        if need_loop:
            # Loop input to cover target_duration
            loop_count = int(target_duration / gen_seconds) + 1
            args += ["-stream_loop", str(loop_count)]
        args += [
            "-i", str(frames_dir / "frame_%05d.png"),
            "-t", str(target_duration),
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-an",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-y", str(output_path),
        ]

        await run_ffmpeg(args, timeout=120)

        logger.info(
            "Post-processed AI clip: %s -> %s (%.1fs, %dx%d @ %dfps)",
            raw_path.name, output_path.name, target_duration, w, h, fps,
        )
        return output_path

    finally:
        # Clean up frames directory
        shutil.rmtree(frames_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def generate_ai_video_clip(
    prompt: str,
    niche_id: str,
    output_path: Path,
    target_duration: float,
    comfyui_url: str,
    cache_dir: Path,
    resolution: tuple[int, int] = (1080, 1920),
    model_size: str = "1.3B",
    fps: int = 30,
) -> Path | None:
    """Generate an AI video clip for a scene using Wan2.1 on ComfyUI.

    Args:
        prompt: Scene description (will be enhanced with niche style).
        niche_id: Niche identifier for style-appropriate prompt enhancement.
        output_path: Final destination for the processed clip.
        target_duration: Desired clip length in seconds.
        comfyui_url: Base URL of the ComfyUI instance (e.g. http://ip:8188).
        cache_dir: Directory for caching raw generated clips.
        resolution: Output (width, height). Defaults to 1080x1920.
        model_size: "1.3B" or "14B" for quality tier selection.
        fps: Output frame rate. Defaults to 30.

    Returns:
        Path to the ready clip, or None if generation failed.
    """
    output_path = Path(output_path)

    # Fast path: already generated
    if output_path.exists():
        logger.debug("AI video cache hit: %s", output_path.name)
        return output_path

    # Enhance prompt with niche style
    enhanced_prompt = enhance_prompt_for_video(prompt, niche_id)
    logger.info(
        "Generating AI video: niche=%s model=%s prompt=%.80s...",
        niche_id, model_size, enhanced_prompt,
    )

    # Generate ~5s of video regardless of target duration (we'll loop/trim in post)
    # RTX A4000 generates ~10 frames/min, so keep frame count manageable
    gen_duration = min(target_duration, 5.0)
    target_frames = int(gen_duration * 16)
    # Wan2.1 works best with frame counts that are multiples of 4 + 1
    target_frames = ((target_frames // 4) * 4) + 1
    target_frames = max(17, min(target_frames, 81))  # cap at 81 frames (~5s)

    # Unique filename prefix to avoid collisions
    clip_id = output_path.stem

    # Select model file and resolution based on model_size
    if model_size == "14B":
        model_file = "wan2.1_t2v_14B_bf16.safetensors"
        gen_w, gen_h = 720, 1280
    else:
        model_file = "wan2.1_t2v_1.3B_bf16.safetensors"
        gen_w, gen_h = 480, 832

    # Build native ComfyUI workflow
    workflow = _build_wan_workflow(
        prompt=enhanced_prompt,
        width=gen_w,
        height=gen_h,
        num_frames=target_frames,
        steps=30,
        cfg=6.0,
        model_file=model_file,
        clip_prefix=clip_id,
    )

    # Queue and wait — retry once on failure (transient ComfyUI/OOM errors)
    max_retries = 2
    for attempt in range(1, max_retries + 1):
        try:
            # Rebuild workflow on retry (fresh seed)
            if attempt > 1:
                workflow = _build_wan_workflow(
                    prompt=enhanced_prompt,
                    width=gen_w, height=gen_h,
                    num_frames=target_frames,
                    steps=30, cfg=6.0,
                    model_file=model_file,
                    clip_prefix=clip_id,
                )
                # Free VRAM between retries
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        await client.post(f"{comfyui_url}/free", json={"unload_models": True})
                        await asyncio.sleep(5)
                except Exception:
                    pass

            prompt_id = await _queue_prompt(comfyui_url, workflow)
            history = await _poll_completion(
                comfyui_url, prompt_id,
                poll_interval=5.0,
                max_wait=600.0,  # 10 min max for video gen
            )

            # Download raw output
            cache_dir.mkdir(parents=True, exist_ok=True)
            raw_path = cache_dir / f"{clip_id}_raw.webp"
            await _download_output(comfyui_url, history, raw_path)

            # Post-process: upscale, trim, re-encode
            await _postprocess_clip(
                raw_path=raw_path,
                output_path=output_path,
                target_duration=target_duration,
                resolution=resolution,
                fps=fps,
            )

            return output_path

        except Exception as e:
            logger.error("AI video generation attempt %d/%d failed: %s", attempt, max_retries, e)
            if attempt < max_retries:
                logger.info("Retrying AI video generation...")
                await asyncio.sleep(10)
            else:
                return None


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

async def check_comfyui_health(base_url: str) -> bool:
    """Check if the ComfyUI instance is reachable and ready."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{base_url}/system_stats")
            resp.raise_for_status()
            stats = resp.json()
            logger.info(
                "ComfyUI healthy: VRAM=%.1fGB free",
                stats.get("devices", [{}])[0].get("vram_free", 0) / 1e9,
            )
            return True
    except Exception as e:
        logger.warning("ComfyUI health check failed: %s", e)
        return False
