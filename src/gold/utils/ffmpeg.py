"""FFmpeg subprocess wrapper for video operations."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Custom fonts directory for Montserrat (used in subtitle burn-in)
# Absolute path for non-FFmpeg uses
_FONTS_DIR_ABS = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "fonts"
# Project root — used as CWD for FFmpeg calls that need relative paths
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
# Relative path for FFmpeg filters (avoids Windows C: colon breaking filter parser)
_FONTS_DIR = "assets/fonts"


def _ass_filter(subtitle_path_safe: str) -> str:
    """Build ASS subtitle filter with custom fonts directory."""
    return f"ass={subtitle_path_safe}:fontsdir={_FONTS_DIR}"


def _find_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg not found in PATH. Install ffmpeg first.")
    return path


async def run_ffmpeg(args: list[str], timeout: int = 600, cwd: str | Path | None = None) -> str:
    """Run an ffmpeg command asynchronously. Returns stderr output."""
    cmd = [_find_ffmpeg()] + args
    logger.debug("Running: %s", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

    if proc.returncode != 0:
        err = stderr.decode(errors="replace")
        raise RuntimeError(f"ffmpeg exited {proc.returncode}: {err[-800:]}")

    return stderr.decode(errors="replace")


async def get_duration(video_path: Path) -> float:
    """Get video duration in seconds using ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe not found in PATH.")

    proc = await asyncio.create_subprocess_exec(
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return float(stdout.decode().strip())


def _wrap_text(text: str, max_chars: int = 35) -> str:
    """Word-wrap text into lines of max_chars, joined by FFmpeg newline."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > max_chars:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return "\n".join(lines)


async def add_visual_hook(
    video_path: Path,
    hook_text: str,
    output_path: Path | None = None,
    sfx_path: Path | None = None,
    duration: float = 2.0,
    niche_id: str = "",
) -> Path:
    """Add a visual hook overlay to the first N seconds of a video.

    Creates an attention-grabbing text animation (zoom-in + fade) in the
    first 2 seconds, optionally with a SFX burst. This is the visual
    pattern interrupt that boosts retention.

    Args:
        video_path: Input video file.
        hook_text: Short hook text to display (max ~8 words).
        output_path: Output path (defaults to replacing input).
        sfx_path: Optional path to a SFX audio file (whoosh/impact).
        duration: Hook overlay duration in seconds. Defaults to 2.0.
        niche_id: For niche-specific accent color.

    Returns:
        Path to the output video with hook overlay.
    """
    # Niche accent colors for hook text
    hook_colors = {
        "true_crime": "0xFF2222",
        "ai_tools": "0x00CCFF",
        "personal_finance": "0xFFD400",
        "english_learning": "0x44CC00",
        "reddit_stories": "0xFF8800",
        "betrayal_revenge": "0xFF4444",
    }
    color = hook_colors.get(niche_id, "0xFFCC00")

    if output_path is None:
        output_path = video_path.with_name(video_path.stem + "_hooked" + video_path.suffix)

    # Escape text for FFmpeg drawtext filter syntax.
    # No wrapping quotes — subprocess passes args directly.
    safe_text = (
        hook_text.upper()[:40]
        .replace("\\", "\\\\")
        .replace("'", "\u2019")
        .replace("%", "%%")
        .replace(",", "\\,")
        .replace(":", "\\:")
        .replace(";", "\\;")
    )

    # Use relative font path to avoid Windows drive letter colon (C:) issue
    # in drawtext's key:value parser. We set CWD to project root when running.
    font_rel = "assets/fonts/Montserrat.ttf"

    # Build drawtext as -filter_complex to avoid -vf quoting issues on Windows.
    # Commas in expressions escaped as \, for filter_complex parser.
    fade_end = duration - 0.3
    drawtext = (
        f"drawtext=text={safe_text}"
        f":fontfile={font_rel}"
        f":fontsize=64:fontcolor={color}:borderw=4:bordercolor=0x000000"
        f":x=(w-text_w)/2:y=h*0.18"
        f":enable=between(t\\,0.2\\,{duration})"
        f":alpha=if(lt(t\\,0.5)\\,t*2\\,if(gt(t\\,{fade_end})\\,({duration}-t)/0.3\\,1))"
    )

    args = [
        "-i", str(video_path),
    ]

    # Always use -filter_complex (works on Windows, avoids -vf quoting issues)
    if sfx_path and sfx_path.exists():
        args.extend(["-i", str(sfx_path)])
        args.extend([
            "-filter_complex",
            f"[0:v]{drawtext}[vout];"
            f"[1:a]volume=0.5,adelay=200|200[sfx];"
            f"[0:a][sfx]amix=inputs=2:duration=first:normalize=0[aout]",
            "-map", "[vout]", "-map", "[aout]",
        ])
    else:
        args.extend([
            "-filter_complex", f"[0:v]{drawtext}[vout]",
            "-map", "[vout]", "-map", "0:a",
            "-c:a", "copy",
        ])

    args.extend([
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-y", str(output_path),
    ])

    # CWD must be project root for relative font path to resolve
    await run_ffmpeg(args, timeout=300, cwd=_PROJECT_ROOT)
    logger.info("Added visual hook to %s: '%s'", output_path.name, hook_text[:30])
    return output_path


def build_visual_treatment_filter(visual_config: dict) -> str:
    """Build FFmpeg filter string for niche-specific visual treatments.

    Supports: color grading, vignette, film grain, color tint overlays.
    Returns a filter string to append to the video filter chain (may be empty).
    """
    filters = []

    color_grade = visual_config.get("color_grade", "")
    if color_grade == "desaturated":
        # Noir documentary: desaturate, boost contrast, add red/crimson tint
        # Red tint creates true crime atmosphere (deep reds against dark backgrounds)
        filters.append("eq=saturation=0.5:contrast=1.2:brightness=-0.05")
        filters.append("colorbalance=rs=0.12:rm=0.06:rh=0.04:bs=-0.04:bm=-0.02")
    elif color_grade == "cool_tech":
        # Cool blue tint for tech content (bs=blue shadows, bm=blue midtones, bh=blue highlights)
        filters.append("colorbalance=bs=0.08:bm=0.04:bh=0.02")
    elif color_grade == "warm":
        # Warm gold tint for finance/trust
        filters.append("colorbalance=rs=0.04:gs=0.02:rh=0.03:gh=0.01")

    if visual_config.get("vignette"):
        filters.append("vignette=PI/4")

    grain = visual_config.get("grain", "")
    if grain == "light":
        filters.append("noise=alls=8:allf=t")
    elif grain == "heavy":
        filters.append("noise=alls=15:allf=t")

    return ",".join(filters)


def _build_hook_overlay_chain(
    hook_text: str,
    hook_duration: float = 4.5,
    resolution: tuple[int, int] = (1080, 1920),
    fps: int = 30,
    subreddit: str = "AskReddit",
    persistent: bool = True,
) -> tuple[str, str]:
    """Build a Reddit-style card overlay as a separate filter chain + overlay instruction.

    Returns (card_chain, overlay_filter):
      - card_chain: semicolon-separated filter chain that creates [hookcard]
      - overlay_filter: overlay filter string to apply to the main video stream

    If persistent=True, the card stays visible for the entire video.
    Card is centered horizontally and positioned in upper-center area.
    """
    w, h = resolution

    fontfile_bold = "/Windows/Fonts/ariblk.ttf"
    fontfile_reg = "/Windows/Fonts/arial.ttf"

    def esc(t: str) -> str:
        return (
            t.replace("\\", "\\\\")
            .replace("'", "\u2019")
            .replace(":", "\\:")
            .replace("%", "%%")
            .replace("\n", "\\n")
        )

    # Wrap hook text so it fits within the card
    wrapped = _wrap_text(hook_text.strip(), max_chars=38)
    num_lines = wrapped.count("\n") + 1
    escaped_hook = esc(wrapped)
    escaped_sub = esc(subreddit)

    # Card sizing — height adjusts based on text lines
    card_w = int(w * 0.90)
    text_area_h = num_lines * 40  # ~40px per line (font 30 + spacing)
    card_h = 60 + text_area_h + 25  # 60 top (sub label + gap) + text + 25 bottom pad
    card_x = int((w - card_w) / 2)  # centered horizontally
    card_y = int(h * 0.28)  # upper-center, above subtitle zone

    # Reddit-style card: dark semi-transparent bg, orange accent bar, subreddit + title
    card_chain = (
        f"color=c=0x1A1A2E@0.92:s={card_w}x{card_h}:d={hook_duration}:r={fps},"
        f"drawbox=x=0:y=0:w=6:h={card_h}:color=0xFF4500:t=fill,"
        f"drawtext=text='{escaped_sub}':fontfile={fontfile_bold}"
        f":fontsize=28:fontcolor=0xFF4500:x=28:y=18,"
        f"drawtext=text='{escaped_hook}':fontfile={fontfile_bold}"
        f":fontsize=30:fontcolor=0xFFFFFF:x=28:y=58:line_spacing=8"
        f"[hookcard]"
    )

    if persistent:
        overlay_filter = (
            f"overlay=x={card_x}:y={card_y}"
            f":eof_action=pass"
        )
    else:
        overlay_filter = (
            f"overlay=x={card_x}:y={card_y}"
            f":enable='between(t\\,0.5\\,{hook_duration})'"
            f":eof_action=pass"
        )

    return card_chain, overlay_filter


def _build_cta_filter(
    target_duration: float,
    resolution: tuple[int, int] = (1080, 1920),
) -> str:
    """Build FFmpeg drawtext filter for 'Follow for more' CTA in last 3 seconds."""
    fontfile = "/Windows/Fonts/ariblk.ttf"
    start = max(target_duration - 3.5, 0)
    bt = f"between(t\\,{start:.1f}\\,{target_duration:.1f})"
    return (
        f"drawtext=enable='{bt}':text='Follow for more'"
        f":fontfile={fontfile}:fontsize=36:fontcolor=black"
        f":box=1:boxcolor=white@0.92:boxborderw=20"
        f":x=(w-text_w)/2:y=h*0.89"
    )


async def compose_gameplay_video(
    background_video: Path,
    audio_path: Path | None,
    music_path: Path | None,
    subtitle_path: Path | None,
    output_path: Path,
    target_duration: float | None = None,
    hook_text: str = "",
    subreddit: str = "AskReddit",
    resolution: tuple[int, int] = (1080, 1920),
    fps: int = 30,
    music_volume: float = 0.30,
    niche_id: str = "",
    part_number: int = 0,
    total_parts: int = 0,
) -> Path:
    """Compose a video with gameplay background + voiceover + subtitles.

    This is the main production function for the gameplay-overlay style
    (Subway Surfers, Minecraft parkour background + voiceover + word-by-word subs).
    """
    w, h = resolution
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Loop background video so it covers the full voiceover duration
    all_inputs = ["-stream_loop", "-1", "-i", str(background_video)]
    input_idx = 1

    vo_idx = None
    mu_idx = None

    if audio_path and audio_path.exists():
        all_inputs.extend(["-i", str(audio_path)])
        vo_idx = input_idx
        input_idx += 1

    if music_path and music_path.exists():
        all_inputs.extend(["-i", str(music_path)])
        mu_idx = input_idx
        input_idx += 1

    # Build filter_complex chains
    filter_chains: list[str] = []

    # Chain 1: Scale and crop the background video
    vf_base = (
        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},setsar=1,fps={fps}"
    )

    # Hook overlay: generate card as separate color source, overlay on video
    if hook_text:
        # Use long duration for persistent card (will be trimmed by video length)
        card_dur = target_duration if target_duration else 300
        card_chain, overlay_filter = _build_hook_overlay_chain(
            hook_text, card_dur, resolution, fps,
            subreddit=subreddit, persistent=True,
        )
        # Card source chain
        filter_chains.append(card_chain)
        # Main video → [bg], then overlay card → [vhook]
        vf_base += "[bg]"
        filter_chains.append(vf_base)
        current_label = "vhook"
        filter_chains.append(f"[bg][hookcard]{overlay_filter}[{current_label}]")
    else:
        current_label = "vcta"
        vf_base += f"[{current_label}]"
        filter_chains.append(vf_base)

    # CTA overlay (last 3.5 seconds) — applied via drawtext on current stream
    if target_duration and target_duration > 10:
        cta_str = _build_cta_filter(target_duration, resolution)
        next_label = "vsub" if (subtitle_path and subtitle_path.exists()) else "vout"
        filter_chains.append(f"[{current_label}]{cta_str}[{next_label}]")
        current_label = next_label
    elif subtitle_path and subtitle_path.exists():
        # Need to relabel for subtitle step
        filter_chains.append(f"[{current_label}]copy[vsub]")
        current_label = "vsub"

    # Part badge for multi-part stories
    if part_number > 0 and total_parts > 1:
        badge_text = f"PART {part_number}/{total_parts}"
        badge_text_safe = badge_text.replace(":", "\\:")
        # Use relative path (FFmpeg runs with cwd=_PROJECT_ROOT) — avoid Windows drive letters
        badge_font = "assets/fonts/Montserrat.ttf"
        badge_filter = (
            f"drawtext=text='{badge_text_safe}':"
            f"fontfile='{badge_font}':"
            f"fontsize=36:fontcolor=white:borderw=3:bordercolor=black:"
            f"x=w-tw-30:y=60"
        )
        next_label_badge = "vbadge"
        filter_chains.append(f"[{current_label}]{badge_filter}[{next_label_badge}]")
        current_label = next_label_badge

    # Subtitle burn-in (with custom Montserrat font directory)
    if subtitle_path and subtitle_path.exists():
        safe_sub = os.path.relpath(subtitle_path).replace(chr(92), "/")
        filter_chains.append(f"[{current_label}]{_ass_filter(safe_sub)}[vout]")
        current_label = "vout"
    elif current_label != "vout":
        filter_chains.append(f"[{current_label}]copy[vout]")
        current_label = "vout"

    # Audio mixing with dynamic ducking
    # sidechaincompress: music automatically ducks when voiceover is present
    # threshold=0.02: duck when voice is detected (low threshold for speech)
    # ratio=6: strong compression (music drops noticeably during speech)
    # attack=50: quick ducking onset (50ms)
    # release=300: smooth recovery when voice pauses (300ms)
    if vo_idx is not None and mu_idx is not None:
        logger.info("[AUDIO-MIX] OK: sidechaincompress ducking (gameplay) — VO + music with dynamic ducking")
        filter_chains.append(
            f"[{vo_idx}:a]aformat=sample_rates=44100,asplit=2[vo][vosc];"
            f"[{mu_idx}:a]aformat=sample_rates=44100,volume={music_volume}[mu];"
            f"[mu][vosc]sidechaincompress=threshold=0.02:ratio=6:attack=50:release=300[ducked];"
            f"[vo][ducked]amix=inputs=2:duration=first:normalize=0[aout]"
        )
        map_args = ["-map", "[vout]", "-map", "[aout]"]
    elif vo_idx is not None:
        logger.warning("[AUDIO-MIX] DEGRADED: VO only, NO music — audio ducking skipped (gameplay)")
        map_args = ["-map", "[vout]", "-map", f"{vo_idx}:a"]
    else:
        logger.warning("[AUDIO-MIX] DEGRADED: NO audio — no VO or music (gameplay)")
        map_args = ["-map", "[vout]"]

    filter_complex = ";".join(filter_chains)

    full_args = all_inputs + [
        "-filter_complex", filter_complex,
    ] + map_args

    # Duration limit
    if target_duration:
        full_args.extend(["-t", str(target_duration)])
    elif vo_idx is not None:
        full_args.extend(["-shortest"])

    full_args.extend([
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        "-y", str(output_path),
    ])

    try:
        await run_ffmpeg(full_args, timeout=1800, cwd=_PROJECT_ROOT)
    except RuntimeError as e:
        if hook_text and "EOF" in str(e):
            logger.warning("Hook overlay failed, retrying without hook card: %s", e)
            # Retry without hook — rebuild simpler filter
            return await compose_gameplay_video(
                background_video=background_video,
                audio_path=audio_path,
                music_path=music_path,
                subtitle_path=subtitle_path,
                output_path=output_path,
                target_duration=target_duration,
                hook_text="",  # disable hook
                resolution=resolution,
                fps=fps,
            )
        raise

    logger.info("Composed gameplay video: %s", output_path.name)
    return output_path


async def compose_slides_video(
    slide_texts: list[str],
    audio_path: Path | None,
    music_path: Path | None,
    subtitle_path: Path | None,
    output_path: Path,
    audio_duration: float | None = None,
    resolution: tuple[int, int] = (1080, 1920),
    fps: int = 30,
) -> Path:
    """Compose a video from text slides with voiceover, music, and subtitles.

    Used for crypto/finance niche: clean light background with bold text slides
    that change in sync with the voiceover. Each slide is displayed for an equal
    portion of the total duration.

    Args:
        slide_texts: List of short bold text strings to display as slides.
        audio_path: Path to voiceover audio file.
        music_path: Path to background music file.
        subtitle_path: Path to ASS subtitle file for word-by-word burn-in.
        output_path: Where to write the final composed video.
        audio_duration: Duration of the voiceover in seconds (used to time slides).
        resolution: Output resolution as (width, height).
        fps: Output frame rate.

    Returns:
        Path to the composed output video.
    """
    w, h = resolution
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not slide_texts:
        slide_texts = ["CRYPTO UPDATE"]

    # Determine total duration from audio or default
    total_duration = audio_duration or 60.0
    slide_duration = total_duration / len(slide_texts)

    # Generate each slide as a video segment using lavfi color + drawtext,
    # then concatenate them all together.
    # We build one big filter_complex that creates all slides inline.
    inputs: list[str] = []
    filter_parts: list[str] = []
    input_idx = 0

    # Create each slide as a color source with drawtext
    for i, text in enumerate(slide_texts):
        # Escape text for FFmpeg drawtext
        safe_text = (
            text.strip()
            .replace("\\", "\\\\")
            .replace("'", "\u2019")  # smart quote to avoid escaping issues
            .replace(":", "\\:")
            .replace("%", "%%")
        )

        # Wrap long text: split into lines of ~25 chars
        words = safe_text.split()
        lines = []
        current_line = ""
        for word in words:
            if current_line and len(current_line) + len(word) + 1 > 25:
                lines.append(current_line)
                current_line = word
            else:
                current_line = f"{current_line} {word}".strip()
        if current_line:
            lines.append(current_line)
        wrapped_text = "\\n".join(lines)

        # Each slide: clean light gray background + bold black text (infographic style)
        # Use fontfile= for Windows compatibility (font= doesn't resolve on Windows)
        fontfile = "/Windows/Fonts/ariblk.ttf"
        filter_parts.append(
            f"color=c=#e8e8e8:s={w}x{h}:d={slide_duration}:r={fps},"
            f"drawtext=text='{wrapped_text}'"
            f":fontsize=90"
            f":fontcolor=black"
            f":x=(w-text_w)/2"
            f":y=h*0.12"
            f":fontfile={fontfile}"
            f":line_spacing=20"
            f"[slide{i}]"
        )

    # Concatenate all slides
    n = len(slide_texts)
    if n == 1:
        filter_parts.append(f"[slide0]copy[vbase]")
    else:
        concat_inputs = "".join(f"[slide{i}]" for i in range(n))
        filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=0[vbase]")

    # Burn in subtitles if provided (with custom Montserrat font directory)
    if subtitle_path and subtitle_path.exists():
        safe_sub = os.path.relpath(subtitle_path).replace(chr(92), "/")
        filter_parts.append(f"[vbase]{_ass_filter(safe_sub)}[vout]")
    else:
        filter_parts.append("[vbase]copy[vout]")

    # Add audio inputs
    vo_idx = None
    mu_idx = None

    if audio_path and audio_path.exists():
        inputs.extend(["-i", str(audio_path)])
        vo_idx = input_idx
        input_idx += 1

    if music_path and music_path.exists():
        inputs.extend(["-i", str(music_path)])
        mu_idx = input_idx
        input_idx += 1

    # Audio mixing with dynamic ducking
    if vo_idx is not None and mu_idx is not None:
        logger.info("[AUDIO-MIX] OK: sidechaincompress ducking (slides) — VO + music with dynamic ducking")
        filter_parts.append(
            f"[{vo_idx}:a]aformat=sample_rates=44100[vo];"
            f"[{mu_idx}:a]aformat=sample_rates=44100,volume=0.35[mu];"
            f"[mu][vo]sidechaincompress=threshold=0.02:ratio=6:attack=50:release=300[ducked];"
            f"[vo][ducked]amix=inputs=2:duration=first:normalize=0[aout]"
        )
        filter_complex = ";".join(filter_parts)
        full_args = inputs + [
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "[aout]",
        ]
    elif vo_idx is not None:
        logger.warning("[AUDIO-MIX] DEGRADED: VO only, NO music — audio ducking skipped (slides)")
        filter_complex = ";".join(filter_parts)
        full_args = inputs + [
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", f"{vo_idx}:a",
        ]
    elif mu_idx is not None:
        filter_parts.append(
            f"[{mu_idx}:a]aformat=sample_rates=44100,volume=0.8[aout]"
        )
        filter_complex = ";".join(filter_parts)
        full_args = inputs + [
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "[aout]",
        ]
    else:
        filter_complex = ";".join(filter_parts)
        full_args = inputs + [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
        ]

    full_args.extend([
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        "-t", str(total_duration),
        "-y", str(output_path),
    ])

    await run_ffmpeg(full_args, timeout=900, cwd=_PROJECT_ROOT)
    logger.info(
        "Composed slides video: %s (%d slides, %.1fs)",
        output_path.name, n, total_duration,
    )
    return output_path


async def compose_clips_video(
    clip_paths: list[Path],
    text_overlays: list[str],
    music_path: Path | None,
    output_path: Path,
    crossfade_duration: float = 0.3,
    resolution: tuple[int, int] = (1080, 1920),
    fps: int = 30,
) -> Path:
    """Compose a video from AI-generated clips with text overlays and background music.

    Used for the ASMR/satisfying niche: stitches together AI video clips,
    burns in short text overlays, crossfades between clips, and mixes in
    background music at full volume (no voiceover).

    Args:
        clip_paths: List of video clip file paths to concatenate.
        text_overlays: List of text strings (one per clip). Empty string = no overlay.
        music_path: Path to background music file (played at full volume).
        output_path: Where to write the final composed video.
        crossfade_duration: Duration of crossfade between clips in seconds.
        resolution: Output resolution as (width, height).
        fps: Output frame rate.

    Returns:
        Path to the composed output video.
    """
    w, h = resolution
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not clip_paths:
        raise ValueError("No clip paths provided to compose_clips_video")

    # Pad text_overlays to match clip count
    while len(text_overlays) < len(clip_paths):
        text_overlays.append("")

    n = len(clip_paths)

    # Build inputs
    inputs: list[str] = []
    for clip in clip_paths:
        inputs.extend(["-i", str(clip)])

    music_idx = None
    if music_path and music_path.exists():
        inputs.extend(["-i", str(music_path)])
        music_idx = n

    # Build filter_complex
    filter_parts: list[str] = []

    for i in range(n):
        # Scale each clip to target resolution
        scale_filter = (
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1,fps={fps}"
        )

        # Add text overlay if present
        overlay_text = text_overlays[i].strip() if i < len(text_overlays) else ""
        if overlay_text:
            # Escape special characters for ffmpeg drawtext
            safe_text = (
                overlay_text
                .replace("\\", "\\\\")
                .replace("'", "\u2019")
                .replace(":", "\\:")
                .replace("%", "%%")
            )
            # Use fontfile= for Windows compatibility
            fontfile = "/Windows/Fonts/impact.ttf"
            scale_filter += (
                f",drawtext=text='{safe_text}'"
                f":fontsize=72"
                f":fontcolor=white"
                f":borderw=4"
                f":bordercolor=black"
                f":x=(w-text_w)/2"
                f":y=h*0.75"
                f":fontfile={fontfile}"
            )

        scale_filter += f"[v{i}]"
        filter_parts.append(scale_filter)

    # Concatenate all clips
    if n == 1:
        filter_parts.append(f"[v0]copy[vout]")
    else:
        concat_inputs = "".join(f"[v{i}]" for i in range(n))
        filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=0[vout]")

    # Add music mixing
    if music_idx is not None:
        filter_parts.append(
            f"[{music_idx}:a]aformat=sample_rates=44100,volume=1.0[music]"
        )
        filter_complex = ";".join(filter_parts)

        full_args = inputs + [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[music]",
            "-shortest",
        ]
    else:
        filter_complex = ";".join(filter_parts)
        full_args = inputs + [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
        ]

    full_args.extend([
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        "-y", str(output_path),
    ])

    await run_ffmpeg(full_args, timeout=900, cwd=_PROJECT_ROOT)
    logger.info(
        "Composed clips video: %s (%d clips)", output_path.name, n
    )
    return output_path


async def compose_asmr_video(
    clip_paths: list[Path],
    sfx_paths: list[Path | None],
    text_overlays: list[str],
    music_path: Path | None,
    output_path: Path,
    resolution: tuple[int, int] = (1080, 1920),
    fps: int = 30,
) -> Path:
    """Compose an ASMR/fantasy video from AI video clips with sound effects, text overlays, and music.

    Each clip gets its own sound effect layered on top of the background music.
    Text overlays are burned in with Impact font.

    Args:
        clip_paths: List of video clip paths (from image-to-video or Ken Burns).
        sfx_paths: List of sound effect audio paths (one per clip, None = no SFX).
        text_overlays: List of text strings for each clip.
        music_path: Background music file path.
        output_path: Where to write the final video.
        resolution: Output resolution.
        fps: Output frame rate.
    """
    w, h = resolution
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not clip_paths:
        raise ValueError("No clip paths provided")

    # Pad lists to match clip count
    while len(text_overlays) < len(clip_paths):
        text_overlays.append("")
    while len(sfx_paths) < len(clip_paths):
        sfx_paths.append(None)

    n = len(clip_paths)

    # Build inputs: video clips first, then SFX audio files, then music
    inputs: list[str] = []
    for clip in clip_paths:
        inputs.extend(["-i", str(clip)])

    # Track SFX input indices
    sfx_indices: list[int | None] = []
    next_idx = n
    for sfx in sfx_paths:
        if sfx and sfx.exists():
            inputs.extend(["-i", str(sfx)])
            sfx_indices.append(next_idx)
            next_idx += 1
        else:
            sfx_indices.append(None)

    music_idx = None
    if music_path and music_path.exists():
        inputs.extend(["-i", str(music_path)])
        music_idx = next_idx

    # Build filter_complex
    filter_parts: list[str] = []
    fontfile = "/Windows/Fonts/impact.ttf"

    for i in range(n):
        scale_filter = (
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1,fps={fps}"
        )
        overlay_text = text_overlays[i].strip() if i < len(text_overlays) else ""
        if overlay_text:
            safe_text = (
                overlay_text
                .replace("\\", "\\\\")
                .replace("'", "\u2019")
                .replace(":", "\\:")
                .replace("%", "%%")
            )
            scale_filter += (
                f",drawtext=text='{safe_text}'"
                f":fontsize=72"
                f":fontcolor=white"
                f":borderw=4"
                f":bordercolor=black"
                f":x=(w-text_w)/2"
                f":y=h*0.75"
                f":fontfile={fontfile}"
            )
        scale_filter += f"[v{i}]"
        filter_parts.append(scale_filter)

    # Concatenate video
    if n == 1:
        filter_parts.append("[v0]copy[vout]")
    else:
        concat_inputs = "".join(f"[v{i}]" for i in range(n))
        filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=0[vout]")

    # Audio: mix SFX into each clip's audio segment, then concat, then mix with music
    # Simpler approach: concat all SFX (with silence for clips without SFX),
    # then mix the result with background music
    has_any_sfx = any(idx is not None for idx in sfx_indices)

    if has_any_sfx or music_idx is not None:
        # For each clip, get its duration and create audio
        # We'll use a simpler approach: just mix music as the base audio
        if music_idx is not None:
            filter_parts.append(
                f"[{music_idx}:a]aformat=sample_rates=44100,volume=0.8[music]"
            )

            # If we have SFX, mix them with the music
            if has_any_sfx:
                # Create a merged SFX track by concatenating available SFX
                sfx_available = [(i, idx) for i, idx in enumerate(sfx_indices) if idx is not None]
                if len(sfx_available) == 1:
                    clip_i, sfx_idx = sfx_available[0]
                    filter_parts.append(
                        f"[{sfx_idx}:a]aformat=sample_rates=44100,volume=1.0[sfx]"
                    )
                else:
                    # Concat all SFX
                    sfx_labels = []
                    for j, (clip_i, sfx_idx) in enumerate(sfx_available):
                        filter_parts.append(
                            f"[{sfx_idx}:a]aformat=sample_rates=44100,volume=1.0[sfx{j}]"
                        )
                        sfx_labels.append(f"[sfx{j}]")
                    sfx_concat = "".join(sfx_labels)
                    filter_parts.append(
                        f"{sfx_concat}concat=n={len(sfx_available)}:v=0:a=1[sfx]"
                    )

                filter_parts.append(
                    "[sfx][music]amix=inputs=2:duration=shortest:normalize=0[aout]"
                )
            else:
                filter_parts.append("[music]acopy[aout]")

            filter_complex = ";".join(filter_parts)
            full_args = inputs + [
                "-filter_complex", filter_complex,
                "-map", "[vout]", "-map", "[aout]",
                "-shortest",
            ]
        else:
            filter_complex = ";".join(filter_parts)
            full_args = inputs + [
                "-filter_complex", filter_complex,
                "-map", "[vout]",
            ]
    else:
        filter_complex = ";".join(filter_parts)
        full_args = inputs + [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
        ]

    full_args.extend([
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        "-y", str(output_path),
    ])

    await run_ffmpeg(full_args, timeout=900, cwd=_PROJECT_ROOT)
    logger.info("Composed ASMR video: %s (%d clips)", output_path.name, n)
    return output_path


async def composite_video(
    video_clips: list[Path],
    audio_path: Path | None,
    music_path: Path | None,
    subtitle_path: Path | None,
    output_path: Path,
    resolution: tuple[int, int] = (1080, 1920),
    fps: int = 30,
) -> Path:
    """Composite video clips with audio, music, and subtitles into final output."""
    w, h = resolution
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build filter complex for concatenating clips
    inputs: list[str] = []
    filter_parts: list[str] = []

    for i, clip in enumerate(video_clips):
        inputs.extend(["-i", str(clip)])
        filter_parts.append(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v{i}]"
        )

    n = len(video_clips)
    concat_inputs = "".join(f"[v{i}]" for i in range(n))
    filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=0[vout]")

    filter_complex = ";".join(filter_parts)

    # Rebuild args properly
    all_inputs = []
    for clip in video_clips:
        all_inputs.extend(["-i", str(clip)])
    if audio_path and audio_path.exists():
        all_inputs.extend(["-i", str(audio_path)])
    if music_path and music_path.exists():
        all_inputs.extend(["-i", str(music_path)])

    full_args = all_inputs + ["-filter_complex", filter_complex, "-map", "[vout]"]

    if audio_path and audio_path.exists() and music_path and music_path.exists():
        logger.info("[AUDIO-MIX] OK: sidechaincompress ducking (clips) — VO + music with dynamic ducking")
        vo_idx = n
        mu_idx = n + 1
        full_args = all_inputs + [
            "-filter_complex",
            filter_complex + f";[{vo_idx}:a]aformat=sample_rates=44100[vo];"
            f"[{mu_idx}:a]aformat=sample_rates=44100,volume=0.35[mu];"
            f"[mu][vo]sidechaincompress=threshold=0.02:ratio=6:attack=50:release=300[ducked];"
            f"[vo][ducked]amix=inputs=2:duration=shortest:normalize=0[aout]",
            "-map", "[vout]", "-map", "[aout]",
        ]
    elif audio_path and audio_path.exists():
        logger.warning("[AUDIO-MIX] DEGRADED: VO only, NO music — audio ducking skipped (clips)")
        vo_idx = n
        full_args = all_inputs + [
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", f"{vo_idx}:a",
        ]

    if subtitle_path and subtitle_path.exists():
        safe_sub = os.path.relpath(subtitle_path).replace(chr(92), "/")
        full_args.extend(["-vf", _ass_filter(safe_sub)])

    full_args.extend([
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-y", str(output_path),
    ])

    await run_ffmpeg(full_args, timeout=900, cwd=_PROJECT_ROOT)
    return output_path


async def create_variant(
    source: Path,
    output: Path,
    speed_factor: float = 1.0,
    color_temp_shift: float = 0.0,
) -> Path:
    """Create a platform variant with slight speed and color adjustments."""
    output.parent.mkdir(parents=True, exist_ok=True)

    filters = []
    if speed_factor != 1.0:
        filters.append(f"setpts={1/speed_factor}*PTS")
    if color_temp_shift != 0.0:
        filters.append(f"colortemperature=temperature={6500 + color_temp_shift}")

    args = ["-i", str(source)]
    if filters:
        args.extend(["-vf", ",".join(filters)])
    if speed_factor != 1.0:
        args.extend(["-af", f"atempo={speed_factor}"])

    args.extend([
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-y", str(output),
    ])

    await run_ffmpeg(args)
    return output


async def apply_ken_burns(
    image_path: Path,
    output_path: Path,
    duration: float = 5.0,
    effect: str = "zoom_in",
    resolution: tuple[int, int] = (1080, 1920),
    fps: int = 30,
) -> Path:
    """Apply Ken Burns effect (zoom/pan) to a still image, producing a video clip."""
    w, h = resolution
    total_frames = int(duration * fps)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if effect == "zoom_in":
        zp = f"zoompan=z='min(zoom+0.006,1.8)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s={w}x{h}:fps={fps}"
    elif effect == "zoom_out":
        zp = f"zoompan=z='if(eq(on,1),1.8,max(zoom-0.006,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s={w}x{h}:fps={fps}"
    elif effect == "pan_left":
        zp = f"zoompan=z='1.3':x='if(eq(on,1),0,min(x+6,iw-iw/zoom))':y='ih/2-(ih/zoom/2)':d={total_frames}:s={w}x{h}:fps={fps}"
    elif effect == "pan_right":
        zp = f"zoompan=z='1.3':x='if(eq(on,1),iw-iw/zoom,max(x-6,0))':y='ih/2-(ih/zoom/2)':d={total_frames}:s={w}x{h}:fps={fps}"
    elif effect == "pan_up":
        zp = f"zoompan=z='1.3':x='iw/2-(iw/zoom/2)':y='if(eq(on,1),ih-ih/zoom,max(y-6,0))':d={total_frames}:s={w}x{h}:fps={fps}"
    elif effect == "pan_down":
        zp = f"zoompan=z='1.3':x='iw/2-(iw/zoom/2)':y='if(eq(on,1),0,min(y+6,ih-ih/zoom))':d={total_frames}:s={w}x{h}:fps={fps}"
    elif effect == "diagonal":
        zp = f"zoompan=z='min(zoom+0.005,1.6)':x='if(eq(on,1),0,min(x+5,iw-iw/zoom))':y='if(eq(on,1),0,min(y+5,ih-ih/zoom))':d={total_frames}:s={w}x{h}:fps={fps}"
    elif effect == "zoom_pan_combo":
        zp = f"zoompan=z='min(zoom+0.005,1.7)':x='if(eq(on,1),0,min(x+5,iw-iw/zoom))':y='ih/2-(ih/zoom/2)':d={total_frames}:s={w}x{h}:fps={fps}"
    else:
        zp = f"zoompan=z='min(zoom+0.005,1.6)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s={w}x{h}:fps={fps}"

    args = [
        "-loop", "1",
        "-i", str(image_path),
        "-vf", zp,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-y", str(output_path),
    ]

    await run_ffmpeg(args, timeout=120)
    logger.info("Ken Burns effect applied: %s -> %s (%.1fs, %s)", image_path.name, output_path.name, duration, effect)
    return output_path


async def create_slideshow(
    clips: list[Path],
    output_path: Path,
    crossfade_duration: float = 0.5,
    resolution: tuple[int, int] = (1080, 1920),
    fps: int = 30,
) -> Path:
    """Concatenate Ken Burns video clips with crossfade transitions."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    w, h = resolution

    if len(clips) == 1:
        shutil.copy2(clips[0], output_path)
        return output_path

    filter_parts_simple = []
    for i, clip in enumerate(clips):
        filter_parts_simple.append(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[v{i}]"
        )

    inputs = []
    for clip in clips:
        inputs.extend(["-i", str(clip)])

    concat_inputs = "".join(f"[v{i}]" for i in range(len(clips)))
    filter_parts_simple.append(f"{concat_inputs}concat=n={len(clips)}:v=1:a=0[vout]")

    filter_complex = ";".join(filter_parts_simple)

    args = inputs + [
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-y", str(output_path),
    ]

    await run_ffmpeg(args, timeout=300)
    logger.info("Created slideshow: %s (%d clips)", output_path.name, len(clips))
    return output_path


async def compose_stock_video(
    clip_paths: list[Path],
    clip_durations: list[float],
    text_overlays: list[str],
    audio_path: Path | None,
    music_path: Path | None,
    subtitle_path: Path | None,
    output_path: Path,
    total_duration: float | None = None,
    crossfade_duration: float = 0.5,
    music_volume: float = 0.45,
    resolution: tuple[int, int] = (1080, 1920),
    fps: int = 30,
) -> Path:
    """Compose a final video from stock footage clips with crossfade transitions.

    Builds a single FFmpeg filter_complex that handles per-clip trimming, scaling,
    optional text overlays, xfade crossfades between clips, subtitle burn-in,
    voiceover + background music mixing (with fade in/out), all in one pass.

    Args:
        clip_paths: Stock footage clip file paths (one per scene).
        clip_durations: Display duration for each clip in seconds.
        text_overlays: Text to burn in per clip. Empty string means no overlay.
        audio_path: Path to voiceover audio file, or None.
        music_path: Path to background music file, or None.
        subtitle_path: Path to ASS subtitle file for word-by-word burn-in, or None.
        output_path: Where to write the final composed video.
        total_duration: Explicit total duration cap in seconds. Defaults to sum of
            clip durations minus crossfade overlaps.
        crossfade_duration: Duration of each xfade transition in seconds.
        music_volume: Volume multiplier applied to background music (0.0–1.0).
        resolution: Output resolution as (width, height).
        fps: Output frame rate.

    Returns:
        Path to the composed output video.

    Raises:
        ValueError: If clip_paths is empty or clip_durations length mismatches.
    """
    if not clip_paths:
        raise ValueError("No clip paths provided to compose_stock_video")

    n = len(clip_paths)

    # Pad or trim clip_durations and text_overlays to match clip count
    while len(clip_durations) < n:
        clip_durations.append(clip_durations[-1] if clip_durations else 5.0)
    clip_durations = clip_durations[:n]

    while len(text_overlays) < n:
        text_overlays.append("")
    text_overlays = text_overlays[:n]

    w, h = resolution
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Compute total duration from clip durations minus crossfade overlaps if not given
    cf = crossfade_duration
    computed_duration = sum(clip_durations) - cf * (n - 1)
    effective_duration = total_duration if total_duration is not None else computed_duration

    # ------------------------------------------------------------------ #
    # Build input list: clips first, then optional audio, then music      #
    # ------------------------------------------------------------------ #
    inputs: list[str] = []
    for clip in clip_paths:
        inputs.extend(["-i", str(clip)])

    vo_idx: int | None = None
    mu_idx: int | None = None
    next_idx = n

    if audio_path and audio_path.exists():
        inputs.extend(["-i", str(audio_path)])
        vo_idx = next_idx
        next_idx += 1

    if music_path and music_path.exists():
        inputs.extend(["-i", str(music_path)])
        mu_idx = next_idx

    # ------------------------------------------------------------------ #
    # Build filter_complex                                                 #
    # ------------------------------------------------------------------ #
    filter_parts: list[str] = []
    fontfile = "/Windows/Fonts/impact.ttf"

    # 1. Per-clip: trim + scale + pad short clips (clone last frame) + optional drawtext → [v{i}]
    for i in range(n):
        dur = clip_durations[i]
        # tpad clones the last frame indefinitely, then re-trim to exact duration.
        # This ensures clips shorter than `dur` are padded to the right length.
        clip_filter = (
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1,fps={fps},"
            f"tpad=stop=-1:stop_mode=clone,"
            f"trim=0:{dur},setpts=PTS-STARTPTS"
        )

        overlay_text = text_overlays[i].strip()
        if overlay_text:
            safe_text = (
                overlay_text
                .replace("\\", "\\\\")
                .replace("'", "\u2019")
                .replace(":", "\\:")
                .replace("%", "%%")
            )
            clip_filter += (
                f",drawtext=text='{safe_text}'"
                f":fontsize=72"
                f":fontcolor=white"
                f":borderw=4"
                f":bordercolor=black"
                f":x=(w-text_w)/2"
                f":y=h*0.78"
                f":fontfile={fontfile}"
            )

        clip_filter += f"[v{i}]"
        filter_parts.append(clip_filter)

    # 2. Crossfade chain between clips → [vbase]
    if n == 1:
        filter_parts.append("[v0]copy[vbase]")
    else:
        # xfade offset[k] = sum(durations[0..k]) - (k+1)*cf
        # Chain: [v0][v1]xfade=...offset=o0[xf01]; [xf01][v2]xfade=...offset=o1[xf02]; ...
        prev_label = "v0"
        running_duration = clip_durations[0]
        for k in range(1, n):
            offset = running_duration - k * cf
            # clamp to a positive value to avoid FFmpeg errors on very short clips
            offset = max(offset, 0.01)
            out_label = f"xf{k - 1}{k}" if k < n - 1 else "vbase"
            filter_parts.append(
                f"[{prev_label}][v{k}]xfade=transition=fade"
                f":duration={cf}"
                f":offset={offset:.4f}"
                f"[{out_label}]"
            )
            prev_label = out_label
            running_duration += clip_durations[k]

    # 3. Subtitles on [vbase] → [vout]
    if subtitle_path and subtitle_path.exists():
        # Use relative path to avoid Windows C: colon issue in FFmpeg filter parser
        safe_sub = os.path.relpath(subtitle_path).replace(chr(92), "/")
        filter_parts.append(f"[vbase]{_ass_filter(safe_sub)}[vout]")
    else:
        filter_parts.append("[vbase]copy[vout]")

    # 4. Audio mixing
    music_fade_out_start = max(effective_duration - 3.0, 0.0)

    has_vo = vo_idx is not None
    has_mu = mu_idx is not None

    if has_vo and has_mu:
        # Dynamic ducking: music dips during voiceover, rises during pauses
        logger.info("[AUDIO-MIX] OK: sidechaincompress ducking (stock_footage) — VO + music with dynamic ducking")
        filter_parts.append(
            f"[{vo_idx}:a]aformat=sample_rates=44100[vo];"
            f"[{mu_idx}:a]aformat=sample_rates=44100,"
            f"volume={music_volume},"
            f"afade=t=in:st=0:d=2,"
            f"afade=t=out:st={music_fade_out_start:.3f}:d=3"
            f"[mu];"
            f"[mu][vo]sidechaincompress=threshold=0.02:ratio=6:attack=50:release=300[ducked];"
            f"[vo][ducked]amix=inputs=2:duration=first:normalize=0[aout]"
        )
        map_args = ["-map", "[vout]", "-map", "[aout]"]
    elif has_vo:
        logger.warning("[AUDIO-MIX] DEGRADED: VO only, NO music — audio ducking skipped (stock_footage)")
        map_args = ["-map", "[vout]", "-map", f"{vo_idx}:a"]
    elif has_mu:
        filter_parts.append(
            f"[{mu_idx}:a]aformat=sample_rates=44100,"
            f"volume={music_volume},"
            f"afade=t=in:st=0:d=2,"
            f"afade=t=out:st={music_fade_out_start:.3f}:d=3"
            f"[aout]"
        )
        map_args = ["-map", "[vout]", "-map", "[aout]"]
    else:
        map_args = ["-map", "[vout]"]

    filter_complex = ";".join(filter_parts)

    full_args = inputs + [
        "-filter_complex", filter_complex,
    ] + map_args + [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-t", str(effective_duration),
        "-y", str(output_path),
    ]

    await run_ffmpeg(full_args, timeout=1800, cwd=_PROJECT_ROOT)
    logger.info("Composed stock video: %s", output_path.name)
    return output_path


# ---------------------------------------------------------------------------
# Compilation pipeline helpers (dangerous_nature + future compilation niches)
# ---------------------------------------------------------------------------


async def crop_to_portrait(
    input_path: Path,
    output_path: Path,
    target_resolution: tuple[int, int] = (1080, 1920),
    fps: int = 30,
) -> Path:
    """Convert any-orientation video to portrait (9:16) via center crop.

    Scales up to cover the target frame, then center-crops to exact dimensions.
    """
    w, h = target_resolution
    output_path.parent.mkdir(parents=True, exist_ok=True)

    args = [
        "-i", str(input_path),
        "-vf", (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1,fps={fps}"
        ),
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-y", str(output_path),
    ]

    await run_ffmpeg(args, timeout=300)
    logger.info("Converted to portrait: %s", output_path.name)
    return output_path


async def build_text_card_video(
    text: str,
    audio_path: Path | None,
    output_path: Path,
    duration: float = 3.0,
    resolution: tuple[int, int] = (1080, 1920),
    fps: int = 30,
    bg_color: str = "0x0a0a0a",
    font_size: int = 64,
) -> Path:
    """Create a dark card video with centered text and optional narration audio.

    Used for title cards, transition bridges, and outro cards in compilations.
    """
    w, h = resolution
    output_path.parent.mkdir(parents=True, exist_ok=True)

    escaped = text.replace("'", "\u2019").replace(":", "\\:").replace("%", "%%")
    font_path = "assets/fonts/Montserrat.ttf"

    # Wrap long text
    wrapped = _wrap_text(escaped, max_chars=25)

    inputs = [
        "-f", "lavfi",
        "-i", f"color=c={bg_color}:s={w}x{h}:d={duration}:r={fps}",
    ]

    # Always include audio (narration or silence) so concat works
    if audio_path and audio_path.exists():
        inputs.extend(["-i", str(audio_path)])
    else:
        # Generate silent audio track
        inputs.extend(["-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={duration}"])

    drawtext = (
        f"drawtext=text='{wrapped}':"
        f"fontfile='{font_path}':"
        f"fontsize={font_size}:fontcolor=white:"
        f"borderw=3:bordercolor=black:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:"
        f"line_spacing=20"
    )

    args = inputs + [
        "-vf", drawtext,
        "-map", "0:v", "-map", "1:a",
        "-shortest",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-y", str(output_path),
    ]

    await run_ffmpeg(args, timeout=120, cwd=_PROJECT_ROOT)
    logger.info("Built text card: %s (%.1fs)", output_path.name, duration)
    return output_path


async def build_clip_with_label(
    clip_path: Path,
    label_text: str,
    output_path: Path,
    max_duration: float = 15.0,
    label_position: str = "top",
    narration_path: Path | None = None,
    resolution: tuple[int, int] = (1080, 1920),
    fps: int = 30,
) -> Path:
    """Build a clip with context label and optional narration overlay.

    When narration_path is provided, narration plays over the first N seconds
    of the clip with original audio ducked to 15%, then original audio fades
    back to 100%. This creates seamless transitions with no blank screens.
    """
    w, h = resolution
    output_path.parent.mkdir(parents=True, exist_ok=True)

    escaped = label_text.replace("'", "\u2019").replace(":", "\\:").replace("%", "%%")
    font_path = "assets/fonts/Montserrat.ttf"

    if label_position == "center":
        y_expr = "(h-text_h)/2"
        fsize = 72
    else:
        y_expr = "80"
        fsize = 40

    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},setsar=1,fps={fps}"
    )
    if label_text.strip():
        vf += (
            f",drawtext=text='{escaped}':"
            f"fontfile='{font_path}':"
            f"fontsize={fsize}:fontcolor=white:"
            f"borderw=3:bordercolor=black:"
            f"x=(w-text_w)/2:y={y_expr}"
        )

    # Get narration duration if provided
    narr_dur = 0.0
    if narration_path and narration_path.exists():
        narr_dur = await get_duration(narration_path)

    # Inputs: clip (0), silence (1), optional narration (2)
    inputs = [
        "-i", str(clip_path),
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
    ]
    if narr_dur > 0:
        inputs.extend(["-i", str(narration_path)])

    # Audio filter: duck clip audio during narration, mix with narration
    if narr_dur > 0:
        # Clip audio: 15% during narration, ramp to 100% after
        audio_filter = (
            f"[0:a][1:a]amix=inputs=2:duration=shortest:normalize=0,"
            f"volume='if(lt(t,{narr_dur:.1f}),0.15,min(1.0,0.15+(t-{narr_dur:.1f})*1.7))':eval=frame[clipa];"
            f"[2:a]apad=whole_dur={max_duration}[narrpad];"
            f"[clipa][narrpad]amix=inputs=2:duration=first:normalize=0[aout]"
        )
    else:
        # No narration: just ensure audio stream exists
        audio_filter = (
            f"[0:a][1:a]amix=inputs=2:duration=shortest:normalize=0[aout]"
        )

    filter_complex = f"[0:v]{vf}[vout];{audio_filter}"

    args = inputs + [
        "-t", str(max_duration),
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-y", str(output_path),
    ]

    try:
        await run_ffmpeg(args, timeout=180, cwd=_PROJECT_ROOT)
    except RuntimeError:
        # Fallback: no clip audio, use silence (+ narration if available)
        logger.warning("Audio mix failed, using silence fallback: %s", clip_path.name)
        fb_inputs = ["-i", str(clip_path)]
        if narr_dur > 0:
            # Use narration as sole audio, padded with silence
            fb_inputs.extend(["-i", str(narration_path)])
            fb_filter = f"[0:v]{vf}[vout];[1:a]apad=whole_dur={max_duration}[aout]"
        else:
            fb_inputs.extend(["-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo"])
            fb_filter = f"[0:v]{vf}[vout];[1:a]acopy[aout]"

        await run_ffmpeg(fb_inputs + [
            "-t", str(max_duration),
            "-filter_complex", fb_filter,
            "-map", "[vout]", "-map", "[aout]",
            "-shortest",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-y", str(output_path),
        ], timeout=120, cwd=_PROJECT_ROOT)

    logger.info("Built clip with label: %s (narr=%.1fs)", output_path.name, narr_dur)
    return output_path


async def concat_segments_with_music(
    segment_paths: list[Path],
    music_path: Path | None,
    output_path: Path,
    music_volume: float = 0.15,
) -> Path:
    """Concatenate pre-built video segments and overlay background music.

    Each segment has its own audio (original clip audio or narration).
    Background music is mixed in at low volume throughout.
    """
    import tempfile

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: Create concat list file
    concat_file = output_path.with_suffix(".concat.txt")
    with open(concat_file, "w", encoding="utf-8") as f:
        for seg in segment_paths:
            # Use forward slashes and escape single quotes for FFmpeg
            safe_path = str(seg.resolve()).replace(chr(92), "/").replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

    # Step 2: Concat all segments using filter_complex for reliable stream handling
    # Build inputs for all segments + music
    n = len(segment_paths)
    inputs: list[str] = []
    for seg in segment_paths:
        inputs.extend(["-i", str(seg)])

    music_idx = None
    if music_path and music_path.exists():
        inputs.extend(["-stream_loop", "-1", "-i", str(music_path)])
        music_idx = n

    # Build filter: normalize all video+audio, concat, then mix music
    filter_parts: list[str] = []

    # Normalize each segment's video and audio
    for i in range(n):
        filter_parts.append(
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
            f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{i}]"
        )
        filter_parts.append(
            f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[a{i}]"
        )

    # Concat — video streams first, then audio streams (FFmpeg concat filter requirement)
    interleaved = "".join(f"[v{i}][a{i}]" for i in range(n))
    filter_parts.append(f"{interleaved}concat=n={n}:v=1:a=1[vout][aconcat]")

    # Mix background music if available
    if music_idx is not None:
        logger.info("[COMPILATION] Adding background music at %.0f%% volume", music_volume * 100)
        filter_parts.append(
            f"[{music_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"volume={music_volume}[music];"
            f"[aconcat][music]amix=inputs=2:duration=first:normalize=0[aout]"
        )
        audio_label = "[aout]"
    else:
        audio_label = "[aconcat]"

    filter_complex = ";".join(filter_parts)

    await run_ffmpeg(
        inputs + [
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", audio_label,
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-y", str(output_path),
        ],
        timeout=900,
    )

    # Cleanup
    concat_file.unlink(missing_ok=True)

    dur = await get_duration(output_path)
    logger.info("Compilation assembled: %s (%.1fs, %d segments)", output_path.name, dur, len(segment_paths))
    return output_path
