import React from 'react';
import {Img, interpolate, staticFile, useCurrentFrame} from 'remotion';
import type {VisualAssetRef} from '../types';

export type VisualAssetBox = {height: number; left: number; top: number; width: number};

export const visualAssetBox = (asset: VisualAssetRef): VisualAssetBox => {
  if (asset.role === 'whiteboard') {
    return {height: 980, left: 90, top: 190, width: 900};
  }
  if (asset.pose === 'explain') {
    return {height: 690, left: 390, top: 650, width: 570};
  }
  return {height: 690, left: 60, top: 650, width: 570};
};

export const VisualAsset: React.FC<{asset: VisualAssetRef}> = ({asset}) => {
  const frame = useCurrentFrame();
  const box = visualAssetBox(asset);
  const opacity = interpolate(frame, [0, 10], [0, 1], {extrapolateRight: 'clamp'});
  return (
    <Img
      aria-label={`PHY ${asset.role} ${asset.pose ?? ''}`.trim()}
      src={staticFile(asset.path)}
      style={{...box, objectFit: 'contain', opacity, position: 'absolute'}}
    />
  );
};
