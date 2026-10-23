import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {anatomyColors as c, brand} from './palette';

export const CONTENT_BOX = {left: 28, top: 28, width: 504, height: 504};
export const signalGeometry = (state: OrganProps['state'], severity: number, frame: number, fps: number) => {
  const level = state === 'normal' ? 0 : Math.max(0, Math.min(1, severity));
  return {level, recruited: Math.ceil(level * 6), phase: ((frame / fps) % 4) / 4};
};

/** Cell/alarm symbols, not a molecular reconstruction. Disease state presupposes priming
 * and activation; crystals alone do not automatically switch the alarm on. */
export const InflammationSignal: React.FC<OrganProps> = ({state, severity}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const g = signalGeometry(state, severity, frame, fps);
  return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img"
    aria-label="Qualitative immune signalling schematic" data-state={state}>
    <rect data-layer="sample-window" x="28" y="28" width="504" height="504" rx="32" fill={brand.navy}/>
    <g data-layer="resident-cell"><circle cx="240" cy="280" r="100" fill={brand.teal}/>
      <ellipse cx="212" cy="290" rx="34" ry="43" fill={c.vesselDeep}/></g>
    <path data-layer="crystal-cue" d="M230 240 L277 215 L241 246Z" fill={brand.off_white}/>
    <g data-layer="alarm-signal" fill={brand.yellow} opacity={g.level}>
      {[0, 1, 2].map(i => <circle key={i} cx={337 + 80 * ((g.phase + i / 3) % 1)} cy={260 + i * 20} r="6"/>)}</g>
    <g data-layer="recruited-cells" fill={c.heartLight}>
      {Array.from({length: g.recruited}, (_, i) => {
        const angle = i * Math.PI / 3;
        const distance = 195 - 35 * g.phase;
        return <circle key={i} cx={280 + distance * Math.cos(angle)} cy={280 + distance * Math.sin(angle)} r="24"/>;
      })}</g>
  </svg>;
};
