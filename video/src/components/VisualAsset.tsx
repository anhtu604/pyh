import React from 'react';
import {Img, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {PresenterMascot} from './PresenterMascot';
import {isReverseLogoPath, logoBadgeSpec} from './logoContrast';
import {slowDriftTransform} from './slowDrift';
import {LAYOUTS, useLayout} from '../layout';
import type {FrameLayout} from '../layout';
import {computeSceneEnvelope, type SceneTransitionProps} from '../motion/sceneEnvelope';
import type {VisualAssetRef} from '../types';

export type VisualAssetBox = {height: number; left: number; top: number; width: number};

export const visualAssetBox = (
  asset: VisualAssetRef, outro = false, layout: FrameLayout = LAYOUTS.vertical_clip,
): VisualAssetBox => {
  const a = layout.assets;
  if (asset.role === 'brand') return outro ? a.outroBrand : a.brand;
  if (outro && asset.role === 'mascot') return a.outroMascot;
  if (asset.role === 'whiteboard') return a.whiteboard;
  return asset.pose === 'explain' ? a.explain : a.standard;
};

export const VisualAsset: React.FC<{
  asset: VisualAssetRef;
  outro?: boolean;
  box?: VisualAssetBox;
  durationFrames?: number;
  continuation?: boolean;
  transition?: SceneTransitionProps;
}> = ({asset, outro = false, box: overrideBox, durationFrames, continuation, transition}) => {
  const frame = useCurrentFrame();
  const layout = useLayout();
  const box = overrideBox ?? visualAssetBox(asset, outro, layout);
  if (asset.role === 'mascot') {
    return <PresenterMascot asset={asset} box={box} continuation={continuation} transition={transition} />;
  }
  const env = transition ? computeSceneEnvelope(frame, transition) : null;
  const baseOpacity = interpolate(frame, [0, 10], [0, 1], {extrapolateRight: 'clamp'});
  const opacity = env ? baseOpacity * env.opacity : baseOpacity;
  const label = `PYH ${asset.role} ${asset.pose ?? ''}`.trim();

  if (asset.role === 'brand') {
    const reverse = isReverseLogoPath(asset.path, false);
    const badge = logoBadgeSpec({reverse, onDark: false});
    return (
      <div
        aria-label={label}
        data-brand-badge="true"
        data-brand-variant={reverse ? 'reverse' : 'primary'}
        style={{
          ...box,
          position: 'absolute',
          boxSizing: 'border-box',
          padding: 20,
          borderRadius: 24,
          backgroundColor: badge.backgroundColor,
          border: `3px solid ${badge.borderColor}`,
          boxShadow: badge.boxShadow,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          opacity,
          transform: env?.transform,
        }}
      >
        <Img
          src={staticFile(asset.path)}
          style={{width: '100%', height: '100%', objectFit: 'contain', filter: badge.imageFilter}}
        />
      </div>
    );
  }

  const drift = asset.role === 'whiteboard' && durationFrames !== undefined
    ? slowDriftTransform(frame, durationFrames)
    : null;
  if (drift?.active) {
    return (
      <div
        aria-label={label}
        data-slow-drift="true"
        style={{...box, overflow: 'hidden', position: 'absolute', transform: env?.transform}}
      >
        <Img
          src={staticFile(asset.path)}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'contain',
            opacity,
            transform: drift.transform,
            transformOrigin: 'center center',
          }}
        />
      </div>
    );
  }

  return (
    <Img
      aria-label={label}
      src={staticFile(asset.path)}
      style={{...box, objectFit: 'contain', opacity, position: 'absolute', transform: env?.transform}}
    />
  );
};
