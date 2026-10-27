import * as Remotion from 'remotion';

export type MotionScale = {
  width: number;
  height: number;
  unit: number;
  isVertical: boolean;
  u: (px: number) => number;
};

export const useMotionScale = (): MotionScale => {
  let width = 1080;
  let height = 1920;
  try {
    if (typeof Remotion.useVideoConfig === 'function') {
      const cfg = Remotion.useVideoConfig();
      if (cfg && typeof cfg.width === 'number' && typeof cfg.height === 'number') {
        width = cfg.width;
        height = cfg.height;
      }
    }
  } catch {
    // Fallback to default vertical_clip (1080x1920) when called outside Remotion composition context.
  }
  const unit = Math.min(width, height) / 1080;
  const isVertical = height > width;
  const u = (px: number): number => Math.round(px * unit);
  return {width, height, unit, isVertical, u};
};
