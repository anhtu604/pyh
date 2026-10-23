import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {HepaticCell, hepaticGeometry} from './HepaticCell';

const clock = vi.hoisted(() => ({frame: 0}));
vi.mock('remotion', () => ({useCurrentFrame: () => clock.frame, useVideoConfig: () => ({fps: 30})}));
const render = (severity: number, state: 'normal' | 'diseased' = 'diseased') =>
  renderToStaticMarkup(<HepaticCell state={state} severity={severity} />);

describe('hepatic cell qualitative mechanism', () => {
  it('keeps storage separate from injury and extracellular matrix', () => {
    expect(render(.25)).toContain('intracellular-storage');
    expect(render(.25)).not.toContain('injury-and-immune-signals');
    expect(render(.25)).not.toContain('extracellular-matrix');
    expect(render(.6)).toContain('injury-and-immune-signals');
    expect(render(.6)).not.toContain('extracellular-matrix');
    expect(render(.9)).toContain('extracellular-matrix');
    expect(render(.9)).toContain('intracellular-storage');
    expect(hepaticGeometry('diseased', .9, 0, 30).dropletRadius)
      .toBe(hepaticGeometry('diseased', .6, 0, 30).dropletRadius);
  });
  it('keeps normal independent of severity and clamps teaching geometry', () => {
    expect(hepaticGeometry('normal', 1, 0, 30)).toEqual(hepaticGeometry('normal', 0, 0, 30));
    expect(hepaticGeometry('diseased', 10, 0, 30)).toEqual(hepaticGeometry('diseased', 1, 0, 30));
  });
  it('supports seeking without accumulating damage as time passes', () => {
    clock.frame = 0; const first = render(.25);
    clock.frame = 120; expect(render(.25)).not.toBe(first);
    expect(render(.25)).not.toContain('extracellular-matrix');
    clock.frame = 0; expect(render(.25)).toBe(first);
  });
  it('uses the same square diagram without cropped content in either frame', () => {
    for (const [width, height] of [[1920,1080],[1080,1920]]) {
      for (const frame of [0,270,539]) {
        clock.frame = frame;
        const output = renderToStaticMarkup(<div style={{width,height}}><HepaticCell state="diseased" severity={.9} /></div>);
        expect(output).toContain('viewBox="0 0 560 560"');
        expect(output).toContain('extracellular-matrix');
        expect(output).not.toMatch(/<text|<filter|<linearGradient|NaN/);
      }
    }
  });
});
