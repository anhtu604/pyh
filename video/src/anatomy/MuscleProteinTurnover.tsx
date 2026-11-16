import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {brand, anatomyColors as c} from './palette';
import {DiagramAnnotations, ProcessArrow} from './annotations';
export const CONTENT_BOX = {left:35,top:45,width:440,height:496};
export const FOCUS_REGIONS = {overview:{left:0,top:0,width:560,height:560}, muscle:{left:55,top:100,width:425,height:405}, blood:{left:245,top:120,width:85,height:370}, tumor:{left:345,top:175,width:190,height:300}};
export const LABELS = {muscle:{text:'Sợi cơ',region:'muscle',x:35,y:45,width:155,height:36,anchor:[130,215] as const},amino:{text:'Axit amin',region:'blood',x:207,y:505,width:145,height:36,anchor:[280,120] as const}};
export const CUE_ACTIONS = ['recycle','inflammation','withdraw','waste'] as const;
/** Qualitative tissue state, not a growth rate, clinical score, or treatment prediction. */
export const proteinGeometry = (state:OrganProps['state'], severity:number, frame:number, fps:number, cues?:Record<string,number>) => {
 const level=state==='normal'?0:Math.max(0,Math.min(1,severity));
 const active=(key:string)=>cues?Math.max(0,Math.min(1,cues[key]??0)):1;
 return {loss:level*active('waste'), inflammation:level*active('inflammation'), withdraw:level*active('withdraw'), phase:(frame/Math.max(1,fps)*.18)%1, recycling:1-level*.65*active('inflammation')};
};
export const MuscleProteinTurnover:React.FC<OrganProps> = ({state,severity,cueProgress,visibleLabels=[]}) => {
 const frame=useCurrentFrame(); const {fps}=useVideoConfig(); const g=proteinGeometry(state,severity,frame,fps,cueProgress);
 const view='muscle';
 return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img" aria-label="Vietnamese qualitative protein metabolism diagram" data-state={state} data-view={view}>
 {true&&<g data-layer="muscle-fibres" transform="translate(-36 -65) scale(2.4 1.2)">
 {Array.from({length:7},(_,i)=><g key={i} transform={`translate(0 0)`}>
 <rect x={40+i*25} y={145+g.loss*55} width={22-g.loss*7} height={325-g.loss*110} rx="11" fill={c.heartDeep} stroke={brand.navy} strokeWidth="1"/>
 <rect x={43+i*25} y={151+g.loss*55} width={14-g.loss*5} height={310-g.loss*110} rx="7" fill={c.heartLight}/>
 <path d={`M${46+i*25} ${162+g.loss*55} v${280-g.loss*110}`} stroke={c.heartMid} strokeWidth="3"/>
 {Array.from({length:8},(_,j)=><path key={j} d={`M${42+i*25} ${180+j*32} h${18-g.loss*6}`} stroke={brand.navy} opacity={.2*(1-g.loss)} strokeWidth="2"/>)}
 </g>)}
 </g>}
 {true&&<g transform="translate(-36 0) scale(2.4 1)" data-layer="protein-recycling" opacity={g.recycling}>
 <ProcessArrow d="M62 130 Q140 87 213 130 L200 118 M213 130 L198 138"/>
 <circle cx={65+g.phase*140} cy={118-Math.sin(g.phase*Math.PI)*16} r="5" fill={brand.teal}/>
 </g>}
 <DiagramAnnotations labels={LABELS} visibleLabels={visibleLabels}/>
 </svg>;
};
