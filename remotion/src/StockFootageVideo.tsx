import React from "react";
import {
  AbsoluteFill,
  Audio,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import type { VideoProps } from "./Root";
import { SceneClip } from "./SceneClip";
import { TikTokCaptions } from "./TikTokCaptions";
import { HookCard } from "./HookCard";
import { ProgressBar } from "./ProgressBar";
import { PartBadge } from "./PartBadge";
import { EmojiReactions } from "./EmojiReaction";

export const StockFootageVideo: React.FC<VideoProps> = ({
  scenes,
  voiceoverPath,
  musicPath,
  subtitles,
  totalDuration,
  musicVolume,
  crossfadeDuration,
  accentColor,
  nicheId,
  hookText,
  partNumber,
  totalParts,
  emojiBeats,
}) => {
  const { fps } = useVideoConfig();
  const frame = useCurrentFrame();
  const cfFrames = Math.round(crossfadeDuration * fps);
  const currentTime = frame / fps;

  // Music fade in (first 2s) and fade out (last 3s)
  const musicVol = interpolate(
    frame,
    [0, fps * 2, fps * (totalDuration - 3), fps * totalDuration],
    [0, musicVolume, musicVolume, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // CTA "Follow for more" in last 3 seconds
  const ctaStart = totalDuration - 3.5;
  const showCta = currentTime >= ctaStart && currentTime <= totalDuration;

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* Stock footage clips with crossfade transitions */}
      {/* Safety net: extend last scene to fill remaining frames so we never */}
      {/* show black screen if clip durations are slightly short. */}
      <TransitionSeries>
        {scenes.map((scene, i) => {
          const isLast = i === scenes.length - 1;
          // For the last scene, extend to cover any remaining frames
          // visible = sum(durations) - (N-1)*crossfade, but rounding can leave gaps
          const baseDurationFrames = Math.round(scene.duration * fps);
          const durationFrames = isLast
            ? Math.max(baseDurationFrames, Math.round(totalDuration * fps))
            : baseDurationFrames;
          const elements: React.ReactNode[] = [];

          if (i > 0) {
            elements.push(
              <TransitionSeries.Transition
                key={`tr-${i}`}
                presentation={fade()}
                timing={linearTiming({ durationInFrames: cfFrames })}
              />
            );
          }

          elements.push(
            <TransitionSeries.Sequence
              key={`seq-${i}`}
              durationInFrames={durationFrames}
            >
              <SceneClip
                clipPath={scene.clipPath}
                textOverlay={scene.textOverlay}
                accentColor={accentColor}
                sceneIndex={i}
                totalScenes={scenes.length}
              />
            </TransitionSeries.Sequence>
          );

          return elements;
        })}
      </TransitionSeries>

      {/* Hook card overlay (first 4 seconds) */}
      {hookText && (
        <HookCard
          hookText={hookText}
          nicheId={nicheId}
          accentColor={accentColor}
          duration={4}
        />
      )}

      {/* Part badge (for multi-part videos) */}
      {partNumber > 0 && totalParts > 1 && (
        <PartBadge partNumber={partNumber} totalParts={totalParts} accentColor={accentColor} />
      )}

      {/* TikTok-style animated captions with 2-3 word groups */}
      {subtitles.length > 0 && (
        <TikTokCaptions
          subtitles={subtitles}
          accentColor={accentColor}
          nicheId={nicheId}
        />
      )}

      {/* Emoji reactions with spring pop animations */}
      {emojiBeats.length > 0 && <EmojiReactions beats={emojiBeats} />}

      {/* CTA end screen */}
      {showCta && <CtaOverlay frame={frame} fps={fps} ctaStart={ctaStart} />}

      {/* Voiceover audio */}
      {voiceoverPath && <Audio src={staticFile(voiceoverPath)} volume={1} />}

      {/* Background music with fade in/out */}
      {musicPath && <Audio src={staticFile(musicPath)} volume={musicVol} loop />}

      {/* Progress bar removed */}
    </AbsoluteFill>
  );
};

/** "Follow for more" CTA overlay in the last few seconds */
const CtaOverlay: React.FC<{
  frame: number;
  fps: number;
  ctaStart: number;
}> = ({ frame, fps, ctaStart }) => {
  const localFrame = frame - Math.round(ctaStart * fps);
  const enter = spring({
    frame: Math.max(0, localFrame),
    fps,
    config: { stiffness: 200, damping: 20, mass: 0.6 },
  });
  const translateY = interpolate(enter, [0, 1], [50, 0]);
  const opacity = interpolate(enter, [0, 1], [0, 1]);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 80,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          transform: `translateY(${translateY}px)`,
          opacity,
          backgroundColor: "rgba(255, 255, 255, 0.95)",
          padding: "14px 36px",
          borderRadius: 30,
        }}
      >
        <span
          style={{
            color: "#000",
            fontSize: 36,
            fontWeight: 800,
            fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif",
            letterSpacing: 1,
          }}
        >
          Follow for more →
        </span>
      </div>
    </AbsoluteFill>
  );
};
