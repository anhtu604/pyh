import React from 'react';
// @ts-expect-error @types/react-dom is not installed
import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it, vi} from 'vitest';
import {MechanismScene, type MechanismKind} from './MechanismScene';
import {ArterySection, arteryGeometry} from '../anatomy/ArterySection';
import {Heart} from '../anatomy/Heart';
import type {Scene} from '../types';

const clock = vi.hoisted(() => ({frame: 0}));
vi.mock('remotion', async (original) => ({
  ...await original<typeof import('remotion')>(),
  AbsoluteFill: 'div', useCurrentFrame: () => clock.frame,
  useVideoConfig: () => ({fps: 30}),
}));
const scene: Scene = {
  id: 'S-MOTION-01', start_frame: 0, duration_frames: 90, narration: '', visual: 'anatomy_animation',
  anatomy: {subject: 'artery_cross_section', state: 'diseased', severity: 0.8, motion: ''},
};
const render = (kind: MechanismKind, frame: number, s = scene) => {
  clock.frame = frame;
  return renderToStaticMarkup(<MechanismScene scene={s} kind={kind} />);
};
const attribute = (markup: string, name: string) => markup.match(new RegExp(`${name}="([^"]+)"`))?.[1];
const camera = (markup: string) => markup.match(/data-mechanism-camera="true" style="([^"]+)"/)?.[1];
const numbers = (markup: string, name: string) => [...markup.matchAll(new RegExp(`${name}="([^"]+)"`, 'g'))].map(m => Number(m[1]));

describe('visible mechanism motion', () => {
  for (const kind of ['anatomy', 'process', 'comparison', 'timelapse'] as const) {
    for (const subject of ['artery_cross_section', 'heart'] as const) {
      it(`${kind}/${subject} moves the camera and organ geometry through first/mid/last frames`, () => {
        const outputs = [0, 45, 89].map(frame => render(kind, frame, {...scene, anatomy: {...scene.anatomy!, subject}}));
        const cameras = outputs.map(camera);
        expect(cameras.every(Boolean)).toBe(true);
        expect(new Set(cameras).size).toBe(3);
        expect(cameras[0]).toContain('scale(1)');
        expect(cameras[2]).toContain('scale(1.12)');
        const geometry = outputs.map(output => subject === 'heart'
          ? attribute(output, 'data-beat-scale') : attribute(output, 'data-lumen-radius'));
        expect(new Set(geometry).size).toBeGreaterThan(1);
        expect(render(kind, 45, {...scene, anatomy: {...scene.anatomy!, subject}})).toBe(outputs[1]);
      });
    }
  }
  it('varies deterministic camera drift with scene id', () => {
    expect(camera(render('process', 45))).not.toBe(camera(render('process', 45, {...scene, id: 'S-MOTION-02'})));
  });
  it('progresses diseased anatomy from 40% and comparison/timelapse from zero to target', () => {
    for (const kind of ['anatomy', 'comparison', 'timelapse'] as const) {
      const expectedStart = kind === 'anatomy' ? 0.32 : 0;
      const diseased = [0, 45, 89].map(frame => numbers(render(kind, frame), 'data-severity').at(-1)!);
      expect(diseased[0]).toBeCloseTo(expectedStart);
      expect(diseased[1]).toBeGreaterThan(diseased[0]);
      expect(diseased[1]).toBeLessThan(diseased[2]);
      expect(diseased[2]).toBeCloseTo(0.8);
    }
    for (const frame of [0, 45, 89]) {
      expect(numbers(render('comparison', frame), 'data-severity')[0]).toBe(0);
      const normal = render('anatomy', frame, {...scene, anatomy: {...scene.anatomy!, state: 'normal'}});
      expect(numbers(normal, 'data-severity')).toEqual([0]);
    }
  });
  it('keeps the stiff artery wall beat visible at a few percent radius', () => {
    const radii = Array.from({length: 30}, (_, frame) => arteryGeometry('diseased', 1, frame, 30).outerRadius);
    expect(Math.max(...radii) - Math.min(...radii)).toBeGreaterThan(216 * 0.04);
    expect(Math.max(...radii) - Math.min(...radii)).toBeLessThan(216 * 0.09);
  });
  for (const Organ of [ArterySection, Heart]) {
    it(`${Organ.name} beats and moves a process arrow and flow faster than ordinary flow`, () => {
      const organ = (frame: number, emphasizeFlow: boolean) => {
        clock.frame = frame;
        return renderToStaticMarkup(<Organ state="diseased" severity={0.8} emphasizeFlow={emphasizeFlow} />);
      };
      const outputs = [0, 5, 89].map(frame => organ(frame, true));
      const arrows = outputs.map(output => output.match(/data-flow-arrow="true" transform="([^"]+)"/)?.[1]);
      expect(arrows.every(Boolean)).toBe(true);
      expect(new Set(arrows).size).toBe(3);
      expect(new Set(outputs.map(output => attribute(output, Organ === Heart ? 'data-beat-scale' : 'data-lumen-radius'))).size).toBe(3);
      if (Organ === ArterySection) {
        const firstCellX = (frame: number, emphasized: boolean) => Number(organ(frame, emphasized).match(/<g transform="translate\(([\d.]+) /)?.[1]);
        expect(firstCellX(1, true) - firstCellX(0, true)).toBeGreaterThan((firstCellX(1, false) - firstCellX(0, false)) * 1.8);
      } else {
        const firstCellY = (frame: number) => Number(organ(frame, true).match(/<circle cx="215" cy="([\d.]+)"/)?.[1]);
        expect(firstCellY(1) - firstCellY(0)).toBeGreaterThan(4);
      }
    });
  }
});
