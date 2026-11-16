import React from 'react';
import {useCurrentFrame,useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {DiagramAnnotations,ProcessArrow} from './annotations';
import {brand} from './palette';
export const CONTENT_BOX={left:40,top:55,width:480,height:450};
export const FOCUS_REGIONS={overview:{left:0,top:0,width:560,height:560},detail:{left:65,top:125,width:430,height:310}};
export const LABELS={
 lumen:{text:'Lòng ruột',region:'detail',x:30,y:55,width:230,height:36,anchor:[140,230] as const},
 cells:{text:'Tế bào hấp thu',region:'detail',x:300,y:55,width:230,height:36,anchor:[300,290] as const},
 blood:{text:'Mạch máu',region:'detail',x:160,y:490,width:230,height:36,anchor:[430,420] as const},
};
export const CUE_ACTIONS=['flow','absorb','retain'] as const;
/** Qualitative intestinal absorption; severity is illustrative, not a dose-response scale. */
export const IntestinalVitaminCAbsorption:React.FC<OrganProps>=({state,severity,cueProgress,visibleLabels=[]})=>{
 const frame=useCurrentFrame();const {fps}=useVideoConfig();const phase=(frame/Math.max(1,fps)*.12)%1;
 const disease=state==='diseased'?Math.max(0,Math.min(1,severity)):0;
 const absorb=cueProgress?.absorb??1;
 return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img" aria-label="Hấp thu vitamin C ở ruột" data-state={state}>
 <g data-layer="intestinal-absorption">
 <rect x="45" y="110" width="470" height="360" rx="25" fill="#E5F3EE" stroke={brand.navy} strokeWidth="3"/>
 <path d="M45 390 L75 390 Q95 390 95 340 V230 Q95 195 120 195 Q145 195 145 230 V340 Q145 390 175 390 Q205 390 205 340 V230 Q205 195 230 195 Q255 195 255 230 V340 Q255 390 285 390 Q315 390 315 340 V230 Q315 195 340 195 Q365 195 365 230 V340 Q365 390 395 390 H515 V470 H45Z" fill="#CBB99D" stroke={brand.navy} strokeWidth="2"/>
 {[120,230,340].map(x=><g key={x}><path d={`M${x-15} 340 V235 Q${x} 210 ${x+15} 235 V340`} fill="#E2CFB0" stroke="#9B7D72"/>
 {Array.from({length:8},(_,i)=><path key={i} d={`M${x-20} ${245+i*14} H${x-10} M${x+10} ${245+i*14} H${x+20}`} stroke={brand.navy}/>)}</g>)}
 <path d="M70 432 H490" stroke="#D8574B" strokeWidth="22"/>
 <path d="M70 427 H490" stroke="#E4AAA1" strokeWidth="9"/>
 {Array.from({length:12},(_,i)=><circle key={i} cx={75+((phase+i/12)%1)*400} cy={140+(i%2)*30} r={6+disease*2} fill={brand.yellow} stroke={brand.navy}/>)}
 <ProcessArrow d="M230 260 V365 L218 353 M230 365 L242 353"/>
 <circle cx="230" cy={260+phase*100*absorb*(1-disease*.5)} r="6" fill={brand.yellow}/>
 </g>
 <DiagramAnnotations labels={LABELS} visibleLabels={visibleLabels}/>
 </svg>;
};
