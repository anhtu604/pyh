import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import {Captions} from '../components/Captions';
import {useLayout} from '../layout';
import type {Scene} from '../types';

type WhiteboardSceneProps = {
  scene: Scene;
};

export const SourceMarker = ({sourceMarker}: {sourceMarker: string}): React.JSX.Element => {
  const m = useLayout().sourceMarker;
  return (
  <div
    aria-label={`Nguồn ${sourceMarker}`}
    style={{
      backgroundColor: '#FFD54F',
      border: '4px solid #202124',
      borderRadius: 18,
      color: '#202124',
      fontFamily: 'Arial, sans-serif',
      fontSize: m.fontSize,
      fontWeight: 800,
      padding: '12px 22px',
      position: 'absolute',
      right: m.right,
      top: m.top,
    }}
  >
    {sourceMarker}
  </div>
  );
};

export const WhiteboardScene: React.FC<WhiteboardSceneProps> = ({scene}) => {
  const frame = useCurrentFrame();
  const layout = useLayout();
  const dashOffset = interpolate(frame, [0, 45], [1, 0], {
    extrapolateRight: 'clamp',
  });
  const visualAssets = scene.visual_assets ?? [];

  return (
    <>
      {visualAssets.length === 0 ? <svg
        aria-label="Nét vẽ whiteboard"
        style={{height: '100%', left: 0, position: 'absolute', top: 0, width: '100%'}}
        viewBox={`0 0 ${layout.frame.width} ${layout.frame.height}`}
      >
        <path
          d={layout.whiteboardPath}
          fill="none"
          pathLength="1"
          stroke="#202124"
          strokeLinecap="round"
          strokeWidth="20"
          style={{strokeDasharray: 1, strokeDashoffset: dashOffset}}
        />
      </svg> : null}
      <div
        style={{
          color: '#202124',
          fontFamily: 'Arial, sans-serif',
          fontSize: layout.narration.fontSize,
          fontWeight: 800,
          left: layout.narration.left,
          lineHeight: 1.15,
          position: 'absolute',
          right: layout.narration.right,
          textAlign: 'center',
          top: layout.narration.top,
        }}
      >
        {scene.narration}
      </div>
      {scene.source_marker ? <SourceMarker sourceMarker={scene.source_marker} /> : null}
      <Captions text={scene.narration} durationInFrames={scene.duration_frames} />
    </>
  );
};
