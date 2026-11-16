import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {OrganProps} from './ArterySection';
import {brand, anatomyColors as c} from './palette';
import {DiagramAnnotations, ProcessArrow} from './annotations';
export const CONTENT_BOX = {left:35,top:45,width:490,height:445};
export const FOCUS_REGIONS = {overview:{left:0,top:0,width:560,height:560}, muscle:{left:40,top:70,width:480,height:420}, blood:{left:245,top:120,width:85,height:370}, tumor:{left:345,top:175,width:190,height:300}};
export const LABELS = {muscle:{text:'Cơ xương',region:'muscle',x:35,y:45,width:155,height:36,anchor:[280,280] as const}};
export const CUE_ACTIONS = ['recycle','inflammation','withdraw','waste'] as const;
/** Qualitative tissue state, not a growth rate, clinical score, or treatment prediction. */
export const proteinGeometry = (state:OrganProps['state'], severity:number, frame:number, fps:number, cues?:Record<string,number>) => {
 const level=state==='normal'?0:Math.max(0,Math.min(1,severity));
 const active=(key:string)=>cues?Math.max(0,Math.min(1,cues[key]??0)):1;
 return {loss:level*active('waste'), inflammation:level*active('inflammation'), withdraw:level*active('withdraw'), phase:(frame/Math.max(1,fps)*.18)%1, recycling:1-level*.65*active('inflammation')};
};
export const MuscleWastingSection:React.FC<OrganProps> = ({state,severity,cueProgress,visibleLabels=[]}) => {
 const frame=useCurrentFrame(); const {fps}=useVideoConfig(); const g=proteinGeometry(state,severity,frame,fps,cueProgress);
 const view='section';
 return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img" aria-label="Vietnamese qualitative protein metabolism diagram" data-state={state} data-view={view}>
 <g data-layer="muscle-fibres">
 <ellipse cx="280" cy="280" rx="240" ry="210" fill={c.heartDeep} stroke={brand.navy} strokeWidth="3"/>
 <ellipse cx="280" cy="280" rx="229" ry="199" fill={c.heartMid}/>
 <ellipse cx="280" cy="280" rx="218" ry="188" fill={c.heartLight}/>
 {Array.from({length:7},(_,row)=>Array.from({length:9},(_,col)=>{
 const x=88+col*48+(row%2)*12, y=123+row*51;
 if(((x-280)/210)**2+((y-280)/180)**2>.86)return null;
 const radius=21*(1-g.loss*.55);
 return <g key={`${row}-${col}`}><circle cx={x} cy={y} r={radius} fill={c.heartDeep} stroke={brand.navy}/><circle cx={x-2} cy={y-2} r={radius*.8} fill={c.heartMid}/><circle cx={x-5} cy={y-4} r={radius*.4} fill={c.heartLight}/><ellipse cx={x+radius*.6} cy={y} rx="2" ry="4" fill={brand.navy}/></g>;
 }))}
 </g>
 <DiagramAnnotations labels={LABELS} visibleLabels={visibleLabels}/>
 </svg>;
};
