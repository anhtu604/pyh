import React from 'react';
import {Img, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {Captions} from '../components/Captions';
import {useLayout} from '../layout';
import type {Scene} from '../types';
import {highlightImageLayout, highlightObjectFit, localHighlightRect} from './highlightGeometry';

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
          backgroundColor: 'rgba(250, 204, 21, 0.72)',
          height: local.height * imageLayout.height,
          left: imageLayout.left + local.x * imageLayout.width,
          position: 'absolute',
          top: imageLayout.top + local.y * imageLayout.height,
          width: highlightedWidth,
        }}
      />
      <div
        style={{
          backgroundColor: 'rgba(255, 253, 247, 0.95)',
          borderRadius: 28,
          bottom: layout.quote.bottom,
          color: '#202124',
          fontFamily: 'Arial, sans-serif',
          fontSize: layout.quote.fontSize,
          fontWeight: 700,
          left: layout.quote.inset,
          lineHeight: 1.3,
          padding: 36,
          position: 'absolute',
          right: layout.quote.inset,
        }}
      >
        <span>{highlight.quote}</span>
        <span style={{color: '#B45309', marginLeft: 18}}>{scene.source_marker}</span>
      </div>
      <Captions text={scene.narration} durationInFrames={scene.duration_frames} />
    </>
  );
};
