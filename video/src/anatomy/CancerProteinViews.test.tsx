import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe,it,expect,vi} from 'vitest';
import * as Axis from './MuscleTumorAminoAcidBalance';
import * as Turnover from './MuscleProteinTurnover';
import * as Uptake from './TumorProteinUptake';
import * as Section from './MuscleWastingSection';
let frame=0;
vi.mock('remotion',()=>({useCurrentFrame:()=>frame,useVideoConfig:()=>({fps:30})}));
describe('protein metabolism diagrams',()=>{
 it('keeps normal muscle intact and separates inflammation, withdrawal and wasting cues',()=>{
  expect(Axis.proteinGeometry('normal',1,0,30).loss).toBe(0);
  const inflamed=Axis.proteinGeometry('diseased',.8,0,30,{inflammation:1});
  expect(inflamed.inflammation).toBe(.8);expect(inflamed.loss).toBe(0);expect(inflamed.withdraw).toBe(0);
  const wasting=Axis.proteinGeometry('diseased',.8,0,30,{waste:1});
  expect(wasting.loss).toBe(.8);expect(wasting.inflammation).toBe(0);
  expect(Axis.proteinGeometry('diseased',2,0,30).loss).toBe(1);
 });
 it('animates flow by frame while keeping tissue loss qualitative and bounded',()=>{
  const a=Axis.proteinGeometry('diseased',.5,0,30),b=Axis.proteinGeometry('diseased',.5,90,30);
  expect(a.phase).not.toBe(b.phase);expect(a.loss).toBe(b.loss);
  expect(b.phase).toBeGreaterThanOrEqual(0);expect(b.phase).toBeLessThan(1);
 });
 it('renders distinct anatomical scales and moving processes without invented data',()=>{
  for(const [Component,view] of [[Axis.MuscleTumorAminoAcidBalance,'axis'],[Turnover.MuscleProteinTurnover,'muscle'],[Uptake.TumorProteinUptake,'tumor'],[Section.MuscleWastingSection,'section']] as const){
   frame=0;const first=renderToStaticMarkup(<Component state="diseased" severity={.7}/>);
   frame=90;const next=renderToStaticMarkup(<Component state="diseased" severity={.7}/>);
   expect(first).toContain(`data-view="${view}"`);expect(first).not.toMatch(/<linearGradient|<radialGradient|<filter/);
   if(view!=='section')expect(next).not.toBe(first);
   if(view==='section')expect((first.match(/<circle/g)||[]).length).toBeGreaterThan(30);
   else expect(first).toContain('data-process-arrow');
  }
 });
 it('makes cross-sectional fibre area smaller only in the wasting state',()=>{
  const a=renderToStaticMarkup(<Section.MuscleWastingSection state="normal" severity={1}/>);
  const b=renderToStaticMarkup(<Section.MuscleWastingSection state="diseased" severity={1} cueProgress={{waste:1}}/>);
  expect(a).toContain('r="21"');expect(b).not.toContain('r="21"');
 });
});
