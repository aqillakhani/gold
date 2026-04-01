import React, { useMemo } from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { SubtitleWord } from "./Root";

type TikTokCaptionsProps = {
  subtitles: SubtitleWord[];
  accentColor: string;
  nicheId: string;
};

/**
 * TikTok-style captions: 3-word groups, spring animation, pill background.
 * Active word highlighted in niche accent color.
 * Manually groups words into chunks of 3 (not using createTikTokStyleCaptions
 * which over-combines in continuous speech).
 */

const WORDS_PER_GROUP = 3;

type WordGroup = {
  words: SubtitleWord[];
  startSec: number;
  endSec: number;
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

  // Group words into chunks of 3
  const groups: WordGroup[] = useMemo(() => {
    const result: WordGroup[] = [];
    for (let i = 0; i < subtitles.length; i += WORDS_PER_GROUP) {
      const chunk = subtitles.slice(i, i + WORDS_PER_GROUP);
      if (chunk.length > 0) {
        result.push({
          words: chunk,
          startSec: chunk[0].start,
          endSec: chunk[chunk.length - 1].end,
        });
      }
    }
    return result;
  }, [subtitles]);

  // Find the current group
  let currentGroup: WordGroup | null = null;
  for (const group of groups) {
    if (currentTime >= group.startSec && currentTime < group.endSec + 0.1) {
      currentGroup = group;
      break;
    }
  }

  if (!currentGroup) return null;

  // Find active word within the group
  let activeIdx = 0;
  for (let i = 0; i < currentGroup.words.length; i++) {
    if (
      currentTime >= currentGroup.words[i].start &&
      currentTime < currentGroup.words[i].end
    ) {
      activeIdx = i;
      break;
    }
  }

  // Spring animation for group entrance
  const groupStartFrame = Math.round(currentGroup.startSec * fps);
  const localFrame = Math.max(0, frame - groupStartFrame);
  const pop = spring({
    frame: localFrame,
    fps,
    config: { stiffness: 300, damping: 18, mass: 0.4 },
  });
  const scale = interpolate(pop, [0, 1], [0.75, 1.0]);
  const opacity = interpolate(pop, [0, 1], [0, 1]);

  const color = NICHE_COLORS[nicheId] || accentColor || "#FFFFFF";

  // During hook card (first 4s), shift subtitles to lower third to avoid overlap
  const hookCardDuration = 4;
  const isHookActive = currentTime < hookCardDuration;
  const verticalPosition = isHookActive ? "flex-end" as const : "center" as const;
  const bottomPad = isHookActive ? 180 : 0;

  return (
    <AbsoluteFill
      style={{
        justifyContent: verticalPosition,
        alignItems: "center",
        paddingBottom: bottomPad,
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
          backgroundColor: "rgba(0, 0, 0, 0.65)",
          borderRadius: 16,
          padding: "10px 20px",
          maxWidth: "85%",
        }}
      >
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            gap: "10px",
            alignItems: "baseline",
          }}
        >
          {currentGroup.words.map((word, idx) => {
            const isActive = idx === activeIdx;
            return (
              <span
                key={`${groupStartFrame}-${idx}`}
                style={{
                  fontSize: isActive ? 56 : 48,
                  fontWeight: 900,
                  fontFamily:
                    "'Montserrat', system-ui, -apple-system, sans-serif",
                  color: isActive ? color : "#FFFFFF",
                  textTransform: "uppercase",
                  textAlign: "center",
                  textShadow: [
                    "0 0 8px rgba(0,0,0,0.6)",
                    "2px 2px 0 #000",
                    "-2px -2px 0 #000",
                    "2px -2px 0 #000",
                    "-2px 2px 0 #000",
                  ].join(", "),
                  letterSpacing: 1,
                  lineHeight: 1.2,
                  display: "inline-block",
                }}
              >
                {word.word}
              </span>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
