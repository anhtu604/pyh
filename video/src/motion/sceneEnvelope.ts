import React from 'react';
import {useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import type {Scene} from '../types';

export type SceneEnterMode = 'hook_open' | 'shared_continuation' | 'scene_cut' | 'chapter_enter';
export type SceneExitMode = 'none' | 'micro_settle' | 'scene_exit' | 'chapter_exit';

export type SceneTransitionProps = {
  readonly enterMode: SceneEnterMode;
  readonly exitMode: SceneExitMode;
  readonly durationFrames: number;
  readonly isOutro?: boolean;
  readonly mascotContinuation?: boolean;
};

export type ChapterBridgeState = {
  readonly widthPercent: number;
  readonly opacity: number;
};

export type SceneEnvelopeState = {
  readonly opacity: number;
  readonly transform: string | undefined;
  readonly bridge: ChapterBridgeState | null;
};

const clamp01 = (v: number): number => Math.max(0, Math.min(1, v));

/** Smoothstep cubic easing with zero overshoot/bounce. */
export const smoothstepCubic = (t: number): number => {
  const x = clamp01(t);
  return x * x * (3 - 2 * x);
};

const hasMascotAsset = (scene?: Scene): boolean =>
  Boolean(scene?.visual_assets?.some((asset) => asset.role === 'mascot'));

const resolveEnterMode = (prev: Scene | undefined, curr: Scene, index: number): SceneEnterMode => {
  if (index === 0 || !prev) return 'hook_open';
  if (curr.visual === 'brand_outro') return 'chapter_enter';
  if (curr.chapter_id !== undefined && prev.chapter_id !== curr.chapter_id) {
    return 'chapter_enter';
  }
  const sameChapter = prev.chapter_id === curr.chapter_id;
  const sameLine = Boolean(curr.script_line_id && prev.script_line_id === curr.script_line_id);
  const sameSubject = Boolean(curr.anatomy?.subject && prev.anatomy?.subject === curr.anatomy.subject);
  if (sameChapter && (sameLine || sameSubject)) {
    return 'shared_continuation';
  }
  return 'scene_cut';
};

/**
 * Computes deterministic transition plan solely from `scenes[index-1]`, `scenes[index]`,
 * and `scenes[index+1]` so chapter-by-chapter renders match full-video renders identically.
 */
export const sceneTransitionPlan = (scenes: readonly Scene[], index: number): SceneTransitionProps => {
  const curr = scenes[index];
  const prev = index > 0 ? scenes[index - 1] : undefined;
  const next = index + 1 < scenes.length ? scenes[index + 1] : undefined;

  const enterMode = resolveEnterMode(prev, curr, index);
  let exitMode: SceneExitMode = 'none';
  if (next) {
    const nextEnter = resolveEnterMode(curr, next, index + 1);
    if (nextEnter === 'chapter_enter') {
      exitMode = 'chapter_exit';
    } else if (nextEnter === 'shared_continuation') {
      exitMode = 'none';
    } else if (curr.duration_frames >= 60) {
      exitMode = 'scene_exit';
    }
  }

  return {
    enterMode,
    exitMode,
    durationFrames: curr.duration_frames,
    isOutro: curr.visual === 'brand_outro',
    mascotContinuation: index > 0 && hasMascotAsset(prev) && hasMascotAsset(curr),
  };
};

/** Computes per-frame opacity, horizontal settle transform, and optional chapter bridge bar. */
export const computeSceneEnvelope = (
  frame: number,
  transition?: SceneTransitionProps,
): SceneEnvelopeState => {
  if (!transition || transition.durationFrames < 45) {
    return {opacity: 1, transform: undefined, bridge: null};
  }

  const {enterMode, exitMode, durationFrames, isOutro = false} = transition;
  let opacity = 1;
  let translateX = 0;

  // Enter phase
  if (enterMode === 'hook_open') {
    const t = smoothstepCubic(frame / 6);
    opacity = 0.92 + 0.08 * t;
    translateX = 0;
  } else if (enterMode === 'shared_continuation') {
    const t = smoothstepCubic(frame / 6);
    opacity = 0.88 + 0.12 * t;
    translateX = 0;
  } else if (enterMode === 'chapter_enter') {
    if (isOutro) {
      opacity = smoothstepCubic(frame / 15);
      translateX = 0;
    } else {
      const t = smoothstepCubic(frame / 12);
      opacity = t;
      translateX = 28 * (1 - t);
    }
  } else if (durationFrames >= 60) {
    const t = smoothstepCubic(frame / 10);
    opacity = t;
    translateX = 18 * (1 - t);
  } else {
    opacity = smoothstepCubic(frame / 6);
    translateX = 0;
  }

  // Exit phase (tail of scene)
  if (exitMode === 'scene_exit' && durationFrames >= 60) {
    const exitStart = durationFrames - 6;
    if (frame >= exitStart) {
      const t = smoothstepCubic((frame - exitStart) / 6);
      opacity *= 1 - t;
      translateX += -12 * t;
    }
  } else if (exitMode === 'chapter_exit') {
    const exitStart = durationFrames - 9;
    if (frame >= exitStart) {
      const t = smoothstepCubic((frame - exitStart) / 9);
      opacity *= 1 - t;
      translateX += -20 * t;
    }
  } else if (exitMode === 'micro_settle') {
    const exitStart = durationFrames - 4;
    if (frame >= exitStart) {
      const t = smoothstepCubic((frame - exitStart) / 4);
      opacity *= 1 - 0.08 * t;
    }
  }

  // Chapter bridge progress bar (4px teal line at top during frames 0..32)
  let bridge: ChapterBridgeState | null = null;
  if (enterMode === 'chapter_enter' && !isOutro && frame >= 0 && frame <= 32) {
    const sweep = smoothstepCubic(frame / 18);
    const fade = frame <= 18 ? 1 : 1 - smoothstepCubic((frame - 18) / 14);
    bridge = {
      widthPercent: Number((sweep * 100).toFixed(2)),
      opacity: Number(fade.toFixed(4)),
    };
  }

  const roundedOpacity = Number(clamp01(opacity).toFixed(4));
  const transform = Math.abs(translateX) >= 0.05 ? `translateX(${translateX.toFixed(2)}px)` : undefined;

  return {opacity: roundedOpacity, transform, bridge};
};

export const ChapterBridgeBar: React.FC<{bridge: ChapterBridgeState | null}> = ({bridge}) => {
  if (!bridge || bridge.opacity <= 0) return null;
  return React.createElement('div', {
    'data-chapter-bridge': 'true',
    style: {
      position: 'absolute',
      left: 0,
      top: 0,
      width: `${bridge.widthPercent}%`,
      height: 4,
      backgroundColor: brand.teal,
      opacity: bridge.opacity,
      pointerEvents: 'none',
      zIndex: 20,
    },
  });
};

/**
 * Wraps fragment-based scenes only when `transition` is supplied by `HealthVideo`,
 * leaving standalone unit tests (`transition === undefined`) structurally unchanged.
 */
export const SceneEnvelopeWrapper: React.FC<{
  transition?: SceneTransitionProps;
  children: React.ReactNode;
}> = ({transition, children}) => {
  const frame = useCurrentFrame();
  const env = computeSceneEnvelope(frame, transition);
  return React.createElement(
    'div',
    {
      'data-scene-envelope': 'true',
      style: {
        position: 'absolute',
        inset: 0,
        opacity: env.opacity,
        transform: env.transform,
      },
    },
    children,
    React.createElement(ChapterBridgeBar, {bridge: env.bridge}),
  );
};
