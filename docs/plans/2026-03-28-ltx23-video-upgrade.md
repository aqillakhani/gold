# LTX-2.3 Video Quality Upgrade — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Wan2.1 1.3B AI video (4/10) with LTX-2.3 via existing ComfyUI integration (target 9/10) for all stock_footage niches.

**Architecture:** Route stock_footage niches through `MediaProducer.generate_video_clip()` → ComfyUI LTX-2.3 (already built in `comfyui.py`) instead of the legacy `ai_video.py` Wan2.1 path. Upgrade Jinja script templates with cinematographic prompts. Enable film grain post-processing on all AI video niches.

**Tech Stack:** Python, ComfyUI, LTX-2.3 model, FFmpeg, Jinja2 templates, Vast.ai GPU

---

### Task 1: Set up LTX-2.3 model on Vast.ai

**Files:**
- Modify: `config/settings.yaml:64-68`

**Step 1: Download LTX-2.3 model to the running Vast.ai ComfyUI instance**

SSH into the Vast.ai instance and download the model:

```bash
# Get current instance details first
python -c "
import requests
api_key = '***REMOVED***'
headers = {'Authorization': f'Bearer {api_key}'}
resp = requests.get('https://console.vast.ai/api/v0/instances', headers=headers)
for i in resp.json().get('instances', []):
    print(f'SSH: ssh -p {i[\"ssh_port\"]} root@{i[\"ssh_host\"]}')
    print(f'Ports: {i.get(\"ports\", {})}')
"

# SSH in and download model
# NOTE: The model file is ~4GB. If the instance doesn't have enough disk,
# you may need to remove the Wan2.1 models first.
ssh -p PORT root@HOST 'bash -s' <<'EOF'
cd /root/ComfyUI

# Check if VHS_VideoCombine node is available (needed for MP4 output)
pip install -q opencv-python imageio imageio-ffmpeg 2>/dev/null

# Check for video_helper_suite custom node
if [ ! -d custom_nodes/ComfyUI-VideoHelperSuite ]; then
    cd custom_nodes
    git clone --depth 1 https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
    cd ComfyUI-VideoHelperSuite && pip install -q -r requirements.txt 2>/dev/null
    cd /root/ComfyUI
fi

# Download LTX-2.3 model
mkdir -p models/checkpoints
cd models/checkpoints
if [ ! -f ltx-video-2b-v0.9.5.safetensors ]; then
    echo "Downloading LTX-2.3 model..."
    wget -q --show-progress https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.5.safetensors
fi
ls -lh ltx-video-2b-v0.9.5.safetensors
echo "DONE"
EOF
```

Expected: Model file ~4GB downloaded to `/root/ComfyUI/models/checkpoints/`

**Step 2: Verify ComfyUI has the LTX nodes**

```bash
ssh -p PORT root@HOST 'python -c "
import sys; sys.path.insert(0, \"/root/ComfyUI\")
# Check node availability
"'
```

Or check via API:
```python
import httpx, asyncio
async def check():
    url = "http://INSTANCE_IP:PORT"
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(f"{url}/object_info")
        nodes = resp.json()
        ltx = [k for k in nodes if 'LTX' in k or 'ltx' in k.lower()]
        vhs = [k for k in nodes if 'VHS' in k]
        print(f"LTX nodes: {ltx}")
        print(f"VHS nodes: {vhs}")
asyncio.run(check())
```

Expected: `LTXVLoader`, `LTXVConditioning`, `LTXVSampler`, `EmptyLTXVLatentVideo`, `LTXVDecode` present. `VHS_VideoCombine` present.

**Step 3: Update settings.yaml**

In `config/settings.yaml`, change:

```yaml
# BEFORE
  comfyui:
    host: ""
    video_model: ltx-2.3
    timeout: 600
  video_backend: fal

# AFTER
  comfyui:
    host: "INSTANCE_IP:PORT"  # Vast.ai ComfyUI instance
    video_model: ltx-2.3
    timeout: 600
  video_backend: comfyui  # Route video generation through ComfyUI LTX-2.3
```

**Step 4: Quick health check test**

```python
cd "C:/Users/claws/OneDrive/Desktop/gold"
python -c "
import sys; sys.path.insert(0, 'src')
from dotenv import load_dotenv; load_dotenv('secrets/.env')
from gold.config import Config
from gold.pipeline.comfyui import ComfyUIClient
import asyncio

config = Config()
client = ComfyUIClient(config)
print(f'Host: {client.host}')
print(f'Available: {client.is_available()}')
print(f'Healthy: {asyncio.run(client.health_check())}')
"
```

Expected: `Available: True`, `Healthy: True`

**Step 5: Restart ComfyUI to load new nodes/models**

```bash
ssh -p PORT root@HOST 'pkill -f "python main.py"; sleep 3; cd /root/ComfyUI && nohup python main.py --listen 0.0.0.0 --port 8188 > /root/comfyui.log 2>&1 &; echo "Restarted"'
```

---

### Task 2: Rewire orchestrator to use MediaProducer instead of ai_video.py

**Files:**
- Modify: `src/gold/pipeline/orchestrator.py:932-1005` (stock footage method)
- Modify: `src/gold/pipeline/orchestrator.py:1263-1320` (cinematic doc method)

**Step 1: Replace AI video block in `_produce_stock_footage_video()`**

Replace lines 932-986 (the entire Wan2.1 setup + scene loop AI video section):

```python
# BEFORE (lines 932-956):
        # AI video generation setup (Wan2.1 on Vast.ai ComfyUI)
        footage_source = visual_config.get("footage_source", "pexels")
        comfyui_url = os.environ.get("VASTAI_COMFYUI_URL", "")
        ai_video_available = footage_source == "ai_video" and comfyui_url
        strict_mode = os.environ.get("GOLD_STRICT_MODE", "") == "1"
        # ... (Wan2.1 health check block) ...
        ai_model_size = visual_config.get("ai_video_model", "1.3B")

# AFTER:
        footage_source = visual_config.get("footage_source", "pexels")
        ai_video_available = footage_source == "ai_video"
        strict_mode = os.environ.get("GOLD_STRICT_MODE", "") == "1"

        # Check if AI video backend (ComfyUI/fal) is available
        if ai_video_available:
            use_comfyui = await self.media._should_use_comfyui()
            if not use_comfyui and strict_mode:
                raise RuntimeError(
                    f"[{account_id}] STRICT MODE: footage_source=ai_video but video backend unavailable."
                )
            if not use_comfyui:
                logger.warning("[%s] AI video backend unavailable, falling back to Pexels", account_id)
                ai_video_available = False
```

Replace the scene loop AI video call (lines 967-986):

```python
# BEFORE:
            # Option 1: AI video generation (Wan2.1 via ComfyUI)
            if ai_video_available:
                video_prompt = scene.get("image_prompt", search_query)
                try:
                    result = await generate_ai_video_clip(
                        prompt=video_prompt,
                        niche_id=niche_id,
                        output_path=clip_path,
                        target_duration=duration,
                        comfyui_url=comfyui_url,
                        cache_dir=cache_dir,
                        resolution=resolution,
                        model_size=ai_model_size,
                    )
                except Exception as e:
                    if strict_mode:
                        raise RuntimeError(...) from e
                    logger.warning(...)

# AFTER:
            # Option 1: AI video generation (LTX-2.3 via ComfyUI or Kling via fal)
            if ai_video_available:
                video_prompt = scene.get("image_prompt", search_query)
                clip_name = f"content_{content_id}_stock_{i}_{ts}"
                try:
                    result = await self.media.generate_video_clip(
                        prompt=video_prompt,
                        output_name=clip_name,
                        duration=str(min(duration, 10)),
                        aspect_ratio="9:16",
                    )
                    if result:
                        logger.info("[%s] Scene %d/%d: AI video (%.1fs)", account_id, i + 1, len(scenes), duration)
                except Exception as e:
                    if strict_mode:
                        raise RuntimeError(
                            f"[{account_id}] STRICT MODE: AI video failed for scene {i+1}: {e}"
                        ) from e
                    logger.warning("[%s] AI video failed for scene %d: %s — falling back", account_id, i + 1, e)
                    result = None
```

Also remove the now-unused Pexels strict-mode guard (the one that checks `if ai_video_available and strict_mode` before Pexels fallback) — it's already handled by the outer exception.

**Step 2: Apply the same replacement in `_produce_cinematic_doc_video()`**

Same pattern at lines 1263-1320. Replace the Wan2.1 setup block and scene loop call with the MediaProducer call. The structure is identical.

**Step 3: Remove the `from ..utils.ai_video import` statements**

These are inside the `if ai_video_available:` blocks at lines 945 and 1275. They're no longer needed since we call `self.media.generate_video_clip()` instead.

**Step 4: Verify the change compiles**

```bash
cd "C:/Users/claws/OneDrive/Desktop/gold"
python -c "from gold.pipeline.orchestrator import ContentPipeline; print('OK')"
```

Expected: `OK` (no import errors)

---

### Task 3: Upgrade niche script templates with cinematographic prompts

**Files:**
- Modify: `templates/ai_tools/script_prompt.jinja2`
- Modify: `templates/true_crime/script_prompt.jinja2`
- Modify: `templates/personal_finance/script_prompt.jinja2`
- Modify: `templates/english_learning/script_prompt.jinja2`

For each template, replace the `image_prompt` guidelines section with detailed cinematographic instructions. The key changes:

1. Replace "REAL STOCK FOOTAGE from Pexels" context with "AI-GENERATED video clips"
2. Replace generic image_prompt guidelines with cinematographic scene descriptions
3. Add hard rules: no faces, no readable text, no generic futuristic imagery
4. Add camera language requirements
5. Add stick figure style for person scenes

**Step 1: Update `templates/ai_tools/script_prompt.jinja2`**

Replace the `IMPORTANT:` context line (line 9) with:

```
IMPORTANT: This video uses AI-GENERATED video clips with smooth crossfade transitions between scenes. Each scene's image_prompt drives the video generation — QUALITY OF PROMPTS IS CRITICAL. Write prompts as if directing a cinematographer. Voiceover carries the narrative. Word-by-word subtitles are burned in automatically. Background music plays underneath.
```

Replace the `scenes` section guidelines (lines 27-41 and 53-68) with:

```
3. scenes: An array of 6-8 scene objects. Each scene has:
   - image_prompt: DETAILED cinematographic prompt for AI video generation. THIS IS CRITICAL — vague prompts produce generic AI slop. Write each prompt as a specific camera direction:
     REQUIRED ELEMENTS (include ALL of these in every prompt):
     - Shot type: macro, close-up, medium, wide, over-shoulder, overhead, tracking, dolly, aerial
     - Subject: what the camera sees (specific objects, textures, actions)
     - Lighting: natural, desk lamp, monitor glow, golden hour, overcast, neon, backlit
     - Depth of field: shallow (blurred background), deep (everything sharp), rack focus
     - Camera motion: slight drift, slow dolly forward, gentle pan right, static, handheld
     - Mood: clean, professional, cozy, energetic, minimal

     GOOD PROMPTS:
     - "Macro close-up of fingers typing on a mechanical keyboard, RGB backlight glow, shallow depth of field, desk lamp warm light, slight camera drift left, professional workspace"
     - "Over-shoulder shot of phone screen showing an app interface, blurred background of coffee shop, natural daylight from window, static camera with subtle handheld movement"
     - "Overhead flat-lay of a clean desk with laptop, notebook, pen, and coffee mug, morning sunlight casting soft shadows, slow gentle zoom in, minimal aesthetic"
     - "Close-up of a cursor clicking through a software interface on a monitor, screen glow reflecting on desk surface, shallow depth of field, steady camera"
     - "Wide shot of a modern workspace at golden hour, large monitor on standing desk, plants, clean cable management, warm natural light through blinds, slow dolly right"

     BAD PROMPTS (NEVER write these):
     - "Futuristic holographic dashboard with blue ambient glow" (generic AI cliche)
     - "Person using AI tool on computer" (too vague, will generate uncanny face)
     - "Technology concept with data flowing" (abstract nonsense)
     - "Modern tech environment" (meaningless, produces nothing specific)

     RULES:
     - NEVER include human faces or full bodies — use hands-only close-ups, over-shoulder (back of head only), or silhouettes
     - NEVER include readable text, logos, or brand names in the image prompt
     - NEVER use the word "futuristic", "holographic", or "glowing interface"
     - For scenes that need a person doing something: write "Simple minimalist stick figure animation, black lines on clean white background, [person doing action], smooth motion, 2D flat style"
     - Each scene prompt MUST be different — no two scenes should look similar

   - search_keywords: 2-4 word backup Pexels search query in case AI video fails.
   - ken_burns: Backup camera effect. One of: "zoom_in", "zoom_out", "pan_left", "pan_right", "diagonal", "zoom_pan_combo".
   - duration: Duration in seconds (5-8). Total should be ~{{ niche.target_duration }}s.
   - text_overlay: Optional short text to display on this scene (max 6 words). Leave empty string for most scenes.
```

**Step 2: Update `templates/true_crime/script_prompt.jinja2`**

Same structure. Replace image_prompt guidelines. Key differences for true_crime:

```
     GOOD PROMPTS:
     - "Slow dolly down a rain-soaked alley at night, red neon sign reflections on wet asphalt, deep shadows, cinematic noir atmosphere, slight handheld camera shake"
     - "Macro close-up of a manila evidence folder being opened, single desk lamp casting harsh shadows, dust particles in light beam, shallow depth of field, static camera"
     - "Wide establishing shot of an empty courtroom, overhead fluorescent lights casting cold shadows, empty jury box, ominous atmosphere, very slow zoom in"
     - "Close-up of police evidence tape fluttering in wind, dark stormy sky out of focus behind it, rain droplets, shallow depth of field, slight camera drift"
     - "Overhead shot of scattered case files and photographs on a detective's desk, single warm desk lamp, coffee cup, dark room around edges, slow pan across documents"
     - "Silhouette of a figure standing in a doorway, backlit by cool blue street light, rain falling, deep noir shadows, static camera with slight drift"

     BAD PROMPTS:
     - "Crime scene" (too vague)
     - "Scary dark place" (meaningless)
     - "Person looking suspicious" (will generate uncanny face)

     RULES:
     - NEVER show identifiable human faces — use silhouettes, back-of-head shots, hands only
     - Every prompt MUST include "noir atmosphere" or "cinematic shadows" for visual consistency
     - Include red/crimson accent lighting where possible (neon signs, tail lights, red lamp)
     - Prefer atmospheric environments over people
```

**Step 3: Update `templates/personal_finance/script_prompt.jinja2`**

Key prompt style for finance:

```
     GOOD PROMPTS:
     - "Macro close-up of gold coins stacked on a warm wooden desk, morning sunlight through window blinds casting striped shadows, shallow depth of field, slight camera drift right"
     - "Over-shoulder view of hands writing numbers in a leather notebook with a fountain pen, calculator and coffee beside it, warm desk lamp, slow gentle zoom in"
     - "Close-up of a credit card being placed on a wooden table, wallet open nearby, soft warm ambient light, shallow depth of field, static camera with slight movement"
     - "Wide shot of a clean home office, laptop showing a financial chart (blurred), plants on shelf, golden hour light, slow dolly forward, calm professional atmosphere"
     - "Overhead flat-lay of budgeting items: notebook, calculator, receipts, pen, on marble surface, soft diffused daylight, slow gentle zoom out, clean minimal aesthetic"

     RULES:
     - NEVER show human faces — use hands, over-shoulder, overhead views
     - Warm, trustworthy aesthetic: golden light, wood textures, clean surfaces
     - Avoid showing specific dollar amounts or real brand logos in the video prompt
     - For person scenes: "Simple minimalist stick figure animation, black lines on warm cream background, [person doing action], friendly smooth motion"
```

**Step 4: Update `templates/english_learning/script_prompt.jinja2`**

Key prompt style for language learning:

```
     GOOD PROMPTS:
     - "Macro close-up of a hand writing in a notebook with a ballpoint pen, lined paper, warm desk lamp light, shallow depth of field, slow camera drift, cozy study atmosphere"
     - "Close-up of an open book with pages turning gently, warm library light, bookshelves blurred in background, shallow depth of field, soft natural movement"
     - "Wide shot of a cozy coffee shop interior, people blurred in background, warm ambient lighting, steam rising from cup on table, slow gentle dolly right, calm atmosphere"
     - "Overhead shot of a study desk with textbook, highlighters, sticky notes, and tea mug, soft morning light, slow zoom in, clean organized aesthetic"
     - "Simple minimalist stick figure animation, black lines on clean white background, two stick figures having a friendly conversation with speech bubbles, smooth 2D animation"

     RULES:
     - NEVER show human faces — use hands, overhead desk shots, blurred background people
     - Bright, friendly, warm aesthetic — this is an educational channel
     - For dialogue/conversation scenes: ALWAYS use stick figure animation style
     - Include study-related objects: books, notebooks, pens, coffee/tea, libraries
```

---

### Task 4: Enable film grain on AI video niches

**Files:**
- Modify: `config/niches/ai_tools.yaml`
- Modify: `config/niches/personal_finance.yaml`
- Modify: `config/niches/english_learning.yaml`

true_crime already has `grain: light`. Add film grain to the other niches that use AI video:

**Step 1: Add grain to ai_tools.yaml**

Add `grain: light` under the `visual:` section (after `vignette: false`):

```yaml
    vignette: false
    grain: light  # subtle film grain to mask AI smoothness
```

**Step 2: Add grain to personal_finance.yaml**

```yaml
    vignette: false
    grain: light  # subtle film grain for organic feel
```

**Step 3: Add grain to english_learning.yaml**

Check the file first — add `grain: light` in the visual section. Also verify `color_grade` is set (if not, add `color_grade: warm`).

**Step 4: Verify visual treatments apply**

```python
from gold.utils.ffmpeg import build_visual_treatment_filter
# Should return non-empty filter string for each niche
for niche_visual in [
    {"color_grade": "cool_tech", "grain": "light"},
    {"color_grade": "warm", "grain": "light"},
    {"color_grade": "desaturated", "vignette": True, "grain": "light"},
]:
    print(build_visual_treatment_filter(niche_visual))
```

Expected: Each prints a filter chain like `colorbalance=...,noise=alls=8:allf=t`

---

### Task 5: Update niche configs for AI video changes

**Files:**
- Modify: `config/niches/ai_tools.yaml:6-10`
- Modify: `config/niches/true_crime.yaml` (similar section)
- Modify: `config/niches/personal_finance.yaml`
- Modify: `config/niches/english_learning.yaml`

**Step 1: Update footage_source config**

The `footage_source: ai_video` setting stays the same, but remove the Wan2.1-specific config keys (`fallback`, `ai_video_model`) since we're now routing through MediaProducer/ComfyUI:

```yaml
# BEFORE
  visual:
    footage_source: ai_video  # Wan2.1 on Vast.ai, falls back to Pexels automatically
    footage_orientation: portrait
    fallback: pexels  # if AI video gen fails, use Pexels stock footage
    ai_video_model: "1.3B"  # "1.3B" (fast/$0.02/clip) or "14B" (quality/$0.25/clip)

# AFTER
  visual:
    footage_source: ai_video  # LTX-2.3 via ComfyUI, falls back to Pexels
    footage_orientation: portrait
```

Apply to all 4 niches that have `footage_source: ai_video`.

---

### Task 6: Test 1 video with LTX-2.3 and verify quality

**Step 1: Run preflight check**

```bash
cd "C:/Users/claws/OneDrive/Desktop/gold"
python preflight_check.py
```

Expected: All checks pass (ComfyUI healthy, all keys set).

**Step 2: Generate 1 test video for ai_tools**

```bash
python test_quality.py ai_tools
```

Monitor progress. Each clip should take ~20-30s (vs 7min with Wan2.1). Total: ~5-10 min for clips + ~25 min for Remotion render.

**Step 3: Visual verification**

Extract frames from the new video and compare to previous Pexels and Wan2.1 outputs:

```bash
mkdir -p data/comparison_ltx
ffmpeg -y -ss 2 -i "data/media/clips/content_XXX_stock_0_*.mp4" -frames:v 1 data/comparison_ltx/ltx_clip0.png
ffmpeg -y -ss 2 -i "data/media/clips/content_XXX_stock_2_*.mp4" -frames:v 1 data/comparison_ltx/ltx_clip2.png
ffmpeg -y -ss 2 -i "data/media/clips/content_XXX_stock_4_*.mp4" -frames:v 1 data/comparison_ltx/ltx_clip4.png
```

Open the frames and score:
- Resolution/sharpness (should be 768x1344 native, no upscale mush)
- No garbled text or AI artifacts
- Cinematographic composition (specific subjects, good lighting)
- No generic "blue holographic" imagery
- Natural color grading applied (film grain visible)

**Step 4: Compare quality report**

```bash
cat data/quality_report.txt
```

Expected: All tags OK (TTS, EMOTION, SUBTITLE, AUDIO-MIX, VISUAL-HOOK).

**Step 5: User visual review**

Open `data/media/rendered/content_XXX/youtube.mp4` and watch the full video. Score against 9/10 target.

---

### Task 7: Update preflight_check.py for LTX-2.3

**Files:**
- Modify: `preflight_check.py`

**Step 1: Replace VASTAI_COMFYUI_URL check with MediaProducer backend check**

The preflight check currently looks for `VASTAI_COMFYUI_URL` env var. Update it to check `settings.yaml` ComfyUI config instead:

```python
# BEFORE:
    comfyui_url = os.environ.get("VASTAI_COMFYUI_URL", "")
    if comfyui_url:
        from gold.utils.ai_video import check_comfyui_health
        healthy = await check_comfyui_health(comfyui_url)
        check("AI Video (ComfyUI)", healthy, ...)

# AFTER:
    from gold.config import Config
    from gold.pipeline.media import MediaProducer
    config = Config()
    mp = MediaProducer(config)
    use_comfy = await mp._should_use_comfyui()
    backend = config.get("api.video_backend", "fal")
    host = config.get("api.comfyui.host", "")
    if backend == "comfyui":
        check("AI Video (LTX-2.3 ComfyUI)", use_comfy, f"host={host}" if use_comfy else f"Unreachable: {host}")
    else:
        check("AI Video (fal.ai)", True, f"backend={backend}")
```
