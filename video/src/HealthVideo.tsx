import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile} from 'remotion';
import {EvidenceHighlightScene} from './scenes/EvidenceHighlightScene';
import {SourceCardScene} from './scenes/SourceCardScene';
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
import {MechanismCameraContext, mechanismSequenceFramings} from './scenes/MechanismScene';
import type {RenderInput, SceneTiming} from './types';

export const activeSceneIndex = (scenes: SceneTiming[], frame: number): number =>
  scenes.findIndex(
    (scene) => frame >= scene.start_frame && frame < scene.start_frame + scene.duration_frames,
  );

export const HealthVideo: React.FC<RenderInput> = (rawInput) => {
  const {audio_file, format_profile, scenes, youtube_cta} = parseRenderInput(rawInput);
  const cameraFramings = mechanismSequenceFramings(scenes);

  return (
    <LayoutContext.Provider value={LAYOUTS[format_profile]}>
    <AbsoluteFill style={{backgroundColor: CAPTION_BACKGROUND_COLOR, color: CAPTION_TEXT_COLOR}}>
      <Audio src={staticFile(audio_file)} />
      {scenes.map((scene, index) => (
        <Sequence key={scene.id} from={scene.start_frame} durationInFrames={scene.duration_frames}>
          {scene.visual_assets.filter((asset) => asset.role === 'whiteboard').map((asset) => (
            <VisualAsset asset={asset} outro={scene.visual === 'brand_outro'} key={asset.path} />
          ))}
          {scene.visual === 'anatomy_animation' ? <MechanismCameraContext.Provider value={cameraFramings[index]}><AnatomyScene scene={scene} /></MechanismCameraContext.Provider>
          : scene.visual === 'process_animation' ? <MechanismCameraContext.Provider value={cameraFramings[index]}><ProcessScene scene={scene} /></MechanismCameraContext.Provider>
          : scene.visual === 'comparison' ? <MechanismCameraContext.Provider value={cameraFramings[index]}><ComparisonScene scene={scene} /></MechanismCameraContext.Provider>
          : scene.visual === 'timelapse' ? <MechanismCameraContext.Provider value={cameraFramings[index]}><TimelapseScene scene={scene} /></MechanismCameraContext.Provider>
          : scene.visual === 'brand_outro' ? (
            <OutroScene scene={scene} />
          ) : scene.visual === 'evidence_highlight' ? (
            <EvidenceHighlightScene scene={scene} />
          ) : scene.visual === 'source_card' ? (
            <SourceCardScene scene={scene} />
          ) : scene.visual === 'chart' && scene.visual_assets.some((asset) => asset.role === 'chart') ? (
            <ChartScene scene={scene} />
          ) : (
            <WhiteboardScene scene={scene} />
          )}
          {scene.visual_assets.filter((asset) => asset.role === 'brand' || asset.role === 'mascot' &&
            !isMechanismVisual(scene.visual)).map((asset) => (
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
