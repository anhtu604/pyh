import React from 'react';
import {spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {brand} from '../anatomy/palette';
import {useLayout, type Box} from '../layout';
import type {Scene} from '../types';
import {VisualAsset} from './VisualAsset';

export const MascotGuide: React.FC<{scene: Pick<Scene, 'visual_assets'>; box?: Box; groupEntrance?: boolean}> = ({scene, box: override, groupEntrance = false}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const layout = useLayout();
  const box = override ?? layout.mechanism.mascot;
  const entrance = spring({frame, fps, config: {damping: 18, stiffness: 140, mass: 0.8}});
  const asset = scene.visual_assets?.find((item) => item.role === 'mascot');
  if (!asset) return null;
  return <div style={{...box, position: 'absolute', opacity: groupEntrance ? 1 : entrance,
    transform: `translateY(${(groupEntrance ? 0 : (1 - entrance) * 32) + Math.sin(frame / fps * 2) * 4}px)`}}>
    <div data-mascot-plate="true" style={{position: 'absolute', left: 0,
      top: (box.height - box.width) / 2, width: box.width, height: box.width,
      borderRadius: '50%', backgroundColor: brand.off_white}} />
    <VisualAsset asset={asset} box={{left: 0, top: 0, width: box.width, height: box.height}} />
  </div>;
};
