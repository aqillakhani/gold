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
  x: number;
  y: number;
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

  const pop = spring({
    frame,
    fps,
    config: { stiffness: 400, damping: 15, mass: 0.3 },
  });
  const scale = interpolate(pop, [0, 1], [0.2, 1.0]);

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
