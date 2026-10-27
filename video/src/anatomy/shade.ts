import React from 'react';
import {anatomyColors as c, brand} from './palette';

const clampByte = (n: number) => Math.max(0, Math.min(255, Math.round(n)));
const parseHex = (hex: string): [number, number, number] => {
  const clean = hex.replace('#', '');
  return [
    parseInt(clean.slice(0, 2), 16),
    parseInt(clean.slice(2, 4), 16),
    parseInt(clean.slice(4, 6), 16),
  ];
};
const toHex = (r: number, g: number, b: number) =>
  `#${[r, g, b].map(v => clampByte(v).toString(16).padStart(2, '0')).join('').toUpperCase()}`;

export const mixHex = (a: string, b: string, weight: number): string => {
  const t = Math.max(0, Math.min(1, weight));
  const [r1, g1, b1] = parseHex(a);
  const [r2, g2, b2] = parseHex(b);
  return toHex(r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t);
};

/** Derives 4 flat tones [lit, midLight, midShade, deep] from a single base hex color. */
export const fourTones = (baseHex: string): readonly [string, string, string, string] => [
  mixHex(baseHex, '#FFFFFF', 0.28),
  baseHex.toUpperCase(),
  mixHex(baseHex, '#0A1C2E', 0.22),
  mixHex(baseHex, '#0A1C2E', 0.44),
] as const;

/** Cubic Hermite smoothstep for calm, non-abrupt anatomical motion. */
export const smoothstep = (x: number): number => {
  const t = Math.max(0, Math.min(1, x));
  return t * t * (3 - 2 * t);
};

/** Multi-faceted flat-shaded acicular crystal (4 flat facets + soft shadow + specular ridge). */
export const FacetedNeedle: React.FC<{
  halfLen: number;
  halfWidth?: number;
  accent?: boolean;
}> = ({halfLen, halfWidth = 3.2, accent = false}) => {
  const L = Math.max(4, halfLen);
  const W = halfWidth;
  const innerL = L * 0.58;
  const innerW = W * 0.48;
  return React.createElement(
    React.Fragment,
    null,
    React.createElement('path', {d: `M${-L} 1.4 L0 ${-W + 1.4} L${L} 1.4 L0 ${W + 1.8}Z`, fill: brand.night, opacity: '0.22'}),
    React.createElement('path', {d: `M${-L} 0 L0 ${-W} L${L} 0 L0 0Z`, fill: c.crystalMid}),
    React.createElement('path', {d: `M${-L} 0 L0 0 L${L} 0 L0 ${W}Z`, fill: c.crystalDeep}),
    React.createElement('path', {d: `M${-L} 0 L0 ${-W} L0 0Z`, fill: c.crystalLight}),
    React.createElement('path', {d: `M0 0 L${L} 0 L0 ${W}Z`, fill: c.crystalShade}),
    React.createElement('path', {
      d: `M${-innerL} 0 L0 ${-innerW} L${innerL} 0 L0 ${innerW}Z`,
      fill: accent ? brand.yellow : c.crystalLight,
      opacity: accent ? '0.55' : '0.85',
    }),
    React.createElement('path', {
      d: `M${-L * 0.88} -0.2 L0 ${-W * 0.68} L${L * 0.88} -0.2`,
      fill: 'none',
      stroke: c.crystalLight,
      strokeWidth: '0.75',
      strokeLinecap: 'round',
    }),
  );
};
