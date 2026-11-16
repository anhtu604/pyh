import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {brand, anatomyColors as c} from './palette';
import {DiagramAnnotations, ProcessArrow} from './annotations';
import type {DiagramLabels} from './annotations';

export const clamp = (x: number) => Math.max(0, Math.min(1, x));
const ease = (x: number) => {const t = clamp(x); return t*t*(3-2*t);};
export const mechanics = (state: OrganProps['state'], severity: number, frame: number, fps: number, cues?: Record<string, number>) => {
  const active = state === 'diseased';
  const progress = (id: string) => ease(cues ? (cues[id] ?? 0) : frame/fps/4);
  return {bolus: progress('swallow'), pressure: active ? progress('press') : 0,
    penetration: active ? clamp(severity)*progress('penetrate') : 0,
    swelling: active ? clamp(severity)*progress('swell') : 0};
};
export const EsophagusDiagram: React.FC<OrganProps & {view: 'overview'|'bolus'|'wall'|'section'; labels: DiagramLabels}> =
({state, severity, cueProgress, visibleLabels, view, labels}) => {
  const frame = useCurrentFrame(); const {fps} = useVideoConfig();
  const g = mechanics(state, severity, frame, fps, cueProgress);
  const active = state === 'diseased';
  const arrow = <ProcessArrow d="M270 164 V224 M258 211 L270 224 L282 211"/>;
  return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img" aria-label="Sơ đồ thực quản và xương cá" data-state={state} data-view={view}>
    {view === 'overview' && <g data-layer="esophagus-aortic-arch">
      <path d="M179 36 C166 102 200 126 187 168 C169 225 169 283 187 325 C200 362 178 398 180 438 C142 447 76 451 36 478 C64 524 144 531 214 510 C252 499 281 473 266 442 C247 400 258 365 248 325 C233 284 235 228 250 168 C260 125 224 103 236 36Z" fill={c.media} stroke={brand.navy} strokeWidth="3"/>
      <path d="M198 36 C184 105 219 124 206 168 C190 227 190 279 207 325 C218 366 197 405 199 454 C156 461 98 466 70 481 C116 508 181 505 214 488 C242 476 249 464 247 450 C227 401 239 364 228 325 C213 278 215 228 230 168 C241 121 204 103 216 36Z" fill={c.intima}/>
      <path d="M207 36 C194 104 229 124 216 168 C200 228 200 279 217 325 C228 366 207 405 209 462" fill="none" stroke={c.lumen} strokeWidth="13"/>
      <path d="M530 510 V218 C530 94 286 78 267 230 L266 280" fill="none" stroke={c.bloodInset} strokeWidth="44"/>
      <path d="M526 510 V218 C526 103 291 90 277 230 L276 280" fill="none" stroke={c.blood} strokeWidth="28"/>
      <path d="M518 510 V218 C518 118 299 104 286 230" fill="none" stroke={c.bloodLight} strokeWidth="8"/>
      {[115,250,425].map(y => <path key={y} d={`M166 ${y} H242`} stroke={brand.yellow} strokeWidth="5"/>)}
      {active && <path d="M207 251 L255 237 L210 258Z" fill={c.boneLight} stroke={brand.navy} strokeWidth="2"/>}
      <ProcessArrow d="M145 155 V208 M135 196 L145 208 L155 196"/>
    </g>}
    {view === 'bolus' && <g data-layer="bolus-and-contraction">
      <path d="M38 36 H170 Q190 150 163 260 Q139 373 172 524 H38Z" fill={c.media} stroke={brand.navy} strokeWidth="3"/>
      <path d="M390 36 H522 V524 H388 Q422 373 397 260 Q370 150 390 36Z" fill={c.media} stroke={brand.navy} strokeWidth="3"/>
      <path d="M145 36 Q165 150 138 260 Q114 373 147 524 H172 Q139 373 163 260 Q190 150 170 36Z" fill={c.intima}/>
      <path d="M390 36 Q370 150 397 260 Q422 373 388 524 H413 Q447 373 422 260 Q395 150 415 36Z" fill={c.intima}/>
      <g transform={`translate(0 ${active ? g.pressure*96 : g.bolus*210})`}><ellipse cx="280" cy="145" rx="73" ry="51" fill={c.boneShade}/><ellipse cx="277" cy="137" rx="68" ry="44" fill={c.boneMid}/><ellipse cx="266" cy="124" rx="47" ry="22" fill={c.boneLight}/></g>
      {active && <path data-layer="impacted-bone" d={`M157 302 L${399+g.penetration*25} 282 L163 312Z`} fill={c.boneLight} stroke={brand.navy} strokeWidth="3"/>}
      <g transform={`translate(0 ${g.bolus*190})`}><ProcessArrow d="M66 132 H132 M119 121 L132 132 L119 143"/><ProcessArrow d="M494 132 H428 M441 121 L428 132 L441 143"/></g>
      <ProcessArrow d="M280 428 V490 M268 477 L280 490 L292 477"/>
    </g>}
    {view === 'wall' && <g data-layer="penetration-and-tissue">
      <path d="M36 60 H524 V524 H36Z" fill={c.media}/>
      <path d="M36 60 H524 V375 H36Z" fill={c.intima}/>
      <path d="M36 60 H524 V251 H36Z" fill={c.lumen}/>
      <path d="M36 251 Q170 238 280 251 T524 251" stroke={c.synoviumLight} strokeWidth={8+g.swelling*15} fill="none"/>
      {active && <g transform={`translate(0 ${g.penetration*116})`}><path d="M226 80 L315 80 L280 301Z" fill={c.boneShade} stroke={brand.navy} strokeWidth="3"/><path d="M243 88 L295 88 L280 282Z" fill={c.boneLight}/></g>}
      {active && <ellipse cx="280" cy={266+g.penetration*100} rx={12+g.swelling*24} ry="15" fill={c.blood} opacity={g.penetration}/>}
      {arrow}
    </g>}
    {view === 'section' && <g data-layer="transverse-impaction">
      <circle cx="280" cy="280" r="244" fill={c.media} stroke={brand.navy} strokeWidth="3"/>
      <circle cx="280" cy="280" r="215" fill={c.synoviumLight}/>
      <circle cx="280" cy="280" r="188" fill={c.intima}/>
      <circle cx="280" cy="280" r="166" fill={c.lumen}/>
      {active ? <g transform={`rotate(${-8-g.pressure*8} 280 280)`}><path d={`M108 278 L${446+g.penetration*36} 265 L113 288Z`} fill={c.boneLight} stroke={brand.navy} strokeWidth="3"/></g> : <ellipse cx="280" cy="280" rx="115" ry="80" fill={c.boneMid}/>}
      {active && <ProcessArrow d="M322 224 L412 254 M396 238 L412 254 L390 257"/>}
    </g>}
    <DiagramAnnotations labels={labels} visibleLabels={visibleLabels}/>
  </svg>;
};
