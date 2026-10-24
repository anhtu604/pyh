import React from 'react';
import {useCurrentFrame,useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {brand} from './palette';
import {DiagramAnnotations,ProcessArrow,type DiagramLabels} from './annotations';
export const CONTENT_BOX={left:28,top:28,width:504,height:504};
export const CUE_ACTIONS=['seed','grow'] as const;
export const FOCUS_REGIONS={fluid:{left:28,top:28,width:504,height:504},seed:{left:215,top:215,width:130,height:130},crystal:{left:100,top:170,width:370,height:240}};
export const LABELS: DiagramLabels={
 dissolved:{text:'Urat hòa tan',region:'fluid',x:45,y:48,width:200,height:36,anchor:[132,170]},
 seed:{text:'Mầm tinh thể',region:'seed',x:310,y:48,width:200,height:36,anchor:[280,280]},
 crystal:{text:'Tinh thể urat dạng kim',region:'crystal',x:132,y:474,width:296,height:36,anchor:[360,320]},
};
export const crystalGeometry=(state:OrganProps['state'],severity:number,seed:number,grow:number)=>{
 const level=state==='normal'?0:Math.max(0,Math.min(1,severity));
 return {count:Math.ceil(level*5*Math.max(0,Math.min(1,seed))),length:10+170*Math.max(0,Math.min(1,grow))*level};
};
/** Dissolved symbols, stable nuclei and needle growth are distinct, schematic states. */
export const UrateCrystalCloseUp:React.FC<OrganProps>=({state,severity,cueProgress,visibleLabels})=>{
 const frame=useCurrentFrame();const {fps}=useVideoConfig();
 const g=crystalGeometry(state,severity,cueProgress?.seed??1,cueProgress?.grow??Math.min(1,frame/fps/5));
 return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img" aria-label="Magnified dissolved urate, crystal nucleus and needle growth" data-state={state}>
  <rect data-layer="sample-window" x="28" y="28" width="504" height="504" rx="32" fill={brand.navy} stroke={brand.teal} strokeWidth="4"/>
  <g data-layer="dissolved-urate" fill={brand.teal}>{Array.from({length:38},(_,i)=>{
   const angle=i*2.4,r=45+165*Math.sqrt(i/37);return <circle key={i} cx={280+r*Math.cos(angle)+4*Math.sin(frame/fps+i)} cy={280+r*Math.sin(angle)+4*Math.cos(frame/fps+i)} r="5"/>;
  })}</g>
  <g data-layer="crystal-seeds" fill={brand.yellow}>{Array.from({length:g.count},(_,i)=><circle data-seed="true" key={i} cx={190+i*48} cy={244+(i%2)*72} r="6"/>)}</g>
  <g data-layer="needle-crystals" fill={brand.off_white}>{g.length>10&&Array.from({length:g.count},(_,i)=><path data-crystal="true" key={i} transform={`translate(${190+i*48} ${244+(i%2)*72}) rotate(${i*38-45})`} d={`M${-g.length/2} 0 L0 -4 L${g.length/2} 0 L0 4Z`}/>)}</g>
  <ProcessArrow d="M170 374 Q276 428 391 370 M391 370 L374 372 M391 370 L385 387" visible={g.count>0}/>
  <DiagramAnnotations labels={LABELS} visibleLabels={visibleLabels}/>
 </svg>;
};
