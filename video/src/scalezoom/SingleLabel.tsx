import React from 'react';
import {
  ENTITY_COLORS,
  surfaceCardBackgroundHex,
  surfaceLabelTextHex,
  type ScaleSurface,
} from '../anatomy/entityColors';
import {brand} from '../anatomy/palette';
import {FONT_FAMILY} from '../fonts';
import {boxesIntersect, type Box} from '../layout';
import {hexToRgba} from '../style/pyhStyle';

export const MAX_SCALEZOOM_LABELS = 6;

export type LabelCandidate = {
  readonly id: string;
  readonly text: string;
  readonly anchorX: number;
  readonly anchorY: number;
  readonly preferredX: number;
  readonly preferredY: number;
  readonly primary: boolean;
};

export type PlacedLabel = {
  readonly id: string;
  readonly text: string;
  readonly primary: boolean;
  readonly anchorX: number;
  readonly anchorY: number;
  readonly box: Box;
};

const estimateLabelBox = (text: string, primary: boolean): {width: number; height: number} => {
  const fontSize = primary ? 26 : 20;
  const charCount = Array.from(text).length;
  const width = Math.max(primary ? 160 : 124, Math.min(380, Math.round(charCount * fontSize * 0.62 + 36)));
  const height = primary ? 54 : 42;
  return {width, height};
};

const clampBoxToBounds = (box: Box, bounds: Box): Box => ({
  left: Math.max(bounds.left, Math.min(bounds.left + bounds.width - box.width, box.left)),
  top: Math.max(bounds.top, Math.min(bounds.top + bounds.height - box.height, box.top)),
  width: box.width,
  height: box.height,
});

const padded = (box: Box, gap: number): Box => ({
  left: box.left - gap,
  top: box.top - gap,
  width: box.width + gap * 2,
  height: box.height + gap * 2,
});

export type LeaderSegment = {
  readonly x1: number;
  readonly y1: number;
  readonly x2: number;
  readonly y2: number;
};

export const leaderSegmentForBox = (box: Box, anchorX: number, anchorY: number): LeaderSegment => {
  const startX = Math.max(box.left, Math.min(box.left + box.width, anchorX));
  const startY =
    anchorY < box.top
      ? box.top
      : anchorY > box.top + box.height
        ? box.top + box.height
        : box.top + box.height / 2;
  return {x1: startX, y1: startY, x2: anchorX, y2: anchorY};
};

export const leaderSegmentForLabel = (label: PlacedLabel): LeaderSegment =>
  leaderSegmentForBox(label.box, label.anchorX, label.anchorY);

const pointInBox = (px: number, py: number, box: Box): boolean =>
  px >= box.left && px <= box.left + box.width && py >= box.top && py <= box.top + box.height;

const orientation = (
  ax: number,
  ay: number,
  bx: number,
  by: number,
  cx: number,
  cy: number,
): number => (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);

const onSegment = (
  ax: number,
  ay: number,
  bx: number,
  by: number,
  px: number,
  py: number,
): boolean =>
  px >= Math.min(ax, bx) - 1e-6 &&
  px <= Math.max(ax, bx) + 1e-6 &&
  py >= Math.min(ay, by) - 1e-6 &&
  py <= Math.max(ay, by) + 1e-6;

/** Exact 2D closed line-segment intersection test. */
export const segmentsIntersect = (a: LeaderSegment, b: LeaderSegment): boolean => {
  const o1 = orientation(a.x1, a.y1, a.x2, a.y2, b.x1, b.y1);
  const o2 = orientation(a.x1, a.y1, a.x2, a.y2, b.x2, b.y2);
  const o3 = orientation(b.x1, b.y1, b.x2, b.y2, a.x1, a.y1);
  const o4 = orientation(b.x1, b.y1, b.x2, b.y2, a.x2, a.y2);

  if (((o1 > 0 && o2 < 0) || (o1 < 0 && o2 > 0)) && ((o3 > 0 && o4 < 0) || (o3 < 0 && o4 > 0))) {
    return true;
  }
  if (Math.abs(o1) < 1e-6 && onSegment(a.x1, a.y1, a.x2, a.y2, b.x1, b.y1)) return true;
  if (Math.abs(o2) < 1e-6 && onSegment(a.x1, a.y1, a.x2, a.y2, b.x2, b.y2)) return true;
  if (Math.abs(o3) < 1e-6 && onSegment(b.x1, b.y1, b.x2, b.y2, a.x1, a.y1)) return true;
  if (Math.abs(o4) < 1e-6 && onSegment(b.x1, b.y1, b.x2, b.y2, a.x2, a.y2)) return true;
  return false;
};

/** Exact Liang-Barsky segment vs axis-aligned box intersection test. */
export const segmentIntersectsBox = (seg: LeaderSegment, box: Box): boolean => {
  const minX = box.left;
  const maxX = box.left + box.width;
  const minY = box.top;
  const maxY = box.top + box.height;
  const dx = seg.x2 - seg.x1;
  const dy = seg.y2 - seg.y1;
  let t0 = 0;
  let t1 = 1;
  const checks: readonly [number, number][] = [
    [-dx, seg.x1 - minX],
    [dx, maxX - seg.x1],
    [-dy, seg.y1 - minY],
    [dy, maxY - seg.y1],
  ];
  for (const [p, q] of checks) {
    if (Math.abs(p) < 1e-9) {
      if (q < 0) return false;
    } else {
      const r = q / p;
      if (p < 0) {
        if (r > t1) return false;
        if (r > t0) t0 = r;
      } else {
        if (r < t0) return false;
        if (r < t1) t1 = r;
      }
    }
  }
  return t0 <= t1;
};

/**
 * Pure deterministic layout resolver:
 * - Enforces at most MAX_SCALEZOOM_LABELS (6) unique labels.
 * - Places primary label first, then resolves any bounding-box overlaps against placed labels
 *   and reserved obstacles (e.g. ScaleBar, mascot, caption band).
 * - Also avoids leader lines cutting through leaderObstacles (arrows, particles, key objects),
 *   other label boxes, or other leader lines.
 */
export const resolveNonOverlappingLabels = (
  candidates: readonly LabelCandidate[],
  bounds: Box,
  obstacles: readonly Box[] = [],
  leaderObstacles: readonly Box[] = [],
): readonly PlacedLabel[] => {
  const unique: LabelCandidate[] = [];
  const seen = new Set<string>();
  const ordered = [...candidates].sort((a, b) => Number(b.primary) - Number(a.primary));
  for (const item of ordered) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    unique.push(item);
    if (unique.length >= MAX_SCALEZOOM_LABELS) break;
  }

  const placed: PlacedLabel[] = [];
  const gap = 10;

  const boxCollides = (candidateBox: Box): boolean => {
    const check = padded(candidateBox, gap);
    for (const obs of obstacles) {
      if (boxesIntersect(check, obs)) return true;
    }
    for (const prev of placed) {
      if (boxesIntersect(check, prev.box)) return true;
    }
    return false;
  };

  const leaderCollides = (candidateBox: Box, anchorX: number, anchorY: number): boolean => {
    const seg = leaderSegmentForBox(candidateBox, anchorX, anchorY);
    for (const obs of leaderObstacles) {
      // If the pin anchor intentionally points inside this region, don't reject on that region alone.
      if (pointInBox(anchorX, anchorY, obs)) continue;
      if (segmentIntersectsBox(seg, padded(obs, 4))) return true;
    }
    for (const prev of placed) {
      if (segmentIntersectsBox(seg, padded(prev.box, 2))) return true;
      const prevSeg = leaderSegmentForLabel(prev);
      if (segmentsIntersect(seg, prevSeg)) return true;
      // Ensure previous leader doesn't cut through this new label box either.
      if (segmentIntersectsBox(prevSeg, padded(candidateBox, 2))) return true;
    }
    return false;
  };

  const collides = (candidateBox: Box, anchorX: number, anchorY: number, checkLeader: boolean): boolean =>
    boxCollides(candidateBox) || (checkLeader && leaderCollides(candidateBox, anchorX, anchorY));

  const offsets: readonly [number, number][] = [
    [0, 0],
    [0, -68],
    [0, 68],
    [150, 0],
    [-150, 0],
    [0, -132],
    [0, 132],
    [150, -68],
    [-150, -68],
    [150, 68],
    [-150, 68],
    [0, -196],
    [0, 196],
    [260, 0],
    [-260, 0],
    [260, -96],
    [-260, -96],
    [260, 96],
    [-260, 96],
    [0, -256],
    [0, 256],
  ];

  for (const item of unique) {
    const {width, height} = estimateLabelBox(item.text, item.primary);
    const baseBox: Box = {
      left: item.preferredX - width / 2,
      top: item.preferredY - height / 2,
      width,
      height,
    };
    const anchorBox: Box = {
      left: item.anchorX - width / 2,
      top: item.anchorY - height / 2,
      width,
      height,
    };

    let chosen = clampBoxToBounds(baseBox, bounds);
    let found = !collides(chosen, item.anchorX, item.anchorY, true);

    // 1. Try offsets around preferred position and around anchor with strict leader-clearance check.
    if (!found) {
      for (const origin of [baseBox, anchorBox]) {
        for (const [dx, dy] of offsets) {
          const trial = clampBoxToBounds(
            {left: origin.left + dx, top: origin.top + dy, width, height},
            bounds,
          );
          if (!collides(trial, item.anchorX, item.anchorY, true)) {
            chosen = trial;
            found = true;
            break;
          }
        }
        if (found) break;
      }
    }

    // 2. Deterministic grid scan with strict leader-clearance check.
    if (!found) {
      outerStrict: for (let y = bounds.top; y <= bounds.top + bounds.height - height; y += height + gap) {
        for (let x = bounds.left; x <= bounds.left + bounds.width - width; x += Math.max(48, Math.floor(width / 2))) {
          const trial: Box = {left: x, top: y, width, height};
          if (!collides(trial, item.anchorX, item.anchorY, true)) {
            chosen = trial;
            found = true;
            break outerStrict;
          }
        }
      }
    }

    // 3. Fallback: relax leader-obstacle constraint only if strictly no collision-free slot exists anywhere.
    if (!found) {
      outerRelaxed: for (let y = bounds.top; y <= bounds.top + bounds.height - height; y += height + gap) {
        for (let x = bounds.left; x <= bounds.left + bounds.width - width; x += Math.max(48, Math.floor(width / 2))) {
          const trial: Box = {left: x, top: y, width, height};
          if (!collides(trial, item.anchorX, item.anchorY, false)) {
            chosen = trial;
            found = true;
            break outerRelaxed;
          }
        }
      }
    }

    if (found) {
      placed.push({
        id: item.id,
        text: item.text,
        primary: item.primary,
        anchorX: item.anchorX,
        anchorY: item.anchorY,
        box: chosen,
      });
    }
  }

  return placed;
};

export type SingleLabelOverlayProps = {
  labels: readonly PlacedLabel[];
  surface: ScaleSurface;
  width: number;
  height: number;
  pulsePhase: number;
  opacity?: number;
};

/**
 * Screen-space overlay for Scale Zoom labels:
 * - One emphasized primary label with pin + leader line + double-layer focus ring + thin R3.23-style underline.
 * - Optional muted secondary labels (total <= 6), guaranteed non-overlapping.
 */
export const SingleLabelOverlay: React.FC<SingleLabelOverlayProps> = ({
  labels,
  surface,
  width,
  height,
  pulsePhase,
  opacity = 1,
}) => {
  if (!labels.length || opacity <= 0) return null;

  const ink = surfaceLabelTextHex(surface);
  const cardBg = surfaceCardBackgroundHex(surface);
  const ringAccent = ENTITY_COLORS.warning_threshold.hex; // yellow
  const secondaryStroke = ENTITY_COLORS.blood_flow.hex; // teal
  const haloRadius = 18 + Math.sin(pulsePhase * Math.PI * 2) * 5;
  const haloOpacity = 0.42 - Math.sin(pulsePhase * Math.PI * 2) * 0.14;

  return (
    <svg
      data-scalezoom-labels="true"
      data-label-count={labels.length}
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      style={{position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 5, opacity}}
    >
      {labels.map((item) => {
        const {box, anchorX, anchorY, primary} = item;
        const startX = Math.max(box.left, Math.min(box.left + box.width, anchorX));
        const startY =
          anchorY < box.top
            ? box.top
            : anchorY > box.top + box.height
              ? box.top + box.height
              : box.top + box.height / 2;
        const fontSize = primary ? 24 : 18;
        const textY = box.top + box.height / 2 + fontSize * 0.34;
        // R3.23 rule: thin accent underline strictly below text baseline (never obscuring glyphs).
        const underlineY = box.top + box.height - 6;

        return (
          <g
            key={item.id}
            data-scalezoom-label-id={item.id}
            data-scalezoom-primary={primary ? 'true' : 'false'}
            data-label-box={`${Math.round(box.left)} ${Math.round(box.top)} ${Math.round(box.width)} ${Math.round(box.height)}`}
          >
            {/* Double-layer focus ring for the active primary anchor */}
            {primary ? (
              <g data-focus-ring="true">
                <circle
                  cx={anchorX}
                  cy={anchorY}
                  r={haloRadius}
                  fill="none"
                  stroke={ringAccent}
                  strokeWidth={3}
                  opacity={haloOpacity}
                />
                <circle
                  cx={anchorX}
                  cy={anchorY}
                  r={10}
                  fill="none"
                  stroke={ringAccent}
                  strokeWidth={3}
                />
              </g>
            ) : null}

            {/* Leader line with subtle contrast halo */}
            <path
              data-leader-line={item.id}
              d={`M${startX} ${startY} L${anchorX} ${anchorY}`}
              fill="none"
              stroke={surface === 'night' ? brand.night : brand.off_white}
              strokeWidth={5}
              strokeLinecap="round"
            />
            <path
              d={`M${startX} ${startY} L${anchorX} ${anchorY}`}
              fill="none"
              stroke={primary ? ringAccent : ink}
              strokeWidth={primary ? 2.4 : 1.6}
              strokeLinecap="round"
            />

            {/* Pin dot */}
            <circle
              cx={anchorX}
              cy={anchorY}
              r={primary ? 5.5 : 4}
              fill={primary ? ringAccent : secondaryStroke}
              stroke={surface === 'night' ? brand.night : brand.off_white}
              strokeWidth={2}
            />

            {/* Flat one-step shadow behind label pill */}
            <rect
              x={box.left}
              y={box.top + 4}
              width={box.width}
              height={box.height}
              rx={10}
              fill={surface === 'night' ? hexToRgba(brand.night, 0.72) : hexToRgba(brand.navy, 0.16)}
            />

            {/* Label card */}
            <rect
              x={box.left}
              y={box.top}
              width={box.width}
              height={box.height}
              rx={10}
              fill={cardBg}
              stroke={primary ? ringAccent : hexToRgba(ink, 0.35)}
              strokeWidth={primary ? 2.5 : 1.5}
            />

            {/* Thin R3.23-style underline strictly below text baseline for primary label */}
            {primary ? (
              <line
                data-emphasis-underline="true"
                x1={box.left + 18}
                y1={underlineY}
                x2={box.left + box.width - 18}
                y2={underlineY}
                stroke={ringAccent}
                strokeWidth={3.5}
                strokeLinecap="round"
              />
            ) : null}

            <text
              x={box.left + box.width / 2}
              y={textY}
              textAnchor="middle"
              fontFamily={FONT_FAMILY}
              fontSize={fontSize}
              fontWeight={primary ? 800 : 700}
              fill={ink}
            >
              {item.text}
            </text>
          </g>
        );
      })}
    </svg>
  );
};
