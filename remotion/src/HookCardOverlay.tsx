import React from "react";
import { AbsoluteFill } from "remotion";
import { HookCard } from "./HookCard";

type HookCardOverlayProps = {
  hookText: string;
  nicheId: string;
  accentColor: string;
  duration: number;
};

/**
 * Standalone hook card overlay composition (transparent background).
 * Rendered as WebM with alpha, then composited onto existing videos via FFmpeg.
 */
export const HookCardOverlay: React.FC<HookCardOverlayProps> = ({
  hookText,
  nicheId,
  accentColor,
  duration,
}) => {
  return (
    <AbsoluteFill style={{ backgroundColor: "transparent" }}>
      {hookText && (
        <HookCard
          hookText={hookText}
          nicheId={nicheId}
          accentColor={accentColor}
          duration={duration}
        />
      )}
    </AbsoluteFill>
  );
};
