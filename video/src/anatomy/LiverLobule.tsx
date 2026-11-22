import React from 'react';
import type {OrganProps} from './ArterySection';
import {ENTITY_COLORS} from './entityColors';
import {brand} from './palette';
import {hexToRgba} from '../style/pyhStyle';

export const CONTENT_BOX = {left: 22, top: 22, width: 516, height: 516};
const corners = [[280, 22], [538, 151], [538, 409], [280, 538], [22, 409], [22, 151]];
/** Classic lobule schematic: central venule, peripheral portal triads and
 * alternating radial hepatocyte plates/sinusoids. Severity is qualitative,
 * not a fibrosis score or a prediction that steatosis must progress. */
export const LiverLobule: React.FC<OrganProps> = ({state, severity}) => {
  const level = state === 'normal' ? 0 : Math.max(0, Math.min(1, severity));
  const normalFill = ENTITY_COLORS.tissue_normal.rgba;
  const cordFill = hexToRgba(ENTITY_COLORS.tissue_normal.hex, 0.45);
  const boundaryStroke = hexToRgba(brand.navy, 0.45);
  return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img"
    aria-label="Classic hepatic lobule schematic" data-state={state} data-severity={level}>
    <polygon data-layer="lobule-boundary" points="280,22 538,151 538,409 280,538 22,409 22,151" fill={normalFill} stroke={boundaryStroke} strokeWidth="4" />
    <polygon points="280,34 526,158 526,402 280,526 34,402 34,158" fill={hexToRgba(ENTITY_COLORS.tissue_normal.hex, 0.16)} />
    <g data-layer="sinusoids" stroke={ENTITY_COLORS.blood_flow.hex} strokeOpacity="0.55" strokeWidth="9" fill="none">
      {Array.from({length: 12}, (_, i) => <path key={i} transform={`rotate(${i * 30} 280 280)`}
        d="M280 244 Q265 186 280 66" />)}
    </g>
    <g data-layer="hepatocyte-cords">
      {Array.from({length: 12}, (_, i) => <g key={i} transform={`rotate(${i * 30 + 15} 280 280)`}>
        {[96, 138, 180, 222].map((y, j) => <g key={y} data-hepatocyte="true">
          <rect x="262" y={y - 18} width="36" height="36" rx="10" fill={cordFill} stroke={hexToRgba(brand.navy, 0.35)} strokeWidth="1.4" />
          <circle cx="271" cy={y - 5} r="4" fill={brand.navy} />
          {level > 0 && <circle data-fat-droplet="true" cx="285" cy={y + 3} r={3 + level * 5} fill={ENTITY_COLORS.tissue_injured.hex} />}
          {level >= 0.6 && j % 2 === 0 && <circle data-fat-droplet="true" cx="275" cy={y + 9} r="4" fill={ENTITY_COLORS.tissue_injured.hex} />}
        </g>)}
      </g>)}
    </g>
    <g data-layer="central-vein">
      <circle cx="280" cy="280" r="35" fill={ENTITY_COLORS.blood_flow.hex} />
      <circle cx="280" cy="280" r="25" fill={brand.off_white} />
      <circle cx="280" cy="280" r="22" fill={hexToRgba(ENTITY_COLORS.blood_flow.hex, 0.24)} />
    </g>
    <g data-layer="portal-triads">
      {corners.map(([x, y], i) => {
        // Inset the triad from its corner so all three structures remain in the lobule.
        const cx = 280 + (x - 280) * 0.80, cy = 280 + (y - 280) * 0.80;
        return <g key={i} data-portal-triad={i} transform={`translate(${cx} ${cy})`}>
          <circle r="25" fill={brand.off_white} stroke={hexToRgba(brand.navy, 0.25)} strokeWidth="1.5" />
          <circle data-portal-vein="true" cx="-7" cy="-3" r="11" fill={brand.navy} />
          <circle data-hepatic-artery="true" cx="12" cy="-6" r="6" fill={ENTITY_COLORS.blood_flow.hex} />
          <circle data-bile-duct="true" cx="9" cy="12" r="6" fill={ENTITY_COLORS.bile_flow.hex} stroke={brand.navy} strokeWidth="1.2" />
        </g>;
      })}
    </g>
    {level >= 0.5 && <g data-layer="inflammation" fill={ENTITY_COLORS.tissue_injured.hex} stroke={brand.navy} strokeWidth="2">
      {[[204, 209], [215, 219], [199, 226], [362, 350], [374, 355], [366, 366]].map(([x, y], i) =>
        <circle key={i} cx={x} cy={y} r="6" />)}
    </g>}
    {level >= 0.8 && <g data-layer="portal-fibrosis" stroke={ENTITY_COLORS.scar_fibrosis.hex} opacity={ENTITY_COLORS.scar_fibrosis.opacity} strokeWidth="4" strokeDasharray="6 4" fill="none">
      {corners.map(([x, y], i) => <path key={i}
        d={`M${280 + (x - 280) * 0.71} ${280 + (y - 280) * 0.71} Q${280 + (x - 280) * 0.57 + 12} ${280 + (y - 280) * 0.57} ${280 + (x - 280) * 0.40} ${280 + (y - 280) * 0.40}`} />)}
    </g>}
  </svg>;
};

export const CUE_ACTIONS: readonly string[] = [];

export const FOCUS_REGIONS = {"overview": {"left": 0, "top": 0, "width": 560, "height": 560}, "central_vein": {"left": 205, "top": 205, "width": 150, "height": 150}, "portal_triad": {"left": 410, "top": 132, "width": 100, "height": 100}};
export const LABELS = {};
