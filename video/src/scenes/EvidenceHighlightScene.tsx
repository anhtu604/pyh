import React from 'react';
import {Img, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {Captions} from '../components/Captions';
import {evidenceFrame, useLayout} from '../layout';
import {SceneEnvelopeWrapper, type SceneTransitionProps} from '../motion/sceneEnvelope';
import type {Scene} from '../types';
import {highlightImageLayout, highlightObjectFit, localHighlightRect} from './highlightGeometry';

type EvidenceHighlightSceneProps = {
  scene: Scene;
  transition?: SceneTransitionProps;
};

export const EvidenceHighlightScene: React.FC<EvidenceHighlightSceneProps> = ({scene, transition}) => {
  const frame = useCurrentFrame();
  const layout = useLayout();
  const highlight = scene.evidence_highlight;
  if (highlight === null || highlight === undefined) {
    throw new Error('evidence_highlight scene requires an evidence highlight');
  }

  const local = localHighlightRect(highlight);
  const imageLayout = highlightImageLayout(highlight, evidenceFrame(layout));

  const highlightedWidth = interpolate(frame, [0, 18], [0, local.width * imageLayout.width], {
    extrapolateRight: 'clamp',
  });

  const content = (
    <>
      <Img
        src={staticFile(highlight.image)}
        style={{...imageLayout, objectFit: highlightObjectFit(highlight), position: 'absolute'}}
      />
      <div
        style={{
          backgroundColor: 'rgba(250, 204, 21, 0.3)',
          mixBlendMode: 'multiply',
          height: local.height * imageLayout.height,
          left: imageLayout.left + local.x * imageLayout.width,
          position: 'absolute',
          top: imageLayout.top + local.y * imageLayout.height,
          width: highlightedWidth,
        }}
      />
      <Captions text={scene.narration} words={scene.words} durationInFrames={scene.duration_frames} />
    </>
  );
  return transition ? <SceneEnvelopeWrapper transition={transition}>{content}</SceneEnvelopeWrapper> : content;
};
