import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {expect, it, vi} from 'vitest';
import {AltAstTissueDistribution, LABELS} from './AltAstTissueDistribution';
const clock = vi.hoisted(() => ({frame: 0}));
vi.mock('remotion', () => ({useCurrentFrame: () => clock.frame}));
const render = (state: 'normal' | 'diseased' = 'normal', cueProgress?: Record<string, number>) => renderToStaticMarkup(
  <AltAstTissueDistribution state={state} severity={1} visibleLabels={Object.keys(LABELS)} cueProgress={cueProgress}/>);
it('separates liver, striated skeletal muscle and branching cardiac muscle without a transport arrow', () => {
  const html = render();
  for (const layer of ['liver-tissue', 'skeletal-muscle', 'cardiac-muscle']) expect(html).toContain(`data-layer="${layer}"`);
  for (const text of ['Gan', 'Cơ vân', 'Cơ tim', 'ALT', 'AST']) expect(html).toContain(text);
  expect(html).not.toContain('data-process-arrow');
  expect(html).not.toMatch(/gradient|filter=/);
  // Distribution is physiological; the renderer's comparison state must not imply injury.
  expect(render('diseased')).toBe(html);
});
it('keeps both tissue groups in motion and cues their emphasis independently', () => {
  const start = render(); clock.frame = 60; expect(render()).not.toBe(start);
  expect(render('normal', {liver: 1, muscle: 0})).not.toBe(render('normal', {liver: 0, muscle: 1}));
});
