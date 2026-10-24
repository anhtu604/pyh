import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {anatomyColors as c, brand} from './palette';
import {DiagramAnnotations, ProcessArrow, type DiagramLabels} from './annotations';

// Union of the joint capsule, exposed bone shafts and circular fluid inset.
export const CONTENT_BOX = {left: 28, top: 28, width: 504, height: 504};
export const CUE_ACTIONS = ['seed', 'grow', 'deposit'] as const;
export const urateGeometry = (state: OrganProps['state'], severity: number, frame: number, fps: number) => {
  const level = state === 'normal' ? 0 : Math.max(0, Math.min(1, severity));
  const growth = Math.min(1, Math.max(0, frame / fps / 8));
  return {level, growth, needles: Math.ceil(level * 8), length: 8 + 62 * growth * level};
};

const insetSites = [[369, 112], [425, 100], [465, 139], [355, 166], [412, 161], [474, 199], [377, 222], [429, 231]];
const cartilageSites = [[105, 238], [150, 249], [198, 245], [237, 230], [110, 302], [166, 296], [220, 307]];
const synovialSites = [[59, 215], [58, 274], [72, 332], [279, 252], [274, 319]];

/** Qualitative joint section and fluid inset, not to scale. Deposits sit along
 * cartilage and within synovium; needle shape does not imply tissue puncture. */
export const UrateFluid: React.FC<OrganProps> = ({state, severity, cueProgress, visibleLabels}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const g = urateGeometry(state, severity, frame, fps);
  const cue = (action: string) => Math.max(0, Math.min(1, cueProgress?.[action] ?? 0));
  if (cueProgress) {
    g.needles = Math.ceil(g.level * 8 * cue('seed'));
    g.growth = cue('grow');
    g.length = 8 + 62 * g.growth * g.level;
  }
  const deposits = g.level * (cueProgress ? cue('deposit') : 1);
  return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img"
    aria-label="Synovial joint section with magnified urate in fluid" data-state={state} data-severity={g.level}>
    <path data-layer="joint-capsule" d="M98 28 H222 C226 111 294 139 304 231 C318 344 244 410 231 532 H89 C86 423 28 359 28 274 C28 155 91 126 98 28Z" fill={c.adventitia}/>
    <path data-layer="synovial-membrane" d="M100 97 H220 C230 148 277 177 285 239 C298 331 235 396 225 459 H95 C84 394 46 342 46 275 C46 187 86 151 100 97Z" fill={c.media}/>
    <path data-layer="synovial-fluid" d="M106 129 H213 C230 176 263 189 266 243 C279 320 222 378 213 427 H108 C97 377 65 335 65 275 C65 200 94 168 106 129Z" fill={c.vesselDeep}/>
    <g data-layer="bone-ends" fill={brand.off_white}>
      <path d="M107 28 H213 L215 139 C216 165 255 178 255 202 C255 225 217 236 167 237 C115 238 77 223 77 202 C77 177 105 165 106 139Z"/>
      <path d="M98 532 H222 L224 396 C225 365 254 351 253 330 C252 308 213 292 166 292 C120 292 78 309 78 332 C78 355 99 368 98 396Z"/>
    </g>
    <g data-layer="trabecular-bone" stroke={brand.yellow} strokeWidth="4" fill="none" opacity=".65">
      {[0, 1, 2].map(i => <path key={i} d={`M${120 + i * 30} 51 l-9 50 18 42 -18 48 M${120 + i * 30} 363 l15 45 -17 46 13 55`}/>)}
    </g>
    <g data-layer="cartilage" fill={c.vesselLight}>
      <path d="M77 201 C94 226 227 234 255 201 L255 217 C235 256 98 261 77 219Z"/>
      <path d="M78 332 C99 303 222 300 253 330 L253 314 C227 280 104 279 78 315Z"/>
    </g>
    <g data-layer="cartilage-deposits" fill={brand.off_white}>
      {cartilageSites.slice(0, deposits >= .6 ? Math.ceil((deposits - .5) * 14) : 0).map(([x, y], i) =>
        <path key={i} data-crystal="true" data-deposit-site="cartilage" transform={`translate(${x} ${y}) rotate(${i % 2 ? -8 : 8})`} d="M-13 0 L0 -2 L13 0 L0 2Z"/>)}
    </g>
    <g data-layer="synovial-deposits" fill={brand.off_white}>
      {synovialSites.slice(0, deposits >= .7 ? Math.ceil((deposits - .6) * 12.5) : 0).map(([x, y], i) =>
        <path key={i} data-crystal="true" data-deposit-site="synovium" transform={`translate(${x} ${y}) rotate(${70 + i * 7})`} d="M-10 0 L0 -2 L10 0 L0 2Z"/>)}
    </g>
    <g data-layer="sample-connector" stroke={brand.teal} strokeWidth="3" fill="none">
      <circle cx="248" cy="268" r="9"/>
      <path d="M256 264 L306 240 L324 222 M255 275 L310 292 L350 270"/>
    </g>
    <rect data-layer="sample-window" x="296" y="52" width="236" height="236" rx="30" fill={brand.teal}/>
    <rect x="302" y="58" width="224" height="224" rx="25" fill={brand.navy}/>
    <g data-layer="dissolved-urate" fill={brand.teal}>
      {Array.from({length: 32}, (_, i) => {
        const angle = i * 2.4, radius = 18 + 76 * Math.sqrt(i / 31);
        return <circle key={i} r="3.5" cx={414 + radius * Math.cos(angle) + 3 * Math.sin(frame / fps + i)}
          cy={170 + radius * Math.sin(angle) + 3 * Math.cos(frame / fps + i)}/>;
      })}
    </g>
    <g data-layer="crystal-seeds" fill={brand.yellow}>
      {insetSites.slice(0, g.needles).map(([x,y], i) => <circle key={i} data-seed="true" r="4" cx={x} cy={y}/>)}
    </g>
    <g data-layer="needle-crystals" fill={brand.off_white}>
      {insetSites.slice(0, cueProgress && g.growth <= 0 ? 0 : g.needles).map(([x,y], i) => <path key={i} data-crystal="true"
        transform={`translate(${x} ${y}) rotate(${i * 37 + 20})`}
        d={`M${-g.length / 2} 0 L0 -2.5 L${g.length / 2} 0 L0 2.5Z`}/>)}
    </g>
    <ProcessArrow d="M280 300 L310 315 L300 302 M310 315 L294 315" visible={g.level > 0}/>
    <DiagramAnnotations labels={LABELS} visibleLabels={visibleLabels}/>
  </svg>;
};

export const FOCUS_REGIONS = {"bone": {"left": 80, "top": 28, "width": 180, "height": 210}, "cartilage": {"left": 60, "top": 193, "width": 220, "height": 154}, "synovium": {"left": 28, "top": 134, "width": 285, "height": 270}, "fluid": {"left": 60, "top": 222, "width": 225, "height": 110}, "capsule": {"left": 28, "top": 28, "width": 285, "height": 504}, "crystal": {"left": 296, "top": 52, "width": 236, "height": 236}};
export const LABELS: DiagramLabels = {"bone": {"text": "Xương", "region": "bone", "x": 330, "y": 310, "width": 180, "height": 34, "anchor": [170, 170]}, "cartilage": {"text": "Sụn khớp", "region": "cartilage", "x": 330, "y": 352, "width": 180, "height": 34, "anchor": [166, 242]}, "synovium": {"text": "Màng hoạt dịch", "region": "synovium", "x": 330, "y": 394, "width": 180, "height": 34, "anchor": [278, 320]}, "fluid": {"text": "Dịch khớp", "region": "fluid", "x": 330, "y": 436, "width": 180, "height": 34, "anchor": [185, 270]}, "capsule": {"text": "Bao khớp", "region": "capsule", "x": 330, "y": 478, "width": 180, "height": 34, "anchor": [285, 360]}, "crystal": {"text": "Tinh thể urat", "region": "crystal", "x": 330, "y": 8, "width": 180, "height": 34, "anchor": [415, 155]}};
