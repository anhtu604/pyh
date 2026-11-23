import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile} from 'remotion';
import {EvidenceHighlightScene} from './scenes/EvidenceHighlightScene';
import {SourceCardScene} from './scenes/SourceCardScene';
import {ChartScene} from './scenes/ChartScene';
import {YouTubeEndCard} from './scenes/YouTubeEndCard';
import {OutroScene} from './scenes/OutroScene';
import {WhiteboardScene} from './scenes/WhiteboardScene';
import {StatGaugeScene} from './scenes/StatGaugeScene';
import {KineticTermScene} from './scenes/KineticTermScene';
import {brand} from './anatomy/palette';
import {SceneMotionOverlay} from './motion/SceneMotionOverlay';
import {sceneTransitionPlan} from './motion/sceneEnvelope';
import {VisualAsset} from './components/VisualAsset';
import {CAPTION_BACKGROUND_COLOR, CAPTION_TEXT_COLOR} from './components/Captions';
import {LAYOUTS, LayoutContext} from './layout';
import {isMechanismVisual, parseRenderInput} from './types';
import {AnatomyScene} from './scenes/AnatomyScene';
import {ProcessScene} from './scenes/ProcessScene';
import {ComparisonScene} from './scenes/ComparisonScene';
import {TimelapseScene} from './scenes/TimelapseScene';
import {MechanismCameraContext, mechanismSequenceFramings} from './scenes/MechanismScene';
import {panelRows} from './components/AuthoredPanels';
import type {RenderInput, Scene, SceneMotion, SceneTiming, VisualStyle} from './types';

const effectiveSceneMotion = (scene: Scene, visualStyle?: VisualStyle): SceneMotion | null | undefined => {
  if (!scene.motion) return scene.motion;
  const usesScaleZoomStage =
    visualStyle === 'scale_zoom' &&
    (scene.visual === 'anatomy_animation' || scene.visual === 'process_animation') &&
    !panelRows(scene, 3).length;
  if (!usesScaleZoomStage || scene.motion.emphasis !== 'marker-underline-title') {
    return scene.motion;
  }
  if (!scene.motion.transition_in) return null;
  return {...scene.motion, emphasis: null, emphasis_text: null};
};

export const activeSceneIndex = (scenes: SceneTiming[], frame: number): number =>
  scenes.findIndex(
    (scene) => frame >= scene.start_frame && frame < scene.start_frame + scene.duration_frames,
  );

export const HealthVideo: React.FC<RenderInput> = (rawInput) => {
  const {audio_file, format_profile, scenes, youtube_cta, visualStyle} = parseRenderInput(rawInput);
  const cameraFramings = mechanismSequenceFramings(scenes);
  const forceLightCanvas = format_profile === 'youtube_long';

  return (
    <LayoutContext.Provider value={LAYOUTS[format_profile]}>
    <AbsoluteFill style={{backgroundColor: forceLightCanvas ? brand.off_white : CAPTION_BACKGROUND_COLOR, color: CAPTION_TEXT_COLOR}}>
      <Audio src={staticFile(audio_file)} />
      {scenes.map((scene, index) => {
        const motion = effectiveSceneMotion(scene, visualStyle);
        const transition = sceneTransitionPlan(scenes, index);
        return (
        <Sequence key={scene.id} from={scene.start_frame} durationInFrames={scene.duration_frames}>
          {scene.visual_assets.filter((asset) => asset.role === 'whiteboard').map((asset) => (
            <VisualAsset asset={asset} outro={scene.visual === 'brand_outro'} durationFrames={scene.duration_frames} transition={transition} key={asset.path} />
          ))}
          {scene.visual === 'anatomy_animation' ? <MechanismCameraContext.Provider value={cameraFramings[index]}><AnatomyScene scene={scene} visualStyle={visualStyle} transition={transition} forceLightCanvas={forceLightCanvas} /></MechanismCameraContext.Provider>
          : scene.visual === 'process_animation' ? <MechanismCameraContext.Provider value={cameraFramings[index]}><ProcessScene scene={scene} visualStyle={visualStyle} transition={transition} forceLightCanvas={forceLightCanvas} /></MechanismCameraContext.Provider>
          : scene.visual === 'comparison' ? <MechanismCameraContext.Provider value={cameraFramings[index]}><ComparisonScene scene={scene} transition={transition} forceLightCanvas={forceLightCanvas} /></MechanismCameraContext.Provider>
          : scene.visual === 'timelapse' ? <MechanismCameraContext.Provider value={cameraFramings[index]}><TimelapseScene scene={scene} transition={transition} forceLightCanvas={forceLightCanvas} /></MechanismCameraContext.Provider>
          : scene.visual === 'brand_outro' ? (
            <OutroScene scene={scene} transition={transition} />
          ) : scene.visual === 'evidence_highlight' ? (
            <EvidenceHighlightScene scene={scene} transition={transition} />
          ) : scene.visual === 'source_card' ? (
            <SourceCardScene scene={scene} transition={transition} />
          ) : scene.visual === 'chart' && scene.visual_assets.some((asset) => asset.role === 'chart') ? (
            <ChartScene scene={scene} transition={transition} />
          ) : scene.visual === 'stat_gauge' ? (
            <StatGaugeScene scene={scene} transition={transition} />
          ) : scene.visual === 'kinetic_term' ? (
            <KineticTermScene scene={scene} transition={transition} />
          ) : (
            <WhiteboardScene scene={scene} transition={transition} />
          )}
          {scene.visual_assets.filter((asset) => asset.role === 'brand' || asset.role === 'mascot' &&
            !isMechanismVisual(scene.visual)).map((asset) => (
            <VisualAsset
              asset={asset}
              outro={scene.visual === 'brand_outro'}
              continuation={asset.role === 'mascot' ? transition.mascotContinuation : undefined}
              transition={transition}
              key={asset.path}
            />
          ))}
          {motion ? <SceneMotionOverlay motion={motion} narration={scene.narration} /> : null}
        </Sequence>
        );
      })}
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
