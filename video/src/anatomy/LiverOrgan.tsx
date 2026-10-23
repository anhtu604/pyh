import React from 'react';
import type {OrganProps} from './ArterySection';
import {anatomyColors as c, brand} from './palette';

export const CONTENT_BOX = {left: 28, top: 48, width: 504, height: 464};
export const liverOrganGeometry = (state: OrganProps['state'], severity: number) => {
  const level = state === 'normal' ? 0 : Math.max(0, Math.min(1, severity));
  const rgb = (hex: string) => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  const healthy = rgb(c.heartDeep), fat = rgb(brand.yellow), pale = rgb(brand.off_white);
  const fill = healthy.map((value, i) => Math.round(value + ((fat[i] + pale[i]) / 2 - value) * level));
  return {level, edgeRadius: 12 + 44 * level,
    fill: `rgb(${fill.join(', ')})`};
};

/** Simplified anterior surface: patient's larger right lobe is screen-left.
 * Color and inferior-edge rounding are qualitative teaching cues only. */
export const LiverOrgan: React.FC<OrganProps> = ({state, severity}) => {
  const g = liverOrganGeometry(state, severity);
  const edge = g.edgeRadius;
  const silhouette = `M28 216 C28 108 103 48 209 48 C285 48 320 80 371 110 C428 137 490 141 532 186 C528 266 460 321 350 342 C305 350 282 363 252 408 C201 ${500 + edge * .2} 101 512 57 ${480 - edge} C28 ${410 - edge * .3} 28 321 28 216Z`;
  return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img"
    aria-label="Simplified anterior liver" data-state={state} data-severity={g.level} data-edge-radius={edge}>
    <path data-layer="liver-silhouette" d={silhouette} fill={g.fill} />
    <path data-layer="right-lobe" d="M46 219 C46 119 110 65 209 65 C259 65 282 80 300 99 L280 305 C248 356 220 418 170 450 C105 470 72 430 54 390 C45 345 46 280 46 219Z"
      fill={g.fill} />
    <path data-layer="left-lobe" d="M320 101 C374 132 473 145 513 189 C493 254 430 301 348 321 L300 332Z"
      fill={g.fill} />
    <path data-layer="falciform-ligament" d="M310 96 Q306 220 286 321 L275 353"
      fill="none" stroke={brand.off_white} strokeWidth="8" strokeLinecap="round" />
  </svg>;
};

export const CUE_ACTIONS: readonly string[] = [];
