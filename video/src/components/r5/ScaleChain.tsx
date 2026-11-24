import React from 'react';
import {useCurrentFrame} from 'remotion';
import {FONT_FAMILY} from '../../fonts';
import type {FormatProfile} from '../../format';
import {
  captionBox,
  LAYOUTS,
  SAFE_GAP,
  shortsCaptionSafeBox,
  type Box,
  type FrameLayout,
} from '../../layout';
import type {ResolvedR5Shot} from '../../types';

/** Brand palette tokens required by R5 (navy, teal, yellow, warm off-white). */
export const R5_PALETTE = {
  navy: '#12304A',
  teal: '#18A6A6',
  tealDark: '#127D7D',
  yellow: '#F4B942',
  bg: '#F7F4EC',
  surface: '#FFFFFF',
  surfaceSoft: '#EFECE2',
  muted: '#5D6E7E',
  border: '#CBD4DA',
  alert: '#C84B52',
} as const;

export const R5_FPS = 30;
export const D1_MAX_TEXT_SECONDS = 6;
export const R5_MAX_TAKEAWAY_WORDS = 8;
export const R5_MAX_LABEL_WORDS = 3;
export const R5_MAX_SIMULTANEOUS_LABELS = 2;

export type R5LayoutInput = FrameLayout | FormatProfile;

export type R5RevisionAsset = {
  id?: string;
  path: string;
  name?: string;
  author: string;
  repository?: string;
  license: string;
  source_page?: string | null;
  role?: string | null;
  transformations?: string | null;
};

export type ScaleTier = {
  id: string;
  label: string;
};

export type ScaleChainProps = {
  shot: ResolvedR5Shot;
  layout: R5LayoutInput;
  assets?: readonly R5RevisionAsset[];
  tiers: readonly ScaleTier[];
  activeTierId?: string | null;
  frame?: number;
};

export type ScaleChainGeometry = {
  box: Box;
  activeTierId: string | null;
  activeIndex: number;
  compacted: boolean;
  visibleTiers: Array<{
    id: string;
    label: string;
    index: number;
    active: boolean;
    visited: boolean;
  }>;
};

export const resolveR5Layout = (layout: R5LayoutInput): FrameLayout =>
  typeof layout === 'string' ? LAYOUTS[layout] : layout;

export const isPortraitLayout = (layout: FrameLayout): boolean =>
  layout.frame.width < layout.frame.height;

/** Reserved subtitle boxes in 9:16 portrait mode that R5 labels/cards must never overlap. */
export const r5PortraitCaptionZones = (layout: FrameLayout): Box[] => {
  if (!isPortraitLayout(layout)) {
    return [];
  }
  return [
    shortsCaptionSafeBox(layout, false),
    shortsCaptionSafeBox(layout, true),
    captionBox(layout),
  ];
};

/** Highest Y coordinate available above the 9:16 subtitle band (inclusive of SAFE_GAP). */
export const r5PortraitContentBottom = (layout: FrameLayout): number => {
  const zones = r5PortraitCaptionZones(layout);
  if (zones.length === 0) {
    return layout.frame.height - SAFE_GAP;
  }
  return Math.min(...zones.map((z) => z.top)) - SAFE_GAP;
};

export const r5Clamp01 = (value: number): number => Math.max(0, Math.min(1, value));
export const r5Lerp = (a: number, b: number, t: number): number => a + (b - a) * t;
export const r5EaseOut = (t: number): number => {
  const u = r5Clamp01(t);
  return 1 - (1 - u) ** 3;
};
export const r5EaseInOut = (t: number): number => {
  const u = r5Clamp01(t);
  return u < 0.5 ? 4 * u * u * u : 1 - (-2 * u + 2) ** 3 / 2;
};

export const computeScaleChainGeometry = (
  layoutInput: R5LayoutInput,
  tiers: readonly ScaleTier[],
  activeTierId: string | null,
): ScaleChainGeometry => {
  const layout = resolveR5Layout(layoutInput);
  const portrait = isPortraitLayout(layout);
  const activeIndex = activeTierId ? tiers.findIndex((t) => t.id === activeTierId) : -1;

  const box: Box = portrait
    ? {left: 48, top: 88, width: layout.frame.width - 96, height: 64}
    : {left: 48, top: 32, width: Math.min(layout.frame.width - 96, 1200), height: 58};

  // In 9:16 portrait mode, compact long chains (> 4 tiers) around the active tier
  // so viewers always see where they are without overflowing the 1080px width.
  const compacted = portrait && tiers.length > 4;
  let indices: number[];
  if (!compacted) {
    indices = tiers.map((_, i) => i);
  } else {
    const center = activeIndex >= 0 ? activeIndex : 0;
    const start = Math.max(0, Math.min(center - 1, tiers.length - 3));
    indices = [start, start + 1, start + 2].filter((i) => i >= 0 && i < tiers.length);
  }

  const visibleTiers = indices.map((index) => {
    const tier = tiers[index];
    return {
      id: tier.id,
      label: tier.label,
      index,
      active: index === activeIndex,
      visited: activeIndex >= 0 && index < activeIndex,
    };
  });

  return {
    box,
    activeTierId: activeIndex >= 0 ? tiers[activeIndex].id : null,
    activeIndex,
    compacted,
    visibleTiers,
  };
};

/**
 * Deterministic anatomical/conceptual scale chain bar ("A -> B -> C").
 * Tier labels come strictly from props; no organ-specific chain is hardcoded.
 */
export const ScaleChain: React.FC<ScaleChainProps> = ({
  shot,
  layout: layoutInput,
  tiers,
  activeTierId,
  frame,
}) => {
  const currentFrame = useCurrentFrame();
  const effectiveFrame = frame ?? currentFrame;
  const layout = resolveR5Layout(layoutInput);
  const portrait = isPortraitLayout(layout);

  if (tiers.length === 0) {
    return null;
  }

  const resolvedActive = activeTierId !== undefined ? activeTierId : shot.tier;
  const geom = computeScaleChainGeometry(layout, tiers, resolvedActive);
  const localFrame = Math.max(0, effectiveFrame - shot.start_frame);
  const enterOpacity = r5EaseOut(localFrame / 10);

  const firstVisible = geom.visibleTiers[0]?.index ?? 0;
  const lastVisible = geom.visibleTiers[geom.visibleTiers.length - 1]?.index ?? -1;

  return (
    <div
      data-r5-component="ScaleChain"
      data-shot-id={shot.id}
      data-layout={portrait ? '9:16' : '16:9'}
      data-active-tier={geom.activeTierId ?? ''}
      data-compacted={String(geom.compacted)}
      aria-label="Thanh tầng phóng to"
      style={{
        position: 'absolute',
        left: geom.box.left,
        top: geom.box.top,
        maxWidth: geom.box.width,
        minHeight: geom.box.height,
        display: 'inline-flex',
        alignItems: 'center',
        gap: portrait ? 6 : 8,
        padding: portrait ? '8px 14px' : '8px 18px',
        borderRadius: 999,
        backgroundColor: 'rgba(255, 255, 255, 0.94)',
        border: `2.5px solid ${R5_PALETTE.navy}`,
        boxShadow: '0 6px 16px rgba(18, 48, 74, 0.12)',
        fontFamily: FONT_FAMILY,
        fontSize: portrait ? 22 : 20,
        fontWeight: 800,
        opacity: Math.max(0.01, enterOpacity),
        boxSizing: 'border-box',
        whiteSpace: 'nowrap',
      }}
    >
      {geom.compacted && firstVisible > 0 ? (
        <span style={{color: R5_PALETTE.muted, padding: '0 4px'}} aria-hidden="true">
          … →
        </span>
      ) : null}
      {geom.visibleTiers.map((tier, idx) => (
        <React.Fragment key={tier.id}>
          <span
            data-tier-id={tier.id}
            data-tier-active={String(tier.active)}
            style={{
              padding: portrait ? '4px 12px' : '3px 12px',
              borderRadius: 999,
              backgroundColor: tier.active ? R5_PALETTE.teal : 'transparent',
              color: tier.active
                ? '#FFFFFF'
                : tier.visited
                  ? R5_PALETTE.navy
                  : R5_PALETTE.muted,
            }}
          >
            {tier.label}
          </span>
          {idx < geom.visibleTiers.length - 1 ? (
            <span style={{color: R5_PALETTE.border}} aria-hidden="true">
              →
            </span>
          ) : null}
        </React.Fragment>
      ))}
      {geom.compacted && lastVisible < tiers.length - 1 ? (
        <span style={{color: R5_PALETTE.muted, padding: '0 4px'}} aria-hidden="true">
          → …
        </span>
      ) : null}
    </div>
  );
};
