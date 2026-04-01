#!/usr/bin/env python3
"""Helper script to launch a ComfyUI + LTX-2.3 instance on Vast.ai.

Usage:
    python scripts/setup_vastai.py          # Search and launch
    python scripts/setup_vastai.py --stop   # Stop running instances

Requires:
    - vastai CLI: pip install vastai
    - VASTAI_API_KEY environment variable (or ~/.vastai_api_key)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time


def run_vastai(*args: str) -> str:
    """Run a vastai CLI command and return stdout."""
    cmd = ["vastai", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"ERROR: vastai {' '.join(args)}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def search_instances() -> list[dict]:
    """Search for cheapest RTX 4090 instances with enough VRAM for LTX-2.3."""
    print("Searching for GPU instances (RTX 4090, 24GB+ VRAM)...")
    raw = run_vastai(
        "search", "offers",
        "--type", "on-demand",
        "--gpu-name", "RTX 4090",
        "--disk", "50",
        "--order", "dph_total",
        "--limit", "10",
        "--raw",
    )
    try:
        offers = json.loads(raw)
    except json.JSONDecodeError:
        print("Could not parse vastai output. Raw:", file=sys.stderr)
        print(raw[:500], file=sys.stderr)
        return []
    return offers


def launch_instance(offer_id: int) -> int:
    """Launch a ComfyUI instance on the selected offer."""
    # Use a ComfyUI docker image with LTX-2.3 support
    docker_image = "yanwk/comfyui-boot:latest"
    onstart_script = (
        "cd /root/ComfyUI && "
        "python -m pip install -q comfyui-manager && "
        "echo 'Downloading LTX-2.3 model...' && "
        "mkdir -p models/checkpoints && "
        "wget -q -c 'https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.5.safetensors' "
        "-O models/checkpoints/ltx-video-2b-v0.9.5.safetensors && "
        "python main.py --listen 0.0.0.0 --port 8188"
    )

    print(f"Launching instance on offer {offer_id}...")
    raw = run_vastai(
        "create", "instance", str(offer_id),
        "--image", docker_image,
        "--disk", "50",
        "--onstart-cmd", onstart_script,
        "--direct",
        "--raw",
    )

    try:
        data = json.loads(raw)
        instance_id = data.get("new_contract")
        if instance_id:
            return instance_id
    except (json.JSONDecodeError, KeyError):
        pass

    # Try parsing as plain text
    for word in raw.split():
        if word.isdigit():
            return int(word)

    print(f"Could not parse instance ID from: {raw}", file=sys.stderr)
    sys.exit(1)


def wait_for_instance(instance_id: int) -> dict:
    """Wait for instance to be running and return its info."""
    print(f"Waiting for instance {instance_id} to start...", end="", flush=True)
    for _ in range(60):  # 5 min timeout
        raw = run_vastai("show", "instance", str(instance_id), "--raw")
        try:
            info = json.loads(raw)
            if isinstance(info, list) and info:
                info = info[0]
            status = info.get("actual_status", "")
            if status == "running":
                print(" RUNNING!")
                return info
        except (json.JSONDecodeError, IndexError):
            pass
        print(".", end="", flush=True)
        time.sleep(5)
    print("\nTimeout waiting for instance to start.", file=sys.stderr)
    sys.exit(1)


def stop_instances():
    """Stop all running Vast.ai instances."""
    raw = run_vastai("show", "instances", "--raw")
    try:
        instances = json.loads(raw)
    except json.JSONDecodeError:
        print("No instances found or could not parse output.")
        return

    if not instances:
        print("No running instances.")
        return

    for inst in instances:
        iid = inst.get("id")
        if iid:
            print(f"Stopping instance {iid}...")
            run_vastai("stop", "instance", str(iid))
            print(f"  Instance {iid} stopped.")

    print("All instances stopped. No further charges will accrue.")


def main():
    parser = argparse.ArgumentParser(description="Launch ComfyUI + LTX-2.3 on Vast.ai")
    parser.add_argument("--stop", action="store_true", help="Stop all running instances")
    args = parser.parse_args()

    # Check for API key
    if not os.environ.get("VASTAI_API_KEY") and not os.path.exists(os.path.expanduser("~/.vastai_api_key")):
        print("ERROR: Set VASTAI_API_KEY env var or create ~/.vastai_api_key", file=sys.stderr)
        print("  Get your key at: https://cloud.vast.ai/account/", file=sys.stderr)
        sys.exit(1)

    if args.stop:
        stop_instances()
        return

    # Search for offers
    offers = search_instances()
    if not offers:
        print("No suitable GPU instances found. Try again later.")
        sys.exit(1)

    # Display top options
    print(f"\nTop {min(5, len(offers))} cheapest RTX 4090 instances:")
    print(f"{'#':<4} {'ID':<10} {'$/hr':<8} {'VRAM':<8} {'Location':<15}")
    print("-" * 50)
    for i, offer in enumerate(offers[:5]):
        price = offer.get("dph_total", 0)
        vram = offer.get("gpu_ram", 0)
        location = offer.get("geolocation", "unknown")
        oid = offer.get("id", "?")
        print(f"{i+1:<4} {oid:<10} ${price:<7.3f} {vram/1024:<7.0f}GB {location:<15}")

    # Auto-select cheapest
    best = offers[0]
    best_id = best["id"]
    best_price = best.get("dph_total", 0)
    print(f"\nSelecting cheapest: offer {best_id} at ${best_price:.3f}/hr")

    # Launch
    instance_id = launch_instance(best_id)
    info = wait_for_instance(instance_id)

    # Extract connection info
    public_ip = info.get("public_ipaddr", "")
    ports = info.get("ports", {})
    # ComfyUI runs on 8188
    comfyui_port = None
    for port_key, port_info in (ports or {}).items():
        if "8188" in str(port_key):
            if isinstance(port_info, list) and port_info:
                comfyui_port = port_info[0].get("HostPort")
            elif isinstance(port_info, dict):
                comfyui_port = port_info.get("HostPort")
            break

    if not comfyui_port:
        # Fallback: direct port mapping
        comfyui_port = "8188"

    host_string = f"{public_ip}:{comfyui_port}"

    print("\n" + "=" * 60)
    print("ComfyUI + LTX-2.3 instance is RUNNING!")
    print("=" * 60)
    print(f"  Instance ID:  {instance_id}")
    print(f"  Public IP:    {public_ip}")
    print(f"  ComfyUI Port: {comfyui_port}")
    print(f"  ComfyUI URL:  http://{host_string}")
    print()
    print("Add this to your config/settings.yaml:")
    print()
    print("  api:")
    print(f"    comfyui:")
    print(f"      host: \"{host_string}\"")
    print(f"    video_backend: comfyui")
    print()
    print("NOTE: The LTX-2.3 model may still be downloading.")
    print("      Wait ~5 min, then test: curl http://{}/system_stats".format(host_string))
    print()
    print(f"To stop and save money: python scripts/setup_vastai.py --stop")
    print(f"  Estimated cost: ${best_price:.3f}/hr")


if __name__ == "__main__":
    main()
