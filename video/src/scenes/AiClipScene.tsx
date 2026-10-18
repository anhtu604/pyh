import React from 'react';
import {OffthreadVideo, staticFile} from 'remotion';
import {Captions} from '../components/Captions';
import {useLayout} from '../layout';
import type {Scene} from '../types';
import {SourceMarker} from './WhiteboardScene';

// Reviewed narration stays the only audio; the clip plays as-is (no loop, trim or rate change).
export const AiClipScene: React.FC<{scene: Scene}> = ({scene}) => {
  const {frame} = useLayout();
  const clip = (scene.visual_assets ?? []).find((asset) => asset.role === 'ai_clip');
  if (!clip) {
    return null;
  }
  return (
    <>
      <OffthreadVideo
        muted
        src={staticFile(clip.path)}
        style={{height: frame.height, left: 0, objectFit: 'cover', position: 'absolute', top: 0, width: frame.width}}
      />
      {scene.source_marker ? <SourceMarker sourceMarker={scene.source_marker} /> : null}
      <Captions text={scene.narration} durationInFrames={scene.duration_frames} />
    </>
  );
};
