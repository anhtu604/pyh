// PYH style A "Mascot dẫn chuyện": tokens from docs/superpowers/specs/2026-11-17-pyh-style-a-mascot-host.md.
// Colours are the values in profiles/brand.vi.yaml; do not add new ones here.
import {brand} from '../anatomy/palette';
import type {FrameLayout} from '../layout';

export type MascotPose = 'welcome' | 'explain' | 'caution' | 'point_up' | 'thinking' | 'surprised'
  | 'thumbs_up' | 'blank_board' | 'myth_bust';

export const pyhColors = {
  background: brand.off_white, ink: brand.navy, accent: brand.teal, alert: brand.yellow, night: brand.night,
} as const;

export const pyhType = {
  fontFamily: "'Be Vietnam Pro', Arial, sans-serif",
  titleWeight: 800, labelWeight: 800, bodyWeight: 600,
  landscape: {label: 44, title: 72, hook: 112},
  portrait: {label: 52, title: 72, hook: 100},
} as const;

export const pyhStroke = {width: 6, radius: 14, ringWidth: 6, underlineWidth: 8} as const;

export const pyhTiming = {
  mascotEnterFrames: 12,
  mascotBobPx: 2,
  mascotBobPeriodSeconds: 2,
  mascotCrossfadeFrames: 6,
  mascotMinHoldSeconds: 2,
  arrowDrawFrames: 14,
  labelFadeFrames: 12,
  labelStartScale: 0.95,
  /** Non-speaking parts of a diagram keep 60% of their strength (-40%). */
  dimOpacity: 0.6,
  transitionFrames: 12,
  maxSecondsBetweenBeats: 6,
} as const;

export const pyhCaptions = {
  landscape: {maxLines: 2, maxCharsPerLine: 42},
  portrait: {maxLines: 2, maxCharsPerLine: 24},
  bandOpacity: 0.9,
} as const;

export const MASCOT_ASSET_DIR = 'assets/brand/mascot';
export const mascotAssetPath = (pose: MascotPose): string => `${MASCOT_ASSET_DIR}/${pose}.png`;

export const clamp01 = (value: number): number => Math.max(0, Math.min(1, value));
export const smoothstep = (value: number): number => {
  const t = clamp01(value);
  return t * t * (3 - 2 * t);
};
/** Gentle overshoot used only for the mascot entrance bounce. */
export const easeOutBack = (value: number, overshoot = 1.2): number => {
  const t = clamp01(value);
  const c3 = overshoot + 1;
  return 1 + c3 * (t - 1) ** 3 + overshoot * (t - 1) ** 2;
};

export type StyleFormat = 'landscape' | 'portrait';
export const formatOf = (layout: FrameLayout): StyleFormat =>
  layout.frame.width >= layout.frame.height ? 'landscape' : 'portrait';

export const hexToRgba = (hex: string, alpha: number): string => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};
