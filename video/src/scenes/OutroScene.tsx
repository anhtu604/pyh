import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import type {Scene} from '../types';

export const OutroScene: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 12], [0, 1], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{backgroundColor: '#FFFDF7'}}>
      <div style={{position: 'absolute', top: 850, left: 90, width: 900,
        textAlign: 'center', fontSize: 54, lineHeight: 1.35, color: '#202124', opacity}}>
        {scene.narration}
      </div>
    </AbsoluteFill>
  );
};
