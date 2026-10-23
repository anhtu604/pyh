import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {HepaticCell, hepaticGeometry} from './HepaticCell';

const clock = vi.hoisted(() => ({frame: 0}));
vi.mock('remotion', () => ({useCurrentFrame: () => clock.frame, useVideoConfig: () => ({fps: 30})}));
const render = (severity: number, state: 'normal' | 'diseased' = 'diseased') =>
  renderToStaticMarkup(<HepaticCell state={state} severity={severity} />);

it('starts fat, injury and extracellular matrix only from their own cues', () => {
  const cueRender = (fat: number, inflame: number, fibrose: number) => renderToStaticMarkup(
    <HepaticCell state="diseased" severity={1} cueProgress={{fat, inflame, fibrose}}/>);
  const before = cueRender(0, 0, 0);
  expect(before).not.toContain('data-layer="injury-and-immune-signals"');
  expect(before).not.toContain('data-layer="extracellular-matrix"');
  expect(before).toContain('r="13"');
  const fat = cueRender(1, 0, 0);
  expect(fat).toContain('r="31"');
  expect(fat).not.toContain('data-layer="injury-and-immune-signals"');
  expect(cueRender(1, 1, 0)).toContain('data-layer="injury-and-immune-signals"');
  expect(cueRender(1, 1, 0)).not.toContain('data-layer="extracellular-matrix"');
  expect(cueRender(1, 1, 1)).toContain('data-layer="extracellular-matrix"');
});

describe('hepatic cell qualitative mechanism', () => {
  it('makes the hepatocyte itself cover 75% of the square while retaining intracellular droplets', () => {
    const output = render(.9);
    const scale = Number(output.match(/data-layer="hepatocyte" transform="translate\(280 280\) scale\(([^)]+)\)/)![1]);
    const cell = output.match(/data-layer="hepatocyte"[^>]*><rect x="([^"]+)" y="([^"]+)" width="([^"]+)" height="([^"]+)"/)!.slice(1).map(Number);
    const left = 280 + (cell[0] - 280) * scale;
    const right = left + cell[2] * scale;
    expect(cell[2] * scale / 560).toBeGreaterThanOrEqual(.75);
    expect(cell[3] * scale / 560).toBeGreaterThanOrEqual(.75);
    // Maximum fat droplet stays inside the enlarged cell membrane.
    const radius = hepaticGeometry('diseased', .9, 0, 30).dropletRadius * scale;
    for (const x of [310, 346, 288]) {
      const center = 280 + (x - 280) * scale;
      expect(center - radius).toBeGreaterThan(left);
      expect(center + radius).toBeLessThan(right);
    }
    expect(output).toContain('data-layer="extracellular-matrix"');
  });
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
