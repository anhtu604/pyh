import {expect, it} from 'vitest';
import type {Scene} from '../types';
import {activeSceneBeat, beatCamera} from './mechanismBeats';
const scene: Scene = {id: 'S1', visual: 'process_animation', narration: 'Tinh thể', start_frame: 0,
  duration_frames: 600, beats: [{at: 2, start_frame: 60, focus: 'crystal', labels: ['crystal']},
    {at: 8, start_frame: 240, focus: null, labels: []}]};
const view = {left: 0, top: 0, width: 560, height: 560};
const regions = {crystal: {left: 150, top: 160, width: 160, height: 160}};
const camera = (frame: number) => beatCamera(scene, frame, regions, view, [view], view);
it('settles camera focus in .8 seconds, deterministically under seeking', () => {
  expect(camera(60).zoom).toBe(1);
  expect(camera(72).zoom).toBeGreaterThan(1);
  expect(camera(84).zoom).toBe(1.65);
  expect(camera(300).zoom).toBe(1);
  expect(camera(72)).toEqual(camera(72));
});
it('shows and clears beat labels at local frame anchors', () => {
  expect(activeSceneBeat(scene, 59)).toBeUndefined();
  expect(activeSceneBeat(scene, 60)?.labels).toEqual(['crystal']);
  expect(activeSceneBeat(scene, 240)?.labels).toEqual([]);
});
it('does not jump if a new beat interrupts a focus transition', () => {
  const interrupted = {...scene, beats: [scene.beats![0], {...scene.beats![1], start_frame: 72}]};
  const {zoom, x, y} = camera(72);
  expect(beatCamera(interrupted, 72, regions, view, [view], view)).toMatchObject({zoom, x, y});
});
