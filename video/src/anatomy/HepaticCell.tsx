import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {anatomyColors as c, brand} from './palette';

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
      {[70, 105, 140].map((x) => <circle key={x} cx={x} cy="62" r="22" fill={brand.yellow} />)}
      <path d="M150 90 L197 140" stroke={brand.teal} strokeWidth="5" />
      <circle cx={150 + g.flow * .47} cy={90 + g.flow * .5} r="6" fill={ink} />
      <path data-layer="insulin-signal" d="M48 118 Q89 149 124 119" stroke={brand.teal}
        strokeWidth="5" fill="none" strokeDasharray={state === 'normal' ? undefined : '6 7'} />
    </g>
    <g data-layer="hepatocyte">
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
      <path d="M45 250 H130 M115 239 L130 250 L115 261" />
      <path d="M430 250 H520 M505 239 L520 250 L505 261" />
      <path d="M280 440 V515 M269 500 L280 515 L291 500" />
      {Array.from({length:g.incomingParticles}, (_,i) => <circle key={i}
        cx={45 + ((g.flow + i * 100 / g.incomingParticles) % 100) * .8}
        cy="250" r="5" fill={brand.teal} stroke="none" />)}
      <circle cx={430 + g.flow * .8} cy="250" r="8" fill={brand.yellow} stroke="none" />
      <circle cx="280" cy={440 + g.flow * .7} r="5" fill={brand.teal} stroke="none" />
    </g>
    {g.injury && <g data-layer="injury-and-immune-signals" opacity={g.signal}>
      <path d="M265 176 l8 15 14 -8 -4 17 16 7 -17 5 2 17 -13 -10 -11 12 1 -18 -17 -3 15 -9 -7 -15Z" fill={c.bloodInset} />
      <path d="M383 356 l7 11 14 -3 -7 12 8 11 -14 -2 -8 13 -2 -16 -13 -5 13 -6Z" fill={c.bloodInset} />
      <circle cx="475" cy="340" r="18" fill={c.blood} />
      <circle cx="475" cy="340" r="8" fill={brand.navy} />
      <path d="M414 349 L449 342" stroke={c.blood} strokeWidth="4" />
    </g>}
    <g data-layer="stellate-cell" transform="translate(79 369)">
      <path d="M0 -32 L8 -10 L30 -18 L13 2 L31 20 L8 13 L0 36 L-8 13 L-29 21 L-13 1 L-29 -18 L-8 -10Z"
        fill={g.matrix ? c.bloodInset : brand.teal} />
      <circle r="8" fill={ink} />
    </g>
    {g.matrix && <g data-layer="extracellular-matrix" stroke={ink} strokeWidth="6" fill="none">
      <path d="M112 165 Q68 270 112 415 M99 160 Q52 275 99 428 M155 448 Q280 485 402 447 M160 462 Q280 500 413 459" />
      <path d="M92 345 L118 330 M90 370 L121 358 M180 452 L188 475 M355 459 L363 481" />
    </g>}
  </svg>;
};
