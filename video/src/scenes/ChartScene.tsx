import React from 'react';
import {Img, staticFile} from 'remotion';
import {Captions} from '../components/Captions';
import type {Scene} from '../types';
import {SourceMarker} from './WhiteboardScene';

export const ChartScene: React.FC<{scene: Scene}> = ({scene}) => {
  const chart = (scene.visual_assets ?? []).find((asset) => asset.role === 'chart');
  if (!chart) {
    return null;
  }
  return (
    <>
      <Img
        aria-label="Biểu đồ dữ liệu đã khai báo"
        src={staticFile(chart.path)}
        style={{height: 1040, left: 70, objectFit: 'contain', position: 'absolute', top: 210, width: 940}}
      />
      <div
        style={{bottom: 430, color: '#202124', fontFamily: 'Arial, sans-serif', fontSize: 58,
          fontWeight: 800, left: 84, lineHeight: 1.15, position: 'absolute', right: 84,
          textAlign: 'center'}}
      >
        {scene.narration}
      </div>
      {scene.source_marker ? <SourceMarker sourceMarker={scene.source_marker} /> : null}
      <Captions text={scene.narration} durationInFrames={scene.duration_frames} />
    </>
  );
};
