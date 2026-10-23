import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {anatomyColors as c, brand} from './palette';

/** Full painted bounds, including pulse and flow extremes. */
export const CONTENT_BOX = {left: 7, top: 12, width: 538, height: 535};

/** Qualitative teaching states, never a clinical score or a disease clock.
 * Yellow droplets remain intracellular; extracellular matrix never replaces fat.
 * Normal, steatosis, injury and matrix are selectable illustrations, not a prognosis.
 */
export const hepaticGeometry = (state: OrganProps['state'], severity: number, frame: number, fps: number) => {
  const level = state === 'normal' ? 0 : Math.max(0, Math.min(1, severity));
  return {
    dropletRadius: 13 + Math.min(level, 0.3) * 60,
    injury: level >= 0.5,
    matrix: level >= 0.8,
    incomingParticles: level > 0 ? 5 : 2,
    flow: ((frame / Math.max(1, fps)) * 30) % 100,
    signal: 0.65 + 0.25 * Math.sin(frame / Math.max(1, fps) * Math.PI),
  };
};

export const HepaticCell: React.FC<OrganProps> = ({state, severity, emphasizeFlow = false, lightBackground = false}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const g = hepaticGeometry(state, severity, frame, fps);
  const ink = lightBackground ? brand.navy : brand.off_white;
  return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img"
    aria-label="Qualitative hepatocyte and surrounding tissue schematic"
    data-state={state} data-stage={g.matrix ? 'matrix' : g.injury ? 'injury' : state === 'normal' ? 'normal' : 'storage'}>
    <g data-layer="adipose-source">
      {[70, 105, 140].map((x) => <circle key={x} cx={x} cy="30" r="18" fill={brand.yellow} />)}
      <path d="M150 50 L197 70" stroke={brand.teal} strokeWidth="5" />
      <circle cx={150 + g.flow * .47} cy={50 + g.flow * .2} r="6" fill={ink} />
      <path data-layer="insulin-signal" d="M10 118 Q34 149 58 119" stroke={brand.teal}
        strokeWidth="5" fill="none" strokeDasharray={state === 'normal' ? undefined : '6 7'} />
    </g>
    <g data-layer="hepatocyte" transform="translate(280 280) scale(1.4482758621) translate(-280 -280)">
      <rect x="135" y="135" width="290" height="290" rx="75" fill={c.heartDeep} />
      <rect x="146" y="146" width="268" height="268" rx="65" fill={c.heartLight} />
      <ellipse cx="230" cy="265" rx="36" ry="43" fill={brand.navy} />
      <g data-layer="intracellular-storage">
        {[[310, 213], [346, 293], [288, 349]].map(([x, y], i) =>
          <circle key={i} cx={x} cy={y} r={g.dropletRadius} fill={brand.yellow} />)}
      </g>
      <g data-layer="energy-use" fill={brand.teal}>
        <ellipse cx="198" cy="344" rx="24" ry="11" transform="rotate(25 198 344)" />
        <ellipse cx="205" cy="191" rx="24" ry="11" transform="rotate(-25 205 191)" />
      </g>
    </g>
    <g data-layer="parallel-flux" stroke={ink} strokeWidth={emphasizeFlow ? 5 : 3} fill="none">
      <path d="M15 250 H65 M50 239 L65 250 L50 261" />
      <path d="M495 250 H535 M520 239 L535 250 L520 261" />
      <path d="M280 495 V535 M269 520 L280 535 L291 520" />
      {Array.from({length:g.incomingParticles}, (_,i) => <circle key={i}
        cx={15 + ((g.flow + i * 100 / g.incomingParticles) % 100) * .45}
        cy="250" r="5" fill={brand.teal} stroke="none" />)}
      <circle cx={495 + g.flow * .35} cy="250" r="8" fill={brand.yellow} stroke="none" />
      <circle cx="280" cy={495 + g.flow * .35} r="5" fill={brand.teal} stroke="none" />
    </g>
    {g.injury && <g data-layer="injury-and-immune-signals" opacity={g.signal}>
      <g transform="translate(280 280) scale(1.4482758621) translate(-280 -280)">
      <path d="M265 176 l8 15 14 -8 -4 17 16 7 -17 5 2 17 -13 -10 -11 12 1 -18 -17 -3 15 -9 -7 -15Z" fill={c.bloodInset} />
      <path d="M383 356 l7 11 14 -3 -7 12 8 11 -14 -2 -8 13 -2 -16 -13 -5 13 -6Z" fill={c.bloodInset} />
      </g>
      <circle cx="525" cy="340" r="18" fill={c.blood} />
      <circle cx="525" cy="340" r="8" fill={brand.navy} />
      <path d="M490 349 L505 342" stroke={c.blood} strokeWidth="4" />
    </g>}
    <g data-layer="stellate-cell" transform="translate(38 390)">
      <path d="M0 -32 L8 -10 L30 -18 L13 2 L31 20 L8 13 L0 36 L-8 13 L-29 21 L-13 1 L-29 -18 L-8 -10Z"
        fill={g.matrix ? c.bloodInset : brand.teal} />
      <circle r="8" fill={ink} />
    </g>
    {g.matrix && <g data-layer="extracellular-matrix" stroke={ink} strokeWidth="6" fill="none">
      <path d="M60 165 Q40 270 60 470 M48 160 Q30 275 48 480 M155 505 Q280 530 440 505 M160 520 Q280 550 450 520" />
      <path d="M42 345 L62 330 M40 370 L64 358 M180 510 L188 535 M355 515 L363 538" />
    </g>}
  </svg>;
};
