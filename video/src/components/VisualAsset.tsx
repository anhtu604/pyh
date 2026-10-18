import React from 'react';
import {Img, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {LAYOUTS, useLayout} from '../layout';
import type {FrameLayout} from '../layout';
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

export const VisualAsset: React.FC<{asset: VisualAssetRef; outro?: boolean}> = ({asset, outro = false}) => {
  const frame = useCurrentFrame();
  const box = visualAssetBox(asset, outro, useLayout());
  const opacity = interpolate(frame, [0, 10], [0, 1], {extrapolateRight: 'clamp'});
  return (
    <Img
      aria-label={`PYH ${asset.role} ${asset.pose ?? ''}`.trim()}
      src={staticFile(asset.path)}
      style={{...box, objectFit: 'contain', opacity, position: 'absolute'}}
    />
  );
};
