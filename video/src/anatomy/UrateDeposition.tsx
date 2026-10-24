import React from 'react';
import type {OrganProps} from './ArterySection';
import {anatomyColors as c,brand} from './palette';
import {DiagramAnnotations,ProcessArrow,type DiagramLabels} from './annotations';
export const CONTENT_BOX={left:28,top:28,width:504,height:504};
export const CUE_ACTIONS=['deposit'] as const;
export const FOCUS_REGIONS={cartilage:{left:28,top:250,width:504,height:180},synovium:{left:28,top:100,width:115,height:400},crystal:{left:205,top:210,width:260,height:140},fluid:{left:148,top:55,width:355,height:240}};
export const LABELS:DiagramLabels={
 cartilage:{text:'Sụn khớp',region:'cartilage',x:304,y:466,width:202,height:36,anchor:[380,370]},
 synovium:{text:'Màng hoạt dịch',region:'synovium',x:40,y:40,width:220,height:36,anchor:[88,233]},
 crystal:{text:'Lắng đọng urat',region:'crystal',x:288,y:40,width:222,height:36,anchor:[350,297]},
 fluid:{text:'Dịch khớp',region:'fluid',x:40,y:466,width:202,height:36,anchor:[240,175]},
};
/** Tissue surface perspective separates deposition from an active inflammatory flare. */
export const UrateDeposition:React.FC<OrganProps>=({state,severity,cueProgress,visibleLabels})=>{
 const burden=(state==='normal'?0:Math.max(0,Math.min(1,severity)))*(cueProgress?cueProgress.deposit??0:1);
 return <svg viewBox="0 0 560 560" width="100%" height="100%" role="img" aria-label="Urate deposition along cartilage and synovium without automatic inflammation" data-state={state}>
  <rect data-layer="joint-fluid" x="28" y="28" width="504" height="504" rx="30" fill={c.vesselDeep}/>
  <path data-layer="synovium" d="M28 58 Q95 90 72 170 T75 325 Q99 423 67 532 H28Z" fill={c.media}/>
  <path data-layer="cartilage" d="M102 331 Q276 274 532 322 V405 Q303 357 102 415Z" fill={c.vesselLight}/>
  <path data-layer="bone" d="M102 415 Q303 357 532 405 V502 Q532 532 500 532 H102Z" fill={brand.off_white}/>
  <g data-layer="surface-deposits" fill={brand.off_white}>{Array.from({length:Math.ceil(burden*9)},(_,i)=><path data-crystal="true" key={i} transform={`translate(${150+i*38} ${309-18*Math.sin(i/3)}) rotate(${i%2?20:-20})`} d="M-22 0 L0 -3 L22 0 L0 3Z"/>)}</g>
  <g data-layer="membrane-deposits" fill={brand.off_white}>{Array.from({length:Math.ceil(burden*3)},(_,i)=><path key={i} transform={`translate(70 ${160+i*62}) rotate(70)`} d="M-18 0 L0 -3 L18 0 L0 3Z"/>)}</g>
  <ProcessArrow d="M330 188 V262 M330 262 L319 247 M330 262 L341 247" visible={burden>0}/>
  <DiagramAnnotations labels={LABELS} visibleLabels={visibleLabels}/>
 </svg>;
};
