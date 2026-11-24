import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {assertNoR5TabLayout} from '../components/AuthoredPanels';
import {Captions, shouldRenderCaptions} from '../components/Captions';
import {CreditCard} from '../components/r5/CreditCard';
import {
  ReferenceDistribution,
  type DistributionBand,
  type DistributionMarker,
  type DistributionPoint,
} from '../components/r5/ReferenceDistribution';
import {
  isPortraitLayout,
  R5_PALETTE,
  r5EaseOut,
  ScaleChain,
  type R5RevisionAsset,
  type ScaleTier,
} from '../components/r5/ScaleChain';
import {TakeawayCard, type TakeawayMascotConfig} from '../components/r5/TakeawayCard';
import {VnLabSheet, type VnLabRow} from '../components/r5/VnLabSheet';
import {ZoomChain, type ZoomAnchor, type ZoomLandmark} from '../components/r5/ZoomChain';
import {useLayout, type FrameLayout} from '../layout';
import {
  R5LiverLeakSignature,
  resolveLeakClock,
  type R5LeakStageActions,
} from '../medanim/R5LiverLeakSignature';
import type {SceneTransitionProps} from '../motion/sceneEnvelope';
import {
  R5_COMPONENT_IDS,
  R5RevisionAssetSchema,
  type R5Contract,
  type ResolvedR5Shot,
  type Scene,
} from '../types';

export type R5ComponentId = (typeof R5_COMPONENT_IDS)[number];

export type R5ShotRenderContext = {
  scene: Scene;
  shot: ResolvedR5Shot;
  previousShot: ResolvedR5Shot | null;
  nextShot: ResolvedR5Shot | null;
  allShots: readonly ResolvedR5Shot[];
  layout: FrameLayout;
  frame: number;
  assets: readonly R5RevisionAsset[];
  r5Contract?: R5Contract | null;
  stageActions?: R5LeakStageActions;
};

export type R5ShotRenderer = (ctx: R5ShotRenderContext) => React.ReactElement;

const failShot = (sceneId: string, shotId: string, reason: string): never => {
  throw new Error(`R5ShotScene (${sceneId}/${shotId}): ${reason}`);
};

const resolveShotAssets = (
  sceneId: string,
  shot: ResolvedR5Shot,
  provided?: readonly R5RevisionAsset[],
): R5RevisionAsset[] => {
  const byPath = new Map((provided ?? []).map((a) => [a.path, a]));
  const paths = shot.asset_paths.length ? shot.asset_paths
    : shot.component === 'CreditCard' ? [...byPath.keys()] : [];
  return paths.map((path) => {
    const asset = byPath.get(path);
    if (!asset) return failShot(sceneId, shot.id, `asset ${path}: missing metadata`);
    if (!asset.license?.trim()) return failShot(sceneId, shot.id, `asset ${path}: missing license`);
    const parsed = R5RevisionAssetSchema.safeParse(asset);
    if (!parsed.success) return failShot(sceneId, shot.id, `asset ${path}: invalid metadata/license`);
    return {...parsed.data, name: parsed.data.title};
  });
};

const extractTiers = (
  shot: ResolvedR5Shot,
  allShots: readonly ResolvedR5Shot[],
): ScaleTier[] => {
  const barWindows = shot.text_windows.filter((w) => w.kind === 'scale_bar');
  if (barWindows.length > 0) {
    const parsed: ScaleTier[] = [];
    const seen = new Set<string>();
    for (const win of barWindows) {
      const parts = win.text
        .split(/\s*(?:→|->)\s*/)
        .map((p) => p.trim())
        .filter(Boolean);
      for (const part of parts) {
        if (!seen.has(part)) {
          seen.add(part);
          parsed.push({id: part, label: part});
        }
      }
    }
    if (parsed.length > 0) return parsed;
  }

  const seen = new Set<string>();
  const tiers: ScaleTier[] = [];
  for (const s of allShots) {
    if (s.tier && !seen.has(s.tier)) {
      seen.add(s.tier);
      tiers.push({id: s.tier, label: s.tier});
    }
  }
  return tiers;
};

const resolveMascotForShot = (
  scene: Scene,
  shot: ResolvedR5Shot,
  assets: readonly R5RevisionAsset[],
): TakeawayMascotConfig | null => {
  const mascotAsset = (scene.visual_assets ?? []).find((a) => a.role === 'mascot');
  if (!mascotAsset) return null;
  const allowed = new Set([...shot.asset_paths, ...assets.map((a) => a.path)]);
  if (!allowed.has(mascotAsset.path)) return null;
  return {
    assetPath: mascotAsset.path,
    pose: mascotAsset.pose ?? 'explain',
    side: 'right',
  };
};

const parseLabRows = (scene: Scene, shot: ResolvedR5Shot): VnLabRow[] => {
  const windows = shot.text_windows.filter((w) => w.kind === 'lab_sheet' || w.kind === 'table');
  if (windows.length === 0) {
    failShot(scene.id, shot.id, 'VnLabSheet requires at least one lab_sheet or table text_window');
  }
  return windows.map((win, idx) => {
    if (win.text.includes('\t')) {
      failShot(scene.id, shot.id, 'VnLabSheet forbids tab-delimited text');
    }
    const parts = win.text.split('|').map((part) => part.trim());
    const analyte = parts[0] || '';
    if (!analyte) {
      failShot(scene.id, shot.id, `VnLabSheet row ${idx} is missing analyte label`);
    }
    const rawFlag = parts[4];
    const flag: 'H' | 'L' | null = rawFlag === 'H' || rawFlag === 'L' ? rawFlag : null;
    return {
      id: `${shot.id}-row-${idx}`,
      analyte,
      result: parts[1] ? parts[1] : null,
      unit: parts[2] ? parts[2] : null,
      referenceRange: parts[3] ? parts[3] : null,
      flag,
      highlight: flag === 'H',
      claimIds: win.claim_ids,
    };
  });
};

const DEFAULT_ILLUSTRATIVE_CURVE: readonly DistributionPoint[] = [
  {x: 0.0, y: 0.04},
  {x: 0.2, y: 0.55},
  {x: 0.42, y: 0.94},
  {x: 0.65, y: 0.52},
  {x: 0.85, y: 0.16},
  {x: 1.0, y: 0.04},
];

const renderScaleChain: R5ShotRenderer = ({scene, shot, allShots, layout, assets, frame}) => {
  const tiers = extractTiers(shot, allShots);
  if (tiers.length === 0) {
    failShot(scene.id, shot.id, 'ScaleChain requires a non-null tier or scale_bar text_window');
  }
  return (
    <ScaleChain
      shot={shot}
      layout={layout}
      assets={assets}
      tiers={tiers}
      activeTierId={shot.tier ?? tiers[0].id}
      frame={frame}
    />
  );
};

const renderZoomChain: R5ShotRenderer = ({
  scene,
  shot,
  previousShot,
  nextShot,
  allShots,
  layout,
  assets,
  frame,
}) => {
  const tier = shot.tier;
  if (!tier) {
    return failShot(scene.id, shot.id, 'ZoomChain requires shot.tier');
  }
  if (shot.asset_paths.length === 0) {
    return failShot(scene.id, shot.id, 'ZoomChain requires at least one licensed asset_path');
  }
  const labelWindows = shot.text_windows.filter((w) => w.kind === 'label');
  const landmarks: ZoomLandmark[] =
    labelWindows.length > 0
      ? labelWindows.map((w, idx) => ({
          id: `${shot.id}-lm-${idx}`,
          label: w.text,
          x: Math.min(0.78, 0.28 + idx * 0.24),
          y: Math.min(0.78, 0.34 + idx * 0.22),
          claimIds: w.claim_ids,
        }))
      : shot.actions.map((action, idx) => ({
          id: `${shot.id}-action-lm-${idx}`,
          label: action.compartment,
          x: Math.min(0.78, 0.3 + idx * 0.22),
          y: Math.min(0.78, 0.36 + idx * 0.2),
          claimIds: [],
        }));

  if (landmarks.length === 0) {
    return failShot(
      scene.id,
      shot.id,
      'ZoomChain requires at least one label text_window or action positioning landmark',
    );
  }

  const fromTierId = previousShot?.tier ?? tier;
  const toTierId = nextShot?.tier ?? tier;
  const fromAnchor: ZoomAnchor = {tierId: fromTierId, x: 0.38, y: 0.46};
  const toAnchor: ZoomAnchor = {tierId: toTierId, x: 0.62, y: 0.54, radius: 48};

  const baseTiers = extractTiers(shot, allShots);
  const tierIds = new Set(baseTiers.map((t) => t.id));
  const tiers: ScaleTier[] = [...baseTiers];
  for (const required of [fromTierId, toTierId]) {
    if (!tierIds.has(required)) {
      tierIds.add(required);
      tiers.push({id: required, label: required});
    }
  }

  return (
    <ZoomChain
      shot={shot}
      layout={layout}
      assets={assets}
      fromAnchor={fromAnchor}
      toAnchor={toAnchor}
      landmarks={landmarks}
      tiers={tiers}
      frame={frame}
    />
  );
};

const renderTakeawayCard: R5ShotRenderer = ({scene, shot, layout, assets, frame}) => {
  const candidates = shot.text_windows.filter(
    (w) => w.kind === 'takeaway' || w.kind === 'question',
  );
  if (candidates.length === 0) {
    failShot(scene.id, shot.id, 'TakeawayCard requires a takeaway or question text_window');
  }
  const active =
    candidates.find((w) => frame >= w.start_frame && frame < w.end_frame) ?? candidates[0];
  const mascot = resolveMascotForShot(scene, shot, assets);

  return (
    <TakeawayCard
      shot={shot}
      layout={layout}
      assets={assets}
      text={active.text}
      claimIds={active.claim_ids}
      tag={active.kind === 'question' ? 'Câu hỏi' : 'Chốt'}
      mascot={mascot}
      frame={frame}
    />
  );
};

const renderVnLabSheet: R5ShotRenderer = ({scene, shot, layout, assets, frame}) => {
  const rows = parseLabRows(scene, shot);
  return (
    <VnLabSheet
      shot={shot}
      layout={layout}
      assets={assets}
      title={scene.on_screen_text ?? 'Kết quả xét nghiệm'}
      rows={rows}
      frame={frame}
    />
  );
};

const renderReferenceDistribution: R5ShotRenderer = ({scene, shot, layout, assets, frame}) => {
  if (shot.text_windows.length === 0 && shot.actions.length === 0) {
    failShot(
      scene.id,
      shot.id,
      'ReferenceDistribution requires at least one text_window or action datum',
    );
  }
  const bandSources =
    shot.text_windows.length > 0
      ? shot.text_windows.map((w) => ({label: w.text, claimIds: w.claim_ids}))
      : shot.actions.map((a) => ({label: a.outcome, claimIds: [] as readonly string[]}));

  const tones: readonly DistributionBand['tone'][] = ['teal', 'yellow', 'navy'];
  const span = 1 / bandSources.length;
  const bands: DistributionBand[] = bandSources.map((item, idx) => ({
    id: `${shot.id}-band-${idx}`,
    label: item.label,
    startX: Number((idx * span).toFixed(3)),
    endX: Number(((idx + 1) * span).toFixed(3)),
    tone: tones[idx % tones.length],
    claimIds: item.claimIds,
  }));

  const markers: DistributionMarker[] = shot.text_windows
    .filter((w) => w.kind === 'label')
    .map((w, idx, arr) => ({
      id: `${shot.id}-marker-${idx}`,
      label: w.text,
      x: (idx + 1) / (arr.length + 1),
      tone: 'alert' as const,
      claimIds: w.claim_ids,
    }));

  return (
    <ReferenceDistribution
      shot={shot}
      layout={layout}
      assets={assets}
      title={scene.on_screen_text ?? 'Phân bố tham chiếu'}
      points={DEFAULT_ILLUSTRATIVE_CURVE}
      bands={bands}
      markers={markers}
      frame={frame}
    />
  );
};

const renderCreditCard: R5ShotRenderer = ({scene, shot, layout, assets, frame}) => {
  const creditAssets = [...assets];
  if (creditAssets.length === 0) {
    failShot(scene.id, shot.id, 'CreditCard requires used asset metadata');
  }

  return (
    <CreditCard
      shot={shot}
      layout={layout}
      assets={creditAssets}
      frame={frame}
    />
  );
};

const renderLiverLeakSignature: R5ShotRenderer = ({
  scene,
  shot,
  layout,
  assets,
  stageActions,
  frame,
}) => {
  try {
    resolveLeakClock(shot, frame, stageActions);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    failShot(scene.id, shot.id, message);
  }
  return (
    <R5LiverLeakSignature
      shot={shot}
      layout={layout}
      assets={assets}
      stageActions={stageActions}
      frame={frame}
    />
  );
};

/** Fixed registry of allowed R5 shot components. Unknown component IDs always fail closed. */
export const R5_COMPONENT_REGISTRY: Readonly<Record<R5ComponentId, R5ShotRenderer>> = Object.freeze({
  ScaleChain: renderScaleChain,
  ZoomChain: renderZoomChain,
  TakeawayCard: renderTakeawayCard,
  VnLabSheet: renderVnLabSheet,
  ReferenceDistribution: renderReferenceDistribution,
  CreditCard: renderCreditCard,
  R5LiverLeakSignature: renderLiverLeakSignature,
});

export type ActiveR5ShotResolution = {
  shots: readonly ResolvedR5Shot[];
  activeShot: ResolvedR5Shot;
  activeIndex: number;
  previousShot: ResolvedR5Shot | null;
  nextShot: ResolvedR5Shot | null;
  anchorTransition: string;
};

type RawResolvedShot = NonNullable<Scene['resolved_shots']>[number];

const normalizeResolvedShot = (raw: RawResolvedShot): ResolvedR5Shot => ({
  ...raw,
  long_shot_reason: raw.long_shot_reason ?? null,
  text_windows: raw.text_windows.map((w) => ({
    ...w,
    claim_ids: w.claim_ids ?? [],
    exception_reason: w.exception_reason ?? null,
  })),
});

/**
 * Validates all resolved shots on an R5 scene and selects the single primary shot for `frame`.
 * Fails closed with scene and shot IDs on missing data, unknown components, tabs, or invalid bounds.
 */
export const resolveActiveR5Shot = (
  scene: Scene,
  frame: number,
): ActiveR5ShotResolution => {
  assertNoR5TabLayout(scene, 'r5_v1');

  const rawShots = scene.resolved_shots;
  if (!rawShots || rawShots.length === 0) {
    throw new Error(`R5ShotScene (${scene.id}): missing resolved_shots`);
  }
  const shots: ResolvedR5Shot[] = rawShots.map(normalizeResolvedShot);

  for (let i = 0; i < shots.length; i++) {
    const shot = shots[i];
    if (!Object.prototype.hasOwnProperty.call(R5_COMPONENT_REGISTRY, shot.component)) {
      failShot(scene.id, shot.id, `unknown R5 component "${String(shot.component)}"`);
    }
    if (shot.end_frame <= shot.start_frame || shot.start_frame < 0) {
      failShot(
        scene.id,
        shot.id,
        `invalid frame interval [${shot.start_frame}, ${shot.end_frame})`,
      );
    }
    if (i > 0 && shot.start_frame < shots[i - 1].end_frame) {
      failShot(
        scene.id,
        shot.id,
        `overlapping shot interval [${shot.start_frame}, ${shot.end_frame}) after ${shots[i - 1].id}`,
      );
    }
    for (const win of shot.text_windows) {
      if (win.text.includes('\t')) {
        failShot(scene.id, shot.id, 'R5 text_window forbids tab layout');
      }
    }
  }

  let activeIndex = shots.findIndex((s) => frame >= s.start_frame && frame < s.end_frame);
  if (activeIndex < 0) {
    if (frame < shots[0].start_frame) {
      failShot(scene.id, shots[0].id, `frame ${frame} falls before first shot start ${shots[0].start_frame}`);
    }
    const last = shots[shots.length - 1];
    if (frame >= last.end_frame && frame <= scene.duration_frames) {
      activeIndex = shots.length - 1;
    } else {
      failShot(scene.id, '*', `frame ${frame} falls in a gap between resolved shots`);
    }
  }

  const activeShot = shots[activeIndex];
  const previousShot = activeIndex > 0 ? shots[activeIndex - 1] : null;
  const nextShot = activeIndex < shots.length - 1 ? shots[activeIndex + 1] : null;
  const fromAnchor = previousShot?.tier ?? previousShot?.id ?? 'scene_start';
  const toAnchor = activeShot.tier ?? activeShot.id;
  const anchorTransition = `${fromAnchor}->${toAnchor}`;

  return {shots, activeShot, activeIndex, previousShot, nextShot, anchorTransition};
};

export type R5ShotSceneProps = {
  scene: Scene;
  r5Contract?: R5Contract | null;
  assets?: readonly R5RevisionAsset[];
  stageActions?: R5LeakStageActions;
  transition?: SceneTransitionProps;
  frame?: number;
};

/**
 * R5 production scene renderer.
 * - Routes strictly through R5_COMPONENT_REGISTRY (fail closed on unknown component or missing data).
 * - Renders a single primary viewpoint per shot with anchor-based shot transitions.
 * - Never renders burned-in captions or narration bands in 16:9; renders 9:16 captions while preserving word timings.
 */
export const R5ShotScene: React.FC<R5ShotSceneProps> = ({
  scene,
  r5Contract = null,
  assets: providedAssets,
  stageActions,
  frame: frameOverride,
}) => {
  const currentFrame = useCurrentFrame();
  const effectiveFrame = frameOverride ?? currentFrame;
  const layout = useLayout();
  const portrait = isPortraitLayout(layout);

  const {shots, activeShot, previousShot, nextShot, anchorTransition} = resolveActiveR5Shot(
    scene,
    effectiveFrame,
  );

  const renderer = R5_COMPONENT_REGISTRY[activeShot.component];
  const shotAssets = resolveShotAssets(scene.id, activeShot, providedAssets);
  const localShotFrame = Math.max(0, effectiveFrame - activeShot.start_frame);
  const transitionOpacity = previousShot ? r5EaseOut(localShotFrame / 8) : 1;
  const hasMascot = Boolean(scene.visual_assets?.some((a) => a.role === 'mascot'));

  const element = renderer({
    scene,
    shot: activeShot,
    previousShot,
    nextShot,
    allShots: shots,
    layout,
    frame: effectiveFrame,
    assets: shotAssets,
    r5Contract,
    stageActions,
  });

  return (
    <AbsoluteFill
      data-r5-scene={scene.id}
      data-active-shot={activeShot.id}
      data-shot-kind={activeShot.kind}
      data-shot-component={activeShot.component}
      data-transition-anchor={anchorTransition}
      data-layout={portrait ? '9:16' : '16:9'}
      style={{
        backgroundColor: R5_PALETTE.bg,
        overflow: 'hidden',
        opacity: Math.max(0.01, transitionOpacity),
      }}
    >
      {element}
      {shouldRenderCaptions(layout) ? (
        <Captions
          variant={scene.words?.length ? 'shorts' : undefined}
          hasMascot={hasMascot}
          text={scene.narration}
          words={scene.words}
          durationInFrames={scene.duration_frames}
        />
      ) : null}
    </AbsoluteFill>
  );
};
