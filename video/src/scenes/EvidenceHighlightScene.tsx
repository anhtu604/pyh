import React from 'react';
import {Img, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {Captions} from '../components/Captions';
import type {Scene} from '../types';

type EvidenceHighlightSceneProps = {
  scene: Scene;
};

export const EvidenceHighlightScene: React.FC<EvidenceHighlightSceneProps> = ({scene}) => {
  const frame = useCurrentFrame();
  const highlight = scene.evidence_highlight;
  if (highlight === null || highlight === undefined) {
    throw new Error('evidence_highlight scene requires an evidence highlight');
  }

  const highlightedWidth = interpolate(frame, [0, 18], [0, highlight.width * 100], {
    extrapolateRight: 'clamp',
  });

  return (
    <>
      <Img
        src={staticFile(highlight.image)}
        style={{height: '100%', objectFit: 'cover', position: 'absolute', width: '100%'}}
      />
      <div
        style={{
          backgroundColor: 'rgba(250, 204, 21, 0.72)',
          height: `${highlight.height * 100}%`,
          left: `${highlight.x * 100}%`,
          position: 'absolute',
          top: `${highlight.y * 100}%`,
          width: `${highlightedWidth}%`,
        }}
      />
      <div
        style={{
          backgroundColor: 'rgba(255, 253, 247, 0.95)',
          borderRadius: 28,
          bottom: 390,
          color: '#202124',
          fontFamily: 'Arial, sans-serif',
          fontSize: 46,
          fontWeight: 700,
          left: 72,
          lineHeight: 1.3,
          padding: 36,
          position: 'absolute',
          right: 72,
        }}
      >
        <span>{highlight.quote}</span>
        <span style={{color: '#B45309', marginLeft: 18}}>{scene.source_marker}</span>
      </div>
      <Captions text={scene.narration} durationInFrames={scene.duration_frames} />
    </>
  );
};
