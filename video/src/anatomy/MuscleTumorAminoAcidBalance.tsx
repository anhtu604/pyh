import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {brand, anatomyColors as c} from './palette';
import {DiagramAnnotations, ProcessArrow} from './annotations';
export const CONTENT_BOX = {left:35,top:45,width:500,height:470};
export const FOCUS_REGIONS = {overview:{left:0,top:0,width:560,height:560}, muscle:{left:35,top:155,width:205,height:320}, blood:{left:245,top:120,width:85,height:370}, tumor:{left:345,top:175,width:190,height:300}};
export const LABELS = {
 muscle:{text:'Cơ xương',region:'muscle',x:35,y:45,width:155,height:36,anchor:[130,215] as const},
 blood:{text:'Máu',region:'blood',x:215,y:45,width:125,height:36,anchor:[285,170] as const},
 tumor:{text:'Khối u',region:'tumor',x:370,y:45,width:155,height:36,anchor:[430,230] as const},
 amino:{text:'Axit amin',region:'blood',x:207,y:479,width:145,height:36,anchor:[280,390] as const},
};
export const CUE_ACTIONS = ['recycle','inflammation','withdraw','waste'] as const;
/** Qualitative tissue state, not a growth rate, clinical score, or treatment prediction. */
export const proteinGeometry = (state:OrganProps['state'], severity:number, frame:number, fps:number, cues?:Record<string,number>) => {
 const level=state==='normal'?0:Math.max(0,Math.min(1,severity));
 const active=(key:string)=>cues?Math.max(0,Math.min(1,cues[key]??0)):1;
 return {loss:level*active('waste'), inflammation:level*active('inflammation'), withdraw:level*active('withdraw'), phase:(frame/Math.max(1,fps)*.18)%1, recycling:1-level*.65*active('inflammation')};
};
export const MuscleTumorAminoAcidBalance:React.FC<OrganProps> = ({state,severity,cueProgress,visibleLabels=[]}) => {
 const frame=useCurrentFrame(); const {fps}=useVideoConfig(); const g=proteinGeometry(state,severity,frame,fps,cueProgress);
 const view='axis';
 return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img" aria-label="Vietnamese qualitative protein metabolism diagram" data-state={state} data-view={view}>
 {true&&<g data-layer="muscle-fibres">
 {Array.from({length:7},(_,i)=><g key={i} transform={`translate(0 0)`}>
 <rect x={40+i*25} y={145+g.loss*55} width={22-g.loss*7} height={325-g.loss*110} rx="11" fill={c.heartDeep} stroke={brand.navy} strokeWidth="1"/>
 <rect x={43+i*25} y={151+g.loss*55} width={14-g.loss*5} height={310-g.loss*110} rx="7" fill={c.heartLight}/>
 <path d={`M${46+i*25} ${162+g.loss*55} v${280-g.loss*110}`} stroke={c.heartMid} strokeWidth="3"/>
 {Array.from({length:8},(_,j)=><path key={j} d={`M${42+i*25} ${180+j*32} h${18-g.loss*6}`} stroke={brand.navy} opacity={.2*(1-g.loss)} strokeWidth="2"/>)}
 </g>)}
 </g>}
 {true&&<g data-layer="circulating-amino-acids">
 <rect x="253" y="105" width="65" height="370" rx="32" fill={c.blood} opacity=".22"/>
 <path d="M259 113 V468 M312 113 V468" stroke={c.blood} strokeWidth="4"/>
 {Array.from({length:9},(_,i)=><circle key={i} cx={275+(i%2)*19} cy={125+((g.phase+i/9)%1)*320} r="5" fill={brand.yellow}/>)}
 </g>}
 {true&&<g data-layer="protein-recycling" opacity={g.recycling}>
 <ProcessArrow d="M62 130 Q140 87 213 130 L200 118 M213 130 L198 138"/>
 <circle cx={65+g.phase*140} cy={118-Math.sin(g.phase*Math.PI)*16} r="5" fill={brand.teal}/>
 </g>}
 {true&&<g data-layer="tumor-uptake">
 <path d="M364 245 Q330 184 393 168 Q440 130 470 197 Q542 211 514 274 Q549 335 489 361 Q450 419 407 365 Q340 363 358 302Z" fill={c.heartDeep} stroke={brand.navy} strokeWidth="3"/>
 {Array.from({length:19},(_,i)=><g key={i}><ellipse cx={383+(i%4)*32} cy={211+Math.floor(i/4)*33} rx="15" ry="17" fill={i%2?c.heartLight:c.heartMid}/><circle cx={383+(i%4)*32} cy={211+Math.floor(i/4)*33} r="5" fill={brand.navy}/></g>)}
 <ProcessArrow d="M322 285 H356 L345 276 M356 285 L345 294"/>
 <circle cx={322+g.phase*34} cy="285" r="6" fill={brand.yellow}/>
 </g>}
 {g.inflammation>0&&<g data-layer="inflammatory-signal" opacity={g.inflammation}>
 <path d="M403 423 Q300 510 168 435 L181 429 M168 435 L174 450" stroke={c.blood} strokeWidth="4" strokeDasharray="7 6" fill="none"/>
 <circle cx={403-g.phase*235} cy={423+Math.sin(g.phase*Math.PI)*40} r="6" fill={c.blood}/>
 </g>}
 {g.withdraw>0&&true&&<g data-layer="muscle-withdrawal" opacity={g.withdraw}><ProcessArrow d="M219 331 H252 L240 321 M252 331 L240 341"/><circle cx={219+g.phase*33} cy="331" r="5" fill={brand.yellow}/></g>}
 <DiagramAnnotations labels={LABELS} visibleLabels={visibleLabels}/>
 </svg>;
};
