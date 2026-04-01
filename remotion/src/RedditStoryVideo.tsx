import React from "react";
import {
  AbsoluteFill,
  Audio,
  interpolate,
  OffthreadVideo,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import type { VideoProps } from "./Root";
import { RedditCard } from "./RedditCard";
import { PartBadge } from "./PartBadge";

/**
 * Reddit Story video composition:
 * - Full-screen gameplay background
 * - Reddit-style post card overlay with progressive text reveal
 * - Word-level yellow highlighting synced to voiceover
 * - Original audio from background + voiceover narration
 */
export const RedditStoryVideo: React.FC<VideoProps> = ({
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
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const currentTime = frame / fps;

  const musicVol = musicVolume ?? 0.25;

  // Music fade in/out
  const musicFadeIn = interpolate(frame, [0, fps * 2], [0, musicVol], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const musicFadeOut = interpolate(
    frame,
    [durationInFrames - fps * 3, durationInFrames],
    [musicVol, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const effectiveMusicVol = Math.min(musicFadeIn, musicFadeOut);

  // Extract subreddit from hookText or use default
  const subreddit = nicheId === "reddit_stories" ? "AskReddit" :
    nicheId === "betrayal_revenge" ? "ProRevenge" : "Reddit";

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* Gameplay background — scene clips with crossfades */}
      <TransitionSeries>
        {scenes.map((scene, idx) => {
          const durFrames = Math.round(scene.duration * fps);
          const isLast = idx === scenes.length - 1;
          // Extend last scene to fill remaining video duration
          const finalDur = isLast ? Math.max(durFrames, durationInFrames) : durFrames;

          return (
            <React.Fragment key={idx}>
              <TransitionSeries.Sequence durationInFrames={finalDur}>
                <AbsoluteFill>
                  {scene.clipPath && (
                    <OffthreadVideo
                      src={staticFile(scene.clipPath)}
                      style={{
                        width: "100%",
                        height: "100%",
                        objectFit: "cover",
                      }}
                      muted
                    />
                  )}
                </AbsoluteFill>
              </TransitionSeries.Sequence>
              {!isLast && (
                <TransitionSeries.Transition
                  presentation={fade()}
                  timing={linearTiming({
                    durationInFrames: Math.round(crossfadeDuration * fps),
                  })}
                />
              )}
            </React.Fragment>
          );
        })}
      </TransitionSeries>

      {/* Reddit post card overlay with progressive text reveal */}
      <RedditCard
        subtitles={subtitles}
        hookText={hookText}
        subreddit={subreddit}
        accentColor={accentColor}
      />

      {/* Part badge for multi-part stories */}
      {partNumber > 0 && totalParts > 1 && (
        <PartBadge partNumber={partNumber} totalParts={totalParts} />
      )}

      {/* CTA end screen (last 3.5 seconds) */}
      {currentTime > totalDuration - 3.5 && (
        <AbsoluteFill
          style={{
            justifyContent: "flex-end",
            alignItems: "center",
            paddingBottom: 120,
          }}
        >
          <div
            style={{
              fontFamily: "'Montserrat', sans-serif",
              fontSize: 36,
              fontWeight: 700,
              color: "#FFFFFF",
              textShadow: "2px 2px 8px rgba(0,0,0,0.8)",
              opacity: interpolate(
                currentTime,
                [totalDuration - 3.5, totalDuration - 3.0],
                [0, 1],
                { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
              ),
            }}
          >
            Follow for Part {(partNumber || 0) + 1} →
          </div>
        </AbsoluteFill>
      )}

      {/* Voiceover audio */}
      {voiceoverPath && <Audio src={staticFile(voiceoverPath)} volume={1} />}

      {/* Background music */}
      {musicPath && (
        <Audio src={staticFile(musicPath)} volume={effectiveMusicVol} loop />
      )}
    </AbsoluteFill>
  );
};
