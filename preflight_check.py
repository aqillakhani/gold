"""Pre-flight check: verify ALL quality upgrades are enabled before testing.

Checks every upgrade component is reachable and configured. If ANY check fails,
prints exactly what's wrong and exits with error — no test run should proceed.
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / "secrets" / ".env")

FFMPEG_DIR = r"C:\Users\claws\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

sys.path.insert(0, str(Path(__file__).parent / "src"))


async def main():
    checks = []
    all_ok = True

    def check(name: str, ok: bool, detail: str = ""):
        nonlocal all_ok
        status = "OK" if ok else "FAIL"
        if not ok:
            all_ok = False
        msg = f"  [{status:>4}] {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        checks.append((name, ok, detail))

    print("=" * 60)
    print("  PRE-FLIGHT CHECK: All Quality Upgrades")
    print("=" * 60)
    print()

    # 1. ComfyUI / AI Video (Wan2.1)
    comfyui_url = os.environ.get("VASTAI_COMFYUI_URL", "")
    if comfyui_url:
        try:
            from gold.utils.ai_video import check_comfyui_health
            healthy = await check_comfyui_health(comfyui_url)
            check("AI Video (ComfyUI)", healthy, comfyui_url if healthy else f"Unreachable: {comfyui_url}")
        except Exception as e:
            check("AI Video (ComfyUI)", False, str(e)[:100])
    else:
        check("AI Video (ComfyUI)", False, "VASTAI_COMFYUI_URL is empty in .env")

    # 2. Fish Audio TTS
    fish_key = os.environ.get("FISH_API_KEY", "")
    check("Fish Audio TTS", bool(fish_key), "Key set" if fish_key else "FISH_API_KEY is empty")

    # 3. Suno Music (via Apiframe)
    suno_key = os.environ.get("SUNO_API_KEY", "")
    check("Suno Music (Apiframe)", bool(suno_key), "Key set" if suno_key else "SUNO_API_KEY is empty")

    # 4. FFmpeg available
    import subprocess
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, text=True, timeout=5,
        )
        version_line = result.stdout.split("\n")[0] if result.returncode == 0 else "not found"
        check("FFmpeg", result.returncode == 0, version_line[:60])
    except Exception as e:
        check("FFmpeg", False, str(e)[:100])

    # 5. Montserrat font (for karaoke subtitles)
    font_path = Path(__file__).parent / "assets" / "fonts" / "Montserrat.ttf"
    check("Montserrat Font", font_path.exists(), str(font_path) if font_path.exists() else "Missing: assets/fonts/Montserrat.ttf")

    # 6. Pexels (for non-ai_video niches)
    pexels_key = os.environ.get("PEXELS_API_KEY", "")
    check("Pexels API Key", bool(pexels_key), "Set" if pexels_key else "Empty")

    # 7. Anthropic API (for script generation)
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    check("Anthropic API Key", bool(anthropic_key), "Set" if anthropic_key else "Empty")

    # 8. Niche configs — check ai_video niches have correct footage_source
    from gold.config import Config
    config = Config()
    ai_video_niches = ["ai_tools", "true_crime", "personal_finance", "english_learning"]
    for niche_id in ai_video_niches:
        niche_path = Path(__file__).parent / "config" / "niches" / f"{niche_id}.yaml"
        if niche_path.exists():
            import yaml
            with open(niche_path) as f:
                nc = yaml.safe_load(f)
            fs = nc.get("niche", {}).get("visual", {}).get("footage_source", "pexels")
            check(f"  {niche_id} footage_source", fs == "ai_video", f"footage_source={fs}")
        else:
            check(f"  {niche_id} config", False, "Config file missing")

    # 9. Strict mode
    os.environ["GOLD_STRICT_MODE"] = "1"
    check("Strict Mode", True, "GOLD_STRICT_MODE=1")

    print()
    print("=" * 60)
    if all_ok:
        print("  ALL CHECKS PASSED — Ready to test!")
    else:
        failed = [c for c in checks if not c[1]]
        print(f"  {len(failed)} CHECK(S) FAILED — Fix before testing:")
        for name, _, detail in failed:
            print(f"    - {name}: {detail}")
    print("=" * 60)

    return all_ok


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
