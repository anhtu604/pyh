import React from 'react';
import {AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame} from 'remotion';

export const YouTubeEndCard: React.FC<{text: string; mascotPath: string}> = ({text, mascotPath}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 10], [0, 1], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{backgroundColor: '#12304A', color: '#FFFDF7'}}>
      <div style={{position: 'absolute', top: 340, left: 96, width: 792,
        textAlign: 'center', fontFamily: 'Arial, sans-serif', fontSize: 64,
        height: 400, display: 'flex', alignItems: 'center', justifyContent: 'center',
        lineHeight: 1.35, overflowWrap: 'anywhere', opacity}}>{text}</div>
      <Img src={staticFile(mascotPath)} aria-label="PYH mascot welcome"
        style={{position: 'absolute', top: 820, left: 190, width: 600,
          height: 710, objectFit: 'contain', opacity}} />
    </AbsoluteFill>
  );
};
