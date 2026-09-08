import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile} from 'remotion';
import {EvidenceHighlightScene} from './scenes/EvidenceHighlightScene';
import {WhiteboardScene} from './scenes/WhiteboardScene';
import {parseRenderInput} from './types';
import type {RenderInput, SceneTiming} from './types';

export const activeSceneIndex = (scenes: SceneTiming[], frame: number): number =>
  scenes.findIndex(
    (scene) => frame >= scene.start_frame && frame < scene.start_frame + scene.duration_frames,
  );

export const HealthVideo: React.FC<RenderInput> = (rawInput) => {
  const {audio_file, scenes} = parseRenderInput(rawInput);

  return (
    <AbsoluteFill style={{backgroundColor: '#FFFDF7', color: '#202124'}}>
      <Audio src={staticFile(audio_file)} />
      {scenes.map((scene) => (
        <Sequence key={scene.id} from={scene.start_frame} durationInFrames={scene.duration_frames}>
          {scene.visual === 'evidence_highlight' ? (
            <EvidenceHighlightScene scene={scene} />
          ) : (
            <WhiteboardScene scene={scene} />
          )}
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
