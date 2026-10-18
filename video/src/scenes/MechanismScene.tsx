import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from 'remotion';
import {ArterySection} from '../anatomy/ArterySection';
import {Heart} from '../anatomy/Heart';
import {brand} from '../anatomy/palette';
import {MascotGuide} from '../components/MascotGuide';
import {useLayout} from '../layout';
import type {Scene} from '../types';

export type MechanismKind = 'anatomy' | 'process' | 'comparison' | 'timelapse';
export const MechanismScene: React.FC<{scene: Scene; kind: MechanismKind}> = ({scene, kind}) => {
  const frame = useCurrentFrame();
  const layout = useLayout().mechanism;
  if (!scene.anatomy) throw new Error(`${scene.visual} requires anatomy`);
  const anatomy = scene.anatomy;
  const Organ = anatomy.subject === 'artery_cross_section' ? ArterySection
    : anatomy.subject === 'heart' ? Heart : null;
  if (!Organ) throw new Error(`Unsupported anatomy subject: ${anatomy.subject}`);
  const severity = kind === 'timelapse' ? interpolate(frame, [0, Math.max(1, scene.duration_frames - 1)], [0, anatomy.severity],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}) : anatomy.severity;
  const zoom = kind === 'anatomy' ? interpolate(frame, [0, 30], [1.15, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.bezier(0.16, 1, 0.3, 1)}) : 1;
  return <AbsoluteFill style={{backgroundColor: brand.night}}>
    {kind === 'comparison' ? <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: layout.axis}}>
      {layout.comparison.map((box, i) => <div key={i} style={{...box, position: 'absolute'}}>
        <Organ state={i === 0 ? 'normal' : 'diseased'} severity={i === 0 ? 0 : severity} />
      </div>)}
    </div> : <div style={{...layout.subject, position: 'absolute', transform: `scale(${zoom})`}}>
      <Organ state={kind === 'timelapse' ? 'diseased' : anatomy.state} severity={severity} emphasizeFlow={kind === 'process'} />
    </div>}
    <MascotGuide scene={scene} />
  </AbsoluteFill>;
};
