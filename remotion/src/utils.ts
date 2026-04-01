import type { SceneProps } from "./Root";

/**
 * Calculate total video duration from scenes, accounting for crossfade overlaps.
 */
export function calculateDuration(
  scenes: SceneProps[],
  crossfadeDuration: number
): number {
  if (scenes.length === 0) return 0;
  const total = scenes.reduce((sum, s) => sum + s.duration, 0);
  return total - crossfadeDuration * (scenes.length - 1);
}

/**
 * Map a scene index to its start time in seconds, accounting for crossfade overlaps.
 */
export function sceneStartTime(
  scenes: SceneProps[],
  index: number,
  crossfadeDuration: number
): number {
  let t = 0;
  for (let i = 0; i < index; i++) {
    t += scenes[i].duration - crossfadeDuration;
  }
  return t;
}
