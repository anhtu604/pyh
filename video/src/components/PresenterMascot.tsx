import React from 'react';
import {Img, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {useLayout, type Box} from '../layout';
import {
  computeSceneEnvelope,
  smoothstepCubic,
  type SceneTransitionProps,
} from '../motion/sceneEnvelope';
import type {VisualAssetRef} from '../types';

// The wrapper stays fixed at the cut line. The lower 35% remains below it,
// even at the highest bob, so animation cannot uncover the bottom edge.
export const presenterGeometry = (box: Box, entrance: number, frame: number, fps: number) => ({
  fullHeight: box.height / 0.65,
  offsetY: (1 - Math.min(1, entrance)) * box.height + Math.sin(frame / fps * 2) * 4,
});

export const PresenterMascot: React.FC<{
  asset: VisualAssetRef;
  box: Box;
  continuation?: boolean;
  transition?: SceneTransitionProps;
}> = ({asset, box, continuation = false, transition}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const layout = useLayout();
  const bob = Math.sin(frame / fps * 2) * 4;
  const fullHeight = box.height / 0.65;

  let offsetY: number;
  let opacity: number;

  if (continuation) {
    // Same-host continuation: stay anchored at the cut line with gentle 6f cross-settle (no bottom-up drop).
    offsetY = bob;
    opacity = 0.82 + 0.18 * smoothstepCubic(frame / 6);
  } else if (transition && transition.durationFrames >= 45) {
    // Smooth video entrance: 12f smoothstep, capped at 36px travel (no 450px jump or bounce).
    const enter = smoothstepCubic(frame / 12);
    offsetY = (1 - enter) * 36 + bob;
    opacity = enter;
  } else {
    const entrance = spring({frame, fps, config: {damping: 18, stiffness: 140, mass: 0.8}});
    const geom = presenterGeometry(box, entrance, frame, fps);
    offsetY = geom.offsetY;
    opacity = Math.min(1, entrance);
  }

  if (transition && transition.durationFrames >= 45) {
    const env = computeSceneEnvelope(frame, transition);
    if (transition.exitMode !== 'none' && frame >= transition.durationFrames - 10) {
      opacity *= env.opacity;
    }
  }

  const flip = box.left + box.width / 2 > layout.frame.width / 2;
  return <div data-mascot-presenter="true" data-mascot-continuation={continuation ? 'true' : undefined} style={{...box, position: 'absolute', overflow: 'hidden'}}>
    <Img aria-label={`PYH mascot ${asset.pose ?? ''}`.trim()} src={staticFile(asset.path)}
      style={{position: 'absolute', left: 0, top: 0, width: '100%', height: fullHeight,
        objectFit: 'contain', objectPosition: 'center top', opacity,
        transform: `translateY(${offsetY}px)${flip ? ' scaleX(-1)' : ''}`}} />
  </div>;
};
