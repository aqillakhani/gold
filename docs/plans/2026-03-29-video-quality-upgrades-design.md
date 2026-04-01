# Video Quality Upgrades Design — 2026-03-29

## Context
Research into top-performing YouTube Shorts / TikTok / IG Reels creators revealed several production quality gaps. This design covers 8 upgrades targeting subtitles, hook cards, voice, audio, and visual overlays — all implementable for $0 using existing tools (Remotion, FFmpeg, Fish Audio).

## Two Rendering Paths

| Path | Niches | Renderer | Current Subtitles |
|---|---|---|---|
| Stock footage | ai_tools, true_crime, personal_finance, english_learning | Remotion | Single-word pop-in (Impact, bottom) |
| Gameplay | reddit_stories, betrayal_revenge | FFmpeg + ASS | 3-word karaoke (Montserrat, bottom) |

---

## Upgrade 1: Remotion TikTok-Style Subtitles (Stock Footage Path)

**Problem:** Current `AnimatedSubtitles.tsx` shows 1 word at a time with Impact font at paddingBottom:200. Top creators use 2-3 word groups with background pills and center positioning.

**Solution:** Replace with new `TikTokCaptions.tsx` using `@remotion/captions` (already installed v4.0.434):
- `createTikTokStyleCaptions()` for 2-3 word groups with active word highlight
- Background pill (rounded rect, 70% opacity black)
- Montserrat Bold font
- All 6 niche accent colors
- Center-screen position (~y=50%)
- Spring bounce animation on group entrance

**Python changes:** Convert Whisper word timestamps to SRT format in `subtitles.py` (Remotion captions API uses SRT).

**Files:**
- NEW: `remotion/src/TikTokCaptions.tsx`
- EDIT: `remotion/src/StockFootageVideo.tsx` (swap component)
- EDIT: `remotion/src/Root.tsx` (add srtContent prop)
- EDIT: `src/gold/pipeline/subtitles.py` (add SRT generation)
- EDIT: `src/gold/utils/remotion_renderer.py` (pass SRT content)

## Upgrade 2: Subtitle Safe Zone Fix (Gameplay/FFmpeg Path)

**Problem:** ASS subtitles at `\pos(540,1550)` — bottom 20% is covered by platform UI buttons.

**Fix:**
- Move to `\pos(540,960)` (vertical center)
- Add all 6 niche accent colors (currently only 4)
- Increase font to 96px

**Files:**
- EDIT: `src/gold/pipeline/subtitles.py`

## Upgrade 3: Hook Cards for Missing Niches

**Problem:** personal_finance and english_learning use generic default hook card.

**Add:**
- Personal Finance: "Money Alert" gold/green gradient, dollar sign motif
- English Learning: "Quick Lesson" blue/teal, speech bubble motif

**Files:**
- EDIT: `remotion/src/HookCard.tsx`

## Upgrade 4: Multi-Voice for Stories

**Problem:** Reddit/betrayal stories have dialogue but use single narrator voice.

**Solution:** New `multi_voice.py` module:
1. Parse script for dialogue markers (quotes, "she said", "he replied")
2. Map narrator vs characters to different Fish Audio voice IDs
3. Generate TTS segments per speaker
4. Concatenate + return word timestamps
5. 2-3 voice variants: narrator (default), male character, female character

**Files:**
- NEW: `src/gold/pipeline/multi_voice.py`
- EDIT: `src/gold/pipeline/orchestrator.py` (wire multi-voice for reddit/betrayal)
- EDIT: `config/niches/reddit_stories.yaml` (add character voice IDs)
- EDIT: `config/niches/betrayal_revenge.yaml` (add character voice IDs)

## Upgrade 5: Audio Post-Processing

**Problem:** Raw TTS output lacks professional polish.

**Fix:** Add FFmpeg EQ chain after TTS generation:
```
highpass=f=80, lowpass=f=12000, loudnorm=I=-16:TP=-1.5:LRA=11
```

**Files:**
- EDIT: `src/gold/pipeline/audio.py` (add post-processing step)

## Upgrade 6: Part Badge Overlay

**Problem:** Multi-part stories (reddit/betrayal) don't visually indicate which part is playing.

**Fix:** "PART 2/3" badge in top-right corner:
- Semi-transparent background pill
- White text, niche accent border
- Visible full duration
- Remotion component for stock path, FFmpeg drawtext for gameplay path

**Files:**
- NEW: `remotion/src/PartBadge.tsx`
- EDIT: `remotion/src/StockFootageVideo.tsx`
- EDIT: `remotion/src/Root.tsx` (add partInfo prop)
- EDIT: `src/gold/utils/ffmpeg.py` (add part badge for gameplay)
- EDIT: `src/gold/utils/remotion_renderer.py` (pass partInfo)

## Upgrade 7: Emoji Reactions

**Problem:** No visual reactions to story beats. Top creators use emoji pops at dramatic moments.

**Fix:** Detect story beats via keyword matching in script:
- "shocking"/"insane" -> skull emoji
- "money"/"rich" -> moneybag emoji
- "love"/"heart" -> heart emoji
- Max 3-4 per video

**Remotion component:** Spring pop-in, hold 1s, fade out. Random position in safe zone.

**Files:**
- NEW: `remotion/src/EmojiReaction.tsx`
- EDIT: `remotion/src/StockFootageVideo.tsx`
- EDIT: `remotion/src/Root.tsx` (add emojiBeats prop)
- EDIT: `src/gold/pipeline/orchestrator.py` (detect beats from script)
- EDIT: `src/gold/utils/remotion_renderer.py` (pass emoji data)

## Upgrade 8: Progress Bar

**Problem:** No visual indication of video progress.

**Fix:** 4px colored bar at top of video, fills left-to-right over duration. Niche accent color.

**Files:**
- NEW: `remotion/src/ProgressBar.tsx`
- EDIT: `remotion/src/StockFootageVideo.tsx`
- EDIT: `src/gold/utils/ffmpeg.py` (drawbox for gameplay path)

---

## Implementation Order

1. Subtitles (Upgrades 1 + 2) — highest impact
2. Hook cards (Upgrade 3) — quick win
3. Progress bar + Part badge (Upgrades 6 + 8) — simple overlays
4. Emoji reactions (Upgrade 7) — moderate complexity
5. Audio post-processing (Upgrade 5) — simple FFmpeg filter
6. Multi-voice (Upgrade 4) — most complex, highest risk

## Success Criteria
- All 6 niches render with upgraded subtitles
- Subtitle text never in platform UI danger zone (bottom 20%, top 15%)
- Hook cards render for all 6 niches
- Multi-part stories show "Part X/Y" badge
- At least 2-3 emoji reactions per video
- Progress bar visible on all videos
- Audio loudness normalized to -16 LUFS
- Multi-voice works for at least reddit_stories
