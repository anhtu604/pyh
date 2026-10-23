import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {expect, it, vi} from 'vitest';
import {UrateFluid, urateGeometry, CONTENT_BOX} from './UrateFluid';
const clock = vi.hoisted(() => ({frame: 120}));
vi.mock('remotion', () => ({useCurrentFrame: () => clock.frame, useVideoConfig: () => ({fps: 30})}));
it('keeps dissolved dots and develops seeds and needles without implying an atomic model', () => {
  expect(urateGeometry('normal', 1, 240, 30).needles).toBe(0);
  expect(urateGeometry('diseased', .5, 240, 30).needles).toBe(4);
  expect(urateGeometry('diseased', 1, 240, 30).length).toBeGreaterThan(urateGeometry('diseased', 1, 0, 30).length);
  expect(urateGeometry('diseased', 2, 240, 30).level).toBe(1);
  const diseased = renderToStaticMarkup(<UrateFluid state="diseased" severity={1}/>);
  expect(diseased).not.toBe(renderToStaticMarkup(<UrateFluid state="normal" severity={1}/>));
  for (const layer of ['sample-window', 'dissolved-urate', 'crystal-seeds', 'needle-crystals']) expect(diseased).toContain(`data-layer="${layer}"`);
  expect(diseased).not.toMatch(/<text|gradient|filter=/i);
  // All centres and needle tips stay inside the painted 28..532 sample window.
  expect(CONTENT_BOX).toEqual({left: 28, top: 28, width: 504, height: 504});
});

it('places a square fluid inset (narration calls it ô vuông) beside a layered joint and deposits crystals only in disease', () => {
  const normal = renderToStaticMarkup(<UrateFluid state="normal" severity={1}/>);
  const stages = [0, .25, .5, .75, 1].map(severity => renderToStaticMarkup(<UrateFluid state="diseased" severity={severity}/>));
  for (const layer of ['joint-capsule', 'bone-ends', 'cartilage', 'synovial-fluid', 'synovial-membrane', 'sample-connector', 'cartilage-deposits', 'synovial-deposits']) {
    expect(stages[4]).toContain(`data-layer="${layer}"`);
  }
  expect(normal).toMatch(/<rect[^>]*data-layer="sample-window"/);
  expect(normal).not.toContain('data-crystal="true"');
  expect(normal).not.toContain('data-seed="true"');
  const count = (s: string) => (s.match(/data-crystal="true"/g) ?? []).length;
  for (let i = 1; i < stages.length; i++) expect(count(stages[i])).toBeGreaterThanOrEqual(count(stages[i - 1]));
  expect(stages[4]).toContain('data-deposit-site="cartilage"');
  expect(stages[4]).toContain('data-deposit-site="synovium"');
});

it('keeps crystal burden monotone throughout growth and is deterministic when seeking', () => {
  for (const frame of [0, 60, 120, 240, 900]) {
    clock.frame = frame;
    const stages = [0, .25, .5, .75, 1].map(severity => renderToStaticMarkup(<UrateFluid state="diseased" severity={severity}/>));
    const counts = stages.map(s => (s.match(/data-crystal="true"/g) ?? []).length);
    expect(counts).toEqual([...counts].sort((a,b) => a-b));
    const lengths = [0, .25, .5, .75, 1].map(s => urateGeometry('diseased', s, frame, 30).length);
    expect(lengths).toEqual([...lengths].sort((a,b) => a-b));
    const output = stages[4];
    clock.frame = frame + 31;
    renderToStaticMarkup(<UrateFluid state="diseased" severity={1}/>);
    clock.frame = frame;
    expect(renderToStaticMarkup(<UrateFluid state="diseased" severity={1}/>)).toBe(output);
    expect(renderToStaticMarkup(<UrateFluid state="normal" severity={1}/>)).not.toMatch(/data-(crystal|seed)="true"/);
  }
  expect(urateGeometry('diseased', -1, 240, 30).needles).toBe(0);
});
