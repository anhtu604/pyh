import React from 'react';
import {Img, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {useLayout, type Box} from '../layout';
import type {VisualAssetRef} from '../types';

// The wrapper stays fixed at the cut line. The lower 35% remains below it,
// even at the highest bob, so animation cannot uncover the bottom edge.
export const presenterGeometry = (box: Box, entrance: number, frame: number, fps: number) => ({
  fullHeight: box.height / 0.65,
  offsetY: (1 - Math.min(1, entrance)) * box.height + Math.sin(frame / fps * 2) * 4,
});

export const PresenterMascot: React.FC<{asset: VisualAssetRef; box: Box}> = ({asset, box}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const layout = useLayout();
  const entrance = spring({frame, fps, config: {damping: 18, stiffness: 140, mass: 0.8}});
  const {fullHeight, offsetY} = presenterGeometry(box, entrance, frame, fps);
  const flip = box.left + box.width / 2 > layout.frame.width / 2;
  return <div data-mascot-presenter="true" style={{...box, position: 'absolute', overflow: 'hidden'}}>
    <Img aria-label={`PYH mascot ${asset.pose ?? ''}`.trim()} src={staticFile(asset.path)}
      style={{position: 'absolute', left: 0, top: 0, width: '100%', height: fullHeight,
        objectFit: 'contain', objectPosition: 'center top', opacity: Math.min(1, entrance),
        transform: `translateY(${offsetY}px)${flip ? ' scaleX(-1)' : ''}`}} />
  </div>;
};
