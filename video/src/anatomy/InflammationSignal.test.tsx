import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {expect, it, vi} from 'vitest';
import {InflammationSignal, signalGeometry, CONTENT_BOX} from './InflammationSignal';
vi.mock('remotion', () => ({useCurrentFrame: () => 90, useVideoConfig: () => ({fps: 30})}));
it('can show a crystal cue without an active alarm and recruits cells only in activated state', () => {
  const quiet = renderToStaticMarkup(<InflammationSignal state="normal" severity={1}/>);
  const active = renderToStaticMarkup(<InflammationSignal state="diseased" severity={1}/>);
  expect(quiet).toContain('data-layer="crystal-cue"');
  expect(signalGeometry('normal', 1, 90, 30).recruited).toBe(0);
  expect(signalGeometry('diseased', 1, 90, 30).recruited).toBe(6);
  expect(signalGeometry('diseased', .5, 90, 30).recruited).toBe(3);
  expect(signalGeometry('diseased', 1, 90, 30).phase).not.toBe(signalGeometry('diseased', 1, 0, 30).phase);
  expect(active).not.toBe(quiet);
  for (const layer of ['sample-window', 'resident-cell', 'crystal-cue', 'alarm-signal', 'recruited-cells']) expect(active).toContain(`data-layer="${layer}"`);
  expect(active).not.toMatch(/<text|gradient|filter=/i);
  // Outermost recruited cell: 280 +/- (195 + 24), within sample bounds 28..532.
  expect(280 + 195 + 24).toBeLessThan(CONTENT_BOX.left + CONTENT_BOX.width);
  expect(280 - 195 - 24).toBeGreaterThan(CONTENT_BOX.left);
});
