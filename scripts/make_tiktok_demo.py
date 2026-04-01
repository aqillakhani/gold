"""Generate a TikTok Developer App demo video.

Creates slide images with Pillow, then stitches into MP4 with FFmpeg.
"""

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FFMPEG = r"C:\Users\claws\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "data" / "media" / "demo" / "tiktok_app_demo.mp4"
SLIDE_DIR = PROJECT_ROOT / "data" / "media" / "demo" / "slides"
SLIDE_DIR.mkdir(parents=True, exist_ok=True)

WIDTH, HEIGHT = 1920, 1080
FPS = 30
DURATION_PER_SLIDE = 5

# Fonts
FONT_TITLE = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 64)
FONT_BODY = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 40)
FONT_SMALL = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 32)

ACCENT = (0, 242, 234)  # TikTok cyan

SLIDES = [
    {
        "title": "Gold Platform",
        "body": [
            "Content Management Tool",
            "for Short-Form Video Creators",
            "",
            "TikTok Content Posting API Demo",
        ],
        "bg": (0, 0, 0),
    },
    {
        "title": "What Gold Platform Does",
        "body": [
            "Helps creators manage and publish",
            "short-form video content to TikTok",
            "",
            "Users authorize their TikTok account",
            "via OAuth and schedule video uploads",
        ],
        "bg": (26, 26, 46),
    },
    {
        "title": "Step 1: User Authorization",
        "body": [
            "User clicks 'Connect TikTok' in dashboard",
            "Redirected to TikTok OAuth consent screen",
            "User grants video.publish permission",
            "App receives authorization code",
            "Code exchanged for access token",
        ],
        "bg": (22, 33, 62),
    },
    {
        "title": "Step 2: Content Creation",
        "body": [
            "User uploads a video file (MP4)",
            "Adds caption and hashtags",
            "Sets privacy level (public/private)",
            "Optionally schedules publish time",
            "AI disclosure label added automatically",
        ],
        "bg": (15, 52, 96),
    },
    {
        "title": "Step 3: Video Upload via API",
        "body": [
            "App calls POST /v2/post/publish/video/init/",
            "Uploads video via chunk upload",
            "Sets title, description, privacy status",
            "Marks AI-generated content (is_aigc: true)",
            "Video published to user's TikTok account",
        ],
        "bg": (26, 26, 46),
    },
    {
        "title": "Step 4: Post Management",
        "body": [
            "App tracks published video status",
            "Retrieves view count and engagement metrics",
            "Users can manage all posts from dashboard",
            "Performance metrics displayed in real-time",
        ],
        "bg": (22, 33, 62),
    },
    {
        "title": "API Scopes Required",
        "body": [
            "video.publish — Publish videos to TikTok",
            "video.upload — Upload video files",
            "",
            "Users can revoke access at any time",
            "via TikTok account settings",
        ],
        "bg": (15, 52, 96),
    },
    {
        "title": "Thank You",
        "body": [
            "Gold Platform",
            "aqillakhani.github.io/gold-platform-site",
            "",
            "Contact: storyvault8.official@gmail.com",
        ],
        "bg": (0, 0, 0),
    },
]


def create_slide_image(index: int, slide: dict) -> Path:
    """Create a single slide as a PNG image."""
    img = Image.new("RGB", (WIDTH, HEIGHT), slide["bg"])
    draw = ImageDraw.Draw(img)

    title = slide["title"]
    body = slide["body"]

    # Draw title centered
    bbox = draw.textbbox((0, 0), title, font=FONT_TITLE)
    tw = bbox[2] - bbox[0]
    draw.text(((WIDTH - tw) // 2, 180), title, fill=(255, 255, 255), font=FONT_TITLE)

    # Accent underline
    bar_w = min(tw + 40, 500)
    bar_x = (WIDTH - bar_w) // 2
    draw.rectangle([bar_x, 270, bar_x + bar_w, 274], fill=ACCENT)

    # Body lines
    y = 330
    for line in body:
        if not line:
            y += 30
            continue
        bbox = draw.textbbox((0, 0), line, font=FONT_BODY)
        lw = bbox[2] - bbox[0]
        draw.text(((WIDTH - lw) // 2, y), line, fill=(200, 200, 200), font=FONT_BODY)
        y += 58

    # Slide number indicator
    indicator = f"{index + 1} / {len(SLIDES)}"
    bbox = draw.textbbox((0, 0), indicator, font=FONT_SMALL)
    iw = bbox[2] - bbox[0]
    draw.text(((WIDTH - iw) // 2, HEIGHT - 60), indicator, fill=(100, 100, 100), font=FONT_SMALL)

    path = SLIDE_DIR / f"slide_{index:02d}.png"
    img.save(path)
    print(f"  Slide {index}: {title}")
    return path


def build_video(slide_paths: list[Path]) -> None:
    """Stitch slide PNGs into an MP4 with FFmpeg."""
    # Create a concat file with each image shown for DURATION_PER_SLIDE seconds
    concat_file = SLIDE_DIR / "concat.txt"
    with open(concat_file, "w") as f:
        for p in slide_paths:
            f.write(f"file '{p}'\n")
            f.write(f"duration {DURATION_PER_SLIDE}\n")
        # Repeat last to avoid FFmpeg cutting it short
        f.write(f"file '{slide_paths[-1]}'\n")

    cmd = [
        FFMPEG, "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-vf", f"fps={FPS},format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-movflags", "+faststart",
        str(OUTPUT),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg FAILED:\n{result.stderr}", file=sys.stderr)
        raise RuntimeError("FFmpeg failed")


def main():
    print(f"Creating {len(SLIDES)} slide images...")
    slide_paths = []
    for i, slide in enumerate(SLIDES):
        path = create_slide_image(i, slide)
        slide_paths.append(path)

    print(f"\nStitching into video ({len(SLIDES) * DURATION_PER_SLIDE}s)...")
    build_video(slide_paths)

    size_mb = OUTPUT.stat().st_size / (1024 * 1024)
    print(f"\nDone! {OUTPUT} ({size_mb:.1f} MB, {len(SLIDES) * DURATION_PER_SLIDE}s)")


if __name__ == "__main__":
    main()
