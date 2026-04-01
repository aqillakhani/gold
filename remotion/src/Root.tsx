import { Composition } from "remotion";
import { StockFootageVideo } from "./StockFootageVideo";
import { RedditStoryVideo } from "./RedditStoryVideo";
import { HookCardOverlay } from "./HookCardOverlay";
import { calculateDuration } from "./utils";

export type SceneProps = {
  clipPath: string;
  duration: number;
  textOverlay: string;
};

export type SubtitleWord = {
  word: string;
  start: number;
  end: number;
};

export type VideoProps = {
  scenes: SceneProps[];
  voiceoverPath: string;
  musicPath: string;
  subtitles: SubtitleWord[];
  totalDuration: number;
  musicVolume: number;
  crossfadeDuration: number;
  accentColor: string;
  nicheId: string;
  hookText: string;
  partNumber: number;
  totalParts: number;
  emojiBeats: Array<{ emoji: string; timestampSec: number; x: number; y: number }>;
};

const FPS = 30;

export const RemotionRoot: React.FC = () => {
  const defaultProps: VideoProps = {
    scenes: [],
    voiceoverPath: "",
    musicPath: "",
    subtitles: [],
    totalDuration: 60,
    musicVolume: 0.6,
    crossfadeDuration: 0.5,
    accentColor: "#0ea5e9",
    nicheId: "ai_tools",
    hookText: "",
    partNumber: 0,
    totalParts: 0,
    emojiBeats: [],
  };

  const hookOverlayProps = {
    hookText: "",
    nicheId: "ai_tools",
    accentColor: "#3b82f6",
    duration: 4,
  };

  return (
    <>
      <Composition
        id="StockFootageVideo"
        component={StockFootageVideo}
        fps={FPS}
        width={1080}
        height={1920}
        durationInFrames={FPS * 60}
        defaultProps={defaultProps}
        calculateMetadata={async ({ props }) => {
          const dur = props.totalDuration || 60;
          return {
            durationInFrames: Math.ceil(dur * FPS),
          };
        }}
      />
      <Composition
        id="RedditStoryVideo"
        component={RedditStoryVideo}
        fps={FPS}
        width={1080}
        height={1920}
        durationInFrames={FPS * 60}
        defaultProps={defaultProps}
        calculateMetadata={async ({ props }) => {
          const dur = props.totalDuration || 60;
          return {
            durationInFrames: Math.ceil(dur * FPS),
          };
        }}
      />
      <Composition
        id="HookCardOverlay"
        component={HookCardOverlay}
        fps={FPS}
        width={1080}
        height={1920}
        durationInFrames={FPS * 4}
        defaultProps={hookOverlayProps}
        calculateMetadata={async ({ props }) => {
          const dur = props.duration || 4;
          return {
            durationInFrames: Math.ceil(dur * FPS),
          };
        }}
      />
    </>
  );
};
