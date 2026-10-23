import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {expect, it, vi} from 'vitest';
import {UrateFluid, urateGeometry, CONTENT_BOX} from './UrateFluid';
vi.mock('remotion', () => ({useCurrentFrame: () => 120, useVideoConfig: () => ({fps: 30})}));
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
