import {expect, it} from 'vitest';
import type {Scene} from '../types';
import {textEntrances} from './entrances';

const scene: Scene = {id: 'S01', visual: 'whiteboard', narration: 'Urat tạo tinh thể', start_frame: 300,
  duration_frames: 300, on_screen_text: 'Urat; tinh thể'};
it('spreads fallback text pieces through 70% of a scene', () => {
  expect(textEntrances(scene).map(piece => piece.start_frame)).toEqual([0, 210]);
  expect(textEntrances({...scene, on_screen_text: 'Một ý'})).toEqual([{text: 'Một ý', start_frame: 105}]);
});
it('uses local aligned first-word timestamps with case and punctuation normalization', () => {
  expect(textEntrances({...scene, words: [{text: 'urat,', start_frame: 30, end_frame: 40},
    {text: 'tinh', start_frame: 160, end_frame: 170}]}).map(piece => piece.start_frame)).toEqual([30, 160]);
});
it('preserves Vietnamese tones when selecting the spoken keyword', () => {
  const words = [{text: 'mỡ', start_frame: 20, end_frame: 30}, {text: 'mô', start_frame: 160, end_frame: 170}];
  expect(textEntrances({...scene, on_screen_text: 'Mô gan', words})[0].start_frame).toBe(160);
  expect(textEntrances({...scene, on_screen_text: 'MỠ gan', words})[0].start_frame).toBe(20);
});
it('honors resolved entrances from production', () => {
  const entrances = [{text: 'Urat;', start_frame: 28}, {text: ' tinh thể', start_frame: 180}];
  expect(textEntrances({...scene, entrances})).toEqual(entrances);
});
