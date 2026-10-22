import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
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
  const light = scene.visual_assets?.some((asset) => asset.role === 'mascot') ?? false;
  const anatomy = scene.anatomy;
  const Organ = anatomy.subject === 'artery_cross_section' ? ArterySection
    : anatomy.subject === 'heart' ? Heart : null;
  if (!Organ) throw new Error(`Unsupported anatomy subject: ${anatomy.subject}`);
  const progress = interpolate(frame, [0, Math.max(1, scene.duration_frames - 1)], [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const severity = kind === 'comparison' || kind === 'timelapse' ? anatomy.severity * progress
    : anatomy.state === 'normal' ? 0
    : kind === 'anatomy' ? anatomy.severity * (0.4 + 0.6 * progress) : anatomy.severity;
  // The local frame makes this deterministic under seeking and out-of-order rendering.
  const seed = Array.from(scene.id).reduce((hash, char) => (hash * 31 + char.charCodeAt(0)) >>> 0, 0);
  const angle = ((seed * 137.508) % 360) * Math.PI / 180;
  const driftX = Math.cos(angle) * 16 * progress;
  const driftY = Math.sin(angle) * 12 * progress;
  const zoom = 1 + 0.12 * progress;
  return <AbsoluteFill style={{backgroundColor: light ? brand.off_white : brand.night, color: light ? brand.navy : brand.off_white}}>
    <AbsoluteFill data-mechanism-camera="true" style={{transform: `translate(${driftX}px, ${driftY}px) scale(${zoom})`, transformOrigin: '50% 50%'}}>
      {kind === 'comparison' ? <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: layout.axis}}>
        {layout.comparison.map((box, i) => <div key={i} style={{...box, position: 'absolute'}}>
          <Organ state={i === 0 ? 'normal' : 'diseased'} severity={i === 0 ? 0 : severity} lightBackground={light} />
        </div>)}
      </div> : <div style={{...layout.subject, position: 'absolute'}}>
        <Organ state={kind === 'timelapse' ? 'diseased' : anatomy.state} severity={severity} emphasizeFlow={kind === 'process'} lightBackground={light} />
      </div>}
      <MascotGuide scene={scene} />
    </AbsoluteFill>
  </AbsoluteFill>;
};
