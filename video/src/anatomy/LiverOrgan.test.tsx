import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {expect, it} from 'vitest';
import {LiverOrgan, liverOrganGeometry, CONTENT_BOX} from './LiverOrgan';

it('renders anterior lobes and falciform division with a state-dependent blunt inferior edge', () => {
  const normal = renderToStaticMarkup(<LiverOrgan state="normal" severity={1} />);
  const severe = renderToStaticMarkup(<LiverOrgan state="diseased" severity={1} />);
  for (const layer of ['liver-silhouette', 'right-lobe', 'left-lobe', 'falciform-ligament']) expect(severe).toContain(`data-layer="${layer}"`);
  expect(normal).not.toBe(severe);
  const a = liverOrganGeometry('normal', 1), b = liverOrganGeometry('diseased', .5), c = liverOrganGeometry('diseased', 1);
  expect(b.edgeRadius).toBeGreaterThan(a.edgeRadius);
  expect(c.edgeRadius).toBeGreaterThan(b.edgeRadius);
  expect(c.fill).not.toBe(a.fill);
  expect(liverOrganGeometry('normal', 0)).toEqual(a);
  expect(CONTENT_BOX.width / 560).toBeGreaterThanOrEqual(.75);
  expect(CONTENT_BOX.height / 560).toBeGreaterThanOrEqual(.75);
  expect(severe).not.toMatch(/<text|gradient|filter=/i);
});
