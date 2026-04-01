import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

type HookCardProps = {
  hookText: string;
  nicheId: string;
  accentColor: string;
  /** How long the card is visible in seconds (default 4) */
  duration?: number;
};

/**
 * Opening hook card shown for the first few seconds of the video.
 * Dispatches to niche-specific sub-components for unique visual styles.
 */
export const HookCard: React.FC<HookCardProps> = (props) => {
  const { hookText, nicheId, duration = 4 } = props;
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;

  if (currentTime > duration || !hookText) return null;

  switch (nicheId) {
    case "ai_tools":
      return <AiToolsHookCard {...props} duration={duration} />;
    case "crypto_finance":
      return <CryptoHookCard {...props} duration={duration} />;
    case "true_crime":
      return <TrueCrimeHookCard {...props} duration={duration} />;
    case "personal_finance":
      return <PersonalFinanceHookCard {...props} duration={duration} />;
    case "english_learning":
      return <EnglishLearningHookCard {...props} duration={duration} />;
    default:
      return <DefaultHookCard {...props} duration={duration} />;
  }
};

/* ─── Shared exit fade helper ─── */

function useExitFade(duration: number) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;
  const exitStart = duration - 0.8;
  return currentTime > exitStart
    ? interpolate(currentTime, [exitStart, duration], [1, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 1;
}

/* ═══════════════════════════════════════════════════════════════════
   1. AI Tools — "Tech Terminal" Card
   ═══════════════════════════════════════════════════════════════════ */

const AiToolsHookCard: React.FC<HookCardProps & { duration: number }> = ({
  hookText,
  duration,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const exitOpacity = useExitFade(duration);

  // Entrance: fade + scale in
  const enterProgress = spring({
    frame,
    fps,
    config: { stiffness: 180, damping: 22, mass: 0.8 },
  });
  const scale = interpolate(enterProgress, [0, 1], [0.92, 1]);
  const enterOpacity = interpolate(enterProgress, [0, 1], [0, 1]);
  const opacity = enterOpacity * exitOpacity;

  // Typewriter: reveal characters over 1.5s
  const typewriterEnd = 1.5 * fps;
  const charsToShow = Math.floor(
    interpolate(frame, [10, typewriterEnd], [0, hookText.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );
  const visibleText = hookText.slice(0, charsToShow);
  const showCursor = frame % Math.round(fps * 0.6) < Math.round(fps * 0.3);

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
          width: "88%",
          backgroundColor: "rgba(5, 10, 30, 0.92)",
          borderRadius: 12,
          padding: "36px 40px",
          border: "1px solid rgba(59, 130, 246, 0.5)",
          position: "relative",
          overflow: "hidden",
        }}
      >
        {/* Scan-line overlay */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            backgroundImage:
              "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(59, 130, 246, 0.03) 2px, rgba(59, 130, 246, 0.03) 4px)",
            pointerEvents: "none",
          }}
        />

        {/* Corner brackets */}
        {cornerBracket("top-left", "#3b82f6")}
        {cornerBracket("top-right", "#3b82f6")}
        {cornerBracket("bottom-left", "#3b82f6")}
        {cornerBracket("bottom-right", "#3b82f6")}

        {/* Circuit pattern — decorative SVG in top-right */}
        <svg
          width="80"
          height="80"
          viewBox="0 0 80 80"
          style={{
            position: "absolute",
            top: 12,
            right: 12,
            opacity: 0.12,
          }}
        >
          <path
            d="M10 40h20M40 10v20M40 50v20M50 40h20M30 30l-10-10M50 30l10-10M30 50l-10 10M50 50l10 10"
            stroke="#3b82f6"
            strokeWidth="2"
            fill="none"
          />
          <circle cx="40" cy="40" r="4" fill="#3b82f6" />
          <circle cx="10" cy="40" r="2" fill="#3b82f6" />
          <circle cx="70" cy="40" r="2" fill="#3b82f6" />
          <circle cx="40" cy="10" r="2" fill="#3b82f6" />
          <circle cx="40" cy="70" r="2" fill="#3b82f6" />
        </svg>

        {/* Label */}
        <div
          style={{
            fontSize: 26,
            fontWeight: 700,
            fontFamily: "'Courier New', monospace",
            color: "#3b82f6",
            letterSpacing: 2,
            textShadow: "0 0 12px rgba(59, 130, 246, 0.6)",
            marginBottom: 16,
          }}
        >
          {">"} DISCOVERY_{showCursor ? "█" : " "}
        </div>

        {/* Hook text — typewriter */}
        <div
          style={{
            fontSize: 48,
            fontWeight: 700,
            fontFamily: "'Courier New', monospace",
            color: "#ffffff",
            lineHeight: 1.3,
            textAlign: "left",
            minHeight: 130,
          }}
        >
          {visibleText}
          {charsToShow < hookText.length && (
            <span style={{ opacity: showCursor ? 1 : 0 }}>▌</span>
          )}
        </div>
      </div>
    </AbsoluteFill>
  );
};

function cornerBracket(
  position: "top-left" | "top-right" | "bottom-left" | "bottom-right",
  color: string
) {
  const size = 18;
  const thickness = 2;
  const offset = 6;

  const isTop = position.includes("top");
  const isLeft = position.includes("left");

  return (
    <div
      style={{
        position: "absolute",
        top: isTop ? offset : undefined,
        bottom: !isTop ? offset : undefined,
        left: isLeft ? offset : undefined,
        right: !isLeft ? offset : undefined,
        width: size,
        height: size,
        borderColor: color,
        borderStyle: "solid",
        borderWidth: 0,
        borderTopWidth: isTop ? thickness : 0,
        borderBottomWidth: !isTop ? thickness : 0,
        borderLeftWidth: isLeft ? thickness : 0,
        borderRightWidth: !isLeft ? thickness : 0,
        pointerEvents: "none",
      }}
    />
  );
}

/* ═══════════════════════════════════════════════════════════════════
   2. Crypto Finance — "Trading Alert" Ticker Card
   ═══════════════════════════════════════════════════════════════════ */

const CryptoHookCard: React.FC<HookCardProps & { duration: number }> = ({
  hookText,
  duration,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const exitOpacity = useExitFade(duration);

  // Slide in from right
  const enterProgress = spring({
    frame,
    fps,
    config: { stiffness: 160, damping: 20, mass: 0.8 },
  });
  const translateX = interpolate(enterProgress, [0, 1], [400, 0]);
  const enterOpacity = interpolate(enterProgress, [0, 1], [0, 1]);
  const opacity = enterOpacity * exitOpacity;

  // Pulsing alert banner (sine wave on opacity)
  const pulseOpacity = interpolate(
    Math.sin((frame / fps) * Math.PI * 3),
    [-1, 1],
    [0.6, 1]
  );

  // Ticker line draw progress (over 2s)
  const tickerProgress = interpolate(frame, [15, 2 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Highlight numbers in green
  const formattedText = highlightNumbers(hookText);

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
          transform: `translateX(${translateX}px)`,
          opacity,
          width: "88%",
          backgroundColor: "rgba(5, 15, 10, 0.94)",
          borderRadius: 12,
          overflow: "hidden",
          position: "relative",
        }}
      >
        {/* Decorative candlestick background pattern */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            backgroundImage: `
              linear-gradient(90deg, transparent 48px, rgba(34, 197, 94, 0.04) 48px, rgba(34, 197, 94, 0.04) 50px, transparent 50px),
              linear-gradient(90deg, transparent 98px, rgba(239, 68, 68, 0.04) 98px, rgba(239, 68, 68, 0.04) 100px, transparent 100px),
              linear-gradient(90deg, transparent 148px, rgba(34, 197, 94, 0.04) 148px, rgba(34, 197, 94, 0.04) 150px, transparent 150px),
              linear-gradient(90deg, transparent 198px, rgba(34, 197, 94, 0.04) 198px, rgba(34, 197, 94, 0.04) 200px, transparent 200px)
            `,
            pointerEvents: "none",
          }}
        />

        {/* Left accent bar */}
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            bottom: 0,
            width: 5,
            background: "linear-gradient(180deg, #22c55e 0%, #ef4444 100%)",
          }}
        />

        {/* Red alert banner */}
        <div
          style={{
            backgroundColor: "rgba(220, 38, 38, 0.9)",
            padding: "10px 24px 10px 20px",
            display: "flex",
            alignItems: "center",
            gap: 10,
            opacity: pulseOpacity,
          }}
        >
          <span style={{ fontSize: 24 }}>⚡</span>
          <span
            style={{
              fontSize: 24,
              fontWeight: 800,
              fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif",
              color: "#ffffff",
              letterSpacing: 3,
            }}
          >
            MARKET ALERT
          </span>
        </div>

        {/* Body */}
        <div style={{ padding: "24px 36px 20px 20px" }}>
          {/* Hook text with green numbers */}
          <div
            style={{
              fontSize: 50,
              fontWeight: 800,
              fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif",
              color: "#ffffff",
              lineHeight: 1.25,
              textAlign: "left",
            }}
            dangerouslySetInnerHTML={{ __html: formattedText }}
          />

          {/* Animated ticker line */}
          <svg
            width="100%"
            height="40"
            viewBox="0 0 600 40"
            style={{ marginTop: 16, opacity: 0.6 }}
            preserveAspectRatio="none"
          >
            <path
              d="M0 30 L60 28 L120 20 L180 22 L240 12 L300 15 L360 8 L420 10 L480 5 L540 8 L600 2"
              stroke="#22c55e"
              strokeWidth="2.5"
              fill="none"
              strokeDasharray="800"
              strokeDashoffset={interpolate(tickerProgress, [0, 1], [800, 0])}
            />
          </svg>
        </div>
      </div>
    </AbsoluteFill>
  );
};

function highlightNumbers(text: string): string {
  return text.replace(
    /(\$?\d[\d,.]*%?)/g,
    '<span style="color: #22c55e">$1</span>'
  );
}

/* ═══════════════════════════════════════════════════════════════════
   3. True Crime — "Case File" Document Card
   ═══════════════════════════════════════════════════════════════════ */

const TrueCrimeHookCard: React.FC<HookCardProps & { duration: number }> = ({
  hookText,
  duration,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const exitOpacity = useExitFade(duration);

  // Stamp-in: scale from 1.3 → 1.0 with heavy spring
  const stampProgress = spring({
    frame,
    fps,
    config: { stiffness: 300, damping: 15, mass: 1.2 },
  });
  const scale = interpolate(stampProgress, [0, 1], [1.35, 1]);
  const enterOpacity = interpolate(stampProgress, [0, 1], [0, 1]);
  const opacity = enterOpacity * exitOpacity;

  // Slight rotation settle
  const rotation = interpolate(stampProgress, [0, 1], [-3, 0]);

  // Pseudo-random case number from hook text length
  const caseNum = String(
    ((hookText.length * 7919 + 100000) % 900000) + 100000
  );

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
          transform: `scale(${scale}) rotate(${rotation}deg)`,
          opacity,
          width: "86%",
          position: "relative",
          // Aged paper texture via CSS gradients
          background: `
            linear-gradient(135deg, #f5f0e1 0%, #ede4cc 40%, #e8dfc4 70%, #f0e8d0 100%)
          `,
          borderRadius: 4,
          padding: "36px 40px 44px",
          // Paper edge shadow
          boxShadow:
            "4px 4px 20px rgba(0, 0, 0, 0.5), inset 0 0 40px rgba(139, 119, 80, 0.15)",
        }}
      >
        {/* Paper texture noise overlay */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            backgroundImage:
              "radial-gradient(ellipse at 20% 50%, rgba(139, 119, 80, 0.08) 0%, transparent 70%)",
            pointerEvents: "none",
          }}
        />

        {/* CLASSIFIED watermark — diagonal */}
        <div
          style={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%) rotate(-25deg)",
            fontSize: 90,
            fontWeight: 900,
            fontFamily: "'Courier New', monospace",
            color: "rgba(200, 30, 30, 0.08)",
            letterSpacing: 14,
            whiteSpace: "nowrap",
            pointerEvents: "none",
          }}
        >
          UNSOLVED
        </div>

        {/* CASE FILE stamp */}
        <div
          style={{
            display: "inline-block",
            border: "3px solid #c41e1e",
            borderRadius: 4,
            padding: "4px 18px",
            transform: "rotate(-2deg)",
            marginBottom: 12,
          }}
        >
          <span
            style={{
              fontSize: 30,
              fontWeight: 900,
              fontFamily: "'Courier New', monospace",
              color: "#c41e1e",
              letterSpacing: 4,
            }}
          >
            CASE FILE
          </span>
        </div>

        {/* Case number */}
        <div
          style={{
            fontSize: 20,
            fontWeight: 600,
            fontFamily: "'Courier New', monospace",
            color: "#5a4a32",
            letterSpacing: 2,
            marginBottom: 20,
          }}
        >
          CASE #{caseNum}
        </div>

        {/* Hook text — typewriter serif on paper */}
        <div
          style={{
            fontSize: 46,
            fontWeight: 700,
            fontFamily: "Georgia, 'Times New Roman', serif",
            color: "#1a1408",
            lineHeight: 1.35,
            textAlign: "left",
          }}
        >
          {hookText}
        </div>

        {/* Redaction bars — decorative */}
        <div style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 8 }}>
          <div
            style={{
              width: "70%",
              height: 16,
              backgroundColor: "#1a1408",
              borderRadius: 1,
              opacity: 0.85,
            }}
          />
          <div
            style={{
              width: "45%",
              height: 16,
              backgroundColor: "#1a1408",
              borderRadius: 1,
              opacity: 0.85,
            }}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};

/* ═══════════════════════════════════════════════════════════════════
   4. Personal Finance — "Money Alert" Card
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

  // Highlight dollar amounts in green
  const formattedText = hookText.replace(
    /(\$[\d,.]+[kKmM]?)/g,
    '<span style="color: #22c55e; font-size: 56px">$1</span>'
  );

  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", pointerEvents: "none" }}>
      <div style={{
        transform: `scale(${scale})`,
        opacity,
        width: "88%",
        background: "linear-gradient(135deg, rgba(5, 15, 5, 0.94) 0%, rgba(10, 25, 10, 0.94) 100%)",
        borderRadius: 16,
        overflow: "hidden",
        border: "1px solid rgba(34, 197, 94, 0.3)",
      }}>
        {/* Gold top bar */}
        <div style={{
          background: "linear-gradient(90deg, #fbbf24, #f59e0b)",
          padding: "10px 24px",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}>
          <span style={{ fontSize: 28, fontWeight: 800, fontFamily: "system-ui, sans-serif", color: "#1a1408", letterSpacing: 3 }}>
            MONEY ALERT
          </span>
        </div>
        <div style={{ padding: "28px 36px" }}>
          <div style={{
            fontSize: 50,
            fontWeight: 800,
            fontFamily: "system-ui, sans-serif",
            color: "#ffffff",
            lineHeight: 1.25,
          }} dangerouslySetInnerHTML={{ __html: formattedText }} />
        </div>
      </div>
    </AbsoluteFill>
  );
};

/* ═══════════════════════════════════════════════════════════════════
   5. English Learning — "Quick Lesson" Card
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
      <div style={{
        transform: `translateY(${translateY}px)`,
        opacity,
        width: "88%",
        background: "linear-gradient(135deg, rgba(5, 25, 40, 0.94), rgba(10, 35, 50, 0.94))",
        borderRadius: 20,
        border: "2px solid rgba(52, 211, 153, 0.4)",
        overflow: "hidden",
      }}>
        <div style={{
          background: "linear-gradient(90deg, #0d9488, #14b8a6)",
          padding: "10px 24px",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}>
          <span style={{ fontSize: 28, fontWeight: 800, fontFamily: "system-ui, sans-serif", color: "#ffffff", letterSpacing: 2 }}>
            QUICK LESSON
          </span>
        </div>
        <div style={{ padding: "28px 36px" }}>
          <div style={{
            fontSize: 48,
            fontWeight: 800,
            fontFamily: "system-ui, sans-serif",
            color: "#ffffff",
            lineHeight: 1.3,
          }}>
            {hookText}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

/* ═══════════════════════════════════════════════════════════════════
   6. Default / Reddit Stories — original generic card
   ═══════════════════════════════════════════════════════════════════ */

const DefaultHookCard: React.FC<HookCardProps & { duration: number }> = ({
  hookText,
  nicheId,
  accentColor,
  duration,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const exitOpacity = useExitFade(duration);

  const enterProgress = spring({
    frame,
    fps,
    config: { stiffness: 180, damping: 22, mass: 0.8 },
  });

  const translateY = interpolate(enterProgress, [0, 1], [80, 0]);
  const enterOpacity = interpolate(enterProgress, [0, 1], [0, 1]);
  const opacity = enterOpacity * exitOpacity;
  const scale = interpolate(enterProgress, [0, 1], [0.9, 1]);

  const labelText = nicheId === "reddit_stories" ? "TRENDING" : "TRENDING";

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
          transform: `translateY(${translateY}px) scale(${scale})`,
          opacity,
          width: "88%",
          backgroundColor: "rgba(0, 0, 0, 0.88)",
          borderRadius: 16,
          padding: "36px 40px",
          border: `2px solid ${accentColor}44`,
          backdropFilter: "blur(8px)",
        }}
      >
        <div
          style={{
            fontSize: 28,
            fontWeight: 700,
            fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif",
            letterSpacing: 3,
            textTransform: "uppercase",
            color: accentColor,
          }}
        >
          {labelText}
        </div>
        <div
          style={{
            fontSize: 52,
            fontWeight: 800,
            fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif",
            lineHeight: 1.3,
            marginTop: 12,
            textAlign: "center",
            color: "#ffffff",
          }}
        >
          {hookText}
        </div>
        <div
          style={{
            height: 4,
            backgroundColor: accentColor,
            borderRadius: 2,
            marginTop: 20,
            width: "60%",
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
