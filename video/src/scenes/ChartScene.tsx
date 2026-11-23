import React from 'react';
import {Img, staticFile} from 'remotion';
import {Captions} from '../components/Captions';
import {useLayout} from '../layout';
import {SceneEnvelopeWrapper, type SceneTransitionProps} from '../motion/sceneEnvelope';
import type {Scene} from '../types';

export const ChartScene: React.FC<{scene: Scene; transition?: SceneTransitionProps}> = ({scene, transition}) => {
  const {chart: layoutChart} = useLayout();
  const chart = (scene.visual_assets ?? []).find((asset) => asset.role === 'chart');
  if (!chart) {
    return null;
  }
  const content = (
    <>
      <Img
        aria-label="Biểu đồ dữ liệu đã khai báo"
        src={staticFile(chart.path)}
        style={{...layoutChart.image, objectFit: 'contain', position: 'absolute'}}
      />
      <Captions text={scene.narration} words={scene.words} durationInFrames={scene.duration_frames} />
    </>
  );
  return transition ? <SceneEnvelopeWrapper transition={transition}>{content}</SceneEnvelopeWrapper> : content;
};
