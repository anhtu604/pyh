import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile} from 'remotion';
import {AiClipScene} from './scenes/AiClipScene';
import {EvidenceHighlightScene} from './scenes/EvidenceHighlightScene';
import {ChartScene} from './scenes/ChartScene';
import {YouTubeEndCard} from './scenes/YouTubeEndCard';
import {OutroScene} from './scenes/OutroScene';
import {WhiteboardScene} from './scenes/WhiteboardScene';
import {VisualAsset} from './components/VisualAsset';
import {CAPTION_BACKGROUND_COLOR, CAPTION_TEXT_COLOR} from './components/Captions';
import {LAYOUTS, LayoutContext} from './layout';
import {isMechanismVisual, parseRenderInput} from './types';
import {AnatomyScene} from './scenes/AnatomyScene';
import {ProcessScene} from './scenes/ProcessScene';
import {ComparisonScene} from './scenes/ComparisonScene';
import {TimelapseScene} from './scenes/TimelapseScene';
import type {RenderInput, SceneTiming} from './types';

export const activeSceneIndex = (scenes: SceneTiming[], frame: number): number =>
  scenes.findIndex(
    (scene) => frame >= scene.start_frame && frame < scene.start_frame + scene.duration_frames,
  );

export const HealthVideo: React.FC<RenderInput> = (rawInput) => {
  const {audio_file, format_profile, scenes, youtube_cta} = parseRenderInput(rawInput);

  return (
    <LayoutContext.Provider value={LAYOUTS[format_profile]}>
    <AbsoluteFill style={{backgroundColor: CAPTION_BACKGROUND_COLOR, color: CAPTION_TEXT_COLOR}}>
      <Audio src={staticFile(audio_file)} />
      {scenes.map((scene) => (
        <Sequence key={scene.id} from={scene.start_frame} durationInFrames={scene.duration_frames}>
          {scene.visual === 'anatomy_animation' ? <AnatomyScene scene={scene} />
          : scene.visual === 'process_animation' ? <ProcessScene scene={scene} />
          : scene.visual === 'comparison' ? <ComparisonScene scene={scene} />
          : scene.visual === 'timelapse' ? <TimelapseScene scene={scene} />
          : scene.visual === 'brand_outro' ? (
            <OutroScene scene={scene} />
          ) : scene.visual === 'evidence_highlight' ? (
            <EvidenceHighlightScene scene={scene} />
          ) : scene.visual === 'chart' && scene.visual_assets.some((asset) => asset.role === 'chart') ? (
            <ChartScene scene={scene} />
          ) : scene.visual === 'ai_clip' && scene.visual_assets.some((asset) => asset.role === 'ai_clip') ? (
            <AiClipScene scene={scene} />
          ) : (
            <WhiteboardScene scene={scene} />
          )}
          {scene.visual_assets.filter((asset) => asset.role !== 'chart' && asset.role !== 'ai_clip' &&
            !(isMechanismVisual(scene.visual) && asset.role === 'mascot')).map((asset) => (
            <VisualAsset asset={asset} outro={scene.visual === 'brand_outro'} key={asset.path} />
          ))}
        </Sequence>
      ))}
      {youtube_cta && (
        <Sequence from={Math.max(...scenes.map((s) => s.start_frame + s.duration_frames))}
          durationInFrames={youtube_cta.duration_frames}>
          <YouTubeEndCard text={youtube_cta.text} mascotPath={youtube_cta.mascot_path} logoPath={youtube_cta.logo_path} />
        </Sequence>
      )}
    </AbsoluteFill>
    </LayoutContext.Provider>
  );
};
