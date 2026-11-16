import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {vi} from 'vitest';
vi.mock('remotion', () => ({useCurrentFrame: () => 180, useVideoConfig: () => ({fps: 30})}));
import {describe, expect, it} from 'vitest';
import {mechanics} from './EsophagusDiagram';
import {ANATOMY_CONTENT_BOXES, ANATOMY_LABELS, ANATOMY_COMPONENTS} from './registry';
describe('fishbone mechanical diagrams', () => {
  it('prevents penetration and inflammation in the normal state', () => {
    expect(mechanics('normal', 1, 180, 30, {penetrate:1, swell:1, press:1})).toMatchObject({penetration:0, swelling:0, pressure:0});
  });
  it('keeps swallowing independent of pressure, penetration and tissue response', () => {
    expect(mechanics('diseased', 0.8, 180, 30, {swallow:1})).toEqual({bolus:1,pressure:0,penetration:0,swelling:0});
    expect(mechanics('diseased', 0.8, 0, 30, {penetrate:1})).toEqual({bolus:0,pressure:0,penetration:0.8,swelling:0});
    expect(mechanics('diseased', 0.8, 0, 30, {swell:1}).swelling).toBe(0.8);
  });
  it('uses cue alignment rather than elapsed time when cues are supplied', () => {
    expect(mechanics('diseased', 1, 999, 30, {})).toEqual({bolus:0,pressure:0,penetration:0,swelling:0});
    expect(mechanics('diseased', 1, 999, 30).penetration).toBe(1);
  });
  it('registers four different anatomical views with safe labels and painted coverage', () => {
    const subjects = ['esophagus_aortic_arch_impaction','esophagus_food_bolus','esophagus_wall_penetration','esophagus_transverse_impaction'] as const;
    for (const s of subjects) {
      expect(typeof ANATOMY_COMPONENTS[s]).toBe('function');
      const b = ANATOMY_CONTENT_BOXES[s]; expect(b.width).toBeGreaterThanOrEqual(420); expect(b.height).toBeGreaterThanOrEqual(420);
      const labels = Object.values(ANATOMY_LABELS[s]); expect(labels.length).toBeLessThanOrEqual(6);
      for (const l of labels) {expect(l.x).toBeGreaterThanOrEqual(0); expect(l.x+l.width).toBeLessThanOrEqual(560); expect(l.y+l.height).toBeLessThanOrEqual(560);}
    }
  });
});

it('renders each view as a flat SVG with separate labels, leaders and process arrows', () => {
  const names = ['esophagus_aortic_arch_impaction','esophagus_food_bolus','esophagus_wall_penetration','esophagus_transverse_impaction'] as const;
  for (const name of names) {
    const Component = ANATOMY_COMPONENTS[name];
    const markup = renderToStaticMarkup(<Component state="diseased" severity={0.7} visibleLabels={Object.keys(ANATOMY_LABELS[name])}/>);
    expect(markup).toContain('viewBox="0 0 560 560"');
    expect(markup).toContain('data-process-arrow'); expect(markup).toContain('data-leader');
    expect(markup).not.toMatch(/linearGradient|radialGradient|<filter/);
  }
});
it('shows an impacted bone with rice pressure, without adding a bone to a normal tissue view', () => {
  const Bolus = ANATOMY_COMPONENTS.esophagus_food_bolus;
  expect(renderToStaticMarkup(<Bolus state="diseased" severity={1}/>)).toContain('impacted-bone');
  expect(renderToStaticMarkup(<Bolus state="normal" severity={1}/>)).not.toContain('impacted-bone');
  const Wall = ANATOMY_COMPONENTS.esophagus_wall_penetration;
  expect(renderToStaticMarkup(<Wall state="normal" severity={1}/>)).not.toContain('L280 301');
  expect(renderToStaticMarkup(<Wall state="diseased" severity={1}/>)).toContain('L280 301');
});
