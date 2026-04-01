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

  // Slide in from right after 0.5s delay
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
        <span style={{
          fontSize: 28,
          fontWeight: 900,
          fontFamily: "system-ui, sans-serif",
          color: accentColor,
        }}>
          PART {partNumber}
        </span>
        <span style={{
          fontSize: 22,
          fontWeight: 600,
          fontFamily: "system-ui, sans-serif",
          color: "rgba(255,255,255,0.6)",
        }}>
          /{totalParts}
        </span>
      </div>
    </AbsoluteFill>
  );
};
