import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame} from 'remotion';
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
  ScaleChain,
  type R5LayoutInput,
  type R5RevisionAsset,
  type ScaleTier,
} from './ScaleChain';

export type ZoomAnchor = {
  tierId: string;
  /** Normalized horizontal position within the stage viewport (0..1). */
  x: number;
  /** Normalized vertical position within the stage viewport (0..1). */
  y: number;
  /** Optional focus reticle radius in pixels (defaults to 48). */
  radius?: number;
  /** Optional short anchor label (from claim-backed data). */
  label?: string;
  claimIds?: readonly string[];
};

export type ZoomLandmark = {
  id: string;
  label: string;
  /** Normalized position within the stage viewport (0..1). */
  x: number;
  y: number;
  claimIds: readonly string[];
  dotColor?: string;
};

export type ZoomBodyOrientation = 'patient_right_on_screen_left' | 'none';

export type ZoomChainProps = {
  shot: ResolvedR5Shot;
  layout: R5LayoutInput;
  assets: readonly R5RevisionAsset[];
  fromAnchor: ZoomAnchor;
  toAnchor: ZoomAnchor;
  /** At least one positioning landmark (vùng định vị) with claim attribution. */
  landmarks: readonly ZoomLandmark[];
  tiers?: readonly ScaleTier[];
  bodyOrientation?: ZoomBodyOrientation;
  transitionFrames?: number;
  maxZoomScale?: number;
  frame?: number;
  children?: React.ReactNode;
};

export type ZoomChainGeometry = {
  stageBox: Box;
  anatomyCloseUpBox: Box;
  fromPoint: {x: number; y: number; tierId: string};
  toPoint: {x: number; y: number; tierId: string};
  camera: {
    scale: number;
    tx: number;
    ty: number;
    originX: number;
    originY: number;
    progress: number;
  };
  landmarkBoxes: Array<{
    id: string;
    label: string;
    claimIds: readonly string[];
    dotColor: string;
    box: Box;
  }>;
  resolvedAssetPath: string | null;
};

const DEFAULT_ZOOM_FRAMES = 20;
const DEFAULT_MAX_ZOOM_SCALE = 2.2;
const LABEL_PILL_HEIGHT = 48;
const LABEL_PILL_WIDTH = 240;

const matchRevisionAssetPath = (
  shot: ResolvedR5Shot,
  assets: readonly R5RevisionAsset[],
): string | null => {
  const allowed = new Set(assets.map((a) => a.path));
  for (const path of shot.asset_paths) {
    if (allowed.has(path)) {
      return path;
    }
  }
  return assets[0]?.path ?? null;
};

export const computeZoomChainGeometry = (
  props: Pick<
    ZoomChainProps,
    | 'shot'
    | 'layout'
    | 'assets'
    | 'fromAnchor'
    | 'toAnchor'
    | 'landmarks'
    | 'transitionFrames'
    | 'maxZoomScale'
    | 'frame'
  >,
): ZoomChainGeometry => {
  const layout = resolveR5Layout(props.layout);
  const portrait = isPortraitLayout(layout);
  const duration = Math.max(1, props.shot.end_frame - props.shot.start_frame);
  const rawFrame = props.frame ?? props.shot.start_frame;
  const localFrame = Math.max(0, Math.min(duration, rawFrame - props.shot.start_frame));
  const transitionFrames = Math.max(1, props.transitionFrames ?? DEFAULT_ZOOM_FRAMES);
  const maxScale = Math.max(1, props.maxZoomScale ?? DEFAULT_MAX_ZOOM_SCALE);

  const portraitBottom = r5PortraitContentBottom(layout);
  const stageBox: Box = portrait
    ? {
        left: 48,
        top: 184,
        width: layout.frame.width - 96,
        height: Math.min(960, portraitBottom - 184 - 160),
      }
    : {
        left: 110,
        top: 112,
        width: 1120,
        height: 820,
      };

  const fromX = stageBox.left + r5Clamp01(props.fromAnchor.x) * stageBox.width;
  const fromY = stageBox.top + r5Clamp01(props.fromAnchor.y) * stageBox.height;
  const toX = stageBox.left + r5Clamp01(props.toAnchor.x) * stageBox.width;
  const toY = stageBox.top + r5Clamp01(props.toAnchor.y) * stageBox.height;

  const zoomStart = Math.max(0, duration - transitionFrames);
  const progress = r5EaseInOut((localFrame - zoomStart) / transitionFrames);
  const scale = r5Lerp(1, maxScale, progress);
  const stageCenterX = stageBox.left + stageBox.width / 2;
  const stageCenterY = stageBox.top + stageBox.height / 2;
  const tx = r5Lerp(0, (stageCenterX - toX) * 0.45, progress);
  const ty = r5Lerp(0, (stageCenterY - toY) * 0.45, progress);

  const maxLabelBottom = portrait ? portraitBottom - 12 : layout.frame.height - 24;
  const landmarkBoxes = props.landmarks.map((landmark) => {
    const rawLeft = stageBox.left + r5Clamp01(landmark.x) * stageBox.width - LABEL_PILL_WIDTH / 2;
    const rawTop = stageBox.top + r5Clamp01(landmark.y) * stageBox.height - LABEL_PILL_HEIGHT / 2;
    const left = Math.max(
      stageBox.left + 16,
      Math.min(rawLeft, stageBox.left + stageBox.width - LABEL_PILL_WIDTH - 16),
    );
    const top = Math.max(
      stageBox.top + 16,
      Math.min(rawTop, Math.min(stageBox.top + stageBox.height, maxLabelBottom) - LABEL_PILL_HEIGHT - 16),
    );
    return {
      id: landmark.id,
      label: landmark.label,
      claimIds: landmark.claimIds,
      dotColor: landmark.dotColor ?? R5_PALETTE.teal,
      box: {left, top, width: LABEL_PILL_WIDTH, height: LABEL_PILL_HEIGHT},
    };
  });

  return {
    stageBox,
    anatomyCloseUpBox: stageBox,
    fromPoint: {x: fromX, y: fromY, tierId: props.fromAnchor.tierId},
    toPoint: {x: toX, y: toY, tierId: props.toAnchor.tierId},
    camera: {
      scale,
      tx,
      ty,
      originX: toX,
      originY: toY,
      progress,
    },
    landmarkBoxes,
    resolvedAssetPath: matchRevisionAssetPath(props.shot, props.assets),
  };
};

/**
 * Deterministic camera zoom controller connecting two anatomical tiers via explicit anchors.
 * Organ-agnostic: asset paths, landmarks, and tier labels are supplied via props.
 */
export const ZoomChain: React.FC<ZoomChainProps> = ({
  shot,
  layout: layoutInput,
  assets,
  fromAnchor,
  toAnchor,
  landmarks,
  tiers,
  bodyOrientation = 'patient_right_on_screen_left',
  transitionFrames = DEFAULT_ZOOM_FRAMES,
  maxZoomScale = DEFAULT_MAX_ZOOM_SCALE,
  frame,
  children,
}) => {
  const currentFrame = useCurrentFrame();
  const effectiveFrame = frame ?? currentFrame;
  const layout = resolveR5Layout(layoutInput);
  const portrait = isPortraitLayout(layout);

  if (landmarks.length === 0) {
    throw new Error(`ZoomChain (${shot.id}) requires at least one positioning landmark`);
  }

  const geom = computeZoomChainGeometry({
    shot,
    layout,
    assets,
    fromAnchor,
    toAnchor,
    landmarks,
    transitionFrames,
    maxZoomScale,
    frame: effectiveFrame,
  });

  const localFrame = Math.max(0, effectiveFrame - shot.start_frame);
  const enterOpacity = r5EaseOut(localFrame / 16);
  const reticleRadius = toAnchor.radius ?? 48;

  const localFromX = geom.fromPoint.x - geom.stageBox.left;
  const localFromY = geom.fromPoint.y - geom.stageBox.top;
  const localToX = geom.toPoint.x - geom.stageBox.left;
  const localToY = geom.toPoint.y - geom.stageBox.top;

  return (
    <AbsoluteFill
      data-r5-component="ZoomChain"
      data-shot-id={shot.id}
      data-layout={portrait ? '9:16' : '16:9'}
      data-from-tier={fromAnchor.tierId}
      data-to-tier={toAnchor.tierId}
      data-landmark-count={String(landmarks.length)}
      data-body-orientation={bodyOrientation}
      style={{
        backgroundColor: R5_PALETTE.bg,
        fontFamily: FONT_FAMILY,
        overflow: 'hidden',
      }}
    >
      <div
        data-zoom-camera="true"
        data-camera-scale={geom.camera.scale.toFixed(4)}
        style={{
          position: 'absolute',
          inset: 0,
          opacity: Math.max(0.01, enterOpacity),
          transform: `translate(${geom.camera.tx.toFixed(1)}px, ${geom.camera.ty.toFixed(1)}px) scale(${geom.camera.scale.toFixed(4)})`,
          transformOrigin: `${geom.camera.originX.toFixed(1)}px ${geom.camera.originY.toFixed(1)}px`,
        }}
      >
        <div
          data-zoom-stage="true"
          style={{
            position: 'absolute',
            left: geom.stageBox.left,
            top: geom.stageBox.top,
            width: geom.stageBox.width,
            height: geom.stageBox.height,
            borderRadius: 28,
            backgroundColor: R5_PALETTE.surface,
            border: `3.5px solid ${R5_PALETTE.border}`,
            overflow: 'hidden',
            boxShadow: '0 12px 28px rgba(18, 48, 74, 0.08)',
          }}
        >
          {bodyOrientation === 'patient_right_on_screen_left' ? (
            <>
              <div
                data-orientation-side="right"
                style={{
                  position: 'absolute',
                  left: 28,
                  top: 20,
                  fontSize: portrait ? 20 : 22,
                  fontWeight: 800,
                  color: R5_PALETTE.muted,
                  zIndex: 5,
                }}
              >
                PHẢI (cơ thể)
              </div>
              <div
                data-orientation-side="left"
                style={{
                  position: 'absolute',
                  right: 28,
                  top: 20,
                  fontSize: portrait ? 20 : 22,
                  fontWeight: 800,
                  color: R5_PALETTE.muted,
                  zIndex: 5,
                }}
              >
                TRÁI (cơ thể)
              </div>
            </>
          ) : null}

          {geom.resolvedAssetPath ? (
            <Img
              src={staticFile(geom.resolvedAssetPath)}
              style={{
                position: 'absolute',
                inset: 0,
                width: '100%',
                height: '100%',
                objectFit: 'contain',
              }}
            />
          ) : null}

          <svg
            viewBox={`0 0 ${geom.stageBox.width} ${geom.stageBox.height}`}
            width={geom.stageBox.width}
            height={geom.stageBox.height}
            style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}
          >
            {/* Anchor connector from source tier anchor to target tier anchor */}
            <line
              data-anchor-connector="true"
              data-from-tier={fromAnchor.tierId}
              data-to-tier={toAnchor.tierId}
              x1={localFromX}
              y1={localFromY}
              x2={localToX}
              y2={localToY}
              stroke={R5_PALETTE.teal}
              strokeWidth={4}
              strokeDasharray="10 8"
              opacity={0.75}
            />
            <circle
              data-anchor-point="from"
              cx={localFromX}
              cy={localFromY}
              r={10}
              fill={R5_PALETTE.navy}
              stroke={R5_PALETTE.bg}
              strokeWidth={3}
            />
            <circle
              data-anchor-point="to"
              cx={localToX}
              cy={localToY}
              r={reticleRadius}
              fill="rgba(24, 166, 166, 0.16)"
              stroke={R5_PALETTE.teal}
              strokeWidth={5}
              strokeDasharray="10 6"
            />
          </svg>

          {children}
        </div>

        {/* Claim-backed anatomical positioning landmarks */}
        {geom.landmarkBoxes.map((item) => (
          <div
            key={item.id}
            data-landmark-id={item.id}
            data-claim-ids={item.claimIds.join(',')}
            style={{
              position: 'absolute',
              left: item.box.left,
              top: item.box.top,
              width: item.box.width,
              height: item.box.height,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 10,
              padding: '6px 16px',
              borderRadius: 999,
              backgroundColor: 'rgba(247, 244, 236, 0.96)',
              border: `3px solid ${R5_PALETTE.navy}`,
              boxShadow: '0 6px 16px rgba(18, 48, 74, 0.12)',
              fontSize: portrait ? 24 : 26,
              fontWeight: 800,
              color: R5_PALETTE.navy,
              boxSizing: 'border-box',
              whiteSpace: 'nowrap',
            }}
          >
            <span
              style={{
                width: 14,
                height: 14,
                borderRadius: 7,
                backgroundColor: item.dotColor,
                border: `2px solid ${R5_PALETTE.navy}`,
                flexShrink: 0,
              }}
            />
            <span>{item.label}</span>
          </div>
        ))}
      </div>

      {tiers && tiers.length > 0 ? (
        <ScaleChain
          shot={shot}
          layout={layout}
          assets={assets}
          tiers={tiers}
          activeTierId={fromAnchor.tierId}
          frame={effectiveFrame}
        />
      ) : null}
    </AbsoluteFill>
  );
};
