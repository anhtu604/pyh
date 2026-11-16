import React from 'react';
import {useCurrentFrame,useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {DiagramAnnotations,ProcessArrow} from './annotations';
import {brand} from './palette';
export const CONTENT_BOX={left:40,top:55,width:480,height:450};
export const FOCUS_REGIONS={"overview": {"left": 0, "top": 0, "width": 560, "height": 560}, "detail": {"left": 65, "top": 125, "width": 430, "height": 310}};
export const LABELS={"lumen": {"text": "Lòng ống thận", "region": "detail", "x": 30, "y": 55, "width": 230, "height": 36, "anchor": [240, 245] as const}, "wall": {"text": "Tế bào ống thận", "region": "detail", "x": 300, "y": 55, "width": 230, "height": 36, "anchor": [130, 170] as const}, "oxalate": {"text": "Oxalat hòa tan", "region": "detail", "x": 160, "y": 490, "width": 230, "height": 36, "anchor": [370, 280] as const}};
export const CUE_ACTIONS=['flow','reclaim','convert','crystallize'] as const;
/** Qualitative mechanism only: no biological timescale, stone probability or dose mapping. */
export const RenalTubuleOxalate:React.FC<OrganProps>=({state,severity,cueProgress,visibleLabels=[]})=>{
 const frame=useCurrentFrame();const {fps}=useVideoConfig();
 const phase=(frame/Math.max(1,fps)*.12)%1;
 const active=(key:string)=>Math.max(0,Math.min(1,cueProgress?.[key]??1));
 const disease=state==='diseased'?Math.max(0,Math.min(1,severity)):0;
 const view='tubule' as string;
 return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img" aria-label="Ống thận và oxalat hòa tan" data-state={state} data-view={view}>
 {view==='tubule'||view==='transport'?<g data-layer="renal-epithelium">
 <rect x="45" y="115" width="470" height="330" rx="80" fill="#EEE6CE" stroke={brand.navy} strokeWidth="3"/>
 <rect x="75" y="145" width="410" height="270" rx="65" fill="#F4E9CF"/>
 <rect x="110" y="185" width="280" height="200" rx="55" fill="#E5F3EE" stroke={brand.teal} strokeWidth="2"/>
 {Array.from({length:12},(_,i)=><g key={i}><rect x={70+i*34} y="125" width="31" height="53" rx="12" fill="#CBB99D" stroke={brand.navy}/><rect x={73+i*34} y="128" width="25" height="43" rx="10" fill="#E2CFB0"/><ellipse cx={85+i*34} cy="152" rx="6" ry="8" fill="#9B7D72"/>
 <rect x={70+i*34} y="391" width="31" height="44" rx="12" fill="#CBB99D" stroke={brand.navy}/><rect x={74+i*34} y="394" width="23" height="30" rx="9" fill="#E2CFB0"/></g>)}
 <path d="M411 181 V386 Q435 405 464 382 V181" fill="#E4AAA1" stroke="#D8574B" strokeWidth="3"/>
 {Array.from({length:10},(_,i)=><circle key={i} cx={144+((phase+i/10)%1)*220} cy={225+(i%4)*34} r="6" fill={i%2?brand.yellow:brand.teal}/>)}
 {view==='transport'&&<g data-layer="reabsorption"><path d="M395 250 V348" stroke={brand.navy} strokeWidth="8"/>
 <ProcessArrow d="M350 300 H445 L433 289 M445 300 L433 311"/>
 <circle cx={350+phase*90*active('reclaim')*(1-disease*.7)} cy="300" r="8" fill={brand.yellow}/></g>}
 {view==='tubule'&&<g data-layer="urinary-oxalate" opacity={disease*active('convert')}>
 {Array.from({length:10},(_,i)=><circle key={i} cx={143+((phase+i/10)%1)*220} cy={236+(i%3)*32} r="7" fill="#D8574B" stroke={brand.navy}/>)}</g>}
 <ProcessArrow d="M70 475 H475 L462 464 M475 475 L462 486"/>
 </g>:view==='pathway'?<g data-layer="ascorbate-catabolism">
 <rect x="40" y="115" width="480" height="330" rx="40" fill="#F7F4EC" stroke={brand.navy}/>
 {[95,265,435].map((x,i)=><g key={x}><ellipse cx={x} cy={i===2?350:220} rx="44" ry="44" fill={i===2?'#D8574B':i===1?'#CFC6A9':brand.yellow} stroke={brand.navy} strokeWidth="3"/><ellipse cx={x-8} cy={(i===2?350:220)-10} rx="26" ry="23" fill="#FFFDF7" opacity=".4"/></g>)}
 <ProcessArrow d="M147 220 H207 L195 208 M207 220 L195 232"/>
 <ProcessArrow d="M310 239 Q435 250 435 295 L423 282 M435 295 L447 282"/>
 <path d="M265 165 Q179 92 95 165" fill="none" stroke={brand.teal} strokeWidth="3"/>
 <path d="M95 165 L98 148 M95 165 L111 161" fill="none" stroke={brand.teal} strokeWidth="3"/>
 <circle cx={310+phase*120} cy={247+phase*42} r="6" fill={brand.teal} opacity={active('convert')*(.3+disease*.7)}/>
 </g>:<g data-layer="calcium-oxalate-crystallization">
 <ellipse cx="280" cy="280" rx="235" ry="185" fill="#E5F3EE" stroke={brand.navy} strokeWidth="3"/>
 {Array.from({length:18},(_,i)=>{const angle=i*Math.PI*2/18+phase*.25;return <g key={i}><circle cx={280+Math.cos(angle)*180} cy={280+Math.sin(angle)*130} r="7" fill={i%2?'#D8574B':brand.yellow} stroke={brand.navy}/></g>;})}
 <g transform={`translate(280 280) scale(${.25+disease*active('crystallize')*.7})`} data-crystal="true">
 <path d="M0 -98 L110 0 L0 98 L-110 0Z" fill="#CFB98C" stroke={brand.navy} strokeWidth="3"/>
 <path d="M0 -98 L0 0 L-110 0Z" fill="#EFE0BC"/><path d="M0 0 L110 0 L0 98Z" fill="#A18F70"/>
 <path d="M0 -98 V98 M-110 0 H110" stroke={brand.navy} strokeWidth="2"/>
 </g><ProcessArrow d="M430 420 Q365 485 280 470 L294 460 M280 470 L294 481"/>
 </g>}
 <DiagramAnnotations labels={LABELS} visibleLabels={visibleLabels}/>
 </svg>;
};
