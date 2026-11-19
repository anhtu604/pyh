import React from 'react';
import {useCurrentFrame} from 'remotion';
import {clamp01, pyhColors, pyhStroke, pyhTiming, smoothstep} from '../style/pyhStyle';

export type MagnifierBox = {left: number; top: number; width: number; height: number};

export type MagnifierZoomProps = {
  sourceRegion: MagnifierBox;
  detailBox: MagnifierBox;
  locatorStart: number;
  open: {start: number; end: number};
  close?: {start: number; end: number};
  detailRadius?: number;
  children: React.ReactNode;
};

type Point = {x: number; y: number};
type WindowRange = {start: number; end: number};

const FRAME_WIDTH = 1920;
const FRAME_HEIGHT = 1080;
const LOCATOR_STROKE_WIDTH = 4;
const LOCATOR_RADIUS = 10;
const LEADER_STROKE_WIDTH = 4;

const lerp = (a: number, b: number, t: number): number => (t <= 0 ? a : t >= 1 ? b : a + (b - a) * t);

const centerOf = (box: MagnifierBox): Point => ({
  x: box.left + box.width / 2,
  y: box.top + box.height / 2,
});

const parseHexChannels = (hex: string): [number, number, number] => [
  Number.parseInt(hex.slice(1, 3), 16),
  Number.parseInt(hex.slice(3, 5), 16),
  Number.parseInt(hex.slice(5, 7), 16),
];

const mixHexColor = (fromHex: string, toHex: string, t: number): string => {
  const u = clamp01(t);
  if (u <= 0) return fromHex;
  if (u >= 1) return toHex;
  const from = parseHexChannels(fromHex);
  const to = parseHexChannels(toHex);
  const hex = from
    .map((channel, index) => Math.round(lerp(channel, to[index], u)).toString(16).padStart(2, '0').toUpperCase())
    .join('');
  return `#${hex}`;
};

const closeRetention = (frame: number, close?: WindowRange): number => {
  if (!close || frame <= close.start) return 1;
  if (frame >= close.end) return 0;
  const span = close.end - close.start;
  return span <= 0 ? 0 : 1 - smoothstep((frame - close.start) / span);
};

const magnifierProgress = (frame: number, open: WindowRange, close?: WindowRange): number => {
  if (frame < open.start) return 0;
  if (close && frame >= close.end) return 0;
  const openSpan = open.end - open.start;
  const openT = openSpan <= 0 ? 1 : smoothstep((frame - open.start) / openSpan);
  return openT * closeRetention(frame, close);
};

/**
 * Opacity for the underlying overview diagram during a magnifier zoom:
 * drops smoothly from 1 to `dimmedOpacity` (default 0.16) as the lens opens,
 * and restores back to 1 when `close` completes.
 */
export function magnifierOverviewOpacity(
  frame: number,
  open: {start: number; end: number},
  close?: {start: number; end: number},
  dimmedOpacity = 0.16,
): number {
  const t = magnifierProgress(frame, open, close);
  return 1 + (dimmedOpacity - 1) * t;
}

/** Intersect a ray from `center` along `dir` with an axis-aligned rounded rectangle. */
const rectBoundaryPoint = (
  center: Point,
  halfWidth: number,
  halfHeight: number,
  dir: Point,
  cornerRadius = 0,
): Point => {
  if (halfWidth <= 0 || halfHeight <= 0) return center;
  const len = Math.hypot(dir.x, dir.y);
  const ux = len > 1e-9 ? dir.x / len : 1;
  const uy = len > 1e-9 ? dir.y / len : 0;
  const tx = Math.abs(ux) > 1e-9 ? halfWidth / Math.abs(ux) : Number.POSITIVE_INFINITY;
  const ty = Math.abs(uy) > 1e-9 ? halfHeight / Math.abs(uy) : Number.POSITIVE_INFINITY;
  let s = Math.min(tx, ty);
  const px = s * ux;
  const py = s * uy;
  const r = Math.max(0, Math.min(cornerRadius, halfWidth, halfHeight));
  if (r > 0) {
    const ix = halfWidth - r;
    const iy = halfHeight - r;
    if (Math.abs(px) > ix && Math.abs(py) > iy) {
      const ax = Math.sign(ux) * ix;
      const ay = Math.sign(uy) * iy;
      const b = ux * ax + uy * ay;
      const c = ax * ax + ay * ay - r * r;
      const disc = b * b - c;
      if (disc >= 0) s = b + Math.sqrt(disc);
    }
  }
  return {x: center.x + s * ux, y: center.y + s * uy};
};

/**
 * Medical magnifier zoom per PYH style A section 3b:
 * 1) Locator box highlights `sourceRegion` before opening.
 * 2) Solid `#F7F4EC` lens expands from `sourceRegion` circle to `detailBox` rounded frame
 *    without semi-transparent cross-fading or >1x bitmap scaling.
 * 3) Optional `close` smoothly retracts the lens back to `sourceRegion` before unmounting.
 */
export const MagnifierZoom: React.FC<MagnifierZoomProps> = ({
  sourceRegion,
  detailBox,
  locatorStart,
  open,
  close,
  detailRadius,
  children,
}) => {
  const frame = useCurrentFrame();
  if (frame < locatorStart || (close && frame >= close.end)) return null;

  const fadeFrames = open.start > locatorStart ? Math.min(pyhTiming.labelFadeFrames, open.start - locatorStart) : 0;
  const locatorEnter = fadeFrames > 0 ? smoothstep((frame - locatorStart) / fadeFrames) : 1;
  const closeFactor = closeRetention(frame, close);
  const locatorOpacity = locatorEnter * closeFactor;

  const locator = (
    <div
      data-zoom-locator="true"
      style={{
        position: 'absolute',
        left: sourceRegion.left,
        top: sourceRegion.top,
        width: sourceRegion.width,
        height: sourceRegion.height,
        boxSizing: 'border-box',
        border: `${LOCATOR_STROKE_WIDTH}px solid ${pyhColors.accent}`,
        borderRadius: LOCATOR_RADIUS,
        backgroundColor: 'transparent',
        opacity: locatorOpacity,
        transform: locatorEnter < 1 ? `scale(${(1.06 - 0.06 * locatorEnter).toFixed(4)})` : undefined,
      }}
    />
  );

  if (frame < open.start) {
    return (
      <div data-magnifier-zoom="true" style={{position: 'absolute', inset: 0}}>
        {locator}
      </div>
    );
  }

  const t = magnifierProgress(frame, open, close);
  const sourceCenter = centerOf(sourceRegion);
  const detailCenter = centerOf(detailBox);
  const lensCenter: Point = {
    x: lerp(sourceCenter.x, detailCenter.x, t),
    y: lerp(sourceCenter.y, detailCenter.y, t),
  };

  const sourceDiameter = Math.max(0, sourceRegion.width, sourceRegion.height);
  const lensWidth = lerp(sourceDiameter, detailBox.width, t);
  const lensHeight = lerp(sourceDiameter, detailBox.height, t);
  const lensLeft = lensCenter.x - lensWidth / 2;
  const lensTop = lensCenter.y - lensHeight / 2;

  const targetRadius = detailRadius ?? pyhStroke.radius;
  const currentRadiusPx = lerp(Math.min(lensWidth, lensHeight) / 2, targetRadius, t);
  const borderRadius = t === 0 ? '50%' : currentRadiusPx;
  const borderColor = mixHexColor(pyhColors.accent, pyhColors.ink, t);

  const rawDx = lensCenter.x - sourceCenter.x;
  const rawDy = lensCenter.y - sourceCenter.y;
  const fallbackDx = detailCenter.x - sourceCenter.x;
  const fallbackDy = detailCenter.y - sourceCenter.y;
  const leaderDir: Point =
    Math.hypot(rawDx, rawDy) > 1e-6
      ? {x: rawDx, y: rawDy}
      : Math.hypot(fallbackDx, fallbackDy) > 1e-6
        ? {x: fallbackDx, y: fallbackDy}
        : {x: 1, y: 0};

  const leaderFrom = rectBoundaryPoint(
    sourceCenter,
    sourceRegion.width / 2,
    sourceRegion.height / 2,
    leaderDir,
    LOCATOR_RADIUS,
  );
  const leaderTo = rectBoundaryPoint(
    lensCenter,
    lensWidth / 2,
    lensHeight / 2,
    {x: -leaderDir.x, y: -leaderDir.y},
    currentRadiusPx,
  );

  // Subtract border width so the 1920x1080 child canvas aligns at 0px error inside a border-box lens.
  const contentLeft = lensWidth / 2 - detailCenter.x - pyhStroke.width;
  const contentTop = lensHeight / 2 - detailCenter.y - pyhStroke.width;

  return (
    <div data-magnifier-zoom="true" style={{position: 'absolute', inset: 0}}>
      {locator}
      <svg
        width={FRAME_WIDTH}
        height={FRAME_HEIGHT}
        viewBox={`0 0 ${FRAME_WIDTH} ${FRAME_HEIGHT}`}
        style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}
      >
        <line
          data-magnifier-leader="true"
          x1={leaderFrom.x}
          y1={leaderFrom.y}
          x2={leaderTo.x}
          y2={leaderTo.y}
          stroke={borderColor}
          strokeWidth={LEADER_STROKE_WIDTH}
          strokeLinecap="round"
          opacity={close ? closeFactor : 1}
        />
      </svg>
      <div
        data-magnifier-lens="true"
        style={{
          position: 'absolute',
          left: lensLeft,
          top: lensTop,
          width: lensWidth,
          height: lensHeight,
          borderRadius,
          overflow: 'hidden',
          backgroundColor: pyhColors.background,
          opacity: 1,
          boxSizing: 'border-box',
          border: `${pyhStroke.width}px solid ${borderColor}`,
        }}
      >
        <div
          data-magnifier-content="true"
          style={{
            position: 'absolute',
            width: FRAME_WIDTH,
            height: FRAME_HEIGHT,
            left: contentLeft,
            top: contentTop,
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
};
