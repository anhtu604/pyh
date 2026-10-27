import React from 'react';
import type {OrganProps} from './ArterySection';
import {anatomyColors as c, brand} from './palette';
import {DiagramAnnotations, ProcessArrow, type DiagramLabels} from './annotations';
import {FacetedNeedle, smoothstep} from './shade';

export const CONTENT_BOX = {left: 28, top: 28, width: 504, height: 504};
export const CUE_ACTIONS = ['deposit'] as const;
export const FOCUS_REGIONS = {
  cartilage: {left: 28, top: 250, width: 504, height: 180},
  synovium: {left: 28, top: 100, width: 115, height: 400},
  crystal: {left: 205, top: 210, width: 260, height: 140},
  fluid: {left: 148, top: 55, width: 355, height: 240},
};
export const LABELS: DiagramLabels = {
  cartilage: {text: 'Sụn khớp', region: 'cartilage', x: 304, y: 466, width: 202, height: 36, anchor: [380, 370]},
  synovium: {text: 'Màng hoạt dịch', region: 'synovium', x: 40, y: 40, width: 220, height: 36, anchor: [88, 233]},
  crystal: {text: 'Lắng đọng urat', region: 'crystal', x: 288, y: 40, width: 222, height: 36, anchor: [350, 297]},
  fluid: {text: 'Dịch khớp', region: 'fluid', x: 40, y: 466, width: 202, height: 36, anchor: [240, 175]},
};

const superficialChondrocytes = [[138, 332], [192, 320], [248, 312], [306, 309], [364, 312], [422, 318], [480, 326]] as const;
const deepChondrocytes = [
  [148, 358], [148, 372], [212, 346], [212, 360], [278, 338], [278, 352],
  [344, 338], [344, 352], [410, 344], [410, 358], [474, 352], [474, 366],
] as const;
const marrowLacunae = [
  [142, 446, 22, 13], [206, 434, 25, 14], [276, 426, 26, 14], [348, 428, 25, 14], [418, 434, 24, 13], [484, 444, 20, 12],
  [172, 488, 26, 16], [246, 480, 28, 17], [324, 478, 28, 17], [402, 482, 26, 16], [472, 490, 22, 15],
] as const;
const synoviocyteRow = [82, 118, 154, 190, 226, 262, 298, 334, 370, 406, 442, 478] as const;

/** Tissue surface perspective separates deposition from an active inflammatory flare. */
export const UrateDeposition: React.FC<OrganProps> = ({state, severity, cueProgress, visibleLabels}) => {
  const rawBurden = (state === 'normal' ? 0 : Math.max(0, Math.min(1, severity))) * (cueProgress ? cueProgress.deposit ?? 0 : 1);
  const burden = smoothstep(rawBurden);
  const surfaceCount = rawBurden > 0 ? Math.ceil(rawBurden * 9) : 0;
  const membraneCount = rawBurden > 0 ? Math.ceil(rawBurden * 4) : 0;

  return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img"
    aria-label="Urate deposition along cartilage and synovium without automatic inflammation" data-state={state}>
    {/* 1. Synovial joint fluid cavity (4 flat tones + calm mucin contour lines) */}
    <rect x="32" y="32" width="500" height="500" rx="30" fill={brand.night} opacity="0.22"/>
    <rect data-layer="joint-fluid" x="28" y="28" width="504" height="504" rx="30" fill={c.fluidDeep}/>
    <path d="M28 54 Q28 34 54 34 H501 Q526 34 526 59 V340 Q296 286 72 342 Q48 250 70 170 Q93 88 28 54Z" fill={c.fluidShade}/>
    <path d="M28 54 Q28 34 54 34 H500 Q526 34 526 60 V320 Q300 270 78 325 Q54 252 75 170 Q98 88 28 54Z" fill={c.fluidMid}/>
    <path d="M44 58 Q106 88 83 170 T86 312 Q302 266 518 308 V64 Q518 40 492 40 H64 Q40 40 44 58Z" fill={c.vesselDeep} opacity="0.72"/>
    <path d="M68 70 Q116 96 94 170 T97 294 Q304 252 504 290 V78 Q504 52 478 52 H92 Q66 52 68 70Z" fill={c.fluidLight} opacity="0.48"/>
    <path d="M88 112 Q238 88 382 114 T514 106 M82 184 Q236 158 396 186 T516 178 M86 254 Q244 226 412 252 T518 248"
      fill="none" stroke={c.cartilageLight} strokeWidth="0.75" opacity="0.4"/>

    {/* 2. Subchondral bone plate & cancellous trabeculae (4 flat tones + marrow cavities) */}
    <g data-layer="bone">
      <path d="M68 415 Q303 357 532 405 V502 Q532 532 500 532 H68Z" fill={c.boneDeep}/>
      <path d="M68 415 Q303 357 532 405 V492 Q314 446 68 496Z" fill={c.boneShade}/>
      <path d="M68 415 Q303 357 532 405 V456 Q308 404 68 458Z" fill={c.boneMid}/>
      <path d="M68 415 Q303 357 532 405 V429 Q304 374 68 431Z" fill={c.boneLight}/>
      <path d="M74 416 Q303 358 532 406" fill="none" stroke={c.crystalLight} strokeWidth="0.9" opacity="0.85"/>
      {/* Trabecular marrow spaces & bony struts */}
      {marrowLacunae.map(([cx, cy, rx, ry], i) => <g key={i}>
        <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill={c.boneDeep} stroke={c.boneLight} strokeWidth="0.75"/>
        <ellipse cx={cx} cy={cy + 1.5} rx={rx * 0.72} ry={ry * 0.68} fill={c.synoviumDeep} opacity="0.55"/>
      </g>)}
      <path d="M120 426 Q174 468 238 420 M242 418 Q312 464 382 420 M386 420 Q448 466 512 428"
        fill="none" stroke={c.boneLight} strokeWidth="1.1" opacity="0.75"/>
    </g>

    {/* 3. Articular hyaline cartilage (4 histological zones + tidemark + chondrocytes + Benninghoff arcades) */}
    <g data-layer="cartilage">
      <path d="M74 326 Q276 269 532 317 V402 Q303 354 68 412Z" fill={brand.night} opacity="0.2"/>
      {/* Calcified zone & deep radial zone */}
      <path d="M74 331 Q276 274 532 322 V405 Q303 357 68 415Z" fill={c.cartilageDeep}/>
      {/* Middle transitional zone */}
      <path d="M74 331 Q276 274 532 322 V388 Q303 340 68 398Z" fill={c.cartilageShade}/>
      {/* Upper transitional zone */}
      <path d="M74 331 Q276 274 532 322 V366 Q303 318 68 376Z" fill={c.cartilageMid}/>
      {/* Superficial tangential zone (lamina splendens) */}
      <path d="M74 331 Q276 274 532 322 V345 Q282 292 72 350Z" fill={c.cartilageLight}/>
      {/* Undulating tidemark between uncalcified and calcified cartilage */}
      <path d="M76 396 Q200 368 302 362 T530 386" fill="none" stroke={c.boneLight} strokeWidth="0.9" strokeDasharray="4 2" opacity="0.8"/>
      {/* Benninghoff collagen arcade curves */}
      <g fill="none" stroke={c.cartilageLight} strokeWidth="0.7" opacity="0.45">
        {[130, 190, 250, 310, 370, 430, 490].map((x, i) =>
          <path key={i} d={`M${x - 16} 392 C${x - 14} 352 ${x - 6} 326 ${x} 324 C${x + 6} 326 ${x + 14} 352 ${x + 16} 392`}/>)}
      </g>
      {/* Superficial flattened chondrocytes */}
      {superficialChondrocytes.map(([cx, cy], i) => <g key={i}>
        <ellipse cx={cx} cy={cy} rx="7.5" ry="2.4" transform={`rotate(${(i - 3) * 3} ${cx} ${cy})`} fill={c.cartilageDeep}/>
        <ellipse cx={cx - 1} cy={cy} rx="3.2" ry="1.2" transform={`rotate(${(i - 3) * 3} ${cx} ${cy})`} fill={c.crystalLight}/>
      </g>)}
      {/* Deep radial paired chondrocyte columns */}
      {deepChondrocytes.map(([cx, cy], i) => <g key={i}>
        <ellipse cx={cx} cy={cy} rx="5.4" ry="3.4" fill={c.cartilageDeep} stroke={c.cartilageLight} strokeWidth="0.5"/>
        <ellipse cx={cx - 0.8} cy={cy - 0.5} rx="2.2" ry="1.5" fill={c.cartilageLight}/>
      </g>)}
      {/* Specular articular surface rim */}
      <path d="M78 331 Q276 274 532 322" fill="none" stroke={c.crystalLight} strokeWidth="1.1" opacity="0.9"/>
    </g>

    {/* 4. Lateral synovial membrane reflection & villi (4 flat tones + capillaries + intimal synoviocytes) */}
    <g data-layer="synovium">
      <path d="M28 52 Q105 86 82 170 T85 325 Q109 423 77 532 H28Z" fill={brand.night} opacity="0.24"/>
      <path d="M28 54 Q101 88 78 170 T81 325 Q105 423 73 532 H28Z" fill={c.synoviumDeep}/>
      <path d="M28 58 Q95 90 72 170 T75 325 Q99 423 67 532 H28Z" fill={c.synoviumShade}/>
      <path d="M28 64 Q86 94 64 170 T67 325 Q90 420 59 532 H28Z" fill={c.synoviumMid}/>
      <path d="M28 74 Q74 102 54 170 T57 325 Q78 416 49 532 H28Z" fill={c.synoviumLight} opacity="0.72"/>
      {/* Subintimal collagen fibers & quiet microvessels */}
      <path d="M40 86 Q64 134 46 196 T50 326 Q66 404 44 504 M34 104 Q54 152 38 212 T42 342 Q56 418 36 512"
        fill="none" stroke={c.synoviumDeep} strokeWidth="0.9" opacity="0.7"/>
      {[[46, 142], [44, 268], [48, 396]].map(([cx, cy], i) => <g key={i}>
        <ellipse cx={cx} cy={cy} rx="6.5" ry="4.5" fill={c.bloodInset} stroke={c.synoviumLight} strokeWidth="0.6"/>
        <ellipse cx={cx - 1} cy={cy - 0.8} rx="3.2" ry="2" fill={c.bloodLight}/>
      </g>)}
      {/* Intimal lining synoviocyte layer */}
      {synoviocyteRow.map((cy, i) => {
        const cx = 74 + 8 * Math.sin(i * 0.85);
        return <g key={i}>
          <ellipse cx={cx} cy={cy} rx="6.5" ry="10.5" fill={c.synoviumMid} stroke={c.synoviumLight} strokeWidth="0.6"/>
          <ellipse cx={cx + 1.2} cy={cy} rx="3.5" ry="6" fill={c.chamber}/>
        </g>;
      })}
      <path d="M28 58 Q95 90 72 170 T75 325 Q99 423 67 532" fill="none" stroke={c.synoviumLight} strokeWidth="0.95"/>
    </g>

    {/* 5. Articular cartilage surface urate crystal deposits (quiet double-contour coating) */}
    <g data-layer="surface-deposits" fill={brand.off_white}>
      {Array.from({length: surfaceCount}, (_, i) => {
        const x = 142 + i * 42;
        const y = 313 - 19 * Math.sin(i / 2.6);
        const rot = (i % 2 ? 14 : -14) - (4 - i) * 2.2;
        return <g data-crystal="true" key={i} transform={`translate(${x} ${y}) rotate(${rot})`}>
          <FacetedNeedle halfLen={16 + 6 * burden} halfWidth={3.1} accent/>
        </g>;
      })}
    </g>

    {/* 6. Synovial membrane embedded urate crystal deposits */}
    <g data-layer="membrane-deposits" fill={brand.off_white}>
      {Array.from({length: membraneCount}, (_, i) => <g data-crystal="true" key={i}
        transform={`translate(${74 + (i % 2) * 6} ${138 + i * 68}) rotate(${66 + (i % 2 ? 8 : -8)})`}>
        <FacetedNeedle halfLen={14 + 4 * burden} halfWidth={2.7}/>
      </g>)}
    </g>

    <ProcessArrow d="M330 188 V262 M330 262 L319 247 M330 262 L341 247" visible={rawBurden > 0}/>
    <DiagramAnnotations labels={LABELS} visibleLabels={visibleLabels}/>
  </svg>;
};
