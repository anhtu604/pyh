import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe,it,expect,vi} from 'vitest';
import {hepaticMechanics,HepatocyteDiagram} from './HepatocyteDiagram';
import {FOCUS_REGIONS as unitFocus} from './HepatocyteSinusoidUnit';
import {FOCUS_REGIONS as functionFocus} from './HepaticSynthesisAndBile';
import {FOCUS_REGIONS as injuryFocus} from './HepaticToxicInjury';
import {FOCUS_REGIONS as scarFocus, LABELS as scarLabels} from './HepaticFibrosisSection';
import {LABELS as unitLabels} from './HepatocyteSinusoidUnit';
import {LABELS as functionLabels} from './HepaticSynthesisAndBile';
import {LABELS as injuryLabels} from './HepaticToxicInjury';
vi.mock('remotion',()=>({useCurrentFrame:()=>150,useVideoConfig:()=>({fps:30})}));
describe('hepatic mechanism boundaries',()=>{
 it('keeps membrane intact and toxicity absent in normal state',()=>{
  const g=hepaticMechanics('normal',1,150,30); expect(g.leak).toBe(0); expect(g.toxic).toBe(0); expect(g.scar).toBe(0);
 });
 it('anchors each injury separately without activating unspoken mechanisms',()=>{
  const g=hepaticMechanics('diseased',0.8,150,30,{leak:1});
  expect(g.leak).toBe(0.8); expect(g.toxic).toBe(0); expect(g.bile).toBe(0); expect(g.scar).toBe(0);
 });
 it('moves blood continuously by frame and clamps pathological severity',()=>{
  expect(hepaticMechanics('normal',0,15,30).flow).not.toBe(hepaticMechanics('normal',0,30,30).flow);
  expect(hepaticMechanics('diseased',5,150,30,{scar:1}).scar).toBe(1);
 });
 it('renders distinct functional and fibrous layers with fixed Vietnamese labels',()=>{
  const render=(view:'unit'|'function'|'injury'|'scar')=>renderToStaticMarkup(<HepatocyteDiagram view={view} labels={{}} state="diseased" severity={1}/>);
  expect(render('function')).toContain('protein-export'); expect(render('unit')).not.toContain('protein-export');
  expect(render('scar')).toContain('fibrous-septa'); expect(render('injury')).not.toContain('fibrous-septa');
  for(const view of ['unit','function','injury','scar'] as const){const svg=render(view);expect(svg).toContain('viewBox="0 0 560 560"');expect(svg).not.toMatch(/gradient|filter/);expect(svg).toContain('data-process-arrow');}
 });
 it('keeps zero-severity comparisons neutral when scene context is unavailable',()=>{
  // S06, S22 and S27 use identical props: anatomy must not infer muscle/heart claims.
  for (const state of ['normal', 'diseased'] as const) {
   const svg=renderToStaticMarkup(<HepatocyteDiagram view="unit" labels={unitLabels} state={state} severity={0}/>);
   expect(svg).toContain('hepatocyte-membrane');
   expect(svg).not.toContain('alt-ast-distribution');
   expect(svg).not.toContain('Cơ bắp');
   expect(svg).not.toContain('Cơ tim');
  }
 });
 it('labels Albumin, clotting factors/INR, and distinguishes Bilirubin reflux vs Bile Acid in function view',()=>{
  const normalFlow=renderToStaticMarkup(<HepatocyteDiagram view="function" labels={{}} state="normal" severity={0} cueProgress={{export:1,block:0}}/>);
  const blockedFlow=renderToStaticMarkup(<HepatocyteDiagram view="function" labels={{}} state="normal" severity={0} cueProgress={{export:1,block:1}}/>);
  expect(normalFlow).toContain('Albumin (đạm gan)');
  expect(normalFlow).toContain('Yếu tố đông máu');
  expect(normalFlow).toContain('Đánh giá đông máu: INR');
  expect(normalFlow).toContain('Bilirubin (sắc tố vàng)');
  expect(normalFlow).toContain('Axit mật (BA)');
  expect(normalFlow).toContain('data-bile-blocked="false"');
  expect(blockedFlow).toContain('data-bile-blocked="true"');
  expect(blockedFlow).toContain('Bilirubin dội ngược vào máu');
 });
 it('renders bile pump lock, BA stasis/BIL reflux, S23 chronic-acute overlay, and S29 E03 contaminant panel in injury view',()=>{
  const openPump=renderToStaticMarkup(<HepatocyteDiagram view="injury" labels={{}} state="normal" severity={0}/>);
  expect(openPump).toContain('data-pump="open"');
  expect(openPump).toContain('Bơm mật mở bình thường');

  const lockedPump=renderToStaticMarkup(<HepatocyteDiagram view="injury" labels={{}} state="diseased" severity={0.8} cueProgress={{block:1,toxic:1}}/>);
  expect(lockedPump).toContain('data-pump="locked"');
  expect(lockedPump).toContain('Khóa bơm mật');
  expect(lockedPump).toContain('Axit mật (BA) ứ kẹt');
  expect(lockedPump).toContain('Bilirubin (BIL) dội ngược');
  expect(lockedPump).not.toContain('chronic-acute-overlay');
  expect(lockedPump).not.toContain('contaminant-panel');

  const s23=renderToStaticMarkup(<HepatocyteDiagram view="injury" labels={{}} state="diseased" severity={0.85} cueProgress={{toxic:1,block:1,leak:1}}/>);
  expect(s23).toContain('chronic-acute-overlay');
  expect(s23).toContain('Nền bệnh gan mạn sẵn có');
  expect(s23).toContain('Suy gan cấp/nền mạn: 36/91 ca');
  expect(s23).toContain('chronic-liver-context');
  expect(s23).not.toContain('contaminant-panel');

  const s29=renderToStaticMarkup(<HepatocyteDiagram view="injury" labels={{}} state="diseased" severity={0.8} emphasizeFlow cueProgress={{toxic:1,block:1,leak:1}}/>);
  expect(s29).toContain('contaminant-panel');
  expect(s29).toContain('386 mẫu từ 91 ca tổn thương gan');
  expect(s29).toContain('34% mẫu vượt ngưỡng thủy ngân');
  expect(s29).toContain('27,7% mẫu');
  expect(s29).not.toContain('chronic-acute-overlay');
 });
});

// Include the largest active beat overlay, which MechanismScene draws separately.
it('keeps the reviewed diagrams within six non-overlapping callouts including beat labels', () => {
  const configurations = [
    {view: 'unit' as const, severity: 0, state: 'normal' as const, overlay: 2},
    {view: 'unit' as const, severity: 0, state: 'diseased' as const, overlay: 2},
    {view: 'function' as const, severity: 0, state: 'normal' as const, overlay: 2},
    {view: 'injury' as const, severity: 0.8, state: 'diseased' as const, overlay: 2},
    {view: 'injury' as const, severity: 0.85, state: 'diseased' as const, overlay: 2},
    {view: 'injury' as const, severity: 0.8, state: 'diseased' as const, overlay: 3, emphasizeFlow: true},
  ];
  for (const configuration of configurations) for (const block of [0, 0.5, 1]) {
    const svg = renderToStaticMarkup(<HepatocyteDiagram {...configuration} labels={{}}
      cueProgress={{block, export: 1, toxic: 1, leak: 1}} />);
    const boxes = [...svg.matchAll(/data-box="([^"]+)"/g)].map(m => m[1].split(' ').map(Number));
    expect(boxes.length + configuration.overlay).toBeLessThanOrEqual(6);
    expect([...svg.matchAll(/data-callout-leader="true"/g)]).toHaveLength(boxes.length);
    boxes.forEach(([x,y,w,h], index) => {
      expect(x).toBeGreaterThanOrEqual(28); expect(y).toBeGreaterThanOrEqual(28);
      expect(x+w).toBeLessThanOrEqual(532); expect(y+h).toBeLessThanOrEqual(512);
      boxes.slice(index+1).forEach(([bx,by,bw,bh]) => {
        expect(x < bx+bw && x+w > bx && y < by+bh && y+h > by).toBe(false);
      });
      // All authored focuses retain the explanatory panel, blood and bile destinations.
      const focuses = configuration.view === 'unit' ? unitFocus : configuration.view === 'function' ? functionFocus : injuryFocus;
      Object.values(focuses).forEach(f => {
        expect(x).toBeGreaterThanOrEqual(f.left); expect(y).toBeGreaterThanOrEqual(f.top);
        expect(x+w).toBeLessThanOrEqual(f.left+f.width); expect(y+h).toBeLessThanOrEqual(f.top+f.height);
      });
    });
  }
});
it('does not assign the E03 cohort or chronic disease to unrelated injury configurations', () => {
  for (const severity of [0.55, 0.65, 0.7, 0.75, 0.9, 1]) {
    const svg = renderToStaticMarkup(<HepatocyteDiagram view="injury" labels={{}} state="diseased"
      severity={severity} emphasizeFlow cueProgress={{toxic:1, block:1}} />);
    expect(svg).not.toContain('contaminant-panel');
    expect(svg).not.toContain('chronic-acute-overlay');
  }
});

it('retains the full cell and nucleus when the scar scene focuses on blood', () => {
  expect(scarFocus).toEqual(unitFocus);
  for (const focus of Object.values(scarFocus)) {
    expect(focus.top).toBeLessThanOrEqual(55);
    expect(focus.top + focus.height).toBeGreaterThanOrEqual(485);
    expect(focus.left).toBeLessThanOrEqual(45);
    expect(focus.left + focus.width).toBeGreaterThanOrEqual(510);
  }
});

it('keeps anatomical leaders local and clear of intracellular callout text', () => {
  const cases = [
    {view: 'unit' as const, labels: unitLabels, severity: 0},
    {view: 'function' as const, labels: functionLabels, severity: 0},
    {view: 'injury' as const, labels: injuryLabels, severity: 0.8},
    {view: 'injury' as const, labels: injuryLabels, severity: 0.85},
    {view: 'scar' as const, labels: scarLabels, severity: 0.75},
  ];
  for (const configuration of cases) {
    const svg = renderToStaticMarkup(<HepatocyteDiagram {...configuration} state="diseased"
      cueProgress={{block:1, toxic:1, scar:1, export:1}} />);
    const boxes = [...svg.matchAll(/data-box="([^"]+)"/g)].map(m => m[1].split(' ').map(Number));
    for (const label of Object.values(configuration.labels)) {
      const {x,y,width,height,anchor: [ax,ay]} = label;
      const sx = Math.max(x, Math.min(x+width, ax));
      const sy = ay < y ? y : ay > y+height ? y+height : y+height/2;
      expect(Math.hypot(ax-sx,ay-sy)).toBeLessThan(60);
      // Sample the complete leader including endpoints against all mechanism text boxes.
      for (let step=0;step<=100;step++) {
        const px=sx+(ax-sx)*step/100, py=sy+(ay-sy)*step/100;
        for (const [bx,by,bw,bh] of boxes) {
          expect(px > bx && px < bx+bw && py > by && py < by+bh).toBe(false);
        }
      }
      // All non-blood labels and leaders stay above the sinusoid.
      if (label.region !== 'blood') expect(Math.max(y+height,ay)).toBeLessThan(395);
    }
  }
});
