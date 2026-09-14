import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile} from 'remotion';
import {EvidenceHighlightScene} from './scenes/EvidenceHighlightScene';
import {ChartScene} from './scenes/ChartScene';
import {OutroScene} from './scenes/OutroScene';
import {WhiteboardScene} from './scenes/WhiteboardScene';
import {VisualAsset} from './components/VisualAsset';
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
          {scene.visual === 'brand_outro' ? (
            <OutroScene scene={scene} />
          ) : scene.visual === 'evidence_highlight' ? (
            <EvidenceHighlightScene scene={scene} />
          ) : scene.visual === 'chart' && scene.visual_assets.some((asset) => asset.role === 'chart') ? (
            <ChartScene scene={scene} />
          ) : (
            <WhiteboardScene scene={scene} />
          )}
          {scene.visual_assets.filter((asset) => asset.role !== 'chart').map((asset) => (
            <VisualAsset asset={asset} outro={scene.visual === 'brand_outro'} key={asset.path} />
          ))}
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
