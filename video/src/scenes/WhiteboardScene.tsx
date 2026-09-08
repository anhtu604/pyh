import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import {Captions} from '../components/Captions';
import type {Scene} from '../types';

type WhiteboardSceneProps = {
  scene: Scene;
};

export const WhiteboardScene: React.FC<WhiteboardSceneProps> = ({scene}) => {
  const frame = useCurrentFrame();
  const dashOffset = interpolate(frame, [0, 45], [1, 0], {
    extrapolateRight: 'clamp',
  });

  return (
    <>
      <svg
        aria-label="Nét vẽ whiteboard"
        style={{height: '100%', left: 0, position: 'absolute', top: 0, width: '100%'}}
        viewBox="0 0 1080 1920"
      >
        <path
          d="M150 570 C 350 400, 650 740, 930 530"
          fill="none"
          pathLength="1"
          stroke="#202124"
          strokeLinecap="round"
          strokeWidth="20"
          style={{strokeDasharray: 1, strokeDashoffset: dashOffset}}
        />
      </svg>
      <div
        style={{
          color: '#202124',
          fontFamily: 'Arial, sans-serif',
          fontSize: 72,
          fontWeight: 800,
          left: 96,
          lineHeight: 1.15,
          position: 'absolute',
          right: 96,
          textAlign: 'center',
          top: 760,
        }}
      >
        {scene.narration}
      </div>
      <Captions text={scene.narration} durationInFrames={scene.duration_frames} />
    </>
  );
};
