import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame} from 'remotion';
import {
  isPortraitLayout,
  R5_MAX_SIMULTANEOUS_LABELS,
  R5_PALETTE,
  r5Clamp01,
  r5EaseInOut,
  r5EaseOut,
  r5Lerp,
  r5PortraitContentBottom,
  resolveR5Layout,
  type R5LayoutInput,
  type R5RevisionAsset,
} from '../components/r5/ScaleChain';
import {FONT_FAMILY} from '../fonts';
import type {Box} from '../layout';
import type {ResolvedR5Shot} from '../types';

export type LeakPhase = 'intact' | 'membrane_change' | 'blood_leak';
export type LeakCompartment = 'intracellular' | 'membrane' | 'bloodstream' | 'vial';
export type LeakEnzymeKind = 'primary' | 'secondary';
export type LeakLabelAnchor = 'cell' | 'membrane' | 'vessel' | 'vial';
export type LeakAssetSlot = 'hepatocyte' | 'mitochondria' | 'vessel' | 'rbc' | 'vial';

export type R5LeakLabel = {
  id: string;
  text: string;
  claimIds: readonly string[];
  startFrame: number;
  endFrame: number;
  anchor?: LeakLabelAnchor;
  /** Optional normalized (0..1) position within stageBox. */
  x?: number;
  y?: number;
  dotColor?: string;
};

export type R5LeakStageActions = {
  intact: number;
  membraneChange: number;
  bloodLeak: number;
};

export type R5LiverLeakSignatureProps = {
  shot: ResolvedR5Shot;
  layout: R5LayoutInput;
  assets: readonly R5RevisionAsset[];
  /** Explicit indices into `shot.actions` for intact -> membraneChange -> bloodLeak. */
  stageActions?: R5LeakStageActions;
  /** Claim-backed labels. If omitted and shot has no label text_windows, no labels render. */
  labels?: readonly R5LeakLabel[];
  /** Optional explicit slot-to-asset mapping (matched by asset.id or asset.path within `assets`). */
  assetRoles?: Partial<Record<LeakAssetSlot, string>>;
  /** Optional explicit frame override for deterministic inspection/testing. */
  frame?: number;
};

export type ResolvedLeakAction = ResolvedR5Shot['actions'][number];

export type ResolvedLeakClock = {
  frame: number;
  phase: LeakPhase;
  intactAction: ResolvedLeakAction;
  membraneAction: ResolvedLeakAction;
  leakAction: ResolvedLeakAction;
  mechanismActionCount: number;
  intactProgress: number;
  membraneChangeProgress: number;
  bloodLeakProgress: number;
  membraneChangeDescription: string;
  membraneOutcome: string;
  leakOutcome: string;
};

export type ResolvedLeakAssets = Record<LeakAssetSlot, R5RevisionAsset | null>;

export type LeakParticleState = {
  id: string;
  kind: LeakEnzymeKind;
  migrates: boolean;
  reachesVial: boolean;
  x: number;
  y: number;
  rot: number;
  compartment: LeakCompartment;
};

export type LeakLabelLayout = {
  id: string;
  text: string;
  claimIds: readonly string[];
  dotColor: string;
  opacity: number;
  box: Box;
};

export type R5LiverLeakGeometry = {
  portrait: boolean;
  frameWidth: number;
  frameHeight: number;
  stageBox: Box;
  cellBox: Box;
  membranePoint: {x: number; y: number};
  vesselBox: Box;
  sampleLoupeCenter: {x: number; y: number; radius: number};
  vialBox: Box;
  clock: ResolvedLeakClock;
  assets: ResolvedLeakAssets;
  particles: LeakParticleState[];
  activeLabels: LeakLabelLayout[];
};

type EnzymeEntitySpec = {
  id: string;
  kind: LeakEnzymeKind;
  /** Normalized coordinates inside cellBox (0..1). */
  nx: number;
  ny: number;
  /** Gentle ambient intracellular drift amplitudes in px. */
  ax: number;
  ay: number;
  fx: number;
  fy: number;
  phase: number;
  migrates: boolean;
  reachesVial: boolean;
  stagger: number;
  /** Offset lane inside vessel / vial (normalized -1..1). */
  lane: number;
};

const ENZYME_ENTITIES: readonly EnzymeEntitySpec[] = [
  {id: 'enzyme-01', kind: 'primary', nx: 0.28, ny: 0.30, ax: 8, ay: 6, fx: 0.042, fy: 0.035, phase: 0.3, migrates: false, reachesVial: false, stagger: 0, lane: -0.6},
  {id: 'enzyme-02', kind: 'primary', nx: 0.66, ny: 0.32, ax: 7, ay: 6, fx: 0.038, fy: 0.044, phase: 1.1, migrates: true, reachesVial: true, stagger: 0.0, lane: -0.45},
  {id: 'enzyme-03', kind: 'primary', nx: 0.56, ny: 0.50, ax: 7, ay: 7, fx: 0.045, fy: 0.032, phase: 2.2, migrates: true, reachesVial: true, stagger: 0.08, lane: 0.0},
  {id: 'enzyme-04', kind: 'primary', nx: 0.70, ny: 0.66, ax: 6, ay: 7, fx: 0.036, fy: 0.047, phase: 3.0, migrates: true, reachesVial: false, stagger: 0.14, lane: 0.45},
  {id: 'enzyme-05', kind: 'primary', nx: 0.34, ny: 0.72, ax: 8, ay: 6, fx: 0.041, fy: 0.039, phase: 4.1, migrates: false, reachesVial: false, stagger: 0, lane: 0.3},
  {id: 'enzyme-06', kind: 'primary', nx: 0.76, ny: 0.48, ax: 6, ay: 6, fx: 0.049, fy: 0.034, phase: 5.0, migrates: true, reachesVial: false, stagger: 0.20, lane: -0.25},
  {id: 'enzyme-07', kind: 'secondary', nx: 0.44, ny: 0.26, ax: 7, ay: 6, fx: 0.039, fy: 0.043, phase: 0.8, migrates: false, reachesVial: false, stagger: 0, lane: 0.5},
  {id: 'enzyme-08', kind: 'secondary', nx: 0.62, ny: 0.42, ax: 6, ay: 7, fx: 0.044, fy: 0.037, phase: 1.9, migrates: true, reachesVial: true, stagger: 0.05, lane: 0.4},
  {id: 'enzyme-09', kind: 'secondary', nx: 0.64, ny: 0.74, ax: 6, ay: 6, fx: 0.037, fy: 0.046, phase: 2.8, migrates: true, reachesVial: false, stagger: 0.17, lane: -0.55},
  {id: 'enzyme-10', kind: 'secondary', nx: 0.26, ny: 0.54, ax: 7, ay: 7, fx: 0.043, fy: 0.041, phase: 3.9, migrates: false, reachesVial: false, stagger: 0, lane: 0.1},
];

const actionProgress = (action: ResolvedLeakAction, frame: number): number => {
  if (frame < action.start_frame) {
    return 0;
  }
  if (frame >= action.end_frame) {
    return 1;
  }
  return r5Clamp01((frame - action.start_frame) / Math.max(1, action.end_frame - action.start_frame));
};

/**
 * Resolves the three mechanism states (intact -> membrane_change -> blood_leak)
 * strictly from explicit `stageActions` indices or the first 3 actions ordered by `start_frame`.
 * Never inspects free-text keywords or infers timing from duration percentages.
 */
export const resolveLeakClock = (
  shot: ResolvedR5Shot,
  frame: number,
  stageActions?: R5LeakStageActions,
): ResolvedLeakClock => {
  const {actions} = shot;
  if (actions.length < 3) {
    throw new Error(
      `R5LiverLeakSignature (${shot.id}) requires at least 3 resolved actions, got ${actions.length}`,
    );
  }

  let intactAction: ResolvedLeakAction;
  let membraneAction: ResolvedLeakAction;
  let leakAction: ResolvedLeakAction;

  if (stageActions) {
    const indices = [stageActions.intact, stageActions.membraneChange, stageActions.bloodLeak];
    for (const idx of indices) {
      if (!Number.isInteger(idx) || idx < 0 || idx >= actions.length) {
        throw new Error(
          `R5LiverLeakSignature (${shot.id}) stageActions index ${idx} is out of range [0..${actions.length - 1}]`,
        );
      }
    }
    if (new Set(indices).size !== 3) {
      throw new Error(
        `R5LiverLeakSignature (${shot.id}) stageActions indices must be distinct`,
      );
    }
    intactAction = actions[stageActions.intact];
    membraneAction = actions[stageActions.membraneChange];
    leakAction = actions[stageActions.bloodLeak];
  } else {
    const sorted = [...actions].sort((a, b) => a.start_frame - b.start_frame);
    [intactAction, membraneAction, leakAction] = sorted;
  }

  if (
    !(intactAction.start_frame < membraneAction.start_frame &&
      membraneAction.start_frame < leakAction.start_frame)
  ) {
    throw new Error(
      `R5LiverLeakSignature (${shot.id}) stage actions must have strictly increasing start_frame (${intactAction.start_frame}, ${membraneAction.start_frame}, ${leakAction.start_frame})`,
    );
  }

  const intactProgress = actionProgress(intactAction, frame);
  const membraneChangeProgress = actionProgress(membraneAction, frame);
  const bloodLeakProgress = actionProgress(leakAction, frame);

  let phase: LeakPhase = 'intact';
  if (frame >= leakAction.start_frame) {
    phase = 'blood_leak';
  } else if (frame >= membraneAction.start_frame) {
    phase = 'membrane_change';
  }

  return {
    frame,
    phase,
    intactAction,
    membraneAction,
    leakAction,
    mechanismActionCount: actions.length,
    intactProgress,
    membraneChangeProgress,
    bloodLeakProgress,
    membraneChangeDescription: membraneAction.change,
    membraneOutcome: membraneAction.outcome,
    leakOutcome: leakAction.outcome,
  };
};

const ASSET_SLOT_PATTERNS: Record<LeakAssetSlot, RegExp> = {
  hepatocyte: /(hepatocyte|tế\s*bào\s*gan)/iu,
  mitochondria: /(mitochondri|ty\s*thể)/iu,
  vessel: /(blood-vessel|vessel|sinusoid|lòng\s*mạch|xoang\s*gan)/iu,
  rbc: /(red-blood-cell|rbc|hồng\s*cầu)/iu,
  vial: /(blood-vial|vial|ống\s*máu|ống\s*nghiệm)/iu,
};

/**
 * Resolves only licensed assets supplied via revision `assets` (and allowed by `shot.asset_paths`
 * when non-empty). Never fabricates or falls back to hardcoded library/cache paths.
 */
export const resolveLeakAssets = (
  shot: ResolvedR5Shot,
  assets: readonly R5RevisionAsset[],
  assetRoles?: Partial<Record<LeakAssetSlot, string>>,
): ResolvedLeakAssets => {
  const allowedPaths = shot.asset_paths.length > 0 ? new Set(shot.asset_paths) : null;
  const pool = allowedPaths ? assets.filter((a) => allowedPaths.has(a.path)) : assets;

  const findSlot = (slot: LeakAssetSlot): R5RevisionAsset | null => {
    const explicit = assetRoles?.[slot];
    if (explicit) {
      return pool.find((a) => a.id === explicit || a.path === explicit) ?? null;
    }
    const pattern = ASSET_SLOT_PATTERNS[slot];
    return (
      pool.find((a) => pattern.test(`${a.id ?? ''} ${a.path} ${a.name ?? ''} ${a.role ?? ''}`)) ??
      null
    );
  };

  return {
    hepatocyte: findSlot('hepatocyte'),
    mitochondria: findSlot('mitochondria'),
    vessel: findSlot('vessel'),
    rbc: findSlot('rbc'),
    vial: findSlot('vial'),
  };
};

const LABEL_PILL_HEIGHT = 50;
const LABEL_PILL_WIDTH = 260;

const labelEnvelope = (frame: number, start: number, end: number): number => {
  if (frame < start || frame >= end) {
    return 0;
  }
  const fade = Math.min(10, Math.max(1, Math.floor((end - start) / 4)));
  const fadeIn = r5EaseOut((frame - start) / fade);
  const fadeOut = 1 - r5EaseOut((frame - (end - fade)) / fade);
  return r5Clamp01(Math.min(fadeIn, fadeOut));
};

const collectLabels = (shot: ResolvedR5Shot, labels?: readonly R5LeakLabel[]): R5LeakLabel[] => {
  if (labels !== undefined) {
    return labels.filter((l) => l.text.trim().length > 0 && l.claimIds.length > 0);
  }
  return shot.text_windows
    .filter((w) => w.kind === 'label' && w.text.trim().length > 0 && w.claim_ids.length > 0)
    .map((w, idx) => ({
      id: `shot-label-${idx}`,
      text: w.text,
      claimIds: w.claim_ids,
      startFrame: w.start_frame,
      endFrame: w.end_frame,
      anchor: (['cell', 'membrane', 'vessel', 'vial'] as const)[idx % 4],
    }));
};

const anchorCenter = (
  anchor: LeakLabelAnchor,
  cellBox: Box,
  membranePoint: {x: number; y: number},
  vesselBox: Box,
  vialBox: Box,
  portrait: boolean,
): {x: number; y: number} => {
  switch (anchor) {
    case 'cell':
      return {x: cellBox.left + cellBox.width * 0.45, y: cellBox.top + 36};
    case 'membrane':
      return portrait
        ? {x: membranePoint.x + 190, y: membranePoint.y}
        : {x: membranePoint.x, y: cellBox.top + 36};
    case 'vessel':
      return {
        x: vesselBox.left + vesselBox.width * 0.5,
        y: portrait ? vesselBox.top + 34 : vesselBox.top + 48,
      };
    case 'vial':
      return {
        x: vialBox.left + vialBox.width * 0.5,
        y: vialBox.top - 32,
      };
  }
};

export const computeR5LiverLeakGeometry = (
  props: Pick<
    R5LiverLeakSignatureProps,
    'shot' | 'layout' | 'assets' | 'stageActions' | 'labels' | 'assetRoles' | 'frame'
  >,
): R5LiverLeakGeometry => {
  const layout = resolveR5Layout(props.layout);
  const portrait = isPortraitLayout(layout);
  const frameWidth = layout.frame.width;
  const frameHeight = layout.frame.height;
  const effectiveFrame = props.frame ?? props.shot.start_frame;

  const clock = resolveLeakClock(props.shot, effectiveFrame, props.stageActions);
  const resolvedAssets = resolveLeakAssets(props.shot, props.assets, props.assetRoles);

  const portraitBottom = r5PortraitContentBottom(layout);
  const stageBox: Box = portrait
    ? {
        left: 44,
        top: 176,
        width: frameWidth - 88,
        height: Math.min(1196, portraitBottom - 176 - 16),
      }
    : {
        left: 64,
        top: 108,
        width: frameWidth - 128,
        height: frameHeight - 196,
      };

  const cellBox: Box = portrait
    ? {
        left: stageBox.left + 126,
        top: stageBox.top + 34,
        width: stageBox.width - 252,
        height: 380,
      }
    : {
        left: stageBox.left + 96,
        top: stageBox.top + 102,
        width: 620,
        height: 640,
      };

  const membranePoint = portrait
    ? {x: cellBox.left + cellBox.width / 2, y: cellBox.top + cellBox.height - 6}
    : {x: cellBox.left + cellBox.width - 6, y: cellBox.top + cellBox.height / 2};

  const vesselBox: Box = portrait
    ? {
        left: stageBox.left + 40,
        top: cellBox.top + cellBox.height + 64,
        width: stageBox.width - 80,
        height: 190,
      }
    : {
        left: cellBox.left + cellBox.width + 104,
        top: stageBox.top + 20,
        width: 220,
        height: stageBox.height - 40,
      };

  const sampleLoupeCenter = portrait
    ? {
        x: stageBox.left + stageBox.width * 0.36,
        y: Math.min(vesselBox.top + vesselBox.height + 216, stageBox.top + stageBox.height - 128),
        radius: 94,
      }
    : {
        x: vesselBox.left + vesselBox.width + 290,
        y: cellBox.top + cellBox.height / 2,
        radius: 112,
      };

  const vialBox: Box = portrait
    ? {
        left: stageBox.left + stageBox.width * 0.62,
        top: sampleLoupeCenter.y - 126,
        width: 170,
        height: 252,
      }
    : {
        left: sampleLoupeCenter.x + sampleLoupeCenter.radius + 78,
        top: sampleLoupeCenter.y - 180,
        width: 170,
        height: 360,
      };

  // Compute deterministic positions for the same enzyme entities across all 3 mechanism states.
  const particles: LeakParticleState[] = ENZYME_ENTITIES.map((spec, idx) => {
    const padX = cellBox.width * 0.14;
    const padY = cellBox.height * 0.16;
    const homeX = cellBox.left + padX + spec.nx * (cellBox.width - padX * 2);
    const homeY = cellBox.top + padY + spec.ny * (cellBox.height - padY * 2);
    const driftX = Math.sin(effectiveFrame * spec.fx + spec.phase) * spec.ax;
    const driftY = Math.cos(effectiveFrame * spec.fy + spec.phase * 1.3) * spec.ay;

    let x = Math.max(cellBox.left + 28, Math.min(cellBox.left + cellBox.width - 28, homeX + driftX));
    let y = Math.max(cellBox.top + 28, Math.min(cellBox.top + cellBox.height - 28, homeY + driftY));
    let compartment: LeakCompartment = 'intracellular';

    const gateX = portrait ? membranePoint.x + spec.lane * 56 : membranePoint.x - 12;
    const gateY = portrait ? membranePoint.y - 12 : membranePoint.y + spec.lane * 56;

    if (spec.migrates && clock.membraneChangeProgress > 0) {
      const mT = r5EaseInOut(clock.membraneChangeProgress);
      x = r5Lerp(x, gateX, mT * 0.88);
      y = r5Lerp(y, gateY, mT * 0.88);
      if (clock.membraneChangeProgress >= 0.45) {
        compartment = 'membrane';
      }
    }

    if (spec.migrates && clock.bloodLeakProgress > 0) {
      const p = r5Clamp01((clock.bloodLeakProgress - spec.stagger) / Math.max(0.05, 1 - spec.stagger));
      const vesselEntryX = portrait
        ? membranePoint.x + spec.lane * 84
        : vesselBox.left + vesselBox.width * 0.5 + spec.lane * 54;
      const vesselEntryY = portrait
        ? vesselBox.top + vesselBox.height * 0.5 + spec.lane * 42
        : membranePoint.y + spec.lane * 76;

      if (p < 0.45) {
        const t = r5EaseInOut(p / 0.45);
        x = r5Lerp(gateX, vesselEntryX, t);
        y = r5Lerp(gateY, vesselEntryY, t);
        compartment = p >= 0.25 ? 'bloodstream' : 'membrane';
      } else {
        const t = r5EaseInOut((p - 0.45) / 0.55);
        if (spec.reachesVial) {
          const angle = (idx * 2.1) % (Math.PI * 2);
          const targetX = sampleLoupeCenter.x + Math.cos(angle) * (sampleLoupeCenter.radius * 0.48);
          const targetY = sampleLoupeCenter.y + Math.sin(angle) * (sampleLoupeCenter.radius * 0.48);
          x = r5Lerp(vesselEntryX, targetX, t);
          y = r5Lerp(vesselEntryY, targetY, t);
          compartment = p >= 0.72 ? 'vial' : 'bloodstream';
        } else {
          const downstreamX = portrait
            ? r5Lerp(vesselEntryX, vesselBox.left + vesselBox.width - 72, t)
            : vesselEntryX + Math.sin(effectiveFrame * 0.04 + idx) * 8;
          const downstreamY = portrait
            ? vesselEntryY + Math.cos(effectiveFrame * 0.04 + idx) * 8
            : r5Lerp(vesselEntryY, vesselBox.top + 96 + (idx % 3) * 44, t);
          x = downstreamX;
          y = downstreamY;
          compartment = 'bloodstream';
        }
      }
    }

    const rot = (effectiveFrame * (spec.kind === 'primary' ? 1.2 : -1.0) + spec.phase * 40) % 360;
    return {
      id: spec.id,
      kind: spec.kind,
      migrates: spec.migrates,
      reachesVial: spec.reachesVial,
      x,
      y,
      rot,
      compartment,
    };
  });

  // Resolve active claim-backed labels, capped at R5_MAX_SIMULTANEOUS_LABELS and clamped above portrait captions.
  const maxLabelBottom = portrait ? portraitBottom - 12 : frameHeight - 24;
  const candidateLabels = collectLabels(props.shot, props.labels);
  const activeLabels: LeakLabelLayout[] = [];

  for (const item of candidateLabels) {
    const opacity = labelEnvelope(effectiveFrame, item.startFrame, item.endFrame);
    if (opacity <= 0.01) {
      continue;
    }
    const baseCenter =
      item.x !== undefined && item.y !== undefined
        ? {
            x: stageBox.left + r5Clamp01(item.x) * stageBox.width,
            y: stageBox.top + r5Clamp01(item.y) * stageBox.height,
          }
        : anchorCenter(item.anchor ?? 'cell', cellBox, membranePoint, vesselBox, vialBox, portrait);

    const left = Math.max(
      stageBox.left + 12,
      Math.min(baseCenter.x - LABEL_PILL_WIDTH / 2, stageBox.left + stageBox.width - LABEL_PILL_WIDTH - 12),
    );
    const top = Math.max(
      stageBox.top + 12,
      Math.min(baseCenter.y - LABEL_PILL_HEIGHT / 2, Math.min(stageBox.top + stageBox.height, maxLabelBottom) - LABEL_PILL_HEIGHT - 12),
    );

    activeLabels.push({
      id: item.id,
      text: item.text,
      claimIds: item.claimIds,
      dotColor: item.dotColor ?? R5_PALETTE.teal,
      opacity,
      box: {left, top, width: LABEL_PILL_WIDTH, height: LABEL_PILL_HEIGHT},
    });

    if (activeLabels.length >= R5_MAX_SIMULTANEOUS_LABELS) {
      break;
    }
  }

  return {
    portrait,
    frameWidth,
    frameHeight,
    stageBox,
    cellBox,
    membranePoint,
    vesselBox,
    sampleLoupeCenter,
    vialBox,
    clock,
    assets: resolvedAssets,
    particles,
    activeLabels,
  };
};

const EnzymeGlyph: React.FC<{
  particle: LeakParticleState;
  r?: number;
}> = ({particle, r = 15}) => {
  const fill = particle.kind === 'primary' ? R5_PALETTE.teal : R5_PALETTE.yellow;
  return (
    <g
      data-enzyme-id={particle.id}
      data-enzyme-kind={particle.kind}
      data-enzyme-compartment={particle.compartment}
      transform={`translate(${particle.x.toFixed(1)}, ${particle.y.toFixed(1)}) rotate(${particle.rot.toFixed(1)})`}
    >
      {particle.kind === 'primary' ? (
        <>
          <rect x={-r - 3} y={-3} width={(r + 3) * 2} height={6} rx={3} fill={R5_PALETTE.navy} />
          <rect x={-3} y={-r - 3} width={6} height={(r + 3) * 2} rx={3} fill={R5_PALETTE.navy} />
          <circle cx={0} cy={0} r={r} fill={fill} stroke={R5_PALETTE.navy} strokeWidth={3} />
          <circle cx={0} cy={0} r={r * 0.36} fill={R5_PALETTE.bg} />
        </>
      ) : (
        <>
          <circle cx={0} cy={0} r={r} fill={fill} stroke={R5_PALETTE.navy} strokeWidth={3} />
          <polygon
            points={`0,${-r * 0.56} ${r * 0.52},0 0,${r * 0.56} ${-r * 0.52},0`}
            fill={R5_PALETTE.bg}
            stroke={R5_PALETTE.navy}
            strokeWidth={1.8}
          />
        </>
      )}
    </g>
  );
};

/**
 * R5 production liver-enzyme-leak mechanism rig.
 * - Clock is driven strictly by resolved action frame intervals (never duration percentages).
 * - Uses only licensed revision assets passed via props (no hardcoded library/cache paths).
 * - Preserves the same enzyme particle entities across intact -> membrane_change -> blood_leak.
 * - Supports both 16:9 landscape and 9:16 portrait while keeping all labels clear of portrait captions.
 */
export const R5LiverLeakSignature: React.FC<R5LiverLeakSignatureProps> = ({
  shot,
  layout: layoutInput,
  assets,
  stageActions,
  labels,
  assetRoles,
  frame,
}) => {
  const currentFrame = useCurrentFrame();
  const effectiveFrame = frame ?? currentFrame;

  const geom = computeR5LiverLeakGeometry({
    shot,
    layout: layoutInput,
    assets,
    stageActions,
    labels,
    assetRoles,
    frame: effectiveFrame,
  });

  const {
    portrait,
    frameWidth,
    frameHeight,
    cellBox,
    membranePoint,
    vesselBox,
    sampleLoupeCenter,
    vialBox,
    clock,
    assets: resolvedAssets,
    particles,
    activeLabels,
  } = geom;

  const membraneT = r5EaseOut(clock.membraneChangeProgress);
  const leakT = r5EaseOut(clock.bloodLeakProgress);

  // Ambient RBCs inside the vessel when a licensed RBC asset is provided.
  // Purely ambient visual continuity — never alters mechanism state.
  const rbcCount = 5;
  const rbcs = resolvedAssets.rbc
    ? Array.from({length: rbcCount}, (_, i) => {
        const t = ((effectiveFrame * 0.004 + i / rbcCount) % 1 + 1) % 1;
        const size = portrait ? 48 : 56;
        const x = portrait
          ? r5Lerp(vesselBox.left + 32, vesselBox.left + vesselBox.width - 32, t)
          : vesselBox.left + vesselBox.width * 0.5 + ((i % 3) - 1) * 34;
        const y = portrait
          ? vesselBox.top + vesselBox.height * 0.5 + ((i % 3) - 1) * 28
          : r5Lerp(vesselBox.top + vesselBox.height - 32, vesselBox.top + 32, t);
        const rot = Math.sin(effectiveFrame * 0.05 + i) * 16;
        return {id: i, x, y, size, rot};
      })
    : [];

  // Subtle mitochondria inside hepatocyte cytosol when a licensed mitochondria asset is provided.
  const mitoSpots = resolvedAssets.mitochondria
    ? [
        {x: cellBox.left + cellBox.width * 0.28, y: cellBox.top + cellBox.height * 0.34, size: portrait ? 72 : 92, rot: -22},
        {x: cellBox.left + cellBox.width * 0.34, y: cellBox.top + cellBox.height * 0.72, size: portrait ? 68 : 86, rot: 20},
      ]
    : [];

  // Connector path from vessel to blood sample loupe.
  const vesselToSamplePath = portrait
    ? `M ${sampleLoupeCenter.x.toFixed(1)} ${(vesselBox.top + vesselBox.height).toFixed(1)} L ${sampleLoupeCenter.x.toFixed(1)} ${(sampleLoupeCenter.y - sampleLoupeCenter.radius - 8).toFixed(1)}`
    : `M ${(vesselBox.left + vesselBox.width).toFixed(1)} ${sampleLoupeCenter.y.toFixed(1)} L ${(sampleLoupeCenter.x - sampleLoupeCenter.radius - 8).toFixed(1)} ${sampleLoupeCenter.y.toFixed(1)}`;

  // Connector path from membrane opening into blood vessel.
  const membraneToVesselPath = portrait
    ? `M ${membranePoint.x.toFixed(1)} ${(membranePoint.y + 8).toFixed(1)} L ${membranePoint.x.toFixed(1)} ${(vesselBox.top - 6).toFixed(1)}`
    : `M ${(membranePoint.x + 8).toFixed(1)} ${membranePoint.y.toFixed(1)} L ${(vesselBox.left - 6).toFixed(1)} ${membranePoint.y.toFixed(1)}`;

  const membraneStrokeColor = membraneT > 0.05 ? R5_PALETTE.alert : R5_PALETTE.teal;

  return (
    <AbsoluteFill
      data-r5-component="R5LiverLeakSignature"
      data-shot-id={shot.id}
      data-layout={portrait ? '9:16' : '16:9'}
      data-leak-phase={clock.phase}
      data-membrane-change={clock.membraneChangeDescription ?? ''}
      data-mechanism-steps={String(clock.mechanismActionCount)}
      style={{
        backgroundColor: R5_PALETTE.bg,
        fontFamily: FONT_FAMILY,
        overflow: 'hidden',
      }}
    >
      {/* Layer 1: Licensed revision assets (hepatocyte, vessel, mitochondria, RBCs, blood vial) */}
      <div data-layer="licensed-assets" style={{position: 'absolute', inset: 0}}>
        {/* Blood vessel backdrop container */}
        <div
          data-compartment="bloodstream"
          style={{
            position: 'absolute',
            left: vesselBox.left,
            top: vesselBox.top,
            width: vesselBox.width,
            height: vesselBox.height,
            borderRadius: 36,
            backgroundColor: '#FCEBED',
            border: '6px solid #C9646F',
            overflow: 'hidden',
            boxSizing: 'border-box',
          }}
        >
          {resolvedAssets.vessel ? (
            <Img
              src={staticFile(resolvedAssets.vessel.path)}
              data-asset-slot="vessel"
              style={{
                position: 'absolute',
                inset: 0,
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                opacity: 0.32,
              }}
            />
          ) : null}
        </div>

        {/* Licensed hepatocyte artwork (never hand-drawn SVG body when licensed asset is supplied) */}
        <div
          data-compartment="intracellular"
          style={{
            position: 'absolute',
            left: cellBox.left,
            top: cellBox.top,
            width: cellBox.width,
            height: cellBox.height,
          }}
        >
          {resolvedAssets.hepatocyte ? (
            <Img
              src={staticFile(resolvedAssets.hepatocyte.path)}
              data-asset-slot="hepatocyte"
              style={{
                position: 'absolute',
                inset: 0,
                width: '100%',
                height: '100%',
                objectFit: 'contain',
              }}
            />
          ) : null}
        </div>

        {/* Licensed mitochondria inside cytosol */}
        {mitoSpots.map((m, idx) =>
          resolvedAssets.mitochondria ? (
            <Img
              key={`mito-${idx}`}
              src={staticFile(resolvedAssets.mitochondria.path)}
              data-asset-slot="mitochondria"
              style={{
                position: 'absolute',
                left: m.x - m.size / 2,
                top: m.y - m.size / 2,
                width: m.size,
                height: m.size,
                opacity: 0.72,
                objectFit: 'contain',
                transform: `rotate(${m.rot}deg)`,
              }}
            />
          ) : null,
        )}

        {/* Flowing licensed RBCs inside the blood vessel */}
        {rbcs.map((rbc) =>
          resolvedAssets.rbc ? (
            <Img
              key={`rbc-${rbc.id}`}
              src={staticFile(resolvedAssets.rbc.path)}
              data-asset-slot="rbc"
              style={{
                position: 'absolute',
                left: rbc.x - rbc.size / 2,
                top: rbc.y - rbc.size / 2,
                width: rbc.size,
                height: rbc.size,
                objectFit: 'contain',
                transform: `rotate(${rbc.rot.toFixed(1)}deg)`,
              }}
            />
          ) : null,
        )}

        {/* Licensed blood test vial */}
        {resolvedAssets.vial ? (
          <Img
            src={staticFile(resolvedAssets.vial.path)}
            data-asset-slot="vial"
            data-compartment="vial"
            style={{
              position: 'absolute',
              left: vialBox.left,
              top: vialBox.top,
              width: vialBox.width,
              height: vialBox.height,
              objectFit: 'contain',
              opacity: r5Lerp(0.45, 1, leakT),
            }}
          />
        ) : null}
      </div>

      {/* Layer 2: Vector Remotion overlay — ONLY membrane, directional arrows, sample loupe, and enzyme particles */}
      <svg
        width={frameWidth}
        height={frameHeight}
        viewBox={`0 0 ${frameWidth} ${frameHeight}`}
        style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}
      >
        <defs>
          <marker
            id="r5-leak-arrow"
            viewBox="0 0 12 12"
            refX="10"
            refY="6"
            markerWidth="8"
            markerHeight="8"
            orient="auto"
          >
            <path d="M 0 1 L 11 6 L 0 11 z" fill={R5_PALETTE.alert} />
          </marker>
          <marker
            id="r5-sample-arrow"
            viewBox="0 0 12 12"
            refX="10"
            refY="6"
            markerWidth="8"
            markerHeight="8"
            orient="auto"
          >
            <path d="M 0 1 L 11 6 L 0 11 z" fill={R5_PALETTE.navy} />
          </marker>
        </defs>

        {/* Plasma membrane contour (intact -> changed permeability opening driven strictly by membraneAction) */}
        <g data-structure="plasma-membrane" data-membrane-state={membraneT > 0.05 ? 'changed' : 'intact'}>
          <rect
            x={cellBox.left + 4}
            y={cellBox.top + 4}
            width={cellBox.width - 8}
            height={cellBox.height - 8}
            rx={64}
            fill="none"
            stroke={membraneStrokeColor}
            strokeWidth={7}
            strokeDasharray={membraneT > 0.05 ? '22 14' : undefined}
            opacity={0.92}
          />
          {membraneT > 0.05 ? (
            <g data-effect="membrane-change-opening" opacity={membraneT}>
              <ellipse
                cx={membranePoint.x}
                cy={membranePoint.y}
                rx={portrait ? 64 : 18}
                ry={portrait ? 18 : 64}
                fill={R5_PALETTE.bg}
              />
              <circle
                cx={membranePoint.x}
                cy={membranePoint.y}
                r={portrait ? 54 : 58}
                fill="none"
                stroke={R5_PALETTE.alert}
                strokeWidth={4}
                strokeDasharray="10 8"
              />
            </g>
          ) : null}
        </g>

        {/* Directional efflux arrow from changed membrane into blood vessel (active during blood_leak) */}
        {leakT > 0.02 ? (
          <path
            data-arrow="membrane-to-vessel"
            d={membraneToVesselPath}
            fill="none"
            stroke={R5_PALETTE.alert}
            strokeWidth={6}
            strokeLinecap="round"
            markerEnd="url(#r5-leak-arrow)"
            opacity={leakT}
          />
        ) : null}

        {/* Blood sample connector arrow + magnified blood sample loupe */}
        <g data-structure="blood-sample" opacity={r5Lerp(0.45, 1, leakT)}>
          <path
            data-arrow="vessel-to-sample"
            d={vesselToSamplePath}
            fill="none"
            stroke={R5_PALETTE.navy}
            strokeWidth={5}
            strokeDasharray="10 10"
            strokeLinecap="round"
            markerEnd="url(#r5-sample-arrow)"
          />
          <circle
            cx={sampleLoupeCenter.x}
            cy={sampleLoupeCenter.y}
            r={sampleLoupeCenter.radius}
            fill="#FCEBED"
            stroke={R5_PALETTE.navy}
            strokeWidth={5}
          />
          <circle
            cx={sampleLoupeCenter.x}
            cy={sampleLoupeCenter.y}
            r={sampleLoupeCenter.radius - 10}
            fill="none"
            stroke="#D97A84"
            strokeWidth={2.5}
            opacity={0.6}
          />
        </g>

        {/* Continuous enzyme particle entities tracked across all 3 mechanism states */}
        <g data-layer="enzyme-particles">
          {particles.map((particle) => (
            <EnzymeGlyph key={particle.id} particle={particle} />
          ))}
        </g>
      </svg>

      {/* Layer 3: Claim-backed floating labels (rendered ONLY when supplied via props or shot text_windows) */}
      {activeLabels.map((lbl) => (
        <div
          key={lbl.id}
          data-leak-label={lbl.id}
          data-claim-ids={lbl.claimIds.join(',')}
          style={{
            position: 'absolute',
            left: lbl.box.left,
            top: lbl.box.top,
            width: lbl.box.width,
            height: lbl.box.height,
            opacity: lbl.opacity,
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 10,
            padding: '6px 16px',
            borderRadius: 999,
            backgroundColor: 'rgba(247, 244, 236, 0.96)',
            border: `3px solid ${R5_PALETTE.navy}`,
            boxShadow: '0 6px 16px rgba(18, 48, 74, 0.12)',
            color: R5_PALETTE.navy,
            fontSize: portrait ? 24 : 26,
            fontWeight: 800,
            boxSizing: 'border-box',
            whiteSpace: 'nowrap',
          }}
        >
          <span
            style={{
              width: 14,
              height: 14,
              borderRadius: 7,
              backgroundColor: lbl.dotColor,
              border: `2px solid ${R5_PALETTE.navy}`,
              flexShrink: 0,
            }}
          />
          <span>{lbl.text}</span>
        </div>
      ))}
    </AbsoluteFill>
  );
};
