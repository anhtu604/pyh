import React, {createContext, useContext} from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {brand} from '../anatomy/palette';
import {ANATOMY_COMPONENTS} from '../anatomy/registry';
import {Captions, CAPTION_BACKGROUND_COLOR} from '../components/Captions';
import {MascotGuide} from '../components/MascotGuide';
import {useLayout} from '../layout';
import {isMechanismVisual, type Scene} from '../types';
import {SourceMarker} from './WhiteboardScene';

export type MechanismKind = 'anatomy' | 'process' | 'comparison' | 'timelapse';
/** Trailing scene numbers cycle through four views, including across 09/10 boundaries. */
export const mechanismCamera = (id: string, progress: number, framingIndex?: number) => {
  const seed = Array.from(id).reduce((hash, char) => (hash * 31 + char.charCodeAt(0)) >>> 0, 0);
  const suffix = id.match(/(\d+)$/)?.[1];
  const index = framingIndex ?? (suffix ? Number(BigInt(suffix) % 4n) : seed % 4);
  const framing = (['wide', 'left', 'right', 'center'] as const)[index];
  const t = Math.max(0, Math.min(1, progress));
  const zoom = [1, 1.18, 1.18, 1.35][index] + [0.08, 0.14, 0.14, 0.15][index] * t;
  const angle = (seed % 360) * Math.PI / 180;
  return {framing, zoom, x: [0, 8, -8, 0][index] + Math.cos(angle) * t,
    y: Math.sin(angle) * t, origin: ['50% 50%', '35% 50%', '65% 50%', '50% 50%'][index]};
};

export const MechanismCameraContext = createContext<number | undefined>(undefined);

/** Track the last view of each subject, including across editorial scene breaks. */
export const mechanismSequenceFramings = (scenes: readonly Scene[]): (number | undefined)[] => {
  const previousBySubject = new Map<string, number>();
  const names = ['wide', 'left', 'right', 'center'];
  return scenes.map(scene => {
    if (!isMechanismVisual(scene.visual) || !scene.anatomy) return undefined;
    let view = names.indexOf(mechanismCamera(scene.id, 0).framing);
    if (previousBySubject.get(scene.anatomy.subject) === view) view = (view + 1) % names.length;
    previousBySubject.set(scene.anatomy.subject, view);
    return view;
  });
};

export const MechanismScene: React.FC<{scene: Scene; kind: MechanismKind}> = ({scene, kind}) => {
  const frame = useCurrentFrame();
  const framingIndex = useContext(MechanismCameraContext);
  const frameLayout = useLayout();
  const layout = frameLayout.mechanism;
  if (!scene.anatomy) throw new Error(`${scene.visual} requires anatomy`);
  const light = scene.visual_assets?.some((asset) => asset.role === 'mascot') ?? false;
  const anatomy = scene.anatomy;
  const Organ = ANATOMY_COMPONENTS[anatomy.subject];
  if (!Organ) throw new Error(`Unsupported anatomy subject: ${anatomy.subject}`);
  const progress = interpolate(frame, [0, Math.max(1, scene.duration_frames - 1)], [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const severity = kind === 'comparison' || kind === 'timelapse' ? anatomy.severity * progress
    : anatomy.state === 'normal' ? 0
    : kind === 'anatomy' ? anatomy.severity * (0.4 + 0.6 * progress) : anatomy.severity;
  const camera = mechanismCamera(scene.id, progress, framingIndex);
  const boxes = kind === 'comparison' ? layout.comparison : [layout.subject];
  const viewport = {left: Math.min(...boxes.map(b => b.left)), top: Math.min(...boxes.map(b => b.top)),
    width: 0, height: 0};
  viewport.width = Math.max(...boxes.map(b => b.left + b.width)) - viewport.left;
  viewport.height = Math.max(...boxes.map(b => b.top + b.height)) - viewport.top;
  const relative = (box: typeof layout.subject) => ({...box, left: box.left - viewport.left, top: box.top - viewport.top});
  const caption = frameLayout.captions;
  return <AbsoluteFill style={{backgroundColor: light ? brand.off_white : brand.night, color: light ? brand.navy : brand.off_white}}>
    <div data-mechanism-subject-region="true" style={{...viewport, position: 'absolute', overflow: 'hidden'}}>
    <AbsoluteFill data-mechanism-camera="true" style={{transform: `translate(${camera.x}%, ${camera.y}%) scale(${camera.zoom})`, transformOrigin: camera.origin}} data-framing={camera.framing}>
      {kind === 'comparison' ? <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: layout.axis}}>
        {layout.comparison.map((box, i) => <div key={i} style={{...relative(box), position: 'absolute'}}>
          <Organ state={i === 0 ? 'normal' : 'diseased'} severity={i === 0 ? 0 : severity} lightBackground={light} />
        </div>)}
      </div> : <div style={{...relative(layout.subject), position: 'absolute'}}>
        <Organ state={kind === 'timelapse' ? 'diseased' : anatomy.state} severity={severity} emphasizeFlow={kind === 'process'} lightBackground={light} />
      </div>}
    </AbsoluteFill>
    </div>
    <MascotGuide scene={scene} />
    <div data-mechanism-caption-band="true" style={{position: 'absolute', left: caption.left, bottom: caption.bottom,
      width: caption.width, height: caption.height, backgroundColor: CAPTION_BACKGROUND_COLOR, borderRadius: 16}} />
    <Captions text={scene.narration} durationInFrames={scene.duration_frames} />
    {scene.source_marker ? <SourceMarker sourceMarker={scene.source_marker} /> : null}
  </AbsoluteFill>;
};
