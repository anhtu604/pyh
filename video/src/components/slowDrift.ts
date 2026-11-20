export const LONG_SCENE_SECONDS = 8;
export const DRIFT_SEGMENT_SECONDS = 8;
export const DRIFT_MAX_SCALE = 1.08;
export const DRIFT_MAX_PAN_X_PCT = 1.5;
export const DRIFT_MAX_PAN_Y_PCT = 1.0;

export type SlowDriftState = {
  active: boolean;
  scale: number;
  translateX: number;
  translateY: number;
  transform: string | undefined;
};

/**
 * Continuous slow zoom/pan for long illustration scenes (>= 8s).
 * Reverses direction smoothly every ~8s (cosine ease-in-out) with no jump at segment boundaries.
 */
export const slowDriftTransform = (
  frame: number,
  durationFrames: number,
  fps = 30,
): SlowDriftState => {
  const minFrames = LONG_SCENE_SECONDS * fps;
  if (durationFrames < minFrames) {
    return {active: false, scale: 1, translateX: 0, translateY: 0, transform: undefined};
  }
  const segmentFrames = DRIFT_SEGMENT_SECONDS * fps;
  const clamped = Math.max(0, Math.min(frame, durationFrames));
  const segmentIndex = Math.floor(clamped / segmentFrames);
  const localProgress = (clamped % segmentFrames) / segmentFrames;
  const eased = 0.5 - 0.5 * Math.cos(Math.PI * localProgress);
  const factor = segmentIndex % 2 === 0 ? eased : 1 - eased;

  const scale = 1 + (DRIFT_MAX_SCALE - 1) * factor;
  const translateX = DRIFT_MAX_PAN_X_PCT * factor;
  const translateY = -DRIFT_MAX_PAN_Y_PCT * factor;
  return {
    active: true,
    scale,
    translateX,
    translateY,
    transform: `translate(${translateX.toFixed(3)}%, ${translateY.toFixed(3)}%) scale(${scale.toFixed(4)})`,
  };
};
