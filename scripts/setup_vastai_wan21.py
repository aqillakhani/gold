"""Vast.ai Wan2.1 setup helper and test script.

Usage:
    # 1. Rent a GPU on Vast.ai with this Docker image (via web UI):
    #    Image: comfyanonymous/comfyui:latest
    #    GPU: RTX 4090 (24GB) or A100 (80GB)
    #    Expose port 8188
    #
    # 2. SSH in and download Wan2.1 model:
    #    cd /opt/ComfyUI/models/diffusion_models/
    #    wget https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_t2v_1.3B_bf16.safetensors
    #
    # 3. Set the URL in your .env:
    #    VASTAI_COMFYUI_URL=http://YOUR_VAST_IP:8188
    #
    # 4. Run this script to test:
    #    python scripts/setup_vastai_wan21.py

How to rent a Vast.ai instance:
    1. Go to https://cloud.vast.ai/create/
    2. Filter: GPU Type = RTX 4090, Min VRAM = 24GB
    3. Select Docker Image: comfyanonymous/comfyui:latest
    4. Set port mapping: 8188:8188
    5. Click "RENT"
    6. Wait for instance to start, note the IP and port
    7. SSH in to download the Wan2.1 model (see commands above)
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv("secrets/.env")

from src.gold.utils.ai_video import (
    check_comfyui_health,
    enhance_prompt_for_video,
    generate_ai_video_clip,
)
from pathlib import Path


async def test_connection():
    """Test connection to ComfyUI instance."""
    url = os.environ.get("VASTAI_COMFYUI_URL", "")
    if not url:
        print("ERROR: VASTAI_COMFYUI_URL not set in secrets/.env")
        print("\nTo set up:")
        print("1. Rent a GPU on https://cloud.vast.ai/create/")
        print("2. Use Docker image: comfyanonymous/comfyui:latest")
        print("3. Set VASTAI_COMFYUI_URL=http://YOUR_IP:8188 in secrets/.env")
        return False

    print(f"Testing connection to ComfyUI at {url}...")
    healthy = await check_comfyui_health(url)
    if healthy:
        print("ComfyUI instance is healthy and ready!")
        return True
    else:
        print("ERROR: ComfyUI instance is not responding.")
        print("Make sure the instance is running and port 8188 is exposed.")
        return False


async def test_generation():
    """Generate a test video clip."""
    url = os.environ.get("VASTAI_COMFYUI_URL", "")
    if not url:
        print("Set VASTAI_COMFYUI_URL first")
        return

    output_dir = Path("data/test_ai_video")
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path("data/ai_video_cache")

    # Test prompts for different niches
    test_cases = [
        ("true_crime", "dark alley at night with red neon reflections on wet pavement"),
        ("ai_tools", "futuristic computer interface with holographic displays"),
        ("personal_finance", "stack of gold coins growing taller on a wooden desk"),
    ]

    for niche_id, prompt in test_cases:
        print(f"\n--- Generating {niche_id} test clip ---")
        enhanced = enhance_prompt_for_video(prompt, niche_id)
        print(f"Enhanced prompt: {enhanced[:100]}...")

        output_path = output_dir / f"test_{niche_id}.mp4"
        result = await generate_ai_video_clip(
            prompt=prompt,
            niche_id=niche_id,
            output_path=output_path,
            target_duration=5.0,
            comfyui_url=url,
            cache_dir=cache_dir,
        )

        if result:
            size_mb = result.stat().st_size / 1_048_576
            print(f"SUCCESS: {result} ({size_mb:.1f} MB)")
        else:
            print(f"FAILED: Could not generate clip for {niche_id}")


async def main():
    print("=== Vast.ai Wan2.1 Setup & Test ===\n")

    connected = await test_connection()
    if not connected:
        return

    print("\nConnection OK! Running test generation...")
    await test_generation()

    print("\n=== Setup Complete ===")
    print("Your pipeline will now use AI-generated video clips instead of stock footage.")
    print("Pexels remains as automatic fallback if ComfyUI is unreachable.")


if __name__ == "__main__":
    asyncio.run(main())
