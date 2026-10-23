import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {brand} from './palette';

// The square is a magnified sample window, not a synovial membrane or joint boundary.
export const CONTENT_BOX = {left: 28, top: 28, width: 504, height: 504};
export const urateGeometry = (state: OrganProps['state'], severity: number, frame: number, fps: number) => {
  const level = state === 'normal' ? 0 : Math.max(0, Math.min(1, severity));
  const growth = Math.min(1, Math.max(0, frame / fps / 8));
  return {level, growth, needles: Math.ceil(level * 8), length: 8 + 62 * growth * level};
};

/** Qualitative solute -> seed -> needle schematic. No atomic structure or physical scale. */
export const UrateFluid: React.FC<OrganProps> = ({state, severity}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const g = urateGeometry(state, severity, frame, fps);
  return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img"
    aria-label="Qualitative magnified fluid sample" data-state={state}>
    <rect data-layer="sample-window" x="28" y="28" width="504" height="504" rx="32" fill={brand.navy}/>
    <g data-layer="dissolved-urate" fill={brand.teal}>
      {Array.from({length: 36}, (_, i) => <circle key={i} r="5"
        cx={72 + (i % 6) * 80 + 7 * Math.sin(frame / fps + i)}
        cy={72 + Math.floor(i / 6) * 80 + 7 * Math.cos(frame / fps + i)}/>)}
    </g>
    <g data-layer="crystal-seeds" fill={brand.yellow}>
      {Array.from({length: g.needles}, (_, i) => <circle key={i} r="4" cx={110 + (i % 3) * 150} cy={130 + Math.floor(i / 3) * 140}/>)}
    </g>
    <g data-layer="needle-crystals" fill={brand.off_white}>
      {Array.from({length: g.needles}, (_, i) => <path key={i}
        transform={`translate(${110 + (i % 3) * 150} ${130 + Math.floor(i / 3) * 140}) rotate(${i * 37})`}
        d={`M${-g.length / 2} 0 L0 -3 L${g.length / 2} 0 L0 3Z`}/>)}
    </g>
  </svg>;
};
