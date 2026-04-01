import React from "react";
import {
  AbsoluteFill,
  OffthreadVideo,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

type SceneClipProps = {
  clipPath: string;
  textOverlay: string;
  accentColor: string;
  sceneIndex: number;
  totalScenes: number;
};

export const SceneClip: React.FC<SceneClipProps> = ({
  clipPath,
  textOverlay,
  accentColor,
  sceneIndex,
  totalScenes,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Subtle slow zoom on each clip for cinematic feel (1.0 → 1.08 over duration)
  const scale = interpolate(frame, [0, fps * 15], [1.0, 1.08], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill>
      {/* Stock footage background with subtle zoom */}
      <AbsoluteFill
        style={{
          transform: `scale(${scale})`,
          transformOrigin: "center center",
        }}
      >
        <OffthreadVideo
          src={staticFile(clipPath)}
          volume={0}
          loop
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
        />
      </AbsoluteFill>

      {/* Gradient overlay at bottom for text readability */}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(transparent 50%, rgba(0,0,0,0.7) 80%, rgba(0,0,0,0.9) 100%)",
        }}
      />

      {/* Text overlay with spring animation */}
      {textOverlay && (
        <TextOverlay
          text={textOverlay}
          accentColor={accentColor}
          frame={frame}
          fps={fps}
        />
      )}
    </AbsoluteFill>
  );
};

const TextOverlay: React.FC<{
  text: string;
  accentColor: string;
  frame: number;
  fps: number;
}> = ({ text, accentColor, frame, fps }) => {
  // Spring animation for entrance
  const enter = spring({
    frame,
    fps,
    config: { stiffness: 200, damping: 20, mass: 0.8 },
  });

  const translateY = interpolate(enter, [0, 1], [60, 0]);
  const opacity = interpolate(enter, [0, 1], [0, 1]);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 340,
      }}
    >
      <div
        style={{
          transform: `translateY(${translateY}px)`,
          opacity,
          backgroundColor: accentColor,
          padding: "12px 28px",
          borderRadius: 8,
          maxWidth: "85%",
        }}
      >
        <span
          style={{
            color: "#fff",
            fontSize: 52,
            fontWeight: 800,
            fontFamily:
              "system-ui, -apple-system, 'Segoe UI', sans-serif",
            textAlign: "center",
            textTransform: "uppercase",
            letterSpacing: 1.5,
            lineHeight: 1.2,
            display: "block",
          }}
        >
          {text}
        </span>
      </div>
    </AbsoluteFill>
  );
};
