import React from 'react';
import {OffthreadVideo, staticFile} from 'remotion';
import {Captions} from '../components/Captions';
import type {Scene} from '../types';
import {SourceMarker} from './WhiteboardScene';

// Reviewed narration stays the only audio; the clip plays as-is (no loop, trim or rate change).
export const AiClipScene: React.FC<{scene: Scene}> = ({scene}) => {
  const clip = (scene.visual_assets ?? []).find((asset) => asset.role === 'ai_clip');
  if (!clip) {
    return null;
  }
  return (
    <>
      <OffthreadVideo
        muted
        src={staticFile(clip.path)}
        style={{height: 1920, left: 0, objectFit: 'cover', position: 'absolute', top: 0, width: 1080}}
      />
      {scene.source_marker ? <SourceMarker sourceMarker={scene.source_marker} /> : null}
      <Captions text={scene.narration} durationInFrames={scene.duration_frames} />
    </>
  );
};
