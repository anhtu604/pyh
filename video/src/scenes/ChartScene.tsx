import React from 'react';
import {Img, staticFile} from 'remotion';
import {Captions} from '../components/Captions';
import {useLayout} from '../layout';
import type {Scene} from '../types';
import {SourceMarker} from './WhiteboardScene';

export const ChartScene: React.FC<{scene: Scene}> = ({scene}) => {
  const {chart: layoutChart} = useLayout();
  const chart = (scene.visual_assets ?? []).find((asset) => asset.role === 'chart');
  if (!chart) {
    return null;
  }
  return (
    <>
      <Img
        aria-label="Biểu đồ dữ liệu đã khai báo"
        src={staticFile(chart.path)}
        style={{...layoutChart.image, objectFit: 'contain', position: 'absolute'}}
      />
      <div
        style={{bottom: layoutChart.narrationBottom, color: '#202124', fontFamily: 'Arial, sans-serif', fontSize: layoutChart.narrationFontSize,
          fontWeight: 800, left: layoutChart.narrationInset, lineHeight: 1.15, position: 'absolute', right: layoutChart.narrationInset,
          textAlign: 'center'}}
      >
        {scene.narration}
      </div>
      {scene.source_marker ? <SourceMarker sourceMarker={scene.source_marker} /> : null}
      <Captions text={scene.narration} durationInFrames={scene.duration_frames} />
    </>
  );
};
