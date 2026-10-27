import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {anatomyColors as c, brand} from './palette';
import {DiagramAnnotations, ProcessArrow, type DiagramLabels} from './annotations';
import {FacetedNeedle, fourTones, smoothstep} from './shade';

export const CONTENT_BOX = {left: 28, top: 28, width: 504, height: 504};
export const CUE_ACTIONS = ['seed', 'grow'] as const;
export const FOCUS_REGIONS = {
  fluid: {left: 28, top: 28, width: 504, height: 504},
  seed: {left: 215, top: 215, width: 130, height: 130},
  crystal: {left: 100, top: 170, width: 370, height: 240},
};
export const LABELS: DiagramLabels = {
  dissolved: {text: 'Urat hòa tan', region: 'fluid', x: 45, y: 48, width: 200, height: 36, anchor: [132, 170]},
  seed: {text: 'Mầm tinh thể', region: 'seed', x: 310, y: 48, width: 200, height: 36, anchor: [280, 280]},
  crystal: {text: 'Tinh thể urat dạng kim', region: 'crystal', x: 132, y: 474, width: 296, height: 36, anchor: [360, 320]},
};

const seedSites = [
  [184, 240, -38],
  [234, 314, 28],
  [280, 280, -18],
  [330, 236, 42],
  [360, 320, -24],
] as const;
const seedTones = fourTones(brand.yellow);

export const crystalGeometry = (state: OrganProps['state'], severity: number, seed: number, grow: number) => {
  const level = state === 'normal' ? 0 : Math.max(0, Math.min(1, severity));
  return {
    count: Math.ceil(level * 5 * Math.max(0, Math.min(1, seed))),
    length: 10 + 170 * Math.max(0, Math.min(1, grow)) * level,
  };
};

/** Dissolved symbols, stable nuclei and needle growth are distinct, schematic states. */
export const UrateCrystalCloseUp: React.FC<OrganProps> = ({state, severity, cueProgress, visibleLabels}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const growInput = cueProgress?.grow ?? smoothstep(Math.min(1, Math.max(0, frame / fps / 5)));
  const g = crystalGeometry(state, severity, cueProgress?.seed ?? 1, growInput);
  const drift = frame / Math.max(1, fps);

  return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img"
    aria-label="Magnified dissolved urate, crystal nucleus and needle growth" data-state={state}>
    {/* 1. Recessed synovial fluid chamber & surrounding articular tissue rim */}
    <rect x="32" y="32" width="500" height="500" rx="32" fill={brand.night} opacity="0.22"/>
    <rect data-layer="sample-window" x="28" y="28" width="504" height="504" rx="32" fill={c.fluidDeep} stroke={brand.teal} strokeWidth="3.5"/>
    <rect x="36" y="36" width="488" height="488" rx="26" fill={c.fluidShade}/>
    <ellipse cx="280" cy="264" rx="224" ry="188" fill={brand.navy}/>
    <ellipse cx="272" cy="252" rx="168" ry="136" fill={c.fluidMid}/>
    <ellipse cx="264" cy="242" rx="108" ry="84" fill={c.fluidLight} opacity="0.5"/>

    {/* Synovial intimal fold at upper-left margin (4 flat tones + lining cells) */}
    <g>
      <path d="M36 62 C92 58 138 78 164 114 C122 126 74 134 36 154Z" fill={c.synoviumDeep}/>
      <path d="M36 62 C88 60 130 78 154 110 C116 121 72 128 36 146Z" fill={c.synoviumShade}/>
      <path d="M36 62 C82 62 120 77 142 104 C108 114 68 120 36 136Z" fill={c.synoviumMid}/>
      <path d="M36 62 C74 63 108 75 128 98 C98 106 64 112 36 124Z" fill={c.synoviumLight}/>
      <path d="M36 154 C74 134 122 126 164 114" fill="none" stroke={c.synoviumLight} strokeWidth="0.9"/>
      {[[54, 134], [82, 124], [112, 116], [140, 108]].map(([cx, cy], i) => <ellipse key={i}
        cx={cx} cy={cy} rx="6" ry="3.4" transform={`rotate(-18 ${cx} ${cy})`} fill={c.chamber} stroke={c.synoviumLight} strokeWidth="0.6"/>)}
    </g>

    {/* Articular hyaline cartilage shelf & subchondral bone margin along bottom */}
    <g>
      <path d="M36 456 Q180 426 320 444 T524 448 V498 Q524 524 498 524 H62 Q36 524 36 498Z" fill={c.cartilageDeep}/>
      <path d="M36 456 Q180 426 320 444 T524 448 V486 Q360 472 200 462 T36 482Z" fill={c.cartilageShade}/>
      <path d="M36 456 Q180 426 320 444 T524 448 V474 Q360 460 200 450 T36 470Z" fill={c.cartilageMid}/>
      <path d="M36 456 Q180 426 320 444 T524 448 V463 Q360 449 200 439 T36 459Z" fill={c.cartilageLight}/>
      <path d="M36 456 Q180 426 320 444 T524 448" fill="none" stroke={c.crystalLight} strokeWidth="0.9" opacity="0.85"/>
      {/* Subchondral bone rim at very bottom */}
      <path d="M36 492 Q190 474 350 486 T524 490 V498 Q524 524 498 524 H62 Q36 524 36 498Z" fill={c.boneShade}/>
      <path d="M36 498 Q190 480 350 492 T524 496 V498 Q524 524 498 524 H62 Q36 524 36 498Z" fill={c.boneMid}/>
      <path d="M44 506 Q190 490 350 500 T516 504" fill="none" stroke={c.boneLight} strokeWidth="0.9"/>
      {[[86, 468], [142, 460], [204, 456], [268, 460], [334, 466], [402, 468], [464, 464]].map(([cx, cy], i) => <g key={i}>
        <ellipse cx={cx} cy={cy} rx="6.5" ry="2.8" fill={c.cartilageDeep}/>
        <ellipse cx={cx - 1.2} cy={cy} rx="2.6" ry="1.4" fill={c.cartilageLight}/>
      </g>)}
    </g>

    {/* Hyaluronic acid / mucin glycoprotein strands in synovial fluid */}
    <g fill="none" stroke={c.cartilageShade} strokeWidth="0.8" opacity="0.45">
      <path d="M68 188 Q176 162 284 194 T492 182"/>
      <path d="M56 266 Q182 294 306 262 T502 276"/>
      <path d="M72 356 Q198 332 324 362 T488 348"/>
    </g>
    <rect x="36" y="36" width="488" height="488" rx="26" fill="none" stroke={c.cartilageLight} strokeWidth="0.8" opacity="0.55"/>

    {/* 2. Dissolved urate solute particles (38 particles with hydration shell + core) */}
    <g data-layer="dissolved-urate" fill={brand.teal}>
      {Array.from({length: 38}, (_, i) => {
        const angle = i * 2.4, r = 45 + 150 * Math.sqrt(i / 37);
        const cx = 280 + r * Math.cos(angle) + 3.5 * Math.sin(drift + i);
        const cy = 264 + r * 0.85 * Math.sin(angle) + 3.5 * Math.cos(drift + i);
        return <g key={i}>
          <circle cx={cx} cy={cy} r="6.2" fill={c.cartilageShade} opacity="0.38"/>
          <circle cx={cx} cy={cy} r="4.1" fill={c.cartilageMid}/>
          <circle cx={cx - 0.9} cy={cy - 0.9} r="1.7" fill={c.cartilageLight}/>
        </g>;
      })}
    </g>

    {/* 3. Crystal nucleation seeds (4-tone micro-lattice clusters) */}
    <g data-layer="crystal-seeds" fill={brand.yellow}>
      {seedSites.slice(0, g.count).map(([cx, cy], i) => <g data-seed="true" key={i} transform={`translate(${cx} ${cy})`}>
        <circle r="10" cy="1.8" fill={brand.night} opacity="0.3"/>
        <circle r="12" fill="none" stroke={seedTones[1]} strokeWidth="0.75" strokeDasharray="2.5 2.5" opacity="0.65"/>
        <polygon points="0,-8 7,-3 5,6 -5,6 -7,-3" fill={seedTones[3]}/>
        <polygon points="0,-8 7,-3 2,4 -5,6 -7,-3" fill={seedTones[2]}/>
        <polygon points="0,-8 6,-2.5 0,2 -6,-2.5" fill={seedTones[1]}/>
        <polygon points="0,-5.5 3.8,-1.5 0,1.5 -3.8,-1.5" fill={seedTones[0]}/>
      </g>)}
    </g>

    {/* 4. Multi-faceted needle crystals suspended in synovial fluid */}
    <g data-layer="needle-crystals" fill={brand.off_white}>
      {g.length > 10 && seedSites.slice(0, g.count).map(([cx, cy, deg], i) => <g data-crystal="true" key={i}
        transform={`translate(${cx} ${cy}) rotate(${deg})`}>
        {g.length > 75 && <g transform="rotate(14)">
          <FacetedNeedle halfLen={g.length * 0.36} halfWidth={2.6}/>
        </g>}
        <FacetedNeedle halfLen={g.length / 2} halfWidth={4.8} accent/>
      </g>)}
    </g>

    <ProcessArrow d="M170 374 Q276 428 391 370 M391 370 L374 372 M391 370 L385 387" visible={g.count > 0}/>
    <DiagramAnnotations labels={LABELS} visibleLabels={visibleLabels}/>
  </svg>;
};
