import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {expect, it, vi} from 'vitest';
import {InflammationSignal, signalGeometry, CONTENT_BOX} from './InflammationSignal';
const clock = vi.hoisted(() => ({frame: 90}));
it('keeps engulfment, activation and recruitment hidden until their separate cues', () => {
  const render = (engulf: number, alarm: number, recruit: number) => renderToStaticMarkup(
    <InflammationSignal state="diseased" severity={1} cueProgress={{engulf, alarm, recruit}}/>);
  const before = render(0, 0, 0);
  for (const marker of ['data-crystal="true"', 'data-phagocytosis="true"', 'data-activation="true"', 'data-neutrophil="true"']) expect(before).not.toContain(marker);
  expect(before).toContain('data-lumen-radius="25"');
  const engulfed = render(1, 0, 0);
  expect(engulfed).toContain('data-phagocytosis="true"');
  expect(engulfed).not.toContain('data-activation="true"');
  const alarmed = render(1, 1, 0);
  expect(alarmed).toContain('data-activation="true"');
  expect(alarmed).not.toContain('data-neutrophil="true"');
  expect(render(1, 1, 1)).toContain('data-neutrophil="true"');
});
vi.mock('remotion', () => ({useCurrentFrame: () => clock.frame, useVideoConfig: () => ({fps: 30})}));
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

it('shows a synovial lining over a dilating capillary and recruits multilobed neutrophils', () => {
  const normal = renderToStaticMarkup(<InflammationSignal state="normal" severity={1}/>);
  const stages = [0, .25, .5, .75, 1].map(severity => renderToStaticMarkup(<InflammationSignal state="diseased" severity={severity}/>));
  for (const layer of ['synovial-membrane', 'subsynovial-tissue', 'capillary', 'inflammasome', 'multilobed-nuclei']) expect(stages[4]).toContain(`data-layer="${layer}"`);
  expect(normal).not.toContain('data-crystal="true"');
  expect(normal).not.toContain('data-neutrophil="true"');
  expect(normal).not.toContain('data-activation="true"');
  const count = (s: string) => (s.match(/data-neutrophil="true"/g) ?? []).length;
  for (let i = 1; i < stages.length; i++) expect(count(stages[i])).toBeGreaterThanOrEqual(count(stages[i - 1]));
  expect(count(stages[4])).toBe(6);
  expect(stages[4].match(/data-nucleus-lobe="true"/g)).toHaveLength(18);
  expect(stages[4]).toContain('data-migration="transendothelial"');
  expect(stages[4]).toContain('data-phagocytosis="true"');
});

it('dilates the vessel with severity and keeps recruitment deterministic across frames', () => {
  for (const frame of [0, 60, 120, 240, 900]) {
    clock.frame = frame;
    const stages = [0, .25, .5, .75, 1].map(severity => renderToStaticMarkup(<InflammationSignal state="diseased" severity={severity}/>));
    const radii = stages.map(s => Number(s.match(/data-lumen-radius="([\d.]+)"/)![1]));
    expect(radii).toEqual([25, 28.25, 31.5, 34.75, 38]);
    const counts = stages.map(s => (s.match(/data-neutrophil="true"/g) ?? []).length);
    expect(counts).toEqual([0, 2, 3, 5, 6]);
    const output = stages[4];
    clock.frame = frame + 31;
    renderToStaticMarkup(<InflammationSignal state="diseased" severity={1}/>);
    clock.frame = frame;
    expect(renderToStaticMarkup(<InflammationSignal state="diseased" severity={1}/>)).toBe(output);
    expect(renderToStaticMarkup(<InflammationSignal state="normal" severity={1}/>)).not.toMatch(/data-(crystal|neutrophil|activation|signal)="true"/);
  }
  expect(signalGeometry('diseased', -1, 240, 30).recruited).toBe(0);
  expect(signalGeometry('diseased', 2, 240, 30).recruited).toBe(6);
});
