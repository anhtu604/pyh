import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {expect,it,vi} from 'vitest';
import library from './library.json';
import {ANATOMY_FOCUS_REGIONS,ANATOMY_LABELS} from './registry';
import {GoutFootOverview} from './GoutFootOverview';
import {UrateCrystalCloseUp,crystalGeometry} from './UrateCrystalCloseUp';
import {UrateDeposition} from './UrateDeposition';
const clock=vi.hoisted(()=>({frame:180}));
vi.mock('remotion',()=>({useCurrentFrame:()=>clock.frame,useVideoConfig:()=>({fps:30})}));
it('keeps JSON metadata identical to the actual component metadata',()=>{
 for(const [key,entry] of Object.entries(library.components)){
  const subject=key as keyof typeof ANATOMY_LABELS;
  expect(ANATOMY_LABELS[subject]).toEqual(entry.labels);
  expect(ANATOMY_FOCUS_REGIONS[subject]).toEqual(entry.focus_regions);
 }
});
it('shows a foot location in both states and inflammatory signs only after swell cue',()=>{
 const normal=renderToStaticMarkup(<GoutFootOverview state="normal" severity={1}/>);
 expect(normal).toContain('mtp1-highlight');expect(normal).not.toContain('inflammatory-halo');
 expect(renderToStaticMarkup(<GoutFootOverview state="diseased" severity={1} cueProgress={{swell:0}}/>)).not.toContain('inflammatory-halo');
 expect(renderToStaticMarkup(<GoutFootOverview state="diseased" severity={1} cueProgress={{swell:1}}/>)).toContain('inflammatory-halo');
});
it('separates dissolved urate, nucleation and growth without creating needles in normal fluid',()=>{
 expect(crystalGeometry('normal',1,1,1).count).toBe(0);
 expect(crystalGeometry('diseased',5,1,1)).toEqual(crystalGeometry('diseased',1,1,1));
 const render=(seed:number,grow:number)=>renderToStaticMarkup(<UrateCrystalCloseUp state="diseased" severity={1} cueProgress={{seed,grow}}/>);
 expect(render(0,0)).not.toContain('data-seed');
 expect(render(1,0)).toContain('data-seed');expect(render(1,0)).not.toContain('data-crystal');
 expect(render(1,1)).toContain('data-crystal');
 const first=render(1,1);clock.frame=120;expect(render(1,1)).not.toBe(first);clock.frame=180;expect(render(1,1)).toBe(first);
});
it('deposits on tissue surfaces independently of an inflammatory alarm',()=>{
 const quiet=renderToStaticMarkup(<UrateDeposition state="normal" severity={1}/>);
 const before=renderToStaticMarkup(<UrateDeposition state="diseased" severity={1} cueProgress={{deposit:0}}/>);
 const after=renderToStaticMarkup(<UrateDeposition state="diseased" severity={1} cueProgress={{deposit:1}}/>);
 expect(quiet).not.toContain('data-crystal');expect(before).not.toContain('data-crystal');expect(after).toContain('data-crystal');
 expect(after).not.toContain('data-signal');expect(after).not.toContain('data-neutrophil');
});
