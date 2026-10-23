import React from 'react';
import {Img, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {Captions} from '../components/Captions';
import {useLayout} from '../layout';
import type {Scene} from '../types';
import {highlightImageLayout, highlightObjectFit, localHighlightRect} from './highlightGeometry';
import {SourceMarker} from './WhiteboardScene';

type EvidenceHighlightSceneProps = {
  scene: Scene;
};

export const EvidenceHighlightScene: React.FC<EvidenceHighlightSceneProps> = ({scene}) => {
  const frame = useCurrentFrame();
  const layout = useLayout();
  const highlight = scene.evidence_highlight;
  if (highlight === null || highlight === undefined) {
    throw new Error('evidence_highlight scene requires an evidence highlight');
  }

  const local = localHighlightRect(highlight);
  const imageLayout = highlightImageLayout(highlight, layout.frame);

  const highlightedWidth = interpolate(frame, [0, 18], [0, local.width * imageLayout.width], {
    extrapolateRight: 'clamp',
  });

  return (
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
      {scene.source_marker ? <SourceMarker sourceMarker={scene.source_marker} /> : null}
      <Captions text={scene.narration} words={scene.words} durationInFrames={scene.duration_frames} />
    </>
  );
};
