import React from 'react';
import {useCurrentFrame} from 'remotion';
import type {OrganProps} from './ArterySection';
import {DiagramAnnotations, type DiagramLabels} from './annotations';
import {anatomyColors as c, brand} from './palette';

// Separate tissue sites, not a transport pathway or a quantitative concentration map.
export const CONTENT_BOX = {left: 32, top: 50, width: 496, height: 460};
export const FOCUS_REGIONS = {overview: {left: 0, top: 0, width: 560, height: 560}};
export const CUE_ACTIONS: readonly string[] = ['liver', 'muscle'];
export const LABELS: DiagramLabels = {
  liver: {text: 'Gan', region: 'overview', x: 32, y: 12, width: 132, height: 34, anchor: [142, 150]},
  alt: {text: 'ALT', region: 'overview', x: 182, y: 12, width: 132, height: 34, anchor: [185, 180]},
  ast: {text: 'AST', region: 'overview', x: 364, y: 12, width: 164, height: 34, anchor: [426, 215]},
  muscle: {text: 'Cơ vân', region: 'overview', x: 32, y: 514, width: 210, height: 34, anchor: [145, 430]},
  heart: {text: 'Cơ tim', region: 'overview', x: 318, y: 514, width: 210, height: 34, anchor: [426, 340]},
};

export const AltAstTissueDistribution: React.FC<OrganProps> = ({visibleLabels = [], cueProgress}) => {
  const frame = useCurrentFrame();
  const liverOpacity = .55 + .45 * (cueProgress?.liver ?? (Math.sin(frame / 28) + 1) / 2);
  const muscleOpacity = .55 + .45 * (cueProgress?.muscle ?? (Math.sin(frame / 31) + 1) / 2);
  return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img" aria-label="ALT ở gan; AST ở gan, cơ vân và cơ tim">
    <g data-layer="liver-tissue" opacity={liverOpacity}>
      <path d="M32 150 Q40 60 132 50 Q195 53 250 110 L270 165 Q238 213 170 235 Q85 270 40 220Z" fill={c.heartDeep} stroke={brand.off_white} strokeWidth="3"/>
      <path d="M45 150 Q55 76 135 66 L171 81 L146 218 Q78 246 52 207Z" fill={c.heartMid}/>
      <path d="M177 81 Q222 104 250 127 Q227 181 164 213Z" fill={c.heartLight}/>
      <path d="M175 78 L150 217" stroke={brand.off_white} strokeWidth="4"/>
      <circle cx="114" cy="155" r="11" fill={brand.teal}/>
      <circle cx="185" cy="180" r="11" fill={brand.teal}/>
      <circle cx="95" cy="195" r="9" fill={brand.yellow}/>
    </g>
    <g data-layer="skeletal-muscle" opacity={muscleOpacity}>
      <path d="M32 325 Q135 285 250 320 L270 475 Q140 510 32 478Z" fill={c.heartDeep} stroke={brand.off_white} strokeWidth="3"/>
      {Array.from({length: 7}, (_, i) => <g key={i}>
        <path d={`M${49 + i * 29} 326 Q${60 + i * 29} 400 ${49 + i * 29} 475`} stroke={i % 2 ? c.heartLight : c.heartMid} strokeWidth="18" fill="none"/>
        {Array.from({length: 7}, (_, j) => <path key={j} d={`M${40 + i * 29} ${342 + j * 19} h18`} stroke={c.heartDeep} strokeWidth="3"/>)}
      </g>)}
      <circle cx="146" cy="400" r="10" fill={brand.yellow}/>
    </g>
    <g data-layer="cardiac-muscle" opacity={muscleOpacity}>
      <path d="M344 118 Q374 90 405 135 L426 176 Q453 120 485 130 L508 165 Q482 214 460 253 L488 330 Q522 380 528 464 L493 510 L459 448 L421 358 L386 438 L350 465 L328 426 L378 320 L396 259 L363 206Z" fill={c.heartMid} stroke={brand.off_white} strokeWidth="3"/>
      <path d="M364 135 L418 250 L351 427 M486 152 L430 254 L500 477" fill="none" stroke={c.heartLight} strokeWidth="17"/>
      {Array.from({length: 8}, (_, i) => <path key={i} d={`M${i < 4 ? 383 : 435} ${185 + i * 30} l22 -9`} stroke={c.heartDeep} strokeWidth="5"/>)}
      <ellipse cx="426" cy="282" rx="12" ry="20" fill={c.chamber}/>
      <circle cx="426" cy="215" r="10" fill={brand.yellow}/>
    </g>
    <DiagramAnnotations labels={LABELS} visibleLabels={visibleLabels}/>
  </svg>;
};
