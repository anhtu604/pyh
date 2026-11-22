import React from 'react';
import type {OrganProps} from './ArterySection';
import {ENTITY_COLORS} from './entityColors';
import {brand} from './palette';
import {hexToRgba} from '../style/pyhStyle';

export const CONTENT_BOX = {left: 28, top: 48, width: 504, height: 464};
export const liverOrganGeometry = (state: OrganProps['state'], severity: number) => {
  const level = state === 'normal' ? 0 : Math.max(0, Math.min(1, severity));
  const fill = level === 0
    ? ENTITY_COLORS.tissue_normal.rgba
    : hexToRgba(ENTITY_COLORS.tissue_injured.hex, Number((0.35 + 0.5 * level).toFixed(3)));
  return {level, edgeRadius: 12 + 44 * level, fill};
};

/** Simplified anterior surface: patient's larger right lobe is screen-left.
 * Color and inferior-edge rounding are qualitative teaching cues only. */
export const LiverOrgan: React.FC<OrganProps> = ({state, severity, lightBackground = true}) => {
  const g = liverOrganGeometry(state, severity);
  const edge = g.edgeRadius;
  const silhouette = `M28 216 C28 108 103 48 209 48 C285 48 320 80 371 110 C428 137 490 141 532 186 C528 266 460 321 350 342 C305 350 282 363 252 408 C201 ${500 + edge * 0.2} 101 512 57 ${480 - edge} C28 ${410 - edge * 0.3} 28 321 28 216Z`;
  const contextInk = lightBackground ? brand.navy : brand.off_white;
  const contourStroke = g.level > 0
    ? ENTITY_COLORS.tissue_injured.hex
    : ENTITY_COLORS.blood_flow.hex;
  const rightLobeFill = g.level === 0
    ? hexToRgba(ENTITY_COLORS.tissue_normal.hex, 0.44)
    : hexToRgba(ENTITY_COLORS.tissue_injured.hex, Number((0.46 + 0.39 * g.level).toFixed(3)));
  const leftLobeFill = g.level === 0
    ? hexToRgba(ENTITY_COLORS.tissue_normal.hex, 0.24)
    : hexToRgba(ENTITY_COLORS.tissue_injured.hex, Number((0.28 + 0.36 * g.level).toFixed(3)));

  return (
    <svg viewBox="0 0 560 560" width="100%" height="100%" role="img"
      aria-label="Simplified anterior liver" data-state={state} data-severity={g.level} data-edge-radius={edge}>
      {/* Minimal anatomical orientation context: stylized diaphragm arch & costal margin */}
      <g data-layer="orientation-context" opacity="0.16" fill="none" stroke={contextInk} strokeLinecap="round">
        <path d="M18 148 Q200 12 370 46 Q470 68 542 132" strokeWidth="4" strokeDasharray="10 8" />
        <path d="M16 148 C10 290 12 430 46 530" strokeWidth="3" />
        <path d="M542 132 C548 250 538 390 506 530" strokeWidth="3" />
      </g>
      <path data-layer="liver-silhouette" d={silhouette} fill={g.fill} stroke={contourStroke} strokeWidth="4" strokeLinejoin="round" />
      <path data-layer="right-lobe" d="M46 219 C46 119 110 65 209 65 C259 65 282 80 300 99 L280 305 C248 356 220 418 170 450 C105 470 72 430 54 390 C45 345 46 280 46 219Z"
        fill={rightLobeFill} />
      <path data-layer="left-lobe" d="M320 101 C374 132 473 145 513 189 C493 254 430 301 348 321 L300 332Z"
        fill={leftLobeFill} />
      {/* Subtle flat superior dome highlight (no gradient) */}
      <path d="M84 128 C126 78 196 66 266 84" fill="none" stroke={brand.off_white} strokeOpacity="0.45" strokeWidth="6" strokeLinecap="round" />
      <path d="M312 98 Q308 222 288 323 L277 355" fill="none" stroke={hexToRgba(brand.navy, 0.24)} strokeWidth="10" strokeLinecap="round" />
      <path data-layer="falciform-ligament" d="M310 96 Q306 220 286 321 L275 353"
        fill="none" stroke={brand.off_white} strokeWidth="7" strokeLinecap="round" />
    </svg>
  );
};

export const CUE_ACTIONS: readonly string[] = [];

export const FOCUS_REGIONS = {"overview": {"left": 0, "top": 0, "width": 560, "height": 560}, "right_lobe": {"left": 30, "top": 50, "width": 290, "height": 460}, "left_lobe": {"left": 285, "top": 90, "width": 250, "height": 270}};
export const LABELS = {};
