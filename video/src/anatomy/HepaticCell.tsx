import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {ENTITY_COLORS} from './entityColors';
import {brand} from './palette';
import {hexToRgba} from '../style/pyhStyle';

/** Full painted bounds, including pulse and flow extremes. */
export const CONTENT_BOX = {left: 7, top: 12, width: 538, height: 535};
export const CUE_ACTIONS = ['fat', 'inflame', 'fibrose'] as const;

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

export const HepaticCell: React.FC<OrganProps> = ({state, severity, emphasizeFlow = false, lightBackground = false, cueProgress}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const g = hepaticGeometry(state, severity, frame, fps);
  const cue = (action: string) => Math.max(0, Math.min(1, cueProgress?.[action] ?? 0));
  if (cueProgress) {
    g.dropletRadius = 13 + (g.dropletRadius - 13) * cue('fat');
    g.incomingParticles = 2 + Math.round((g.incomingParticles - 2) * cue('fat'));
    g.injury = g.injury && cue('inflame') > 0;
    g.matrix = g.matrix && cue('fibrose') > 0;
    g.signal *= cue('inflame');
  }
  const ink = lightBackground ? brand.navy : brand.off_white;
  const membraneFill = hexToRgba(ENTITY_COLORS.tissue_normal.hex, 0.65);
  const cytoplasmFill = ENTITY_COLORS.tissue_normal.rgba;
  const injuredHex = ENTITY_COLORS.tissue_injured.hex;
  const flowHex = ENTITY_COLORS.blood_flow.hex;
  const scarStroke = lightBackground ? ENTITY_COLORS.scar_fibrosis.hex : hexToRgba(brand.off_white, 0.55);

  return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img"
    aria-label="Qualitative hepatocyte and surrounding tissue schematic"
    data-state={state} data-stage={g.matrix ? 'matrix' : g.injury ? 'injury' : state === 'normal' ? 'normal' : 'storage'}>
    <g data-layer="adipose-source">
      {[70, 105, 140].map((x) => <circle key={x} cx={x} cy="30" r="18" fill={injuredHex} fillOpacity="0.85" />)}
      <path d="M150 50 L197 70" stroke={flowHex} strokeWidth="5" />
      <circle cx={150 + g.flow * 0.47} cy={50 + g.flow * 0.2} r="6" fill={ink} />
      <path data-layer="insulin-signal" d="M10 118 Q34 149 58 119" stroke={flowHex}
        strokeWidth="5" fill="none" strokeDasharray={state === 'normal' || (cueProgress && cue('fat') <= 0) ? undefined : '6 7'} />
    </g>
    <g data-layer="hepatocyte" transform="translate(280 280) scale(1.4482758621) translate(-280 -280)">
      <rect x="135" y="135" width="290" height="290" rx="75" fill={membraneFill} stroke={brand.navy} strokeWidth="3" />
      <rect x="146" y="146" width="268" height="268" rx="65" fill={cytoplasmFill} />
      <ellipse cx="230" cy="265" rx="36" ry="43" fill={brand.navy} />
      <g data-layer="intracellular-storage">
        {[[310, 213], [346, 293], [288, 349]].map(([x, y], i) =>
          <circle key={i} cx={x} cy={y} r={g.dropletRadius} fill={injuredHex} />)}
      </g>
      <g data-layer="energy-use" fill={flowHex}>
        <ellipse cx="198" cy="344" rx="24" ry="11" transform="rotate(25 198 344)" />
        <ellipse cx="205" cy="191" rx="24" ry="11" transform="rotate(-25 205 191)" />
      </g>
    </g>
    <g data-layer="parallel-flux" stroke={ink} strokeWidth={emphasizeFlow ? 5 : 3} fill="none">
      <path d="M15 250 H65 M50 239 L65 250 L50 261" />
      <path d="M495 250 H535 M520 239 L535 250 L520 261" />
      <path d="M280 495 V535 M269 520 L280 535 L291 520" />
      {Array.from({length: g.incomingParticles}, (_, i) => <circle key={i}
        cx={15 + ((g.flow + i * 100 / g.incomingParticles) % 100) * 0.45}
        cy="250" r="5" fill={flowHex} stroke="none" />)}
      <circle cx={495 + g.flow * 0.35} cy="250" r="8" fill={injuredHex} stroke="none" />
      <circle cx="280" cy={495 + g.flow * 0.35} r="5" fill={flowHex} stroke="none" />
    </g>
    {g.injury && <g data-layer="injury-and-immune-signals" opacity={g.signal}>
      <g transform="translate(280 280) scale(1.4482758621) translate(-280 -280)">
        <path d="M265 176 l8 15 14 -8 -4 17 16 7 -17 5 2 17 -13 -10 -11 12 1 -18 -17 -3 15 -9 -7 -15Z" fill={injuredHex} stroke={brand.navy} strokeWidth="2" />
        <path d="M383 356 l7 11 14 -3 -7 12 8 11 -14 -2 -8 13 -2 -16 -13 -5 13 -6Z" fill={injuredHex} stroke={brand.navy} strokeWidth="2" />
      </g>
      <circle cx="525" cy="340" r="18" fill={injuredHex} stroke={brand.navy} strokeWidth="2" />
      <circle cx="525" cy="340" r="8" fill={brand.navy} />
      <path d="M490 349 L505 342" stroke={injuredHex} strokeWidth="4" />
    </g>}
    <g data-layer="stellate-cell" transform="translate(38 390)">
      <path d="M0 -32 L8 -10 L30 -18 L13 2 L31 20 L8 13 L0 36 L-8 13 L-29 21 L-13 1 L-29 -18 L-8 -10Z"
        fill={g.matrix ? injuredHex : flowHex} />
      <circle r="8" fill={ink} />
    </g>
    {g.matrix && <g data-layer="extracellular-matrix" opacity={cueProgress ? cue('fibrose') : 1} stroke={scarStroke} strokeWidth="5" strokeDasharray="10 6" fill="none">
      <path d="M60 165 Q40 270 60 470 M48 160 Q30 275 48 480 M155 505 Q280 530 440 505 M160 520 Q280 550 450 520" />
      <path d="M42 345 L62 330 M40 370 L64 358 M180 510 L188 535 M355 515 L363 538" />
    </g>}
  </svg>;
};

export const FOCUS_REGIONS = {"overview": {"left": 0, "top": 0, "width": 560, "height": 560}, "hepatocyte": {"left": 65, "top": 65, "width": 430, "height": 430}, "lipid": {"left": 275, "top": 170, "width": 180, "height": 230}};
export const LABELS = {};
