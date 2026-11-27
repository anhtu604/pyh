import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame} from 'remotion';
import {FONT_FAMILY} from '../../fonts';
import type {Box} from '../../layout';
import type {MascotPose} from '../../style/pyhStyle';
import type {ResolvedR5Shot} from '../../types';
import {
  isPortraitLayout,
  R5_MAX_SIMULTANEOUS_LABELS,
  R5_PALETTE,
  r5Clamp01,
  r5EaseOut,
  r5Lerp,
  r5PortraitContentBottom,
  resolveR5Layout,
  type R5LayoutInput,
  type R5RevisionAsset,
} from './ScaleChain';

export type StoryShotMascot = {
  assetPath: string;
  pose: MascotPose;
};

export type StoryShotProps = {
  shot: ResolvedR5Shot;
  layout: R5LayoutInput;
  assets: readonly R5RevisionAsset[];
  mascot?: StoryShotMascot | null;
  frame?: number;
};

export type StoryShotLabelBox = {
  id: string;
  text: string;
  claimIds: readonly string[];
  box: Box;
};

export type StoryShotGeometry = {
  mode: 'asset' | 'mascot';
  resolvedAssetPath: string | null;
  resolvedAsset: R5RevisionAsset | null;
  stageBox: Box;
  mascotBox: Box | null;
  motion: {
    scale: number;
    tx: number;
    ty: number;
    rotateDeg: number;
    opacity: number;
  };
  labelBoxes: StoryShotLabelBox[];
};

const LABEL_PILL_HEIGHT = 48;
const LABEL_PILL_MAX_WIDTH = 340;
const OUTER_MARGIN_LANDSCAPE = 64;
const OUTER_MARGIN_PORTRAIT = 48;

const matchLicensedAsset = (
  shot: ResolvedR5Shot,
  assets: readonly R5RevisionAsset[],
): R5RevisionAsset | null => {
  if (shot.asset_paths.length === 0 || assets.length === 0) {
    return null;
  }
  const byPath = new Map(assets.map((a) => [a.path, a]));
  for (const path of shot.asset_paths) {
    const found = byPath.get(path);
    if (found) {
      return found;
    }
  }
  return null;
};

export const computeStoryShotGeometry = (
  props: Pick<StoryShotProps, 'shot' | 'layout' | 'assets' | 'mascot' | 'frame'>,
): StoryShotGeometry => {
  const layout = resolveR5Layout(props.layout);
  const portrait = isPortraitLayout(layout);
  const duration = Math.max(1, props.shot.end_frame - props.shot.start_frame);
  const rawFrame = props.frame ?? props.shot.start_frame;
  const localFrame = Math.max(0, Math.min(duration, rawFrame - props.shot.start_frame));
  const progress = r5Clamp01(localFrame / duration);
  const opacity = Math.max(0.01, r5EaseOut(localFrame / 10));

  const resolvedAsset = matchLicensedAsset(props.shot, props.assets);
  const hasMascot = Boolean(props.mascot?.assetPath);
  if (!resolvedAsset && !hasMascot) {
    throw new Error(
      `StoryShot (${props.shot.id}) requires at least one licensed asset or a scene mascot`,
    );
  }

  const mode: 'asset' | 'mascot' = resolvedAsset ? 'asset' : 'mascot';
  const portraitBottom = r5PortraitContentBottom(layout);

  const stageBox: Box = portrait
    ? {
        left: OUTER_MARGIN_PORTRAIT,
        top: 120,
        width: layout.frame.width - OUTER_MARGIN_PORTRAIT * 2,
        height: Math.max(480, portraitBottom - 120 - 24),
      }
    : {
        left: OUTER_MARGIN_LANDSCAPE,
        top: 60,
        width: layout.frame.width - OUTER_MARGIN_LANDSCAPE * 2,
        height: layout.frame.height - 120,
      };

  let mascotBox: Box | null = null;
  if (mode === 'mascot') {
    const mascotHeight = portrait
      ? Math.min(720, Math.max(360, Math.round(stageBox.height * 0.7)))
      : 640;
    const mascotWidth = Math.round(mascotHeight * 0.78);
    mascotBox = {
      left: Math.round(stageBox.left + (stageBox.width - mascotWidth) / 2),
      top: Math.round(stageBox.top + (stageBox.height - mascotHeight) / 2),
      width: mascotWidth,
      height: mascotHeight,
    };
  }

  // Pure frame-driven storytelling motion: slow push-in/pan for assets, gentle breath/tilt for mascot.
  const motion =
    mode === 'asset'
      ? {
          scale: r5Lerp(1.0, 1.07, progress),
          tx: r5Lerp(portrait ? -10 : -18, portrait ? 10 : 18, progress),
          ty: r5Lerp(6, -6, progress),
          rotateDeg: 0,
          opacity,
        }
      : {
          scale: 1 + Math.sin(localFrame * 0.08) * 0.015,
          tx: 0,
          ty: Math.sin(localFrame * 0.08) * 5,
          rotateDeg: Math.sin(localFrame * 0.05) * 1.4,
          opacity,
        };

  const activeLabels = props.shot.text_windows
    .filter((w) => w.kind === 'label' && rawFrame >= w.start_frame && rawFrame < w.end_frame)
    .slice(0, R5_MAX_SIMULTANEOUS_LABELS);

  const labelBoxes: StoryShotLabelBox[] = activeLabels.map((win, idx) => {
    const pillWidth = Math.min(LABEL_PILL_MAX_WIDTH, stageBox.width - 48);
    const left = stageBox.left + 24;
    const top = stageBox.top + 24 + idx * (LABEL_PILL_HEIGHT + 12);
    return {
      id: `${props.shot.id}-label-${idx}`,
      text: win.text,
      claimIds: win.claim_ids,
      box: {
        left,
        top: Math.min(top, (portrait ? portraitBottom : layout.frame.height - 60) - LABEL_PILL_HEIGHT),
        width: pillWidth,
        height: LABEL_PILL_HEIGHT,
      },
    };
  });

  return {
    mode,
    resolvedAssetPath: resolvedAsset?.path ?? null,
    resolvedAsset,
    stageBox,
    mascotBox,
    motion,
    labelBoxes,
  };
};

/**
 * Pure storytelling R5 shot (narration + visual, no slide text/data).
 * Priority: licensed asset in shot.asset_paths (slow push-in/pan) -> scene mascot (gentle breath/tilt).
 * Never renders an empty frame; fails closed if neither asset nor mascot is available.
 */
export const StoryShot: React.FC<StoryShotProps> = ({
  shot,
  layout: layoutInput,
  assets,
  mascot = null,
  frame,
}) => {
  const currentFrame = useCurrentFrame();
  const effectiveFrame = frame ?? currentFrame;
  const layout = resolveR5Layout(layoutInput);
  const portrait = isPortraitLayout(layout);

  const geom = computeStoryShotGeometry({
    shot,
    layout,
    assets,
    mascot,
    frame: effectiveFrame,
  });

  const haloSize = portrait ? 680 : 760;

  return (
    <AbsoluteFill
      data-r5-component="StoryShot"
      data-shot-id={shot.id}
      data-layout={portrait ? '9:16' : '16:9'}
      data-story-mode={geom.mode}
      data-asset-path={geom.resolvedAssetPath ?? ''}
      data-asset-author={geom.resolvedAsset?.author ?? ''}
      data-asset-license={geom.resolvedAsset?.license ?? ''}
      data-mascot-pose={geom.mode === 'mascot' ? mascot?.pose ?? '' : ''}
      style={{
        backgroundColor: R5_PALETTE.bg,
        backgroundImage:
          'radial-gradient(circle at 50% 44%, #FFFFFF 0%, #F7F4EC 62%, #EFECE2 100%)',
        fontFamily: FONT_FAMILY,
        overflow: 'hidden',
      }}
    >
      {geom.mode === 'asset' && geom.resolvedAssetPath ? (
        <div
          data-story-asset-stage="true"
          style={{
            position: 'absolute',
            left: geom.stageBox.left,
            top: geom.stageBox.top,
            width: geom.stageBox.width,
            height: geom.stageBox.height,
            borderRadius: 28,
            overflow: 'hidden',
            backgroundColor: R5_PALETTE.surface,
            boxShadow: '0 14px 36px rgba(18, 48, 74, 0.08)',
            opacity: geom.motion.opacity,
          }}
        >
          <Img
            data-story-asset-img="true"
            src={staticFile(geom.resolvedAssetPath)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              transform: `translate(${geom.motion.tx.toFixed(2)}px, ${geom.motion.ty.toFixed(2)}px) scale(${geom.motion.scale.toFixed(4)})`,
              transformOrigin: '50% 50%',
            }}
          />
        </div>
      ) : null}

      {geom.mode === 'mascot' && mascot && geom.mascotBox ? (
        <div
          data-story-mascot-stage="true"
          style={{
            position: 'absolute',
            left: geom.stageBox.left,
            top: geom.stageBox.top,
            width: geom.stageBox.width,
            height: geom.stageBox.height,
            overflow: 'hidden',
            opacity: geom.motion.opacity,
          }}
        >
          <div
            aria-hidden="true"
            style={{
              position: 'absolute',
              left: '50%',
              top: '50%',
              width: haloSize,
              height: haloSize,
              marginLeft: -haloSize / 2,
              marginTop: -haloSize / 2,
              borderRadius: '50%',
              backgroundColor: 'rgba(24, 166, 166, 0.07)',
              border: '3px solid rgba(24, 166, 166, 0.16)',
            }}
          />
          <div
            data-story-mascot="true"
            data-mascot-pose={mascot.pose}
            style={{
              position: 'absolute',
              left: geom.mascotBox.left - geom.stageBox.left,
              top: geom.mascotBox.top - geom.stageBox.top,
              width: geom.mascotBox.width,
              height: geom.mascotBox.height,
              transform: `translateY(${geom.motion.ty.toFixed(2)}px) scale(${geom.motion.scale.toFixed(4)}) rotate(${geom.motion.rotateDeg.toFixed(2)}deg)`,
              transformOrigin: '50% 80%',
              filter: 'drop-shadow(0 12px 24px rgba(18, 48, 74, 0.18))',
            }}
          >
            <Img
              src={staticFile(mascot.assetPath)}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'contain',
                objectPosition: 'bottom center',
              }}
            />
          </div>
        </div>
      ) : null}

      {geom.labelBoxes.map((label) => (
        <div
          key={label.id}
          data-story-label={label.id}
          data-claim-ids={label.claimIds.join(',')}
          style={{
            position: 'absolute',
            left: label.box.left,
            top: label.box.top,
            maxWidth: label.box.width,
            height: label.box.height,
            display: 'inline-flex',
            alignItems: 'center',
            gap: 10,
            padding: '6px 18px',
            borderRadius: 999,
            backgroundColor: 'rgba(247, 244, 236, 0.96)',
            border: `3px solid ${R5_PALETTE.navy}`,
            boxShadow: '0 6px 16px rgba(18, 48, 74, 0.12)',
            fontSize: portrait ? 24 : 26,
            fontWeight: 800,
            color: R5_PALETTE.navy,
            boxSizing: 'border-box',
            whiteSpace: 'nowrap',
            opacity: geom.motion.opacity,
          }}
        >
          <span
            style={{
              width: 12,
              height: 12,
              borderRadius: 6,
              backgroundColor: R5_PALETTE.teal,
              flexShrink: 0,
            }}
          />
          <span>{label.text}</span>
        </div>
      ))}
    </AbsoluteFill>
  );
};
