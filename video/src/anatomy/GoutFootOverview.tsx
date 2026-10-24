import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {anatomyColors as c, brand} from './palette';
import {DiagramAnnotations, type DiagramLabels} from './annotations';
export const CONTENT_BOX = {left: 26, top: 44, width: 508, height: 472};
export const CUE_ACTIONS = ['swell'] as const;
export const FOCUS_REGIONS = {foot: {left:30,top:48,width:500,height:464}, mtp1: {left:300,top:326,width:190,height:170}};
export const LABELS: DiagramLabels = {
  mtp1: {text:'Khớp MTP1',region:'mtp1',x:306,y:72,width:206,height:36,anchor:[402,405]},
  bone: {text:'Xương bàn chân',region:'foot',x:42,y:72,width:218,height:36,anchor:[258,349]},
};
/** Example anatomic location only; not a diagnostic image or a claim that every flare affects MTP1. */
export const GoutFootOverview: React.FC<OrganProps> = ({state,severity,cueProgress,visibleLabels}) => {
 const frame=useCurrentFrame(); const {fps}=useVideoConfig();
 const level=state==='normal'?0:Math.max(0,Math.min(1,severity))*(cueProgress?cueProgress.swell??0:1);
 return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img" aria-label="Schematic foot with first metatarsophalangeal joint highlighted" data-state={state}>
  <path data-layer="foot-silhouette" d="M91 48 H214 L220 236 Q231 285 306 318 L454 355 Q493 356 510 383 Q530 402 519 429 Q506 448 477 450 L207 495 Q158 512 100 495 Q44 478 34 432 Q30 398 52 364 L84 294Z" fill={level>0?c.intima:brand.off_white} stroke={c.adventitia} strokeWidth="7"/>
  <g data-layer="foot-bones" fill={brand.off_white} stroke={c.adventitia} strokeWidth="5">
   <path d="M112 75 H171 L177 284 Q191 322 165 347 Q130 367 106 337 Q94 315 107 283Z"/>
   <ellipse cx="126" cy="401" rx="52" ry="42"/>
   <path d="M184 365 L356 382 Q372 384 370 402 Q368 420 349 419 L185 414 Q170 389 184 365Z"/>
   <path d="M425 384 L479 389 Q497 393 490 411 Q486 421 467 420 L427 419 Q411 403 425 384Z"/>
   {[0,1,2].map(i=><path key={i} d={`M${192+i*8} ${438+i*15} L${413-i*16} ${430+i*11}`} strokeWidth="10" strokeLinecap="round"/>)}
  </g>
  <circle data-layer="mtp1-highlight" cx="399" cy="404" r={43+level*10} fill={level>0?c.blood:'none'} fillOpacity={level>0?.2:1} stroke={level>0?c.blood:brand.teal} strokeWidth="5"/>
  {level>0&&<g data-layer="inflammatory-halo" fill="none" stroke={c.blood} strokeWidth="4" opacity={.6+.15*Math.sin(frame/fps*2)}>
    <circle cx="399" cy="404" r={63+level*7}/><path d="M374 327 Q365 312 376 299 M401 323 Q392 306 403 290 M428 329 Q419 313 430 300"/>
  </g>}
  <DiagramAnnotations labels={LABELS} visibleLabels={visibleLabels}/>
 </svg>;
};

