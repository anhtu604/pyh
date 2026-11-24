import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {FONT_FAMILY} from '../../fonts';
import type {Box} from '../../layout';
import type {ResolvedR5Shot} from '../../types';
import {
  isPortraitLayout,
  R5_PALETTE,
  r5Clamp01,
  r5EaseInOut,
  r5EaseOut,
  r5Lerp,
  r5PortraitContentBottom,
  resolveR5Layout,
  type R5LayoutInput,
  type R5RevisionAsset,
} from './ScaleChain';

export type DistributionPoint = {
  /** Normalized x in [0, 1]. */
  x: number;
  /** Normalized y height in [0, 1]. */
  y: number;
};

export type DistributionBand = {
  id: string;
  label: string;
  startX: number;
  endX: number;
  tone: 'teal' | 'yellow' | 'navy';
  claimIds: readonly string[];
};

export type DistributionMarker = {
  id: string;
  label: string;
  x: number;
  tone?: 'navy' | 'teal' | 'alert';
  claimIds: readonly string[];
};

export type DistributionCohort = {
  total: number;
  outsideCount: number;
  caption?: string;
  claimIds: readonly string[];
};

export type ReferenceDistributionProps = {
  shot: ResolvedR5Shot;
  layout: R5LayoutInput;
  assets?: readonly R5RevisionAsset[];
  title: string;
  /** Explicit illustrative badge (always contains "minh họa"). */
  illustrationLabel?: string;
  /** Optional non-Gaussian scope note. */
  scopeNote?: string;
  points: readonly DistributionPoint[];
  bands: readonly DistributionBand[];
  markers?: readonly DistributionMarker[];
  cohort?: DistributionCohort | null;
  frame?: number;
};

export type DistributionGeometry = {
  badgeBox: Box;
  plotBox: Box;
  cohortBox: Box | null;
  noteBox: Box;
};

const BAND_COLORS: Record<DistributionBand['tone'], string> = {
  teal: R5_PALETTE.teal,
  yellow: R5_PALETTE.yellow,
  navy: R5_PALETTE.navy,
};

const MARKER_COLORS: Record<NonNullable<DistributionMarker['tone']>, string> = {
  navy: R5_PALETTE.navy,
  teal: R5_PALETTE.tealDark,
  alert: R5_PALETTE.alert,
};

const sampleCurveY = (sorted: readonly DistributionPoint[], x: number): number => {
  if (sorted.length === 0) return 0;
  if (x <= sorted[0].x) return sorted[0].y;
  const last = sorted[sorted.length - 1];
  if (x >= last.x) return last.y;
  for (let i = 0; i < sorted.length - 1; i++) {
    const a = sorted[i];
    const b = sorted[i + 1];
    if (x >= a.x && x <= b.x) {
      const span = b.x - a.x;
      const t = span > 0 ? (x - a.x) / span : 0;
      return r5Lerp(a.y, b.y, t);
    }
  }
  return last.y;
};

export const computeDistributionGeometry = (
  layoutInput: R5LayoutInput,
  hasCohort: boolean,
): DistributionGeometry => {
  const layout = resolveR5Layout(layoutInput);
  const portrait = isPortraitLayout(layout);

  if (portrait) {
    const maxBottom = r5PortraitContentBottom(layout);
    const badgeBox: Box = {left: 48, top: 96, width: layout.frame.width - 96, height: 64};
    const plotBox: Box = {left: 48, top: 192, width: layout.frame.width - 96, height: 640};
    const cohortBox: Box | null = hasCohort
      ? {left: 48, top: 856, width: layout.frame.width - 96, height: 280}
      : null;
    const noteTop = Math.min(hasCohort ? 1156 : 860, maxBottom - 76);
    const noteBox: Box = {left: 48, top: noteTop, width: layout.frame.width - 96, height: 64};
    return {badgeBox, plotBox, cohortBox, noteBox};
  }

  const badgeBox: Box = {left: 84, top: 44, width: 1752, height: 64};
  const plotBox: Box = {left: 120, top: 144, width: 1680, height: hasCohort ? 560 : 720};
  const cohortBox: Box | null = hasCohort
    ? {left: 120, top: 724, width: 1680, height: 210}
    : null;
  const noteBox: Box = {left: 120, top: 960, width: 1680, height: 64};
  return {badgeBox, plotBox, cohortBox, noteBox};
};

/**
 * Data-driven illustrative reference distribution curve.
 * Receives curve points, shaded bands, markers, and cohort counts via props;
 * explicitly labeled "Minh họa" and never assumes all lab values are Gaussian.
 */
export const ReferenceDistribution: React.FC<ReferenceDistributionProps> = ({
  shot,
  layout: layoutInput,
  title,
  illustrationLabel = 'Minh họa',
  scopeNote = 'Biểu đồ minh họa phân bố — không mặc định mọi chỉ số đều phân phối chuẩn.',
  points,
  bands,
  markers = [],
  cohort = null,
  frame,
}) => {
  const currentFrame = useCurrentFrame();
  const effectiveFrame = frame ?? currentFrame;
  const layout = resolveR5Layout(layoutInput);
  const portrait = isPortraitLayout(layout);

  if (points.length < 2) {
    throw new Error(`ReferenceDistribution (${shot.id}) requires at least 2 curve points`);
  }

  const normalizedBadge = illustrationLabel.toLowerCase().includes('minh họa')
    ? illustrationLabel
    : `${illustrationLabel} (minh họa)`;

  const geom = computeDistributionGeometry(layout, Boolean(cohort && cohort.total > 0));
  const localFrame = Math.max(0, effectiveFrame - shot.start_frame);
  const enterOpacity = r5EaseOut(localFrame / 14);
  const drawProgress = r5EaseInOut(localFrame / 28);

  const sorted = [...points]
    .map((p) => ({x: r5Clamp01(p.x), y: r5Clamp01(p.y)}))
    .sort((a, b) => a.x - b.x);

  const padX = 48;
  const padTop = 72;
  const padBottom = 64;
  const innerW = geom.plotBox.width - padX * 2;
  const innerH = geom.plotBox.height - padTop - padBottom;
  const baseY = geom.plotBox.height - padBottom;

  const toSvgX = (nx: number): number => padX + r5Clamp01(nx) * innerW;
  const toSvgY = (ny: number): number => baseY - r5Clamp01(ny) * innerH;

  const strokePath = sorted
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${toSvgX(p.x).toFixed(1)} ${toSvgY(p.y).toFixed(1)}`)
    .join(' ');

  const buildBandPath = (startX: number, endX: number): string => {
    const lo = Math.min(r5Clamp01(startX), r5Clamp01(endX));
    const hi = Math.max(r5Clamp01(startX), r5Clamp01(endX));
    const interior = sorted.filter((p) => p.x > lo && p.x < hi);
    const bandPts: DistributionPoint[] = [
      {x: lo, y: sampleCurveY(sorted, lo)},
      ...interior,
      {x: hi, y: sampleCurveY(sorted, hi)},
    ];
    const parts = [`M ${toSvgX(lo).toFixed(1)} ${baseY.toFixed(1)}`];
    for (const pt of bandPts) {
      parts.push(`L ${toSvgX(pt.x).toFixed(1)} ${toSvgY(pt.y).toFixed(1)}`);
    }
    parts.push(`L ${toSvgX(hi).toFixed(1)} ${baseY.toFixed(1)} Z`);
    return parts.join(' ');
  };

  return (
    <AbsoluteFill
      data-r5-component="ReferenceDistribution"
      data-shot-id={shot.id}
      data-layout={portrait ? '9:16' : '16:9'}
      style={{
        backgroundColor: R5_PALETTE.bg,
        fontFamily: FONT_FAMILY,
        overflow: 'hidden',
        opacity: Math.max(0.01, enterOpacity),
      }}
    >
      {/* Header + mandatory illustrative badge */}
      <div
        style={{
          position: 'absolute',
          left: geom.badgeBox.left,
          top: geom.badgeBox.top,
          width: geom.badgeBox.width,
          height: geom.badgeBox.height,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16,
        }}
      >
        <div style={{fontSize: portrait ? 30 : 34, fontWeight: 800, color: R5_PALETTE.navy}}>
          {title}
        </div>
        <div
          data-illustration-label="true"
          style={{
            padding: '8px 20px',
            borderRadius: 999,
            backgroundColor: R5_PALETTE.navy,
            color: R5_PALETTE.yellow,
            fontSize: portrait ? 22 : 24,
            fontWeight: 800,
            flexShrink: 0,
          }}
        >
          {normalizedBadge}
        </div>
      </div>

      {/* Curve plot area */}
      <div
        data-distribution-plot="true"
        style={{
          position: 'absolute',
          left: geom.plotBox.left,
          top: geom.plotBox.top,
          width: geom.plotBox.width,
          height: geom.plotBox.height,
          backgroundColor: R5_PALETTE.surface,
          border: `3.5px solid ${R5_PALETTE.border}`,
          borderRadius: 24,
          boxShadow: '0 10px 24px rgba(18, 48, 74, 0.08)',
        }}
      >
        <svg
          viewBox={`0 0 ${geom.plotBox.width} ${geom.plotBox.height}`}
          width={geom.plotBox.width}
          height={geom.plotBox.height}
        >
          {bands.map((band) => {
            const midX = toSvgX((band.startX + band.endX) / 2);
            const midY = baseY - Math.max(36, sampleCurveY(sorted, (band.startX + band.endX) / 2) * innerH * 0.45);
            return (
              <g key={band.id} data-band-id={band.id} data-claim-ids={band.claimIds.join(',')}>
                <path
                  d={buildBandPath(band.startX, band.endX)}
                  fill={BAND_COLORS[band.tone]}
                  opacity={band.tone === 'yellow' ? 0.65 : 0.28}
                />
                <text
                  x={midX}
                  y={midY}
                  textAnchor="middle"
                  fontSize={portrait ? 26 : 30}
                  fontWeight={800}
                  fill={R5_PALETTE.navy}
                >
                  {band.label}
                </text>
              </g>
            );
          })}

          <line
            x1={padX - 12}
            y1={baseY}
            x2={geom.plotBox.width - padX + 12}
            y2={baseY}
            stroke={R5_PALETTE.navy}
            strokeWidth={5}
            strokeLinecap="round"
          />

          <path
            data-distribution-curve="true"
            d={strokePath}
            fill="none"
            stroke={R5_PALETTE.navy}
            strokeWidth={7}
            strokeLinecap="round"
            strokeDasharray={3000}
            strokeDashoffset={((1 - drawProgress) * 3000).toFixed(1)}
          />

          {markers.map((marker, idx) => {
            const mx = toSvgX(marker.x);
            const color = MARKER_COLORS[marker.tone ?? 'navy'];
            const labelY = 38 + (idx % 2) * 44;
            return (
              <g key={marker.id} data-marker-id={marker.id} data-claim-ids={marker.claimIds.join(',')}>
                <line
                  x1={mx}
                  y1={labelY + 14}
                  x2={mx}
                  y2={baseY}
                  stroke={color}
                  strokeWidth={5}
                  strokeDasharray="10 8"
                />
                <text
                  x={mx}
                  y={labelY}
                  textAnchor="middle"
                  fontSize={portrait ? 22 : 24}
                  fontWeight={800}
                  fill={color}
                >
                  {marker.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Optional data-driven cohort icons */}
      {cohort && cohort.total > 0 && geom.cohortBox ? (
        <div
          data-distribution-cohort="true"
          data-claim-ids={cohort.claimIds.join(',')}
          style={{
            position: 'absolute',
            left: geom.cohortBox.left,
            top: geom.cohortBox.top,
            width: geom.cohortBox.width,
            height: geom.cohortBox.height,
            backgroundColor: R5_PALETTE.surface,
            border: `3px solid ${R5_PALETTE.navy}`,
            borderRadius: 20,
            padding: '16px 24px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            gap: 12,
            boxSizing: 'border-box',
          }}
        >
          <div style={{display: 'flex', flexWrap: 'wrap', gap: portrait ? 14 : 18, justifyContent: 'center'}}>
            {Array.from({length: cohort.total}, (_, index) => {
              const isOutside = index >= cohort.total - cohort.outsideCount;
              return (
                <span
                  key={index}
                  data-cohort-outside={String(isOutside)}
                  style={{
                    width: portrait ? 28 : 32,
                    height: portrait ? 28 : 32,
                    borderRadius: 999,
                    backgroundColor: isOutside ? R5_PALETTE.yellow : R5_PALETTE.teal,
                    border: `2.5px solid ${R5_PALETTE.navy}`,
                    display: 'inline-block',
                  }}
                />
              );
            })}
          </div>
          {cohort.caption ? (
            <div style={{textAlign: 'center', fontSize: portrait ? 22 : 24, fontWeight: 700, color: R5_PALETTE.navy}}>
              {cohort.caption}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* Explicit scope note */}
      <div
        data-distribution-note="true"
        style={{
          position: 'absolute',
          left: geom.noteBox.left,
          top: geom.noteBox.top,
          width: geom.noteBox.width,
          minHeight: geom.noteBox.height,
          display: 'flex',
          alignItems: 'center',
          fontSize: portrait ? 20 : 22,
          fontWeight: 600,
          color: R5_PALETTE.muted,
        }}
      >
        {scopeNote}
      </div>
    </AbsoluteFill>
  );
};
