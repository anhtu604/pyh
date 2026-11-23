import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {
  ANATOMY_COMPONENTS,
  ANATOMY_FOCUS_REGIONS,
  ANATOMY_LABELS,
  ANATOMY_VIEW_BOXES,
  type AnatomySubject,
} from '../anatomy/registry';
import {
  ENTITY_COLORS,
  surfaceBackgroundHex,
  surfaceCardBackgroundHex,
  surfaceLabelTextHex,
} from '../anatomy/entityColors';
import {brand} from '../anatomy/palette';
import {Captions, CAPTION_BACKGROUND_COLOR, shouldRenderCaptions} from '../components/Captions';
import {MascotGuide} from '../components/MascotGuide';
import {FONT_FAMILY} from '../fonts';
import {captionBox, useLayout, type Box} from '../layout';
import {hexToRgba} from '../style/pyhStyle';
import type {Scene} from '../types';
import {
  computeLayerTransition,
  computeScaleZoomState,
  resolveScaleSurface,
  SCALE_LEVEL_MAP,
} from './levels';
import {
  MembraneMolecularCloseup,
  MOLECULAR_LABEL_ANCHORS,
  MOLECULAR_LEADER_OBSTACLES,
} from './MembraneMolecularCloseup';
import {ScaleBar} from './ScaleBar';
import {
  MAX_SCALEZOOM_LABELS,
  resolveNonOverlappingLabels,
  SingleLabelOverlay,
  type LabelCandidate,
} from './SingleLabel';
import {
  isScientificHepaticSubject,
  ScientificHepaticArtwork,
} from '../medanim/ScientificHepaticArtwork';

export type ScaleZoomStageProps = {
  scene: Scene;
  kind: 'anatomy' | 'process';
  cueProgress?: Record<string, number>;
  /** Corner placement for the compact Style A mascot guide (defaults to 'left'). */
  mascotSide?: 'left' | 'right';
  /** Keep light off_white canvas across all zoom levels in 16:9 full videos to avoid dark flashes. */
  forceLightCanvas?: boolean;
};

const HEPATIC_CELL_SUBJECTS: ReadonlySet<AnatomySubject> = new Set([
  'hepatocyte_sinusoid_unit',
  'hepatic_toxic_injury',
  'hepatic_synthesis_and_bile',
  'hepatic_fibrosis_section',
]);

/** ViewBox keep-out regions (arrows & primary visual structures) so leader lines never cut across them. */
const SUBJECT_LEADER_OBSTACLES: Readonly<Partial<Record<AnatomySubject, readonly Box[]>>> = {
  liver_organ: [
    {left: 266, top: 88, width: 54, height: 274}, // Falciform ligament white band
  ],
  hepatocyte_sinusoid_unit: [
    {left: 68, top: 486, width: 356, height: 26}, // Sinusoidal blood flow arrow
    {left: 266, top: 58, width: 28, height: 42}, // Bile canaliculus arrow
  ],
  hepatic_toxic_injury: [
    {left: 68, top: 486, width: 356, height: 26},
    {left: 266, top: 58, width: 28, height: 42},
  ],
  hepatic_synthesis_and_bile: [
    {left: 68, top: 486, width: 356, height: 26},
    {left: 266, top: 58, width: 28, height: 42},
  ],
  hepatic_fibrosis_section: [
    {left: 68, top: 486, width: 356, height: 26},
    {left: 266, top: 58, width: 28, height: 42},
  ],
};

const FALLBACK_SUBJECT_LABEL_VI: Readonly<Partial<Record<AnatomySubject, string>>> = {
  liver_organ: 'Gan (cơ quan)',
  liver_lobule: 'Tiểu thùy gan',
  hepatocyte_sinusoid_unit: 'Tế bào gan & mao mạch nan hoa',
  hepatic_toxic_injury: 'Tổn thương tế bào gan',
  hepatic_synthesis_and_bile: 'Tổng hợp đạm & đường mật',
  hepatic_fibrosis_section: 'Mô xơ gan',
  alt_ast_tissue_distribution: 'Phân bố men ALT / AST',
  artery_cross_section: 'Thành động mạch',
  heart: 'Tim',
};

export const ScaleZoomStage: React.FC<ScaleZoomStageProps> = ({
  scene,
  kind,
  cueProgress,
  mascotSide = 'left',
  forceLightCanvas = false,
}) => {
  const frame = useCurrentFrame();
  const frameLayout = useLayout();
  if (!scene.anatomy) throw new Error(`${scene.visual} requires anatomy`);

  const anatomy = scene.anatomy;
  const Organ = ANATOMY_COMPONENTS[anatomy.subject];
  if (!Organ) throw new Error(`Unsupported anatomy subject: ${anatomy.subject}`);

  const isVertical = frameLayout.frame.height > frameLayout.frame.width;
  const hasMascot = Boolean(scene.visual_assets?.some((asset) => asset.role === 'mascot'));
  const view = ANATOMY_VIEW_BOXES[anatomy.subject];
  const regions = ANATOMY_FOCUS_REGIONS[anatomy.subject];
  const rawLabels = ANATOMY_LABELS[anatomy.subject];
  const availableLabelKeys = Object.keys(rawLabels);

  // Compact Style A corner mascot box.
  const mascotBox: Box = isVertical
    ? {
        left: mascotSide === 'left' ? 32 : frameLayout.frame.width - 252,
        top: 1350,
        width: 220,
        height: 192,
      }
    : {
        left: mascotSide === 'left' ? 28 : frameLayout.frame.width - 268,
        top: 842,
        width: 240,
        height: 210,
      };

  // Center main subject in the available non-mascot area so half the frame is never left empty.
  const stageViewport: Box = isVertical
    ? {left: 36, top: 168, width: frameLayout.frame.width - 72, height: 1120}
    : hasMascot
      ? mascotSide === 'left'
        ? {left: 276, top: 112, width: frameLayout.frame.width - 336, height: 916}
        : {left: 60, top: 112, width: frameLayout.frame.width - 336, height: 916}
      : {left: 140, top: 112, width: frameLayout.frame.width - 280, height: 916};

  const subjectPadX = HEPATIC_CELL_SUBJECTS.has(anatomy.subject) ? 14 : 28;
  const subjectPadY = HEPATIC_CELL_SUBJECTS.has(anatomy.subject) ? 10 : 24;
  const subjectBox: Box = {
    left: stageViewport.left + subjectPadX,
    top: stageViewport.top + subjectPadY,
    width: stageViewport.width - subjectPadX * 2,
    height: stageViewport.height - subjectPadY * 2,
  };

  const state = computeScaleZoomState(
    scene,
    frame,
    regions,
    view,
    subjectBox,
    stageViewport,
    availableLabelKeys,
  );

  const progress = interpolate(frame, [0, Math.max(1, scene.duration_frames - 1)], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const severity = cueProgress
    ? anatomy.state === 'normal'
      ? 0
      : anatomy.severity
    : anatomy.state === 'normal'
      ? 0
      : kind === 'anatomy'
        ? anatomy.severity * (0.4 + 0.6 * progress)
        : anatomy.severity;

  // Cross-tier log-zoom transitions:
  // 1) Hepatic cell -> stylized ~10 nm molecular closeup (centered on sinusoidal membrane)
  // 2) Liver organ -> hepatocyte/sinusoid unit (centered on right-lobe parenchyma)
  const usesMolecularCloseup =
    HEPATIC_CELL_SUBJECTS.has(anatomy.subject) && state.level === 'molecule';
  const usesOrganToCellTransition =
    anatomy.subject === 'liver_organ' && state.level === 'cell';
  const isLayerTransition = usesMolecularCloseup || usesOrganToCellTransition;
  const layerTransitionT = isLayerTransition
    ? state.previousLevel === state.level
      ? 1
      : state.transitionProgress
    : 0;
  const layerTransition = computeLayerTransition(layerTransitionT);

  const activeSurface = forceLightCanvas
    ? 'off_white'
    : isLayerTransition && !layerTransition.handedOff
      ? resolveScaleSurface(state.previousLevel)
      : state.surface;
  const bgHex = surfaceBackgroundHex(activeSurface);
  const inkHex = surfaceLabelTextHex(activeSurface);
  const lightSurface = activeSurface === 'off_white';

  // Map viewBox anchor points into full-frame screen coordinates.
  const fitScale = Math.min(subjectBox.width / view.width, subjectBox.height / view.height);
  const offsetX = subjectBox.left - stageViewport.left + (subjectBox.width - view.width * fitScale) / 2;
  const offsetY = subjectBox.top - stageViewport.top + (subjectBox.height - view.height * fitScale) / 2;

  // Outgoing camera smoothly pans & log-zooms straight into the region that becomes the next tier.
  const targetViewPoint: readonly [number, number] = usesMolecularCloseup
    ? [280, 374] // Hepatocyte sinusoidal membrane interface
    : [180, 240]; // Central right-lobe liver parenchyma
  const targetPx = offsetX + (targetViewPoint[0] - view.left) * fitScale;
  const targetPy = offsetY + (targetViewPoint[1] - view.top) * fitScale;
  const startZoom = state.fromCamera.zoom;
  const startFx = (stageViewport.width / 2 - (state.fromCamera.x / 100) * stageViewport.width) / startZoom;
  const startFy = (stageViewport.height / 2 - (state.fromCamera.y / 100) * stageViewport.height) / startZoom;
  const activeFx = startFx + (targetPx - startFx) * layerTransition.outgoingPanProgress;
  const activeFy = startFy + (targetPy - startFy) * layerTransition.outgoingPanProgress;
  const outgoingZoom = isLayerTransition ? startZoom * layerTransition.outgoingZoom : state.camera.zoom;
  const outgoingX = isLayerTransition
    ? ((stageViewport.width / 2 - activeFx * outgoingZoom) / stageViewport.width) * 100
    : state.camera.x;
  const outgoingY = isLayerTransition
    ? ((stageViewport.height / 2 - activeFy * outgoingZoom) / stageViewport.height) * 100
    : state.camera.y;

  const toScreen = (vx: number, vy: number): [number, number] => {
    const px = offsetX + (vx - view.left) * fitScale;
    const py = offsetY + (vy - view.top) * fitScale;
    if (isLayerTransition && layerTransition.handedOff) {
      // Incoming layer is centered in subjectBox at layerTransition.incomingScale.
      const cx = stageViewport.width / 2;
      const cy = stageViewport.height / 2;
      const sx = stageViewport.left + cx + (px - cx) * layerTransition.incomingScale;
      const sy = stageViewport.top + cy + (py - cy) * layerTransition.incomingScale;
      return [sx, sy];
    }
    const sx = stageViewport.left + px * outgoingZoom + (outgoingX / 100) * stageViewport.width;
    const sy = stageViewport.top + py * outgoingZoom + (outgoingY / 100) * stageViewport.height;
    return [sx, sy];
  };

  const mapViewBoxToScreen = (vb: Box): Box => {
    const [x1, y1] = toScreen(vb.left, vb.top);
    const [x2, y2] = toScreen(vb.left + vb.width, vb.top + vb.height);
    return {
      left: Math.min(x1, x2),
      top: Math.min(y1, y2),
      width: Math.abs(x2 - x1),
      height: Math.abs(y2 - y1),
    };
  };

  // Build label candidates: ONE primary label at a time (plus optional authored secondary labels, max 6).
  const activeBeat = state.activeBeat;
  const primaryId = activeBeat?.primaryLabelId ?? null;
  const baseCandidateIds = activeBeat?.labelIds.length
    ? [...activeBeat.labelIds]
    : primaryId
      ? [primaryId]
      : [];
  const incomingMolecularActive = usesMolecularCloseup && layerTransition.handedOff;
  const incomingCellActive = usesOrganToCellTransition && layerTransition.handedOff;
  const effectiveRawLabels = incomingCellActive
    ? ANATOMY_LABELS.hepatocyte_sinusoid_unit
    : rawLabels;

  // Always label the top yellow bile canaliculus in cellular hepatic views so it never appears unexplained.
  if (
    ((HEPATIC_CELL_SUBJECTS.has(anatomy.subject) && !incomingMolecularActive) || incomingCellActive) &&
    effectiveRawLabels.bile &&
    !baseCandidateIds.includes('bile') &&
    baseCandidateIds.length < MAX_SCALEZOOM_LABELS
  ) {
    baseCandidateIds.push('bile');
  }
  if (incomingCellActive && !baseCandidateIds.includes('cell') && baseCandidateIds.length < MAX_SCALEZOOM_LABELS) {
    baseCandidateIds.unshift('cell');
  }
  const candidateIds = baseCandidateIds;
  const effectivePrimaryId = incomingCellActive ? (primaryId ?? 'cell') : primaryId;

  const candidates: LabelCandidate[] = [];
  for (const id of candidateIds) {
    if (incomingMolecularActive && MOLECULAR_LABEL_ANCHORS[id]) {
      const mDef = MOLECULAR_LABEL_ANCHORS[id];
      const [ax, ay] = toScreen(mDef.anchor[0], mDef.anchor[1]);
      const [px, py] = toScreen(mDef.preferred[0], mDef.preferred[1]);
      candidates.push({
        id,
        text: mDef.text,
        anchorX: ax,
        anchorY: ay,
        preferredX: px,
        preferredY: py,
        primary: id === effectivePrimaryId,
      });
      continue;
    }
    const def = effectiveRawLabels[id];
    if (!def) continue;
    const [ax, ay] = toScreen(def.anchor[0], def.anchor[1]);
    let [px, py] = toScreen(def.x + def.width / 2, def.y + def.height / 2);
    // In wide 16:9 frames, pull edge cellular labels cleanly outside the cell wall so they never cover membrane or mitochondria.
    if (!isVertical && (HEPATIC_CELL_SUBJECTS.has(anatomy.subject) || incomingCellActive)) {
      if (def.x < 60) {
        px = Math.min(px, ax - 156);
      } else if (def.x + def.width > 500 && def.region !== 'blood' && def.region !== 'bile') {
        px = Math.max(px, ax + 172);
      }
    }
    candidates.push({
      id,
      text: def.text,
      anchorX: ax,
      anchorY: ay,
      preferredX: px,
      preferredY: py,
      primary: id === effectivePrimaryId,
    });
  }

  // Fallback single primary label when a subject (e.g. LiverOrgan / LiverLobule) has empty LABELS.
  if (candidates.length === 0) {
    const focusKey = activeBeat?.focus && regions[activeBeat.focus] ? activeBeat.focus : 'overview';
    const focusBox = regions[focusKey] ?? view;
    const fallbackText =
      FALLBACK_SUBJECT_LABEL_VI[anatomy.subject] ?? SCALE_LEVEL_MAP[state.level].labelVi;
    if (anatomy.subject === 'liver_organ') {
      // Place label cleanly outside the liver silhouette (upper-right of left lobe) with a short leader that never crosses the falciform ligament.
      const [ax, ay] = toScreen(436, 178);
      const [px, py] = toScreen(548, 86);
      candidates.push({
        id: `${anatomy.subject}:${focusKey}`,
        text: fallbackText,
        anchorX: ax,
        anchorY: ay,
        preferredX: Math.min(frameLayout.frame.width - 140, px + 88),
        preferredY: Math.max(stageViewport.top + 48, py),
        primary: true,
      });
    } else {
      const [ax, ay] = toScreen(focusBox.left + focusBox.width / 2, focusBox.top + focusBox.height / 2);
      candidates.push({
        id: `${anatomy.subject}:${focusKey}`,
        text: fallbackText,
        anchorX: ax,
        anchorY: ay,
        preferredX: ax,
        preferredY: Math.max(stageViewport.top + 60, ay - 150),
        primary: true,
      });
    }
  }

  const scaleBarObstacle: Box = isVertical
    ? {left: 24, top: 24, width: frameLayout.frame.width - 48, height: 112}
    : {left: frameLayout.frame.width - 480, top: 20, width: 460, height: 112};
  const takeawayObstacle: Box | null = scene.visualTakeaway
    ? isVertical
      ? {left: 36, top: 148, width: frameLayout.frame.width - 72, height: 76}
      : {left: 44, top: 32, width: 820, height: 74}
    : null;
  const obstacles: Box[] = [
    scaleBarObstacle,
    ...(hasMascot ? [mascotBox] : []),
    ...(shouldRenderCaptions(frameLayout) ? [captionBox(frameLayout)] : []),
    ...(takeawayObstacle ? [takeawayObstacle] : []),
  ];

  const viewLeaderObstacles = incomingMolecularActive
    ? MOLECULAR_LEADER_OBSTACLES
    : incomingCellActive
      ? (SUBJECT_LEADER_OBSTACLES.hepatocyte_sinusoid_unit ?? [])
      : (SUBJECT_LEADER_OBSTACLES[anatomy.subject] ?? []);
  const leaderObstacles: Box[] = [
    ...obstacles,
    ...viewLeaderObstacles.map(mapViewBoxToScreen),
  ];

  const labelBounds: Box = {
    left: 28,
    top: isVertical ? (takeawayObstacle ? 236 : 156) : 124,
    width: frameLayout.frame.width - 56,
    height: isVertical ? 1020 : frameLayout.frame.height - 170,
  };

  const visibleCandidates = candidates.filter(
    (c) =>
      c.anchorX >= 24 &&
      c.anchorX <= frameLayout.frame.width - 24 &&
      c.anchorY >= Math.max(24, labelBounds.top - 24) &&
      c.anchorY <= frameLayout.frame.height - 24,
  );
  const placedLabels = resolveNonOverlappingLabels(visibleCandidates, labelBounds, obstacles, leaderObstacles);
  const labelOverlayOpacity = isLayerTransition
    ? layerTransition.handedOff
      ? Math.max(0, Math.min(1, (layerTransitionT - 0.56) / 0.22))
      : Math.max(0, Math.min(1, 1 - (layerTransitionT - 0.08) / 0.2))
    : 1;
  const pulsePhase = (frame % 45) / 45;
  const IncomingCellOrgan = ANATOMY_COMPONENTS.hepatocyte_sinusoid_unit;

  // Flat one-step drop shadow (Style: Scale Zoom — no soft blur, single crisp offset step).
  const flatShadowFilter = lightSurface
    ? `drop-shadow(0px 10px 0px ${hexToRgba(brand.navy, 0.14)})`
    : `drop-shadow(0px 10px 0px ${hexToRgba(brand.navy, 0.55)})`;

  const caption = frameLayout.captions;

  return (
    <AbsoluteFill
      data-scalezoom-stage="true"
      data-scalezoom-level={state.level}
      data-scalezoom-surface={activeSurface}
      data-scalezoom-zoom={outgoingZoom.toFixed(4)}
      data-scalezoom-beat={state.activeBeatIndex}
      data-scalezoom-label={placedLabels.find((l) => l.primary)?.id ?? ''}
      data-mascot-side={mascotSide}
      style={{backgroundColor: bgHex, color: inkHex, overflow: 'hidden'}}
    >
      {/* Visual takeaway pill with thin R3.23-style underline accent */}
      {scene.visualTakeaway ? (
        <div
          data-scalezoom-takeaway="true"
          style={{
            position: 'absolute',
            left: isVertical ? 36 : 44,
            top: isVertical ? 148 : 32,
            maxWidth: isVertical ? frameLayout.frame.width - 72 : 820,
            padding: '12px 22px 16px',
            borderRadius: 12,
            backgroundColor: hexToRgba(surfaceCardBackgroundHex(activeSurface), 0.94),
            border: `2px solid ${ENTITY_COLORS.blood_flow.hex}`,
            fontFamily: FONT_FAMILY,
            fontSize: 24,
            fontWeight: 800,
            color: inkHex,
            zIndex: 6,
            pointerEvents: 'none',
          }}
        >
          <span style={{position: 'relative', display: 'inline-block', paddingBottom: 6}}>
            {scene.visualTakeaway}
            <span
              data-emphasis-underline="true"
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                bottom: 0,
                height: 4,
                borderRadius: 2,
                backgroundColor: ENTITY_COLORS.warning_threshold.hex,
              }}
            />
          </span>
        </div>
      ) : null}

      {/* Main log-zoom stage viewport (zero rotation, flat one-step shadow, full-frame outer clip so no inner border seam) */}
      <div
        data-mechanism-subject-region="true"
        style={{...stageViewport, position: 'absolute', overflow: 'visible'}}
      >
        {(!isLayerTransition || layerTransitionT < 1) ? (
          <AbsoluteFill
            data-mechanism-camera={!isLayerTransition || !layerTransition.handedOff ? 'true' : undefined}
            data-scalezoom-camera={!isLayerTransition || !layerTransition.handedOff ? 'true' : undefined}
            data-scalezoom-outgoing-layer={isLayerTransition ? 'true' : undefined}
            data-layer-opacity={isLayerTransition ? layerTransition.outgoingOpacity.toFixed(4) : '1.0000'}
            data-framing={activeBeat?.focus ?? 'overview'}
            style={{
              transform: `translate(${outgoingX.toFixed(3)}%, ${outgoingY.toFixed(3)}%) scale(${outgoingZoom.toFixed(4)})`,
              transformOrigin: '0% 0%',
              opacity: isLayerTransition ? layerTransition.outgoingOpacity : 1,
              visibility: isLayerTransition && layerTransition.outgoingOpacity <= 0 ? 'hidden' : 'visible',
            }}
          >
            <div
              style={{
                position: 'absolute',
                left: subjectBox.left - stageViewport.left,
                top: subjectBox.top - stageViewport.top,
                width: subjectBox.width,
                height: subjectBox.height,
                filter: flatShadowFilter,
              }}
            >
              {isScientificHepaticSubject(anatomy.subject) ? (
                <ScientificHepaticArtwork
                  subject={anatomy.subject}
                  state={anatomy.state}
                  severity={severity}
                  cueProgress={cueProgress}
                  lightBackground={lightSurface}
                  durationFrames={scene.duration_frames}
                />
              ) : (
                <Organ
                  state={anatomy.state}
                  severity={severity}
                  emphasizeFlow={kind === 'process'}
                  lightBackground={lightSurface}
                  cueProgress={cueProgress}
                  visibleLabels={[]}
                />
              )}
            </div>
          </AbsoluteFill>
        ) : null}

        {isLayerTransition ? (
          <AbsoluteFill
            data-mechanism-camera={layerTransition.handedOff ? 'true' : undefined}
            data-scalezoom-camera={layerTransition.handedOff ? 'true' : undefined}
            data-scalezoom-incoming-layer="true"
            data-scalezoom-molecular-layer={usesMolecularCloseup ? 'true' : undefined}
            data-layer-opacity={layerTransition.incomingOpacity.toFixed(4)}
            style={{
              transform: `scale(${layerTransition.incomingScale.toFixed(4)})`,
              transformOrigin: '50% 50%',
              opacity: layerTransition.incomingOpacity,
              visibility: layerTransition.incomingOpacity <= 0 ? 'hidden' : 'visible',
            }}
          >
            <div
              style={{
                position: 'absolute',
                left: subjectBox.left - stageViewport.left,
                top: subjectBox.top - stageViewport.top,
                width: subjectBox.width,
                height: subjectBox.height,
                filter: flatShadowFilter,
              }}
            >
              {usesMolecularCloseup ? (
                <MembraneMolecularCloseup
                  state={anatomy.state}
                  severity={severity}
                  lightBackground={lightSurface}
                />
              ) : isScientificHepaticSubject('hepatocyte_sinusoid_unit') ? (
                <ScientificHepaticArtwork
                  subject="hepatocyte_sinusoid_unit"
                  state={anatomy.state}
                  severity={severity}
                  cueProgress={cueProgress}
                  lightBackground={lightSurface}
                  durationFrames={scene.duration_frames}
                />
              ) : (
                <IncomingCellOrgan
                  state={anatomy.state}
                  severity={severity}
                  emphasizeFlow={kind === 'process'}
                  lightBackground={false}
                  cueProgress={cueProgress}
                  visibleLabels={[]}
                />
              )}
            </div>
          </AbsoluteFill>
        ) : null}
      </div>

      {/* Crisp non-shadowed disclaimer caption when zoomed into stylized ~10 nm molecular view */}
      {usesMolecularCloseup ? (
        <div
          data-stylized-caption="true"
          style={{
            position: 'absolute',
            left: stageViewport.left,
            width: stageViewport.width,
            bottom: isVertical ? 320 : 28,
            textAlign: 'center',
            fontFamily: FONT_FAMILY,
            fontSize: isVertical ? 18 : 17,
            fontWeight: 600,
            color: hexToRgba(inkHex, 0.82),
            pointerEvents: 'none',
            zIndex: 6,
            opacity: layerTransition.incomingOpacity,
          }}
        >
          {anatomy.state === 'normal'
            ? 'Minh họa cách điệu (~10 nm) — màng tế bào gan nguyên vẹn giữ men ALT/AST bên trong tế bào'
            : 'Minh họa cách điệu (~10 nm) — men ALT/AST trong tế bào gan thoát ra máu khi màng tổn thương'}
        </div>
      ) : null}

      {/* Screen-space single primary label + double-layer focus ring */}
      <SingleLabelOverlay
        labels={placedLabels}
        surface={activeSurface}
        width={frameLayout.frame.width}
        height={frameLayout.frame.height}
        pulsePhase={pulsePhase}
        opacity={labelOverlayOpacity}
      />

      {/* Scale tier bar */}
      <ScaleBar
        level={state.level}
        previousLevel={state.previousLevel}
        transitionProgress={state.transitionProgress}
        surface={activeSurface}
        isVertical={isVertical}
      />

      {/* Small corner mascot guide (elevated above label overlay so it is never obscured) */}
      <div style={{position: 'absolute', inset: 0, zIndex: 6, pointerEvents: 'none'}}>
        <MascotGuide scene={scene} box={mascotBox} />
      </div>

      {/* Standard 9:16 captions (suppressed in 16:9 per shouldRenderCaptions) */}
      {shouldRenderCaptions(frameLayout) && !scene.words?.length ? (
        <div
          data-mechanism-caption-band="true"
          style={{
            position: 'absolute',
            left: caption.left,
            bottom: caption.bottom,
            width: caption.width,
            height: caption.height,
            backgroundColor: CAPTION_BACKGROUND_COLOR,
            borderRadius: 16,
            zIndex: 7,
          }}
        />
      ) : null}
      <Captions
        variant={scene.words?.length ? 'shorts' : undefined}
        hasMascot={hasMascot}
        text={scene.narration}
        words={scene.words}
        durationInFrames={scene.duration_frames}
      />
    </AbsoluteFill>
  );
};
