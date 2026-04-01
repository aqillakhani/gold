# LTX-2.3 Video Quality Upgrade Design

**Date:** 2026-03-28
**Goal:** Replace Wan2.1 1.3B (4/10 quality) with LTX-2.3 (target 9/10) for AI video B-roll
**Budget:** $0.50-1.00 per video total, ~$0.04-0.08 for video generation alone

## Problem

Stock footage niches (ai_tools, true_crime, personal_finance, english_learning) route through `ai_video.py` → Wan2.1 1.3B on ComfyUI. Output is 480x832 upscaled to 1080x1920, generic AI slop, garbled text, flat lighting. Scored 4/10.

Meanwhile, `media.py` already has a ComfyUI LTX-2.3 integration (`comfyui.py`) that is never used by these niches. LTX-2.3 outputs 768x1344 native, 22B parameters, 18x faster, direct MP4 output.

## Solution: Three Layers

### Layer 1: Swap model (baseline 8.5/10)

Route stock_footage niches through `MediaProducer.generate_video_clip()` instead of `generate_ai_video_clip()` from `ai_video.py`.

**Changes:**
- `orchestrator.py` `_produce_stock_footage_video()`: replace `generate_ai_video_clip()` calls with `self.media.generate_video_clip()`
- `orchestrator.py` `_produce_cinematic_doc_video()`: same replacement
- `settings.yaml`: set `api.video_backend: comfyui`, `api.comfyui.host: <vast.ai IP:port>`
- Vast.ai instance: download LTX-2.3 model (`ltx-video-2b-v0.9.5.safetensors`)

**LTX-2.3 specs:**
- Resolution: 768x1344 (9:16 portrait)
- Frame rate: 24fps
- Frame count: 8n+1 formula (e.g., 97 frames for ~4s)
- Output: MP4 H.264 via VHS_VideoCombine node (no WEBP conversion)
- Generation time: ~20-30s per clip on RTX A4000

### Layer 2: Prompt engineering (8.5 → 9/10)

Update niche Jinja script templates to generate cinematographic, grounded scene descriptions instead of generic AI cliches.

**Prompt rules (enforced in templates):**
1. Every scene must specify camera type: macro, close-up, wide, over-shoulder, dolly, tracking, aerial
2. Every scene must specify lighting: natural, golden hour, desk lamp, neon, overcast, etc.
3. Every scene must specify depth of field: shallow/deep/rack focus
4. Never generate faces or readable text
5. Never generate "futuristic holographic UI" or generic sci-fi imagery
6. For person scenes: use "minimalist stick figure animation, black lines on white background"
7. Include subtle camera motion in every prompt: "slight camera drift", "slow dolly forward", "gentle handheld"

**Per-niche scene guidelines:**

#### ai_tools
- Hands on mechanical keyboard close-up, screen glow reflecting on fingers
- Phone screen showing app interface (filmed from behind, over shoulder, blurred)
- Workspace macro: coffee steam, mouse click, cable management
- Monitor with code (blurred/bokeh, focus on desk items in foreground)
- Stick figure at computer for "person using tool" scenes

#### true_crime
- Rain on window at night, streetlight reflections
- Empty corridor with flickering fluorescent light
- Police tape close-up, shallow depth of field
- Evidence file folders on desk, overhead shot
- Silhouette in doorway, backlit

#### personal_finance
- Gold coins macro, warm desk lamp lighting
- Hand writing numbers in notebook, shallow DoF
- Calculator close-up, soft morning light
- Wallet/cards on wooden table, overhead
- Stock chart on laptop screen (filmed from behind)

#### english_learning
- Open book pages turning, warm library light
- Pen writing in notebook, macro close-up
- Coffee shop ambient wide shot (no faces)
- Bookshelf dolly shot, shallow depth of field
- Stick figure in conversation for dialogue scenes

### Layer 3: Post-processing (final polish)

After Remotion render, add FFmpeg post-processing pass:

```
-vf "noise=c0s=6:allf=t,eq=contrast=1.05:brightness=0.02:saturation=1.1,vignette=PI/6"
```

**Per-niche color grading:**
- ai_tools: cool blue shift (slight blue in shadows)
- true_crime: desaturated, slight teal shadows + orange highlights
- personal_finance: warm golden tint
- english_learning: bright, slightly warm, high clarity

## Architecture

```
BEFORE:
  orchestrator → ai_video.py → ComfyUI Wan2.1 → WEBP → PIL extract → FFmpeg upscale → Remotion

AFTER:
  orchestrator → media.py → ComfyUI LTX-2.3 → MP4 direct → Remotion → FFmpeg post-process
```

## Cost

| Component | Per video |
|---|---|
| GPU rental (8 clips × 30s = 4min @ $0.045/hr) | $0.003 |
| Anthropic API (script) | $0.05-0.10 |
| Fish Audio TTS | $0.05-0.10 |
| Suno music | $0.05-0.10 |
| fal.ai images (thumbnails) | $0.015 |
| **Total** | **$0.17-0.33** |

## Implementation Scope

1. Download LTX-2.3 model on Vast.ai instance
2. Update `settings.yaml` (video_backend + comfyui host)
3. Modify `_produce_stock_footage_video()` in orchestrator.py — reroute to media.py
4. Modify `_produce_cinematic_doc_video()` in orchestrator.py — same
5. Update 4 niche Jinja templates with cinematographic prompt rules
6. Add FFmpeg post-processing step after Remotion render
7. Test 1 video per niche, verify quality
