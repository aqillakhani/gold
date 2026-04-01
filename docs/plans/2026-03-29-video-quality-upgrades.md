# Video Quality Upgrades Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade subtitle rendering, hook cards, voice, audio, and visual overlays across all 6 niches to match top-performing YouTube Shorts / TikTok creators.

**Architecture:** Two rendering paths — Remotion (stock footage niches: ai_tools, true_crime, personal_finance, english_learning) and FFmpeg (gameplay niches: reddit_stories, betrayal_revenge). Remotion upgrades via new React components; FFmpeg upgrades via filter chain changes. Python orchestrator wires everything together.

**Tech Stack:** Remotion 4.0.434 + @remotion/captions, FFmpeg, Fish Audio TTS, Python 3.14, TypeScript

---

## Task 1: Remotion TikTok-Style Captions Component

Replaces the single-word `AnimatedSubtitles.tsx` with proper 2-3 word groups using `@remotion/captions`.

**Files:**
- Create: `remotion/src/TikTokCaptions.tsx`
- Modify: `remotion/src/StockFootageVideo.tsx:14-15,103-109` (swap component)
- Modify: `remotion/src/Root.tsx:22-23` (add srtContent to VideoProps)

**Step 1: Create `remotion/src/TikTokCaptions.tsx`**

```tsx
import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { createTikTokStyleCaptions } from "@remotion/captions";
import type { SubtitleWord } from "./Root";

type TikTokCaptionsProps = {
  subtitles: SubtitleWord[];
  accentColor: string;
  nicheId: string;
};

const NICHE_COLORS: Record<string, string> = {
  true_crime: "#f87171",
  ai_tools: "#60a5fa",
  personal_finance: "#fbbf24",
  english_learning: "#34d399",
  reddit_stories: "#fb923c",
  betrayal_revenge: "#f87171",
  crypto_finance: "#22c55e",
};

export const TikTokCaptions: React.FC<TikTokCaptionsProps> = ({
  subtitles,
  accentColor,
  nicheId,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;

  // Convert SubtitleWord[] to the format createTikTokStyleCaptions expects
  const captions = subtitles.map((w) => ({
    text: w.word + " ",
    startMs: Math.round(w.start * 1000),
    endMs: Math.round(w.end * 1000),
    timestampMs: Math.round(w.start * 1000),
    confidence: 1,
  }));

  const { pages } = createTikTokStyleCaptions({ captions, combineTokensWithinMilliseconds: 800 });

  const color = NICHE_COLORS[nicheId] || accentColor || "#FFFFFF";

  // Find the current page (word group)
  const currentMs = currentTime * 1000;
  const currentPage = pages.find(
    (p) => currentMs >= p.startMs && currentMs < p.startMs + (p.tokens[p.tokens.length - 1].endMs - p.startMs)
  );

  if (!currentPage) return null;

  // Spring animation for page entrance
  const pageStartFrame = Math.round((currentPage.startMs / 1000) * fps);
  const localFrame = Math.max(0, frame - pageStartFrame);
  const pop = spring({
    frame: localFrame,
    fps,
    config: { stiffness: 300, damping: 18, mass: 0.4 },
  });
  const scale = interpolate(pop, [0, 1], [0.75, 1.0]);
  const opacity = interpolate(pop, [0, 1], [0, 1]);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          transform: `scale(${scale})`,
          opacity,
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          alignItems: "center",
          gap: 8,
          maxWidth: "90%",
          backgroundColor: "rgba(0, 0, 0, 0.65)",
          borderRadius: 16,
          padding: "12px 24px",
        }}
      >
        {currentPage.tokens.map((token, i) => {
          const isActive = currentMs >= token.fromMs && currentMs < token.toMs;
          return (
            <span
              key={`${currentPage.startMs}-${i}`}
              style={{
                fontSize: isActive ? 80 : 72,
                fontWeight: 900,
                fontFamily: "'Montserrat', system-ui, -apple-system, sans-serif",
                color: isActive ? color : "#FFFFFF",
                textTransform: "uppercase",
                textShadow: [
                  "0 0 8px rgba(0,0,0,0.6)",
                  "2px 2px 0 #000",
                  "-2px -2px 0 #000",
                  "2px -2px 0 #000",
                  "-2px 2px 0 #000",
                ].join(", "),
                letterSpacing: 1,
                lineHeight: 1.2,
                transition: "font-size 0.1s ease",
              }}
            >
              {token.text.trim()}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
```

**Step 2: Update `remotion/src/Root.tsx`**

In the `VideoProps` type, no change needed — `subtitles: SubtitleWord[]` already passes word data. The TikTokCaptions component converts internally.

**Step 3: Update `remotion/src/StockFootageVideo.tsx`**

Replace the AnimatedSubtitles import and usage:
- Line 15: Change `import { AnimatedSubtitles }` to `import { TikTokCaptions }`
- Lines 103-109: Replace `<AnimatedSubtitles ... />` with `<TikTokCaptions ... />`

**Step 4: Verify Remotion renders**

Run: `cd remotion && npx remotion studio src/index.ts`
- Open browser preview, check subtitles appear as word groups with background pill
- Verify accent color highlighting works
- Verify spring animation on group entrance

**Step 5: Commit**

```bash
git add remotion/src/TikTokCaptions.tsx remotion/src/StockFootageVideo.tsx
git commit -m "feat: replace single-word subtitles with TikTok-style word groups"
```

---

## Task 2: ASS Subtitle Safe Zone Fix (Gameplay Path)

Move subtitles from bottom (y=1550) to center (y=960) and update accent colors.

**Files:**
- Modify: `src/gold/pipeline/subtitles.py`

**Step 1: Update subtitle position and colors**

In `subtitles.py`, find `\pos(540,1550)` and change to `\pos(540,960)`.

Find `NICHE_ACCENT_COLORS` dict and ensure all 6 active niches have colors:
```python
NICHE_ACCENT_COLORS = {
    "true_crime": "&H002222FF",       # Deep red
    "ai_tools": "&H00FFCC00",         # Cyan
    "personal_finance": "&H0000D4FF", # Gold
    "english_learning": "&H0044CC00", # Green
    "reddit_stories": "&H000088FF",   # Orange
    "betrayal_revenge": "&H004444FF", # Dark red
}
```

Also update font size from 88 to 96 in the ASS Style definitions.

**Step 2: Test with a gameplay niche**

Run a quick subtitle generation for reddit_stories, inspect the .ass file:
- Verify `\pos(540,960)` appears
- Verify font size is 96
- Verify accent colors are correct

**Step 3: Commit**

```bash
git add src/gold/pipeline/subtitles.py
git commit -m "fix: move ASS subtitles to center safe zone, update colors and font size"
```

---

## Task 3: Hook Cards for Personal Finance & English Learning

Add niche-specific Remotion hook card designs for the two niches currently using the generic default card.

**Files:**
- Modify: `remotion/src/HookCard.tsx`

**Step 1: Add PersonalFinanceHookCard component**

Add inside HookCard.tsx after the TrueCrimeHookCard component (~line 539):

```tsx
/* ═══════════════════════════════════════════════════════════════════
   5. Personal Finance — "Money Alert" Card
   ═══════════════════════════════════════════════════════════════════ */

const PersonalFinanceHookCard: React.FC<HookCardProps & { duration: number }> = ({
  hookText,
  duration,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const exitOpacity = useExitFade(duration);

  const enterProgress = spring({
    frame,
    fps,
    config: { stiffness: 200, damping: 20, mass: 0.7 },
  });
  const scale = interpolate(enterProgress, [0, 1], [0.9, 1]);
  const enterOpacity = interpolate(enterProgress, [0, 1], [0, 1]);
  const opacity = enterOpacity * exitOpacity;

  const formattedText = hookText.replace(
    /(\$[\d,.]+[kKmM]?)/g,
    '<span style="color: #22c55e; font-size: 56px">$1</span>'
  );

  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", pointerEvents: "none" }}>
      <div
        style={{
          transform: `scale(${scale})`,
          opacity,
          width: "88%",
          background: "linear-gradient(135deg, rgba(5, 15, 5, 0.94) 0%, rgba(10, 25, 10, 0.94) 100%)",
          borderRadius: 16,
          overflow: "hidden",
          border: "1px solid rgba(34, 197, 94, 0.3)",
        }}
      >
        {/* Gold top bar */}
        <div
          style={{
            background: "linear-gradient(90deg, #fbbf24, #f59e0b)",
            padding: "10px 24px",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <span style={{ fontSize: 24 }}>💰</span>
          <span
            style={{
              fontSize: 24,
              fontWeight: 800,
              fontFamily: "system-ui, sans-serif",
              color: "#1a1408",
              letterSpacing: 3,
            }}
          >
            MONEY ALERT
          </span>
        </div>
        <div style={{ padding: "28px 36px" }}>
          <div
            style={{
              fontSize: 50,
              fontWeight: 800,
              fontFamily: "system-ui, sans-serif",
              color: "#ffffff",
              lineHeight: 1.25,
            }}
            dangerouslySetInnerHTML={{ __html: formattedText }}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};
```

**Step 2: Add EnglishLearningHookCard component**

```tsx
/* ═══════════════════════════════════════════════════════════════════
   6. English Learning — "Quick Lesson" Card
   ═══════════════════════════════════════════════════════════════════ */

const EnglishLearningHookCard: React.FC<HookCardProps & { duration: number }> = ({
  hookText,
  duration,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const exitOpacity = useExitFade(duration);

  const enterProgress = spring({
    frame,
    fps,
    config: { stiffness: 220, damping: 22, mass: 0.6 },
  });
  const translateY = interpolate(enterProgress, [0, 1], [-60, 0]);
  const enterOpacity = interpolate(enterProgress, [0, 1], [0, 1]);
  const opacity = enterOpacity * exitOpacity;

  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", pointerEvents: "none" }}>
      <div
        style={{
          transform: `translateY(${translateY}px)`,
          opacity,
          width: "88%",
          background: "linear-gradient(135deg, rgba(5, 25, 40, 0.94), rgba(10, 35, 50, 0.94))",
          borderRadius: 20,
          border: "2px solid rgba(52, 211, 153, 0.4)",
          overflow: "hidden",
        }}
      >
        {/* Teal header */}
        <div
          style={{
            background: "linear-gradient(90deg, #0d9488, #14b8a6)",
            padding: "10px 24px",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <span style={{ fontSize: 24 }}>💬</span>
          <span
            style={{
              fontSize: 24,
              fontWeight: 800,
              fontFamily: "system-ui, sans-serif",
              color: "#ffffff",
              letterSpacing: 2,
            }}
          >
            QUICK LESSON
          </span>
        </div>
        <div style={{ padding: "28px 36px" }}>
          <div
            style={{
              fontSize: 48,
              fontWeight: 800,
              fontFamily: "system-ui, sans-serif",
              color: "#ffffff",
              lineHeight: 1.3,
            }}
          >
            {hookText}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
```

**Step 3: Wire into switch statement**

In the `HookCard` component switch (line 30-39), add cases:
```tsx
case "personal_finance":
  return <PersonalFinanceHookCard {...props} duration={duration} />;
case "english_learning":
  return <EnglishLearningHookCard {...props} duration={duration} />;
```

**Step 4: Commit**

```bash
git add remotion/src/HookCard.tsx
git commit -m "feat: add hook cards for personal_finance and english_learning niches"
```

---

## Task 4: Progress Bar Component

Thin accent-colored bar at top of video showing playback progress.

**Files:**
- Create: `remotion/src/ProgressBar.tsx`
- Modify: `remotion/src/StockFootageVideo.tsx` (add component)
- Modify: `src/gold/utils/ffmpeg.py` (add for gameplay path)

**Step 1: Create `remotion/src/ProgressBar.tsx`**

```tsx
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

type ProgressBarProps = {
  accentColor: string;
};

export const ProgressBar: React.FC<ProgressBarProps> = ({ accentColor }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const progress = interpolate(frame, [0, durationInFrames], [0, 100], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: `${progress}%`,
          height: 4,
          backgroundColor: accentColor,
          opacity: 0.85,
        }}
      />
    </AbsoluteFill>
  );
};
```

**Step 2: Add to `StockFootageVideo.tsx`**

Import: `import { ProgressBar } from "./ProgressBar";`

Add before the closing `</AbsoluteFill>` (after music Audio):
```tsx
<ProgressBar accentColor={accentColor} />
```

**Step 3: Add FFmpeg drawbox for gameplay path**

In `src/gold/utils/ffmpeg.py`, in `compose_gameplay_video()`, after the CTA overlay filter chain and before subtitle burn-in, add a progress bar filter:

```python
# Progress bar: thin accent-colored line at top, grows left to right
progress_color = _get_niche_hex_color(niche_id) if niche_id else "0xFFCC00"
progress_filter = (
    f"drawbox=x=0:y=0:w='iw*t/{target_duration}':h=4:"
    f"color={progress_color}@0.85:t=fill"
)
```

Insert this into the filter chain at the appropriate point.

**Step 4: Commit**

```bash
git add remotion/src/ProgressBar.tsx remotion/src/StockFootageVideo.tsx src/gold/utils/ffmpeg.py
git commit -m "feat: add progress bar overlay to all videos"
```

---

## Task 5: Part Badge Component

"PART 2/3" badge in top-right corner for multi-part stories.

**Files:**
- Create: `remotion/src/PartBadge.tsx`
- Modify: `remotion/src/Root.tsx` (add partInfo to VideoProps)
- Modify: `remotion/src/StockFootageVideo.tsx` (render PartBadge)
- Modify: `src/gold/utils/remotion_renderer.py` (pass partInfo)
- Modify: `src/gold/utils/ffmpeg.py` (add drawtext for gameplay)
- Modify: `src/gold/pipeline/orchestrator.py` (detect part info from title)

**Step 1: Create `remotion/src/PartBadge.tsx`**

```tsx
import React from "react";
import { AbsoluteFill, spring, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

type PartBadgeProps = {
  partNumber: number;
  totalParts: number;
  accentColor: string;
};

export const PartBadge: React.FC<PartBadgeProps> = ({
  partNumber,
  totalParts,
  accentColor,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Slide in from right after 0.5s
  const delayFrames = Math.round(0.5 * fps);
  const localFrame = Math.max(0, frame - delayFrames);
  const enter = spring({
    frame: localFrame,
    fps,
    config: { stiffness: 200, damping: 22, mass: 0.6 },
  });
  const translateX = interpolate(enter, [0, 1], [120, 0]);
  const opacity = interpolate(enter, [0, 1], [0, 1]);

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          top: 60,
          right: 24,
          transform: `translateX(${translateX}px)`,
          opacity,
          backgroundColor: "rgba(0, 0, 0, 0.75)",
          border: `2px solid ${accentColor}`,
          borderRadius: 12,
          padding: "8px 16px",
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        <span
          style={{
            fontSize: 28,
            fontWeight: 900,
            fontFamily: "system-ui, sans-serif",
            color: accentColor,
          }}
        >
          PART {partNumber}
        </span>
        <span
          style={{
            fontSize: 22,
            fontWeight: 600,
            fontFamily: "system-ui, sans-serif",
            color: "rgba(255,255,255,0.6)",
          }}
        >
          /{totalParts}
        </span>
      </div>
    </AbsoluteFill>
  );
};
```

**Step 2: Update `Root.tsx` VideoProps**

Add to VideoProps type (after hookText):
```typescript
partNumber: number;
totalParts: number;
```

Add to defaultProps:
```typescript
partNumber: 0,
totalParts: 0,
```

**Step 3: Wire into `StockFootageVideo.tsx`**

Import: `import { PartBadge } from "./PartBadge";`

Destructure `partNumber` and `totalParts` from props.

Add after hook card, before subtitles:
```tsx
{partNumber > 0 && totalParts > 1 && (
  <PartBadge partNumber={partNumber} totalParts={totalParts} accentColor={accentColor} />
)}
```

**Step 4: Update `remotion_renderer.py`**

Add `part_number` and `total_parts` params to `render_stock_video()` function signature (default 0).

Add to the props dict:
```python
"partNumber": part_number,
"totalParts": total_parts,
```

**Step 5: Update `orchestrator.py`**

In the content generation flow, detect part info from the content title (e.g., "— Part 2" suffix) and pass to the renderer. Add a helper:

```python
import re

def _extract_part_info(title: str) -> tuple[int, int]:
    """Extract (part_number, total_parts) from title like '... — Part 2'."""
    match = re.search(r'Part\s+(\d+)(?:\s*/\s*(\d+))?', title, re.IGNORECASE)
    if match:
        part = int(match.group(1))
        total = int(match.group(2)) if match.group(2) else 3  # default 3 for multi-part
        return (part, total)
    return (0, 0)
```

**Step 6: Add FFmpeg drawtext for gameplay path**

In `compose_gameplay_video()`, add a `part_number` and `total_parts` parameter. If part_number > 0, add drawtext filter for the badge:

```python
if part_number and part_number > 0 and total_parts > 1:
    badge_text = f"PART {part_number}/{total_parts}"
    badge_filter = (
        f"drawtext=text='{badge_text}':fontfile={_FONTS_DIR}/Montserrat.ttf:"
        f"fontsize=36:fontcolor=white:borderw=3:bordercolor=black:"
        f"x=w-tw-30:y=60:enable='gte(t,0.5)'"
    )
    # Insert into filter chain
```

**Step 7: Commit**

```bash
git add remotion/src/PartBadge.tsx remotion/src/Root.tsx remotion/src/StockFootageVideo.tsx \
  src/gold/utils/remotion_renderer.py src/gold/utils/ffmpeg.py src/gold/pipeline/orchestrator.py
git commit -m "feat: add Part X/Y badge for multi-part stories"
```

---

## Task 6: Emoji Reactions Component

Pop emoji overlays at detected story beats.

**Files:**
- Create: `remotion/src/EmojiReaction.tsx`
- Modify: `remotion/src/Root.tsx` (add emojiBeats prop)
- Modify: `remotion/src/StockFootageVideo.tsx` (render emoji reactions)
- Modify: `src/gold/utils/remotion_renderer.py` (pass emoji data)
- Modify: `src/gold/pipeline/orchestrator.py` (detect beats from script)

**Step 1: Create `remotion/src/EmojiReaction.tsx`**

```tsx
import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
  Sequence,
} from "remotion";

type EmojiBeat = {
  emoji: string;
  timestampSec: number;
  x: number; // 0-100 percentage
  y: number; // 0-100 percentage
};

type EmojiReactionsProps = {
  beats: EmojiBeat[];
};

const EMOJI_DURATION_SEC = 1.2;

export const EmojiReactions: React.FC<EmojiReactionsProps> = ({ beats }) => {
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {beats.map((beat, i) => (
        <Sequence
          key={i}
          from={Math.round(beat.timestampSec * fps)}
          durationInFrames={Math.round(EMOJI_DURATION_SEC * fps)}
        >
          <SingleEmoji emoji={beat.emoji} x={beat.x} y={beat.y} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};

const SingleEmoji: React.FC<{ emoji: string; x: number; y: number }> = ({
  emoji,
  x,
  y,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Pop-in spring
  const pop = spring({
    frame,
    fps,
    config: { stiffness: 400, damping: 15, mass: 0.3 },
  });
  const scale = interpolate(pop, [0, 1], [0.2, 1.0]);

  // Fade out in last 0.3s
  const totalFrames = Math.round(EMOJI_DURATION_SEC * fps);
  const fadeOutStart = totalFrames - Math.round(0.3 * fps);
  const opacity =
    frame > fadeOutStart
      ? interpolate(frame, [fadeOutStart, totalFrames], [1, 0], {
          extrapolateRight: "clamp",
        })
      : interpolate(pop, [0, 1], [0, 1]);

  return (
    <div
      style={{
        position: "absolute",
        left: `${x}%`,
        top: `${y}%`,
        transform: `translate(-50%, -50%) scale(${scale})`,
        opacity,
        fontSize: 80,
        filter: "drop-shadow(0 4px 8px rgba(0,0,0,0.4))",
      }}
    >
      {emoji}
    </div>
  );
};
```

**Step 2: Update Root.tsx**

Add to VideoProps type:
```typescript
emojiBeats: Array<{ emoji: string; timestampSec: number; x: number; y: number }>;
```

Add to defaultProps:
```typescript
emojiBeats: [],
```

**Step 3: Wire into StockFootageVideo.tsx**

Import: `import { EmojiReactions } from "./EmojiReaction";`

Destructure `emojiBeats` from props.

Add after subtitles, before CTA:
```tsx
{emojiBeats.length > 0 && <EmojiReactions beats={emojiBeats} />}
```

**Step 4: Add beat detection in orchestrator**

In `orchestrator.py`, add a helper function:

```python
EMOJI_KEYWORDS = {
    "😱": ["shocking", "insane", "unbelievable", "crazy", "horrifying", "terrifying"],
    "💀": ["dead", "killed", "murder", "death", "dies", "fatal"],
    "🔥": ["fire", "viral", "exploded", "blew up", "incredible", "amazing"],
    "💰": ["money", "million", "thousand", "salary", "income", "profit", "rich", "wealth"],
    "😭": ["cried", "crying", "tears", "heartbreak", "devastating", "emotional"],
    "💡": ["discovered", "realized", "figured out", "breakthrough", "found"],
    "⚠️": ["warning", "danger", "careful", "risk", "scam", "fraud"],
}

def _detect_emoji_beats(
    script: str,
    subtitle_words: list[dict],
) -> list[dict]:
    """Detect emotional beats in script and map to emoji + timestamp."""
    import random
    beats = []
    script_lower = script.lower()

    for emoji, keywords in EMOJI_KEYWORDS.items():
        for kw in keywords:
            idx = script_lower.find(kw)
            if idx == -1:
                continue
            # Find the word timestamp closest to this position
            word_pos = len(script_lower[:idx].split())
            if word_pos < len(subtitle_words):
                ts = subtitle_words[word_pos]["start"]
                beats.append({
                    "emoji": emoji,
                    "timestampSec": round(ts, 2),
                    "x": random.randint(15, 85),
                    "y": random.randint(25, 45),
                })
            break  # one per emoji type

    # Limit to 4 max, spread out
    beats.sort(key=lambda b: b["timestampSec"])
    if len(beats) > 4:
        step = len(beats) / 4
        beats = [beats[int(i * step)] for i in range(4)]

    return beats
```

**Step 5: Pass emoji data to renderer**

In `remotion_renderer.py`, add `emoji_beats` param (default `[]`) and add to props dict:
```python
"emojiBeats": emoji_beats,
```

**Step 6: Commit**

```bash
git add remotion/src/EmojiReaction.tsx remotion/src/Root.tsx remotion/src/StockFootageVideo.tsx \
  src/gold/utils/remotion_renderer.py src/gold/pipeline/orchestrator.py
git commit -m "feat: add emoji reaction overlays at detected story beats"
```

---

## Task 7: Audio Post-Processing

Add FFmpeg EQ chain to polish TTS output.

**Files:**
- Modify: `src/gold/pipeline/audio.py`

**Step 1: Add post-processing function**

After `generate_voiceover()` returns, call a new method to apply EQ:

```python
async def _post_process_voice(self, audio_path: Path) -> Path:
    """Apply EQ and loudness normalization to TTS output."""
    from ..utils.ffmpeg import run_ffmpeg

    processed = audio_path.with_name(audio_path.stem + "_eq" + audio_path.suffix)
    await run_ffmpeg(
        "-i", str(audio_path),
        "-af", "highpass=f=80,lowpass=f=12000,loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(processed),
    )
    # Replace original
    processed.replace(audio_path)
    logger.info("[TTS] Post-processed audio: EQ + loudnorm applied")
    return audio_path
```

Call at the end of `generate_voiceover()`:
```python
await self._post_process_voice(output_path)
return output_path
```

**Step 2: Verify `run_ffmpeg` exists in ffmpeg.py**

Check that there's a utility function for running FFmpeg commands. If not, use `asyncio.create_subprocess_exec` directly.

**Step 3: Commit**

```bash
git add src/gold/pipeline/audio.py
git commit -m "feat: add audio post-processing EQ and loudnorm to TTS output"
```

---

## Task 8: Multi-Voice for Story Niches

Parse dialogue in scripts and route to different Fish Audio voices.

**Files:**
- Create: `src/gold/pipeline/multi_voice.py`
- Modify: `src/gold/pipeline/orchestrator.py` (wire for reddit/betrayal)
- Modify: `config/niches/reddit_stories.yaml` (add character voices)
- Modify: `config/niches/betrayal_revenge.yaml` (add character voices)

**Step 1: Create `src/gold/pipeline/multi_voice.py`**

```python
"""Multi-voice dialogue detection and TTS routing for story niches."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpeechSegment:
    text: str
    speaker: str  # "narrator", "male", "female"
    start_word_idx: int
    end_word_idx: int


# Patterns for dialogue detection
_QUOTE_PATTERN = re.compile(
    r"""(?:(?:she|her|mom|mother|wife|girlfriend|sister|daughter|aunt|grandma)\s+(?:said|replied|yelled|whispered|asked|screamed|told|cried|shouted))\s*[:\-,]?\s*["'](.+?)["']"""
    r"""|["'](.+?)["']\s*(?:she|her|mom|mother|wife|girlfriend|sister|daughter|aunt|grandma)\s+(?:said|replied|yelled|whispered|asked|screamed|told|cried|shouted)""",
    re.IGNORECASE | re.DOTALL,
)

_MALE_QUOTE = re.compile(
    r"""(?:(?:he|him|dad|father|husband|boyfriend|brother|son|uncle|grandpa|boss|guy|man)\s+(?:said|replied|yelled|whispered|asked|screamed|told|cried|shouted))\s*[:\-,]?\s*["'](.+?)["']"""
    r"""|["'](.+?)["']\s*(?:he|him|dad|father|husband|boyfriend|brother|son|uncle|grandpa|boss|guy|man)\s+(?:said|replied|yelled|whispered|asked|screamed|told|cried|shouted)""",
    re.IGNORECASE | re.DOTALL,
)


def detect_dialogue(script: str) -> list[SpeechSegment]:
    """Split a script into narrator and character speech segments.

    Returns ordered list of SpeechSegment with speaker assignments.
    Simple approach: find quoted dialogue attributed to gendered characters,
    everything else is narrator.
    """
    segments: list[SpeechSegment] = []
    words = script.split()

    # Find all dialogue positions
    dialogue_spans: list[tuple[int, int, str]] = []  # (char_start, char_end, speaker)

    for match in _QUOTE_PATTERN.finditer(script):
        quote = match.group(1) or match.group(2)
        if quote:
            start = script.find(quote, match.start())
            dialogue_spans.append((start, start + len(quote), "female"))

    for match in _MALE_QUOTE.finditer(script):
        quote = match.group(1) or match.group(2)
        if quote:
            start = script.find(quote, match.start())
            dialogue_spans.append((start, start + len(quote), "male"))

    # Sort by position
    dialogue_spans.sort(key=lambda s: s[0])

    if not dialogue_spans:
        # No dialogue detected — single narrator
        return [SpeechSegment(text=script, speaker="narrator", start_word_idx=0, end_word_idx=len(words))]

    # Build segments: narrator between dialogues, character during
    result: list[SpeechSegment] = []
    last_end = 0

    for char_start, char_end, speaker in dialogue_spans:
        # Narrator segment before this dialogue
        narrator_text = script[last_end:char_start].strip()
        if narrator_text:
            n_start = len(script[:last_end].split())
            n_end = len(script[:char_start].split())
            result.append(SpeechSegment(
                text=narrator_text, speaker="narrator",
                start_word_idx=n_start, end_word_idx=n_end,
            ))

        # Character dialogue
        d_start = len(script[:char_start].split())
        d_end = len(script[:char_end].split())
        result.append(SpeechSegment(
            text=script[char_start:char_end],
            speaker=speaker,
            start_word_idx=d_start, end_word_idx=d_end,
        ))
        last_end = char_end

    # Trailing narrator
    if last_end < len(script):
        trailing = script[last_end:].strip()
        if trailing:
            result.append(SpeechSegment(
                text=trailing, speaker="narrator",
                start_word_idx=len(script[:last_end].split()),
                end_word_idx=len(words),
            ))

    return result
```

**Step 2: Add character voice IDs to niche configs**

In `config/niches/reddit_stories.yaml`, add:
```yaml
character_voices:
  male: "e58b0d7efbe04e6e87a14c3452e7b4a9"    # Fish Audio male narrator
  female: "a0e99dbb5a5c48d2b25f944b23d09853"  # Fish Audio female narrator
```

Same for `betrayal_revenge.yaml`.

Note: These are placeholder voice IDs — the actual Fish Audio voice IDs should be selected from Fish Audio's voice library for natural-sounding male/female narrators.

**Step 3: Wire into orchestrator**

In `orchestrator.py`, for reddit_stories and betrayal_revenge niches:
1. Call `detect_dialogue(script)` to get segments
2. If segments have multiple speakers, generate TTS per segment
3. Concatenate audio files with FFmpeg
4. Use combined audio for subtitle timing

This is the most complex upgrade and may need iteration.

**Step 4: Commit**

```bash
git add src/gold/pipeline/multi_voice.py config/niches/reddit_stories.yaml \
  config/niches/betrayal_revenge.yaml src/gold/pipeline/orchestrator.py
git commit -m "feat: add multi-voice dialogue for reddit and betrayal story niches"
```

---

## Integration Test

After all tasks, run a test generation for one niche per rendering path:

```bash
# Stock footage path (Remotion)
python -c "
from gold.pipeline.orchestrator import ContentPipeline
from gold.config import Config
import asyncio

async def test():
    config = Config()
    pipeline = ContentPipeline(config)
    content = await pipeline.generate_content('ai_tools', 'ai_tools')
    print(f'Generated: {content.id} - {content.title}')

asyncio.run(test())
"

# Gameplay path (FFmpeg) — reddit
python -c "
from gold.pipeline.orchestrator import ContentPipeline
from gold.config import Config
import asyncio

async def test():
    config = Config()
    pipeline = ContentPipeline(config)
    content = await pipeline.generate_content('reddit_stories', 'reddit_stories')
    print(f'Generated: {content.id} - {content.title}')

asyncio.run(test())
"
```

Inspect the output videos:
- [ ] Subtitles appear as 2-3 word groups (not single word)
- [ ] Subtitles are centered vertically (not at bottom)
- [ ] Background pill behind subtitle text
- [ ] Accent color highlighting on active word
- [ ] Spring bounce animation on word group entrance
- [ ] Hook card renders for all niches
- [ ] Progress bar visible at top
- [ ] Part badge shows for multi-part content
- [ ] Emoji reactions pop at story beats
- [ ] Audio sounds clear (no rumble, normalized loudness)
- [ ] Multi-voice works for reddit stories (if dialogue detected)
