import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { SubtitleWord } from "./Root";

type AnimatedSubtitlesProps = {
  subtitles: SubtitleWord[];
  accentColor: string;
  nicheId: string;
};

/**
 * Single-word-at-a-time captions — matches the Reddit/TikTok viral style.
 * One big uppercase word, centered near the bottom, Impact font, thick outline.
 *
 * Each word stays on screen for at least MIN_WORD_DURATION seconds,
 * even if Whisper timestamps are shorter, so captions feel readable
 * rather than flickering.
 */

const MIN_WORD_DURATION = 0.35; // seconds — minimum time each word stays visible

export const AnimatedSubtitles: React.FC<AnimatedSubtitlesProps> = ({
  subtitles,
  accentColor,
  nicheId,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;

  // Find the current word being spoken, with minimum display time enforced
  let currentWord: SubtitleWord | null = null;
  for (let i = 0; i < subtitles.length; i++) {
    const wordEnd = Math.max(subtitles[i].end, subtitles[i].start + MIN_WORD_DURATION);
    // Clamp extended end so it doesn't overlap next word's start
    const clampedEnd =
      i < subtitles.length - 1
        ? Math.min(wordEnd, subtitles[i + 1].start)
        : wordEnd;

    if (currentTime >= subtitles[i].start && currentTime <= clampedEnd) {
      currentWord = subtitles[i];
      break;
    }
    // Between words — show the last spoken word briefly
    if (
      i < subtitles.length - 1 &&
      currentTime > clampedEnd &&
      currentTime < subtitles[i + 1].start
    ) {
      // Only show between-word if gap is small (< 0.4s)
      if (subtitles[i + 1].start - clampedEnd < 0.4) {
        currentWord = subtitles[i];
      }
      break;
    }
  }

  if (!currentWord) return null;

  // Pop-in spring animation — slightly slower for readability
  const wordFrame = Math.max(0, frame - Math.round(currentWord.start * fps));
  const pop = spring({
    frame: wordFrame,
    fps,
    config: { stiffness: 260, damping: 20, mass: 0.5 },
  });
  const scale = interpolate(pop, [0, 1], [0.7, 1.0]);
  const opacity = interpolate(pop, [0, 1], [0, 1]);

  // Niche-specific accent for variety
  const color = getNicheColor(nicheId, accentColor);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 200,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          transform: `scale(${scale})`,
          opacity,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        <span
          style={{
            fontSize: 90,
            fontWeight: 900,
            fontFamily: "Impact, 'Arial Black', sans-serif",
            color: color,
            textTransform: "uppercase",
            textAlign: "center",
            // Thick outline via text-shadow (matches ASS bord=5 style)
            textShadow: [
              "0 0 10px rgba(0,0,0,0.8)",
              "3px 3px 0 #000",
              "-3px -3px 0 #000",
              "3px -3px 0 #000",
              "-3px 3px 0 #000",
              "0 3px 0 #000",
              "3px 0 0 #000",
              "0 -3px 0 #000",
              "-3px 0 0 #000",
            ].join(", "),
            letterSpacing: 2,
            lineHeight: 1.1,
            maxWidth: "90%",
            display: "inline-block",
          }}
        >
          {currentWord.word}
        </span>
      </div>
    </AbsoluteFill>
  );
};

function getNicheColor(nicheId: string, accentColor: string): string {
  switch (nicheId) {
    case "crypto_finance":
      return "#22c55e";
    case "ai_tools":
      return "#60a5fa";
    case "true_crime":
      return "#f87171";
    default:
      return "#FFFFFF";
  }
}
