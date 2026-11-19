// Pure, frame-driven mascot motion (no randomness) for the style A host.
import {easeOutBack, clamp01, pyhTiming, type MascotPose} from '../style/pyhStyle';

export type MascotBeat = {frame: number; pose: MascotPose};

/** Sorts beats and drops pose changes that would hold the previous pose for under minHold frames. */
export const normalizePoseTrack = (track: readonly MascotBeat[], fps: number,
  minHoldSeconds: number = pyhTiming.mascotMinHoldSeconds): MascotBeat[] => {
  const minHold = Math.round(minHoldSeconds * fps);
  const result: MascotBeat[] = [];
  [...track].sort((a, b) => a.frame - b.frame).forEach((beat) => {
    const last = result[result.length - 1];
    if (!last) result.push(beat);
    else if (beat.pose !== last.pose && beat.frame - last.frame >= minHold) result.push(beat);
  });
  return result;
};

export type PoseState = {pose: MascotPose; from: MascotPose | null; mix: number};

/** Current pose plus the 6-frame cross-fade from the previous pose. */
export const poseAt = (track: readonly MascotBeat[], frame: number,
  fade: number = pyhTiming.mascotCrossfadeFrames): PoseState => {
  let index = -1;
  track.forEach((beat, i) => {if (beat.frame <= frame) index = i;});
  if (index < 0) return {pose: track[0]?.pose ?? 'welcome', from: null, mix: 1};
  const mix = index === 0 ? 1 : clamp01((frame - track[index].frame) / fade);
  return {pose: track[index].pose, from: index > 0 && mix < 1 ? track[index - 1].pose : null, mix};
};

/** 0..1 progress with a slight bounce overshoot over 12 frames. */
export const entranceProgress = (frame: number, enterFrame = 0,
  duration: number = pyhTiming.mascotEnterFrames): number => easeOutBack((frame - enterFrame) / duration);

/** Vertical slide offset in px: starts one slide distance below, overshoots up a little, settles at 0. */
export const entranceOffset = (frame: number, slide: number, enterFrame = 0): number =>
  (1 - entranceProgress(frame, enterFrame)) * slide;

/** 2 px breathing bob, one cycle every 2 seconds, only while speaking. */
export const bobOffset = (frame: number, fps: number, speaking = true): number =>
  speaking ? Math.sin(frame / (fps * pyhTiming.mascotBobPeriodSeconds) * Math.PI * 2) * pyhTiming.mascotBobPx : 0;

/** Source artwork looks to the right; flip when the diagram sits to the mascot's left. */
export const facesDiagram = (mascotCenterX: number, diagramCenterX: number): boolean =>
  diagramCenterX < mascotCenterX;
