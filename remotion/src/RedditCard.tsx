import React, { useMemo } from "react";
import {
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { SubtitleWord } from "./Root";

type RedditCardProps = {
  subtitles: SubtitleWord[];
  hookText: string;
  subreddit: string;
  accentColor: string;
};

/**
 * Reddit-style post card that reveals text progressively as the narrator reads.
 *
 * - Mimics a real Reddit post: avatar, subreddit, username, awards
 * - Title shown immediately (bold, large)
 * - Body text appears line-by-line as narrator reads
 * - Currently-spoken word highlighted in yellow
 * - Card grows downward as more text is revealed
 */
export const RedditCard: React.FC<RedditCardProps> = ({
  subtitles,
  hookText,
  subreddit,
  accentColor,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;

  // Card entrance animation
  const entrance = spring({
    frame,
    fps,
    config: { stiffness: 200, damping: 22, mass: 0.6 },
  });
  const cardY = interpolate(entrance, [0, 1], [-40, 0]);
  const cardOpacity = interpolate(entrance, [0, 1], [0, 1]);

  // Split hookText into title words for initial display
  const titleWords = hookText.split(/\s+/).filter(Boolean);

  // Find which subtitle words have been reached (progressive reveal)
  const revealedUpTo = useMemo(() => {
    for (let i = subtitles.length - 1; i >= 0; i--) {
      if (currentTime >= subtitles[i].start) {
        return i;
      }
    }
    return -1;
  }, [currentTime, subtitles]);

  // Find the currently active word
  let activeWordIdx = -1;
  for (let i = 0; i < subtitles.length; i++) {
    if (currentTime >= subtitles[i].start && currentTime < subtitles[i].end + 0.05) {
      activeWordIdx = i;
      break;
    }
  }

  // Group revealed words into lines (~8 words per line for readability)
  const WORDS_PER_LINE = 8;
  const revealedWords = subtitles.slice(0, revealedUpTo + 1);

  const lines: SubtitleWord[][] = useMemo(() => {
    const result: SubtitleWord[][] = [];
    for (let i = 0; i < revealedWords.length; i += WORDS_PER_LINE) {
      result.push(revealedWords.slice(i, i + WORDS_PER_LINE));
    }
    return result;
  }, [revealedWords.length]);

  const HIGHLIGHT_COLOR = "#FFD700"; // yellow — matches example video

  // Estimate max card height so we can position it centered at full expansion
  // Header (~80px) + Awards (~30px) + Title (~120px) + Body lines + Padding (~60px)
  const avgWordsPerLine = 9;
  const lineHeightPx = 48; // 32px font * 1.5 line-height
  const totalLines = Math.ceil(subtitles.length / avgWordsPerLine);
  const bodyHeight = totalLines * lineHeightPx;
  const headerHeight = 80 + 30 + 120; // avatar row + awards + title
  const cardPadding = 60;
  const maxCardHeight = headerHeight + bodyHeight + cardPadding;

  // Fixed top: card will be centered when fully expanded
  const screenHeight = 1920;
  const fixedTop = Math.max(40, (screenHeight - maxCardHeight) / 2);

  return (
    <div
      style={{
        position: "absolute",
        top: fixedTop,
        left: 30,
        right: 30,
        transform: `translateY(${cardY}px)`,
        opacity: cardOpacity,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(15, 15, 15, 0.88)",
          borderRadius: 16,
          padding: "18px 22px",
          maxHeight: 1400,
          overflow: "hidden",
        }}
      >
        {/* Reddit header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            marginBottom: 6,
          }}
        >
          {/* Reddit avatar */}
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 18,
              backgroundColor: "#FF4500",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 20,
            }}
          >
            😤
          </div>
          <span
            style={{
              fontFamily: "'Montserrat', sans-serif",
              fontWeight: 700,
              fontSize: 24,
              color: "#FFFFFF",
            }}
          >
            r/{subreddit}
          </span>
          <span
            style={{
              fontFamily: "'Montserrat', sans-serif",
              fontSize: 18,
              color: "#888888",
            }}
          >
            · u/User · 5h
          </span>
        </div>

        {/* Award emojis */}
        <div style={{ fontSize: 20, marginBottom: 10 }}>💰 🤯 👑</div>

        {/* Title (always visible, bold) */}
        <div
          style={{
            fontFamily: "'Montserrat', sans-serif",
            fontWeight: 800,
            fontSize: 40,
            color: "#FFFFFF",
            lineHeight: 1.3,
            marginBottom: 14,
          }}
        >
          {titleWords.map((word, idx) => {
            // Highlight last word in title with accent color
            const isAccent = idx === titleWords.length - 1;
            return (
              <span key={idx}>
                <span style={{ color: isAccent ? HIGHLIGHT_COLOR : "#FFFFFF" }}>
                  {word}
                </span>
                {" "}
              </span>
            );
          })}
        </div>

        {/* Body text — revealed progressively, active word highlighted */}
        <div
          style={{
            fontFamily: "'Montserrat', sans-serif",
            fontWeight: 400,
            fontSize: 32,
            lineHeight: 1.5,
            color: "#DDDDDD",
            width: "100%",
          }}
        >
          {revealedWords.map((wordObj, idx) => {
            const isActive = idx === activeWordIdx;
            return (
              <span key={idx}>
                <span
                  style={{
                    color: isActive ? HIGHLIGHT_COLOR : "#DDDDDD",
                    fontWeight: isActive ? 700 : 400,
                  }}
                >
                  {wordObj.word}
                </span>
                {" "}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
};
