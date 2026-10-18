import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {useLayout} from '../layout';
import type {Scene} from '../types';

export const OutroScene: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const t = useLayout().outroText;
  const opacity = interpolate(frame, [0, 12], [0, 1], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{backgroundColor: '#FFFDF7'}}>
      <div style={{position: 'absolute', top: t.top, left: t.left, width: t.width,
        textAlign: 'center', fontSize: t.fontSize, lineHeight: 1.35, color: '#202124', opacity}}>
        {scene.narration}
      </div>
    </AbsoluteFill>
  );
};
