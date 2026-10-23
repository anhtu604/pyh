import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {anatomyColors as c, brand} from './palette';

// Tissue sample boundary contains all vessel, cell and signal motion.
export const CONTENT_BOX = {left: 28, top: 28, width: 504, height: 504};
export const signalGeometry = (state: OrganProps['state'], severity: number, frame: number, fps: number) => {
  const level = state === 'normal' ? 0 : Math.max(0, Math.min(1, severity));
  return {level, recruited: Math.ceil(level * 6), phase: ((frame / fps) % 4) / 4,
    capillaryRadius: 25 + 13 * level, engulfment: Math.min(1, Math.max(0, frame / fps / 2)),
    migration: Math.min(1, Math.max(0, frame / fps / 7))};
};

/** Synovial lining with subsynovial microvasculature, not to scale. Activated
 * disease presupposes priming as well as activation; crystal presence alone
 * does not imply an acute flare. Normal is a clean, resting reference. */
export const InflammationSignal: React.FC<OrganProps> = ({state, severity}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const g = signalGeometry(state, severity, frame, fps);
  return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img"
    aria-label="Synovial lining, macrophage signalling and neutrophil recruitment" data-state={state} data-severity={g.level}>
    <rect data-layer="sample-window" x="28" y="28" width="504" height="504" rx="32" fill={brand.navy}/>
    <path data-layer="subsynovial-tissue" d="M28 321 Q113 290 204 319 T379 315 T532 319 V500 Q532 532 500 532 H60 Q28 532 28 500Z" fill={c.chamber}/>
    <g data-layer="tissue-fibres" stroke={c.adventitia} strokeWidth="5" fill="none">
      <path d="M54 373 Q120 351 180 374 T309 372 T500 367 M58 501 Q120 482 194 500 M333 502 Q419 479 502 500"/>
    </g>
    <g data-layer="synovial-membrane">
      <path d="M28 294 Q113 263 204 292 T379 288 T532 292 V320 Q458 295 379 316 T204 320 T28 322Z" fill={c.media}/>
      {/* Midpoints between the two lining curves keep nuclei inside the membrane. */}
      {[302.5, 295.8, 295.8, 302.2, 312, 316.5, 314.2, 304.5, 292.5, 289.7, 297.6].map((y, i) => <ellipse key={i}
        cx={49 + i * 46} cy={y}
        rx="12" ry="7" fill={c.chamber}/>)}
    </g>
    <g data-layer="capillary" data-lumen-radius={g.capillaryRadius}>
      <rect x="44" y={436 - g.capillaryRadius - 6} width="472" height={2 * g.capillaryRadius + 12} rx={g.capillaryRadius + 6} fill={g.level > 0 ? c.bloodInset : c.adventitia}/>
      <rect x="50" y={436 - g.capillaryRadius} width="460" height={2 * g.capillaryRadius} rx={g.capillaryRadius} fill={g.level > 0 ? c.blood : c.heartDeep}/>
      {[0, 1, 2, 3, 4, 5, 6].map(i => <g key={i} transform={`translate(${79 + ((i * 60 + frame / fps * 9) % 395)} 443)`}>
        <ellipse rx="13" ry="8" fill={c.bloodLight}/><ellipse rx="6" ry="3" fill={c.bloodInset}/>
      </g>)}
      {[0, 1, 2, 3, 4, 5].map(i => <ellipse key={i} cx={92 + i * 73} cy={432 - g.capillaryRadius} rx="11" ry="3" fill={c.chamber}/>)}
    </g>
    <g data-layer="resident-cell">
      <path data-phagocytosis={g.level > 0 ? 'true' : undefined}
        d="M78 206 C70 165 94 117 135 109 C164 92 203 105 217 126 C230 137 250 119 263 132 C280 153 253 174 249 187 C272 219 245 258 217 270 C185 289 150 269 128 279 C94 272 72 241 78 206Z" fill={brand.teal}/>
      <path d="M116 181 C100 196 111 229 132 239 C151 246 180 230 171 216 C148 221 146 201 151 189 C145 175 127 173 116 181Z" fill={c.vesselDeep}/>
      <g data-layer="inflammasome">
        {g.level > 0 && <g data-activation="true" opacity={.5 + .5 * g.level}>
          <circle cx="206" cy="201" r={23 + 3 * Math.sin(frame / fps * 2)} fill="none" stroke={brand.yellow} strokeWidth="5"/>
          {[0, 1, 2, 3, 4, 5].map(i => <circle key={i} cx={206 + 12 * Math.cos(i * Math.PI / 3)} cy={201 + 12 * Math.sin(i * Math.PI / 3)} r="3.5" fill={brand.yellow}/>)}
        </g>}
      </g>
    </g>
    <g data-layer="crystal-cue" fill={brand.off_white}>
      {g.level > 0 && <g transform={`translate(${267 - 37 * g.engulfment} ${132 + 22 * g.engulfment}) rotate(-35)`}>
        <ellipse rx="31" ry="12" fill={c.vesselDeep}/>
        <path data-crystal="true" d="M-25 0 L0 -3 L25 0 L0 3Z"/>
      </g>}
    </g>
    <g data-layer="alarm-signal" fill={brand.yellow}>
      {g.level > 0 && Array.from({length: Math.ceil(g.level * 7)}, (_, i) => {
        const t = (g.phase + i / 7) % 1;
        return <circle key={i} data-signal="true" cx={264 + t * 122} cy={210 + t * 155 + 15 * Math.sin(i * 2)} r={4 + g.level * 2} opacity={1 - .55 * t}/>;
      })}
    </g>
    <g data-layer="recruited-cells">
      {Array.from({length: g.recruited}, (_, i) => {
        // Staggered, one-way transit: lumen -> endothelium -> lining -> joint fluid.
        const t = Math.max(0, Math.min(1, g.migration * 1.5 - i * .13));
        const x = 99 + i * 70 + (260 - (99 + i * 70)) * t * .35;
        const y = 431 - (183 + (i % 3) * 27) * t;
        return <g key={i} data-neutrophil="true" data-migration="transendothelial" transform={`translate(${x} ${y})`}>
          <ellipse rx={19 - 4 * Math.sin(t * Math.PI)} ry={19 + 3 * Math.sin(t * Math.PI)} fill={c.heartLight} stroke={brand.off_white} strokeWidth="2"/>
          <g data-layer="multilobed-nuclei" fill={c.chamber}>
            <path d="M-8 -5 L2 6 L8 -5" fill="none" stroke={c.chamber} strokeWidth="3"/>
            {[[-8, -5], [0, 6], [8, -5]].map(([nx, ny], j) => <ellipse key={j} data-nucleus-lobe="true" cx={nx} cy={ny} rx="5" ry="6"/>)}
          </g>
        </g>;
      })}
    </g>
  </svg>;
};
