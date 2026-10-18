import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {Anatomy} from '../types';
import {anatomyColors as c, brand} from './palette';

export type OrganProps = Pick<Anatomy, 'state' | 'severity'> & {emphasizeFlow?: boolean};
export const arteryGeometry = (state: Anatomy['state'], severity: number, frame: number, fps: number) => {
  const disease = state === 'diseased' ? Math.max(0, Math.min(1, severity)) : 0;
  const pulse = Math.sin(frame / fps * Math.PI * 2 * 1.1);
  const outerRadius = 216 + pulse * (5 - disease * 4);
  const wallThickness = 53 + disease * 83;
  return {outerRadius, wallThickness, lumenRadius: outerRadius - wallThickness,
    flowSpeed: 52 - disease * 33, cellCount: 9 + Math.round(disease * 9)};
};

export const ArterySection: React.FC<OrganProps> = ({state, severity, emphasizeFlow = false}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const g = arteryGeometry(state, severity, frame, fps);
  return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img" aria-label="Stylised artery cross section"
    data-state={state} data-severity={severity}>
    <circle cx="280" cy="280" r={g.outerRadius + 18} fill={brand.teal} />
    <circle cx="280" cy="280" r={g.outerRadius} fill={c.adventitia} />
    <circle cx="280" cy="280" r={g.outerRadius - g.wallThickness * 0.27} fill={c.media} />
    <circle cx="280" cy="280" r={g.outerRadius - g.wallThickness * 0.73} fill={c.intima} />
    <circle cx="280" cy="280" r={g.lumenRadius} fill={c.lumen} data-lumen-radius={g.lumenRadius} />
    {Array.from({length: g.cellCount}, (_, i) => {
      // Parallel lanes stay inside the lumen; modulo wraps deterministically at the edge.
      const lane = ((i * 0.61803398875) % 1 - 0.5) * 1.35;
      const y = lane * g.lumenRadius;
      const half = Math.sqrt(g.lumenRadius ** 2 - y ** 2) - 22;
      const x = ((i * 57 + frame / fps * g.flowSpeed * (emphasizeFlow ? 1.3 : 1)) % (half * 2)) - half;
      return <g key={i} transform={`translate(${280 + x} ${280 + y}) rotate(${i * 31 % 70 - 35})`}>
        <ellipse rx="19" ry="13" fill={c.bloodInset} />
        <ellipse cy="-3" rx="19" ry="12" fill={c.blood} />
        <ellipse cy="-4" rx="10" ry="5" fill={c.bloodLight} />
      </g>;
    })}
    {emphasizeFlow && <path d="M240 510 H320 L306 498 M320 510 L306 522" fill="none" stroke={brand.yellow} strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />}
  </svg>;
};
